#!/usr/bin/env python3
"""Freeze, run, and report the Phase 2 planner benchmark."""

from __future__ import annotations

import argparse
from collections import Counter
import copy
from dataclasses import asdict
from datetime import datetime, timezone
from hashlib import sha256
from importlib.metadata import version
import json
import math
import os
from pathlib import Path
import platform
import random
import statistics
import sys
import time
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from rdflib import Graph
from rdflib.compare import to_canonical_graph

from shapelens import (
    ApplicationOverlay,
    AuthorizationScope,
    Catalog,
    DatasetScope,
    QualificationRecord,
    QueryPolicy,
    SemanticQualification,
    ShapeQueryEngine,
    ShapeSource,
    Term,
    plan_digest,
)
from phase2.planning import (
    EntityLabel,
    OpenAIPlanner,
    PlanningError,
    ShapeRAG,
    cards_from_catalog,
    resolve_entity,
    retrieve_cards,
)


WORKSPACE = ROOT / "phase2"
MANIFEST = WORKSPACE / "manifest.json"
INPUT_FILES = ("cards.json", "cases.json", "entities.json", "prompt.txt")
HARNESS_FILES = ("benchmark.py", "planning.py")
SHAPE_PATHS = (
    "phase0/corpus/shapes/staffing-skills.ttl",
    "phase0/corpus/shapes/service-operations.ttl",
    "phase0/corpus/shapes/research-publication-catalog.ttl",
    "phase0/fixtures/artifacts/semantic-shapes.ttl",
)
SCALAR_OVERRIDES = (
    ("https://catalog.example.org/ns/PublicationShape", "https://catalog.example.org/ns/title"),
    ("https://catalog.example.org/ns/PublicationShape", "https://catalog.example.org/ns/publicationYear"),
    ("https://catalog.example.org/ns/ResearcherShape", "https://catalog.example.org/ns/displayName"),
)


def load_json(path: Path | str) -> Any:
    path = Path(path)
    return json.loads((path if path.is_absolute() else ROOT / path).read_text())


def file_digest(path: Path) -> str:
    return "sha256:" + sha256(path.read_bytes()).hexdigest()


def write_new_json(path: Path, value: Any) -> None:
    if path.exists():
        raise SystemExit(f"refusing to overwrite existing artifact: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n")


def nonempty_strings(value: Any) -> bool:
    return (
        isinstance(value, list)
        and bool(value)
        and all(isinstance(item, str) and item.strip() for item in value)
    )


def build_catalog(build_id: str) -> Catalog:
    sources = []
    for relative in SHAPE_PATHS:
        parsed = Graph().parse(ROOT / relative)
        graph = Graph()
        for triple in to_canonical_graph(parsed):
            graph.add(triple)
        qualification = SemanticQualification.reviewed_graph(
            graph,
            owner="phase-2 benchmark",
            fixture_revision="sha256:c35149a9543e911b05599272819fe4759906df4c8ee37a00eff9da3f2153b458",
            fixture_ids=("accepted-phase0-fixtures",),
        )
        sources.append(ShapeSource(graph, relative, "ShapeLens project", "trusted", qualification))
    signatures = {
        (record.shape_term, json.loads(record.value)["predicate"]): record.value
        for source in sources
        for record in source.qualification.records
        if record.behavior == "property"
    }
    overlay_qualification = SemanticQualification(
        "research information office",
        "sha256:c35149a9543e911b05599272819fe4759906df4c8ee37a00eff9da3f2153b458",
        tuple(
            QualificationRecord(
                shape,
                "scalar_projection",
                signatures[(shape, predicate)],
                ("research-overlay",),
            )
            for shape, predicate in SCALAR_OVERRIDES
        ),
    )
    overlay = ApplicationOverlay(
        "phase0-research-projections",
        "executable",
        "research information office",
        True,
        SCALAR_OVERRIDES,
        overlay_qualification,
    )
    return Catalog.build(tuple(sources), overlays=(overlay,), build_id=build_id)


def remap_plan(raw: Mapping[str, Any], old: Mapping[str, Any], new: Catalog) -> dict[str, Any]:
    raw = copy.deepcopy(raw)
    old_lenses = {item["key"]: item for item in old["lenses"]}
    new_lenses = {item.shape_term: item for item in new.lenses}
    lens_map = {key: new_lenses[item["shape_term"]].key for key, item in old_lenses.items()}
    new_properties = {
        (next(x.shape_term for x in new.lenses if x.key == item.lens_key), item.predicate_iri, item.inverse): item
        for item in new.properties
    }
    property_map, branch_map = {}, {}
    for item in old["properties"]:
        shape = old_lenses[item["lens_key"]]["shape_term"]
        candidate = new_properties[(shape, item["predicate_iri"], item["inverse"])]
        property_map[item["key"]] = candidate.key
        for index, key in enumerate(item["branch_keys"]):
            branch_map[key] = candidate.branch_keys[index]
    new_selectors = {
        (next(x.shape_term for x in new.lenses if x.key == item.lens_key), item.kind, item.classes, item.target_iris): item
        for item in new.selectors
    }
    selector_map = {}
    for item in old["selectors"]:
        shape = old_lenses[item["lens_key"]]["shape_term"]
        classes = (item["class_iri"],) if item["class_iri"] else ()
        selector_map[item["key"]] = new_selectors[(shape, item["kind"], classes, tuple(item["target_iris"]))].key
    raw["catalog_revision"] = new.revision
    for item in raw["lenses"]:
        item["key"] = lens_map[item["key"]]
    for item in raw["selectors"]:
        item["key"] = selector_map[item["key"]]
    for group in ("edges", "filters", "projections"):
        for item in raw[group]:
            if "property_key" in item:
                item["property_key"] = property_map[item["property_key"]]
            if "branch_key" in item:
                item["branch_key"] = branch_map[item["branch_key"]]
    properties = {item.key: item for item in new.properties}
    bindings = {item["id"]: item.get("binding") for item in raw["entities"]}
    for item in raw["filters"]:
        if item.get("kind") == "eq":
            prop = properties[item["property_key"]]
            item["branch_key"] = next(
                (branch.key for branch in prop.branches if branch.accepts(Term.load(item["value"]))),
                prop.branches[0].key,
            )
    for item in raw["edges"]:
        prop, binding = properties[item["property_key"]], bindings[item["target_entity"]]
        item["branch_key"] = (
            next(branch.key for branch in prop.branches if branch.accepts(Term.load(binding)))
            if binding is not None
            else next(branch.key for branch in prop.branches if branch.accepts_iri)
        )
    return raw


def load_cards(catalog: Catalog) -> tuple[Any, ...]:
    annotations = {}
    lenses = {item.shape_term: item for item in catalog.lenses}
    for record in load_json(WORKSPACE / "cards.json"):
        kind, shape = record["kind"], record["shape"]
        if kind == "lens":
            item = lenses.get(shape)
        elif kind == "selector":
            item = next((x for x in catalog.selectors if x.lens_key == lenses[shape].key), None)
        else:
            item = next(
                (
                    x
                    for x in catalog.properties
                    if x.lens_key == lenses[shape].key
                    and x.predicate_iri == record["predicate"]
                    and x.inverse is record.get("inverse", False)
                ),
                None,
            )
        if item is None:
            raise ValueError(f"card does not match catalog: {record}")
        annotations[item.key] = record
    return cards_from_catalog(catalog, annotations)


def load_entities() -> tuple[EntityLabel, ...]:
    records = load_json(WORKSPACE / "entities.json")
    if any(not isinstance(item.get("aliases"), list) for item in records):
        raise ValueError("entity aliases must be arrays")
    return tuple(
        EntityLabel(item["iri"], item["label"], tuple(item["aliases"]))
        for item in records
        if item["provider_allowed"]
    )


def gold_entity_resolutions(
    case: Mapping[str, Any], entities: tuple[EntityLabel, ...]
) -> list[dict[str, Any]]:
    results = []
    for item in case["intent_items"]:
        value = item.get("value")
        if not value or item["role"] not in {"relationship", "condition"}:
            continue
        resolution = resolve_entity(value, entities)
        if resolution.status != "unsupported" or case.get("safety_category") == "unknown_entity":
            results.append({"label": value, "status": resolution.status, "iris": list(resolution.iris)})
    return results


def question(case: Mapping[str, Any]) -> str:
    return load_json(case["question_path"])["question"] if case.get("question_path") else case["question"]


def oracle_plan(case: Mapping[str, Any], catalog: Catalog) -> dict[str, Any] | None:
    if not case.get("acceptable_plan_path"):
        return None
    return remap_plan(
        load_json(case["acceptable_plan_path"]),
        load_json("phase0/fixtures/catalog.json"),
        catalog,
    )


def required_card_keys(plan: Mapping[str, Any] | None) -> frozenset[str]:
    if plan is None:
        return frozenset()
    keys = {item["key"] for item in plan["lenses"]} | {item["key"] for item in plan["selectors"]}
    keys.update(
        item["property_key"]
        for group in ("edges", "filters", "projections")
        for item in plan[group]
        if "property_key" in item
    )
    return frozenset(keys)


def intent_signature(item: Mapping[str, Any]) -> tuple[Any, ...]:
    return item["role"], tuple(sorted(item.get("catalog_keys", ()))), item.get("value")


def source_digests(cases: list[Mapping[str, Any]]) -> dict[str, str]:
    paths = {
        "shapelens/__init__.py",
        "phase0/fixtures/catalog.json",
        "phase0/fixtures/manifest.json",
        *SHAPE_PATHS,
    }
    for case in cases:
        paths.update(
            case[name]
            for name in ("question_path", "acceptable_plan_path", "semantic_oracle_path", "dataset_path")
            if case.get(name)
        )
    return {path: file_digest(ROOT / path) for path in sorted(paths)}


def catalog_reference_keys(catalog: Catalog) -> dict[str, str]:
    old = load_json("phase0/fixtures/catalog.json")
    old_lenses = {item["key"]: item for item in old["lenses"]}
    new_lenses = {item.shape_term: item for item in catalog.lenses}
    keys = {
        f"L{index}": new_lenses[item["shape_term"]].key
        for index, item in enumerate(old["lenses"])
    }
    for index, item in enumerate(old["selectors"]):
        shape = old_lenses[item["lens_key"]]["shape_term"]
        classes = (item["class_iri"],) if item["class_iri"] else ()
        keys[f"S{index}"] = next(
            candidate.key
            for candidate in catalog.selectors
            if new_lenses[shape].key == candidate.lens_key
            and candidate.classes == classes
            and candidate.target_iris == tuple(item["target_iris"])
        )
    for index, item in enumerate(old["properties"]):
        shape = old_lenses[item["lens_key"]]["shape_term"]
        keys[f"P{index}"] = next(
            candidate.key
            for candidate in catalog.properties
            if new_lenses[shape].key == candidate.lens_key
            and candidate.predicate_iri == item["predicate_iri"]
            and candidate.inverse is item["inverse"]
        )
    return keys


def gold_intent_signature(
    item: Mapping[str, Any],
    catalog: Catalog,
    references: Mapping[str, str] | None = None,
) -> tuple[Any, ...]:
    references = references or catalog_reference_keys(catalog)
    keys = tuple(references[ref] for ref in item.get("catalog_refs", ()))
    return item["role"], tuple(sorted(keys)), item.get("value")


def validate() -> tuple[list[str], dict[str, Any]]:
    errors = []
    manifest = load_json(MANIFEST)
    cases = load_json(WORKSPACE / "cases.json")
    cards_raw = load_json(WORKSPACE / "cards.json")
    entities_raw = load_json(WORKSPACE / "entities.json")
    required_manifest = {
        "schema_version",
        "status",
        "benchmark_revision",
        "phase0_corpus_revision",
        "phase0_fixture_revision",
        "catalog_build_id",
        "catalog_revision",
        "authorization_scope",
        "query_policy",
        "model",
        "prompt_revision",
        "card_revision",
        "decoding",
        "shuffle_seeds",
        "provider_transmission",
        "provider_material_reviewed_by",
        "metric_owners",
        "thresholds",
        "price_source",
        "latency_machine",
        "direct_query_prompt",
        "source_digests",
        "harness_digests",
        "input_digests",
    }
    if manifest.get("schema_version") != 1 or manifest.get("status") not in {"draft", "frozen"}:
        errors.append("manifest must be schema 1 and draft or frozen")
    if missing := required_manifest - manifest.keys():
        errors.append(f"manifest fields missing: {sorted(missing)}")
    decoding_value = manifest.get("decoding", {})
    decoding = decoding_value if isinstance(decoding_value, Mapping) else {}
    if not isinstance(decoding_value, Mapping):
        errors.append("decoding must be an object")
    if decoding.get("max_calls") != 2 or decoding.get("structured_retries") != 1:
        errors.append("decoding must allow exactly one retry and at most two calls")
    if (
        decoding.get("response_format") != "json_object"
        or decoding.get("temperature") != "provider_default"
        or type(decoding.get("candidate_limit")) is not int
        or decoding.get("candidate_limit", 0) <= 0
    ):
        errors.append("decoding response format, temperature, and candidate limit must be pinned")
    seeds = manifest.get("shuffle_seeds")
    if (
        not isinstance(seeds, list)
        or len(seeds) != 3
        or any(type(seed) is not int for seed in seeds)
        or len(set(seeds)) != 3
    ):
        errors.append("three distinct integer shuffle seeds are required")
    if not isinstance(manifest.get("direct_query_prompt"), str) or not manifest["direct_query_prompt"].strip():
        errors.append("direct-query prompt must be pinned")
    model_value = manifest.get("model", {})
    model = model_value if isinstance(model_value, Mapping) else {}
    prices = model.get("price_per_million_tokens", {})
    if (
        model.get("provider") != "OpenAI"
        or any(
            not isinstance(model.get(name), str) or not model[name].strip()
            for name in ("identifier", "api_key_env")
        )
        or not isinstance(prices, Mapping)
        or any(
            type(prices.get(name)) not in {int, float}
            or not math.isfinite(prices[name])
            or prices[name] <= 0
            for name in ("input", "output")
        )
    ):
        errors.append("OpenAI model identity, credential environment, and prices must be pinned")
    transmission_value = manifest.get("provider_transmission", {})
    transmission = transmission_value if isinstance(transmission_value, Mapping) else {}
    if (
        not nonempty_strings(transmission.get("allowed"))
        or not nonempty_strings(transmission.get("local_only"))
        or set(transmission.get("allowed", ())) & set(transmission.get("local_only", ()))
    ):
        errors.append("provider transmission must contain disjoint allowed and local-only inventories")
    if not nonempty_strings(manifest.get("provider_material_reviewed_by")):
        errors.append("provider material requires a reviewer list")
    owners = manifest.get("metric_owners", {})
    if (
        not isinstance(owners, Mapping)
        or set(owners) != {"planner_fidelity", "semantic_review", "latency_and_cost"}
        or any(not isinstance(owner, str) or not owner.strip() for owner in owners.values())
    ):
        errors.append("all metric owner roles must be named")
    price_source = manifest.get("price_source", {})
    if (
        not isinstance(price_source, Mapping)
        or not isinstance(price_source.get("url"), str)
        or not price_source["url"].startswith("https://developers.openai.com/")
        or not isinstance(price_source.get("checked_at"), str)
        or not price_source["checked_at"].strip()
    ):
        errors.append("price source must name a checked official OpenAI page")
    machine_value = manifest.get("latency_machine", {})
    machine = machine_value if isinstance(machine_value, Mapping) else {}
    if set(machine) != {"system", "release", "machine", "network", "python", "rdflib"} or any(
        not isinstance(value, str) or not value.strip() for value in machine.values()
    ):
        errors.append("latency machine record must be complete")
    thresholds_value = manifest.get("thresholds", {})
    thresholds = thresholds_value if isinstance(thresholds_value, Mapping) else {}
    if not isinstance(thresholds_value, Mapping):
        errors.append("thresholds must be an object")
    exact_thresholds = {
        "intent_extraction_recall",
        "intent_restriction_precision",
        "internal_coverage",
        "lens_retrieval_recall",
        "entity_accuracy",
        "plan_validity",
        "critical_faithful_coverage",
        "completed_plan_semantic_precision",
        "unsupported_precision",
        "unsupported_recall",
    }
    if any(
        type(thresholds.get(name)) not in {int, float} or thresholds.get(name) != 1
        for name in exact_thresholds
    ):
        errors.append("exact fidelity thresholds must remain 100%")
    faithful_threshold = thresholds.get("faithful_automation_coverage")
    if type(faithful_threshold) not in {int, float} or not 0.8 <= faithful_threshold <= 1:
        errors.append("faithful automation threshold cannot be relaxed below 80%")
    if type(thresholds.get("false_completion_count")) is not int or thresholds.get("false_completion_count") != 0:
        errors.append("false completion threshold must remain zero")
    call_threshold = thresholds.get("max_model_calls")
    if type(call_threshold) is not int or not 0 < call_threshold <= 2:
        errors.append("model-call threshold must be between one and two")
    latency_threshold = thresholds.get("p95_latency_seconds")
    if (
        type(latency_threshold) not in {int, float}
        or not math.isfinite(latency_threshold)
        or not 0 < latency_threshold <= 10
    ):
        errors.append("p95 latency threshold cannot be relaxed above ten seconds")
    cost_threshold = thresholds.get("mean_cost_usd")
    if (
        type(cost_threshold) not in {int, float}
        or not math.isfinite(cost_threshold)
        or not 0 < cost_threshold <= 0.05
    ):
        errors.append("mean cost threshold cannot be relaxed above USD 0.05")
    phase0_manifest = load_json("phase0/fixtures/manifest.json")
    if manifest.get("phase0_corpus_revision") != phase0_manifest["corpus_revision"]:
        errors.append("Phase 0 corpus revision does not match")
    if manifest.get("phase0_fixture_revision") != phase0_manifest["fixture_revision"]:
        errors.append("Phase 0 fixture revision does not match")
    if manifest.get("status") == "frozen":
        if not all(manifest.get(name) for name in ("benchmark_revision", "prompt_revision", "card_revision")):
            errors.append("frozen manifest needs immutable benchmark, prompt, and card revisions")
        if "pending-freeze" in machine.values():
            errors.append("frozen manifest needs the actual latency machine and network")
        if "pending-human-review" in manifest.get("provider_material_reviewed_by", ()):
            errors.append("frozen provider cards and aliases require named human review")
    ids = [case.get("case_id") for case in cases]
    if len(cases) != 28 or len(ids) != len(set(ids)):
        errors.append("cases must contain 28 unique records")
    representative = [case for case in cases if case.get("representative")]
    if len(representative) != 20:
        errors.append("exactly 20 representative cases required")
    expected_questions = {path.stem for path in (ROOT / "phase0/corpus/questions").glob("*.json")}
    if {case.get("case_id") for case in representative} != expected_questions:
        errors.append("representative case IDs must exactly match the frozen Phase 0 corpus")
    safety = Counter(case.get("safety_category") for case in cases if not case.get("representative"))
    if safety != Counter({"ambiguous_entity": 2, "unknown_entity": 2, "mixed_unsupported": 2, "partial_plan": 2}):
        errors.append("safety set must have exactly two cases in each required category")
    for case in cases:
        if case.get("expected_disposition") not in {"completed", "unsupported", "ambiguous"}:
            errors.append(f"{case.get('case_id')}: invalid expected disposition")
        if not case.get("intent_items") or not nonempty_strings(case.get("reviewed_by")):
            errors.append(f"{case.get('case_id')}: intent items and reviewers required")
        if manifest.get("status") == "frozen" and "pending-human-review" in case.get("reviewed_by", ()):
            errors.append(f"{case.get('case_id')}: frozen labels require named human review")
        if any(
            item.get("role") not in {"population", "relationship", "condition", "projection", "boolean", "result_extent"}
            or not isinstance(item.get("catalog_refs", []), list)
            for item in case.get("intent_items", ())
        ):
            errors.append(f"{case.get('case_id')}: invalid intent item")
        if case.get("expected_disposition") == "completed" and not case.get("acceptable_plan_path"):
            errors.append(f"{case.get('case_id')}: completed case needs an acceptable plan")
        for path_name in ("question_path", "acceptable_plan_path", "semantic_oracle_path", "dataset_path"):
            if case.get(path_name) and not (ROOT / case[path_name]).is_file():
                errors.append(f"{case.get('case_id')}: missing {path_name}")
    for name, records in (("card", cards_raw), ("entity", entities_raw)):
        for index, record in enumerate(records):
            if type(record.get("provider_allowed")) is not bool:
                errors.append(f"{name} {index}: provider_allowed must be explicit")
    try:
        catalog = build_catalog(manifest["catalog_build_id"])
        cards = load_cards(catalog)
        if manifest.get("catalog_revision") != catalog.revision:
            errors.append(f"catalog revision must be {catalog.revision}")
        for case in cases:
            plan = oracle_plan(case, catalog)
            if plan:
                data = Graph().parse(ROOT / case["dataset_path"])
                engine = ShapeQueryEngine(
                    data=data,
                    catalog=catalog,
                    authorization=AuthorizationScope.allow_all(manifest["authorization_scope"]),
                    dataset_scope=DatasetScope(case["case_id"]),
                    policy=QueryPolicy(**manifest["query_policy"]),
                )
                engine.validate_plan(plan)
                candidates = retrieve_cards(question(case), cards, manifest["decoding"]["candidate_limit"])
                missing = required_card_keys(plan) - {card.key for card in candidates}
                if missing:
                    errors.append(f"{case['case_id']}: candidate retrieval misses {sorted(missing)}")
    except Exception as exc:
        errors.append(f"catalog or plan validation failed: {exc}")
    actual_digests = {name: file_digest(WORKSPACE / name) for name in INPUT_FILES}
    if manifest.get("status") == "frozen":
        if manifest.get("input_digests") != actual_digests:
            errors.append("frozen input digests do not match")
        if manifest.get("source_digests") != source_digests(cases):
            errors.append("frozen Phase 0 and runtime source digests do not match")
        actual_harness = {
            name: file_digest(WORKSPACE / name) for name in HARNESS_FILES
        }
        if manifest.get("harness_digests") != actual_harness:
            errors.append("frozen benchmark harness digests do not match")
        if manifest.get("prompt_revision") != actual_digests["prompt.txt"]:
            errors.append("frozen prompt revision does not match")
        if manifest.get("card_revision") != actual_digests["cards.json"]:
            errors.append("frozen card revision does not match")
        expected_revision = "sha256:" + sha256(
            json.dumps(
                {**manifest, "benchmark_revision": None},
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
        if manifest.get("benchmark_revision") != expected_revision:
            errors.append("frozen benchmark revision does not match")
    evidence = {
        "cases": len(cases),
        "representative": len(representative),
        "safety_categories": dict(safety),
        "catalog_revision": catalog.revision if "catalog" in locals() else None,
        "input_digests": actual_digests,
    }
    return errors, evidence


def freeze(reviewer: str, network: str) -> None:
    errors, _ = validate()
    if errors:
        raise SystemExit("draft inputs failed validation:\n" + "\n".join(errors))
    manifest, cases = load_json(MANIFEST), load_json(WORKSPACE / "cases.json")
    if manifest["status"] != "draft":
        raise SystemExit("only a draft benchmark can be frozen")
    reviewer, network = reviewer.strip(), network.strip()
    if not reviewer or not network:
        raise SystemExit("reviewer and network description are required")
    for case in cases:
        case["reviewed_by"] = [reviewer if name == "pending-human-review" else name for name in case["reviewed_by"]]
    (WORKSPACE / "cases.json").write_text(json.dumps(cases, indent=2) + "\n")
    manifest.update(
        {
            "status": "frozen",
            "frozen_at": datetime.now(timezone.utc).isoformat(),
            "frozen_by": reviewer,
            "prompt_revision": file_digest(WORKSPACE / "prompt.txt"),
            "card_revision": file_digest(WORKSPACE / "cards.json"),
            "latency_machine": {
                "system": platform.system(),
                "release": platform.release(),
                "machine": platform.machine(),
                "network": network,
                "python": platform.python_version(),
                "rdflib": version("rdflib"),
            },
            "input_digests": {name: file_digest(WORKSPACE / name) for name in INPUT_FILES},
            "source_digests": source_digests(cases),
            "harness_digests": {
                name: file_digest(WORKSPACE / name) for name in HARNESS_FILES
            },
            "provider_material_reviewed_by": [
                reviewer if name == "pending-human-review" else name
                for name in manifest["provider_material_reviewed_by"]
            ],
        }
    )
    revision_payload = {**manifest, "benchmark_revision": None}
    manifest["benchmark_revision"] = "sha256:" + sha256(
        json.dumps(revision_payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n")
    errors, _ = validate()
    if errors:
        raise SystemExit("frozen inputs failed validation:\n" + "\n".join(errors))


def outcome_fingerprint(outcome: Any) -> Any:
    if hasattr(outcome, "rows"):
        return [
            [asdict(value) if value is not None else None for value in row.values]
            for row in outcome.rows
        ]
    if hasattr(outcome, "value"):
        return outcome.value
    return type(outcome).__name__


def serialize_result(
    result: Any,
    required: frozenset[str],
    gold_digest: str | None,
    gold_outcome: Any,
    latency_seconds: float | None = None,
) -> dict[str, Any]:
    execution_correct = bool(result.outcome and outcome_fingerprint(result.outcome) == outcome_fingerprint(gold_outcome))
    return {
        "status": result.status,
        "reason": result.reason,
        "model": result.model,
        "calls": result.calls,
        "input_tokens": result.input_tokens,
        "output_tokens": result.output_tokens,
        "latency_seconds": result.latency_seconds if latency_seconds is None else latency_seconds,
        "model_latency_seconds": result.latency_seconds,
        "candidate_card_keys": list(result.candidate_card_keys),
        "required_card_keys": sorted(required),
        "intent_items": [asdict(item) for item in result.intent_items],
        "coverage": [asdict(item) for item in result.coverage],
        "entity_resolutions": [asdict(item) for item in result.entity_resolutions],
        "internal_coverage_valid": result.internal_coverage_valid,
        "plan_digest": plan_digest(result.plan) if result.plan else None,
        "gold_plan_digest": gold_digest,
        "execution_correct": execution_correct,
        "semantic_correct": bool(
            result.plan and gold_digest and plan_digest(result.plan) == gold_digest and execution_correct
        ),
        "outcome": type(result.outcome).__name__ if result.outcome else None,
        "raw_replies": list(result.raw_replies),
    }


def run(output: Path) -> None:
    errors, _ = validate()
    manifest = load_json(MANIFEST)
    if errors or manifest["status"] != "frozen":
        raise SystemExit("benchmark must be valid and frozen before model runs:\n" + "\n".join(errors))
    api_key = os.environ.get(manifest["model"]["api_key_env"])
    if not api_key:
        raise SystemExit(f"missing {manifest['model']['api_key_env']}")
    catalog = build_catalog(manifest["catalog_build_id"])
    cards, entities = load_cards(catalog), load_entities()
    prompt = (WORKSPACE / "prompt.txt").read_text()
    reasoning_effort = manifest["decoding"]["reasoning_effort"]
    candidate_planner = OpenAIPlanner(
        api_key, manifest["model"]["identifier"], prompt,
        reasoning_effort=reasoning_effort,
    )
    direct_planner = OpenAIPlanner(
        api_key, manifest["model"]["identifier"], manifest["direct_query_prompt"],
        reasoning_effort=reasoning_effort,
    )
    cases = load_json(WORKSPACE / "cases.json")
    records = []
    for run_number in range(1, 4):
        order = list(cases)
        random.Random(manifest["shuffle_seeds"][run_number - 1]).shuffle(order)
        for case in order:
            data = Graph().parse(ROOT / case["dataset_path"])
            engine = ShapeQueryEngine(
                data=data,
                catalog=catalog,
                authorization=AuthorizationScope.allow_all(manifest["authorization_scope"]),
                dataset_scope=DatasetScope(f"{case['case_id']}:run-{run_number}"),
                policy=QueryPolicy(**manifest["query_policy"]),
            )
            gold = oracle_plan(case, catalog)
            required = required_card_keys(gold)
            gold_digest = plan_digest(engine.validate_plan(gold)) if gold else None
            gold_outcome = engine.execute_plan(gold) if gold else None
            rag = ShapeRAG(engine, candidate_planner, cards, entities, candidate_limit=manifest["decoding"]["candidate_limit"])
            started = time.monotonic()
            candidate = rag.ask(question(case))
            candidate_record = serialize_result(
                candidate,
                required,
                gold_digest,
                gold_outcome,
                time.monotonic() - started,
            )
            flat_rag = ShapeRAG(engine, candidate_planner, cards, entities, candidate_limit=len(cards))
            started = time.monotonic()
            flat = flat_rag.ask(question(case))
            flat_latency = time.monotonic() - started
            started = time.monotonic()
            try:
                direct = direct_planner(
                    question(case),
                    tuple(card.provider_payload() for card in cards),
                    None,
                )
                direct_record = {
                    "value": direct.value,
                    "model": direct.model,
                    "calls": 1,
                    "input_tokens": direct.input_tokens,
                    "output_tokens": direct.output_tokens,
                    "latency_seconds": time.monotonic() - started,
                    "model_latency_seconds": direct.latency_seconds,
                    "semantic_correct": None,
                }
            except PlanningError as exc:
                direct_record = {
                    "value": {"request_error": type(exc).__name__},
                    "model": manifest["model"]["identifier"],
                    "calls": 1,
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "latency_seconds": time.monotonic() - started,
                    "model_latency_seconds": None,
                    "error": str(exc),
                    "semantic_correct": None,
                }
            records.append(
                {
                    "case_id": case["case_id"],
                    "scenario": case["scenario"],
                    "representative": case["representative"],
                    "critical": case["critical"],
                    "expected_disposition": case["expected_disposition"],
                    "run": run_number,
                    "candidate": candidate_record,
                    "always_defer": {"status": "unsupported", "calls": 0},
                    "flat_catalog": serialize_result(
                        flat,
                        required,
                        gold_digest,
                        gold_outcome,
                        flat_latency,
                    ),
                    "direct_query": direct_record,
                }
            )
    write_new_json(
        output,
        {"manifest_revision": manifest["benchmark_revision"], "attempts": records},
    )


def ratio(numerator: int, denominator: int) -> dict[str, Any]:
    return {"numerator": numerator, "denominator": denominator, "value": numerator / denominator if denominator else None}


def percentile(values: list[float], percentile_value: float) -> float:
    if not values:
        return math.nan
    ordered = sorted(values)
    return ordered[math.ceil(percentile_value * len(ordered)) - 1]


def entity_signature(item: Mapping[str, Any]) -> tuple[Any, ...]:
    label = " ".join(
        "".join(
            character if character.isalnum() else " "
            for character in item["label"].casefold()
        ).split()
    )
    return item["status"], label, tuple(item["iris"])


def metrics_for(
    attempts: list[Mapping[str, Any]],
    cases: Mapping[str, Mapping[str, Any]],
    catalog: Catalog,
    manifest: Mapping[str, Any],
) -> dict[str, Any]:
    references = catalog_reference_keys(catalog)
    completed = [row for row in attempts if row["candidate"]["status"] == "completed"]
    supported = [row for row in attempts if row["expected_disposition"] == "completed"]
    predicted_unsupported = [row for row in attempts if row["candidate"]["status"] == "unsupported"]
    gold_unsupported = [row for row in attempts if row["expected_disposition"] == "unsupported"]
    false_completions = [
        row
        for row in completed
        if row["expected_disposition"] != "completed" or not row["candidate"]["semantic_correct"]
    ]
    gold_intents = sum(len(cases[row["case_id"]]["intent_items"]) for row in completed)
    matched_intents = sum(
        len(
            Counter(intent_signature(item) for item in row["candidate"]["intent_items"])
            & Counter(
                gold_intent_signature(item, catalog, references)
                for item in cases[row["case_id"]]["intent_items"]
            )
        )
        for row in completed
    )
    restrictions = sum(len(row["candidate"]["intent_items"]) for row in completed)
    correct_unsupported = sum(row["expected_disposition"] == "unsupported" for row in predicted_unsupported)
    recovered_unsupported = sum(row["candidate"]["status"] == "unsupported" for row in gold_unsupported)
    card_required = sum(len(row["candidate"]["required_card_keys"]) for row in completed)
    card_found = sum(
        len(set(row["candidate"]["required_card_keys"]) & set(row["candidate"]["candidate_card_keys"]))
        for row in completed
    )
    semantically_correct = sum(row["candidate"]["semantic_correct"] for row in completed)
    faithful = sum(row["candidate"]["semantic_correct"] for row in supported)
    critical = [row for row in supported if row["critical"]]
    faithful_critical = sum(row["candidate"]["semantic_correct"] for row in critical)
    entities = load_entities()
    entity_correct = entity_total = 0
    for row in attempts:
        gold_entities = gold_entity_resolutions(cases[row["case_id"]], entities)
        predicted_entities = row["candidate"]["entity_resolutions"]
        entity_total += len(gold_entities)
        entity_correct += sum(
            (
                Counter(entity_signature(item) for item in gold_entities)
                & Counter(entity_signature(item) for item in predicted_entities)
            ).values()
        )
    latencies = [row["candidate"]["latency_seconds"] for row in attempts]
    prices = manifest["model"]["price_per_million_tokens"]
    costs = [
        (row["candidate"]["input_tokens"] * prices["input"] + row["candidate"]["output_tokens"] * prices["output"]) / 1_000_000
        for row in attempts
    ]
    flat_tokens = sum(row["flat_catalog"]["input_tokens"] for row in attempts)
    candidate_tokens = sum(row["candidate"]["input_tokens"] for row in attempts)
    direct_reviewed = [row for row in attempts if type(row["direct_query"].get("semantic_correct")) is bool]
    return {
        "intent_extraction_recall": ratio(matched_intents, gold_intents),
        "intent_restriction_precision": ratio(matched_intents, restrictions),
        "internal_coverage": ratio(
            sum(row["candidate"]["internal_coverage_valid"] for row in attempts),
            len(attempts),
        ),
        "lens_retrieval_recall": ratio(card_found, card_required),
        "entity_accuracy": ratio(entity_correct, entity_total),
        "plan_validity": ratio(len(completed), len(completed)),
        "faithful_automation_coverage": ratio(faithful, len(supported)),
        "critical_faithful_coverage": ratio(faithful_critical, len(critical)),
        "completed_plan_semantic_precision": ratio(semantically_correct, len(completed)),
        "unsupported_precision": ratio(correct_unsupported, len(predicted_unsupported)),
        "unsupported_recall": ratio(recovered_unsupported, len(gold_unsupported)),
        "false_completion_count": len(false_completions),
        "max_model_calls": max(row["candidate"]["calls"] for row in attempts),
        "p50_latency_seconds": statistics.median(latencies),
        "p95_latency_seconds": percentile(latencies, 0.95),
        "mean_cost_usd": statistics.mean(costs),
        "candidate_context_token_reduction": (
            1 - candidate_tokens / flat_tokens if flat_tokens else None
        ),
        "direct_query_semantic_accuracy": ratio(
            sum(row["direct_query"]["semantic_correct"] for row in direct_reviewed),
            len(direct_reviewed),
        ),
    }


def gates_for(metrics: Mapping[str, Any], thresholds: Mapping[str, Any]) -> dict[str, bool]:
    def at_least(name: str) -> bool:
        value = metrics[name]["value"]
        return value is not None and value >= thresholds[name]

    return {
        "intent_extraction_recall": at_least("intent_extraction_recall"),
        "intent_restriction_precision": at_least("intent_restriction_precision"),
        "internal_coverage": at_least("internal_coverage"),
        "lens_retrieval_recall": at_least("lens_retrieval_recall"),
        "entity_accuracy": at_least("entity_accuracy"),
        "plan_validity": at_least("plan_validity"),
        "faithful_automation_coverage": at_least("faithful_automation_coverage"),
        "critical_faithful_coverage": at_least("critical_faithful_coverage"),
        "completed_plan_semantic_precision": at_least("completed_plan_semantic_precision"),
        "unsupported_precision": at_least("unsupported_precision"),
        "unsupported_recall": at_least("unsupported_recall"),
        "false_completion_count": metrics["false_completion_count"] <= thresholds["false_completion_count"],
        "model_calls": metrics["max_model_calls"] <= thresholds["max_model_calls"],
        "latency": metrics["p95_latency_seconds"] <= thresholds["p95_latency_seconds"],
        "cost": metrics["mean_cost_usd"] <= thresholds["mean_cost_usd"],
    }


def failure_categories(
    attempts: list[Mapping[str, Any]], thresholds: Mapping[str, Any]
) -> dict[str, int]:
    failures = Counter()
    for row in attempts:
        candidate = row["candidate"]
        if not candidate["internal_coverage_valid"]:
            failures["internal_coverage_rejected"] += 1
        if candidate["status"] == "completed" and not candidate["semantic_correct"]:
            failures["false_completion"] += 1
        elif row["expected_disposition"] == "completed" and candidate["status"] != "completed":
            failures["false_defer"] += 1
        elif row["expected_disposition"] != "completed" and candidate["status"] != row["expected_disposition"]:
            failures["wrong_disposition"] += 1
        if not set(candidate["required_card_keys"]) <= set(candidate["candidate_card_keys"]):
            failures["candidate_retrieval_miss"] += 1
        if candidate["calls"] > thresholds["max_model_calls"]:
            failures["model_call_limit"] += 1
        if candidate["latency_seconds"] > thresholds["p95_latency_seconds"]:
            failures["attempt_over_latency_threshold"] += 1
        flat = row["flat_catalog"]
        if flat["status"] == "completed" and not flat["semantic_correct"]:
            failures["flat_catalog_false_completion"] += 1
        elif row["expected_disposition"] == "completed" and flat["status"] != "completed":
            failures["flat_catalog_false_defer"] += 1
        direct = row["direct_query"]
        if direct.get("semantic_correct") is False:
            failures[
                "direct_query_" + (direct.get("failure_category") or "semantic_failure")
            ] += 1
        elif direct.get("semantic_correct") is None:
            failures["direct_query_pending_review"] += 1
    return dict(sorted(failures.items()))


def baseline_summary(attempts: list[Mapping[str, Any]]) -> dict[str, Any]:
    supported = [row for row in attempts if row["expected_disposition"] == "completed"]
    gold_unsupported = [row for row in attempts if row["expected_disposition"] == "unsupported"]
    flat_completed = [row for row in attempts if row["flat_catalog"]["status"] == "completed"]
    direct_reviewed = [row for row in attempts if type(row["direct_query"].get("semantic_correct")) is bool]
    return {
        "always_defer": {
            "faithful_automation_coverage": ratio(0, len(supported)),
            "unsupported_precision": ratio(len(gold_unsupported), len(attempts)),
            "unsupported_recall": ratio(len(gold_unsupported), len(gold_unsupported)),
        },
        "flat_catalog": {
            "completed_plan_semantic_precision": ratio(
                sum(row["flat_catalog"]["semantic_correct"] for row in flat_completed),
                len(flat_completed),
            ),
            "mean_input_tokens": statistics.mean(
                row["flat_catalog"]["input_tokens"] for row in attempts
            ),
        },
        "direct_query": {
            "semantic_accuracy": ratio(
                sum(row["direct_query"]["semantic_correct"] for row in direct_reviewed),
                len(direct_reviewed),
            ),
            "reviewed_attempts": len(direct_reviewed),
        },
    }


def direct_review_template(results_path: Path, output: Path) -> None:
    results = load_json(results_path)
    attempts = results["attempts"]
    reviews = [
        {
            "case_id": row["case_id"],
            "run": row["run"],
            "direct_query": row["direct_query"]["value"],
            "semantic_correct": None,
            "failure_category": None,
            "reviewed_by": None,
        }
        for row in attempts
    ]
    write_new_json(
        output,
        {
            "manifest_revision": results.get("manifest_revision"),
            "results_digest": file_digest(results_path),
            "reviews": reviews,
        },
    )


def load_results(results_path: Path, manifest: Mapping[str, Any], cases: Mapping[str, Any]) -> list[dict[str, Any]]:
    results = load_json(results_path)
    attempts = results.get("attempts", ())
    expected = {(case_id, run_number) for case_id in cases for run_number in (1, 2, 3)}
    actual = {(row.get("case_id"), row.get("run")) for row in attempts}
    if (
        results.get("manifest_revision") != manifest["benchmark_revision"]
        or len(attempts) != len(expected)
        or actual != expected
    ):
        raise SystemExit("results must contain exactly three attempts per frozen case and match the benchmark revision")
    return attempts


def report(results_path: Path, output: Path, reviews_path: Path | None = None) -> None:
    errors, _ = validate()
    if errors:
        raise SystemExit("benchmark inputs failed validation:\n" + "\n".join(errors))
    manifest = load_json(MANIFEST)
    cases = {x["case_id"]: x for x in load_json(WORKSPACE / "cases.json")}
    catalog = build_catalog(manifest["catalog_build_id"])
    attempts = load_results(results_path, manifest, cases)
    if reviews_path:
        review_artifact = load_json(reviews_path)
        if (
            not isinstance(review_artifact, Mapping)
            or review_artifact.get("manifest_revision") != manifest["benchmark_revision"]
            or review_artifact.get("results_digest") != file_digest(results_path)
            or not isinstance(review_artifact.get("reviews"), list)
        ):
            raise SystemExit("direct-query reviews must match the exact raw-results artifact")
        reviews = review_artifact["reviews"]
        indexed = {(item["case_id"], item["run"]): item for item in reviews}
        if len(indexed) != len(attempts) or any(
            type(item.get("semantic_correct")) is not bool or not item.get("reviewed_by")
            for item in reviews
        ):
            raise SystemExit("direct-query reviews must cover every attempt with a Boolean decision and reviewer")
        for row in attempts:
            review = indexed[(row["case_id"], row["run"])]
            row["direct_query"].update(
                {
                    "semantic_correct": review["semantic_correct"],
                    "failure_category": review.get("failure_category"),
                    "reviewed_by": review["reviewed_by"],
                }
            )
    overall = metrics_for(attempts, cases, catalog, manifest)
    by_run = {
        str(run_number): metrics_for([row for row in attempts if row["run"] == run_number], cases, catalog, manifest)
        for run_number in (1, 2, 3)
    }
    by_scenario = {
        scenario: metrics_for([row for row in attempts if row["scenario"] == scenario], cases, catalog, manifest)
        for scenario in sorted({row["scenario"] for row in attempts})
    }
    by_question = {
        case_id: metrics_for([row for row in attempts if row["case_id"] == case_id], cases, catalog, manifest)
        for case_id in sorted(cases)
    }
    by_set = {
        "representative": metrics_for([row for row in attempts if row["representative"]], cases, catalog, manifest),
        "safety": metrics_for([row for row in attempts if not row["representative"]], cases, catalog, manifest),
    }
    gates = {
        "overall": gates_for(overall, manifest["thresholds"]),
        **{f"run_{number}": gates_for(by_run[str(number)], manifest["thresholds"]) for number in (1, 2, 3)},
    }
    direct_review_complete = overall["direct_query_semantic_accuracy"]["denominator"] == len(attempts)
    decision = (
        "proceed"
        if manifest["status"] == "frozen"
        and direct_review_complete
        and all(value for group in gates.values() for value in group.values())
        else "revise_and_repeat"
    )
    write_new_json(
        output,
        {
            "benchmark_revision": manifest["benchmark_revision"],
            "configuration": {
                "catalog_revision": manifest["catalog_revision"],
                "model": manifest["model"]["identifier"],
                "prompt_revision": manifest["prompt_revision"],
                "card_revision": manifest["card_revision"],
                "provider_transmission": manifest["provider_transmission"],
                "price_source": manifest["price_source"],
                "latency_machine": manifest["latency_machine"],
                "raw_results_digest": file_digest(results_path),
                "direct_reviews_digest": file_digest(reviews_path) if reviews_path else None,
            },
            "metrics": {
                "overall": overall,
                "by_run": by_run,
                "by_scenario": by_scenario,
                "by_question": by_question,
                "by_set": by_set,
            },
            "baselines": baseline_summary(attempts),
            "failures_by_category": failure_categories(attempts, manifest["thresholds"]),
            "gates": gates,
            "direct_query_review_complete": direct_review_complete,
            "decision": decision,
        },
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("validate")
    freeze_parser = sub.add_parser("freeze")
    freeze_parser.add_argument("--reviewer", required=True)
    freeze_parser.add_argument("--network", required=True)
    run_parser = sub.add_parser("run")
    run_parser.add_argument("--output", type=Path, required=True)
    review_parser = sub.add_parser("direct-review-template")
    review_parser.add_argument("results", type=Path)
    review_parser.add_argument("--output", type=Path, required=True)
    report_parser = sub.add_parser("report")
    report_parser.add_argument("results", type=Path)
    report_parser.add_argument("--output", type=Path, required=True)
    report_parser.add_argument("--direct-reviews", type=Path)
    args = parser.parse_args()
    if args.command == "validate":
        errors, evidence = validate()
        print(json.dumps({"valid": not errors, "errors": errors, **evidence}, indent=2))
        return bool(errors)
    if args.command == "run":
        run(args.output)
    elif args.command == "freeze":
        freeze(args.reviewer, args.network)
    elif args.command == "direct-review-template":
        direct_review_template(args.results, args.output)
    else:
        report(args.results, args.output, args.direct_reviews)
    return 0


if __name__ == "__main__":
    sys.exit(main())
