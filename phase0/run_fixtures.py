#!/usr/bin/env python3
"""Verify the frozen Phase 0 fixtures and print an independently reproducible result."""

from __future__ import annotations

import copy
import hashlib
import json
import statistics
import sys
from collections import Counter
from dataclasses import asdict
from pathlib import Path
from typing import Any

from rdflib import BNode, Dataset, Graph, Literal, URIRef

from author_plans import authored_plans
from kernel import Catalog, PlanError, Term, compile_plan, execute, normalize


ROOT = Path(__file__).resolve().parent.parent
MANIFEST_PATH = ROOT / "phase0/fixtures/manifest.json"
CATALOG_PATH = ROOT / "phase0/fixtures/catalog.json"
CORPUS_PATH = ROOT / "phase0/corpus/manifest.json"
PLACEHOLDER = "replace-with-fixture-revision"
SCALAR_OVERRIDES = (
    ("https://catalog.example.org/ns/PublicationShape", "https://catalog.example.org/ns/title"),
    ("https://catalog.example.org/ns/PublicationShape", "https://catalog.example.org/ns/publicationYear"),
    ("https://catalog.example.org/ns/ResearcherShape", "https://catalog.example.org/ns/displayName"),
)


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def digest(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def referenced_paths(value: Any, key: str = "") -> set[str]:
    paths: set[str] = set()
    if isinstance(value, dict):
        for name, item in value.items():
            paths |= referenced_paths(item, name)
    elif key.endswith("_path") and isinstance(value, str):
        paths.add(value)
    elif isinstance(value, list):
        if key.endswith("_paths"):
            paths |= {item for item in value if isinstance(item, str)}
        else:
            for item in value:
                paths |= referenced_paths(item)
    return paths


def fixture_revision(manifest: dict[str, Any]) -> str:
    stable = copy.deepcopy(manifest)
    stable["fixture_revision"] = PLACEHOLDER
    paths = referenced_paths(stable) | {
        "phase0/fixtures/catalog.json",
        "phase0/overlays/research-projection-contracts.json",
        "requirements.txt",
    }
    paths |= {
        str(path.relative_to(ROOT))
        for path in (ROOT / "phase0/corpus/classifications").glob("*.json")
    }
    files = {}
    for relative in sorted(paths):
        path = ROOT / relative
        if not path.is_file():
            raise PlanError(f"missing fixture input: {relative}")
        files[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    return digest({"manifest": stable, "files": files})


def term_key(value: Term | URIRef | Literal) -> tuple[str, str, str | None, str | None]:
    if isinstance(value, Term):
        return value.kind, value.value, value.datatype, value.language
    if isinstance(value, URIRef):
        return "iri", str(value), None, None
    if isinstance(value, Literal):
        return "literal", str(value), str(value.datatype) if value.datatype else None, value.language.lower() if value.language else None
    raise PlanError(f"unsupported oracle term: {type(value).__name__}")


def load_data(mode: str, paths: list[str]) -> Graph | Dataset:
    graph: Graph | Dataset = Graph() if mode == "graph" else Dataset()
    for path in paths:
        graph.parse(ROOT / path)
    return graph


def oracle(graph: Graph | Dataset, record: dict[str, Any]) -> tuple[str, bool | Counter[tuple[Any, ...]]]:
    result = graph.query((ROOT / record["semantic_oracle_query_path"]).read_text())
    if not record["oracle_variables"]:
        return "boolean", bool(result)
    rows = Counter(
        tuple(term_key(row[name]) for name in record["oracle_variables"])
        for row in result
    )
    return "select", rows


def evidence_complete(outcome: Any, atom_ids: tuple[str, ...]) -> tuple[int, int]:
    positive = outcome.kind == "selected" or outcome.kind == "boolean" and outcome.value is True
    if not positive:
        if outcome.supports:
            raise PlanError("non-positive outcome fabricated row support")
        return 0, 0
    denominator = len(outcome.rows) if outcome.kind == "selected" else 1
    if len(outcome.supports) != denominator:
        return 0, denominator
    numerator = 0
    for support in outcome.supports:
        ids = tuple(atom.atom_id for atom in support.atoms)
        valid = ids == atom_ids and len(ids) == len(set(ids))
        valid = valid and all(
            atom.status in {"derived", "witnessed"}
            and (atom.status != "witnessed" or atom.witness is not None)
            for atom in support.atoms
        )
        numerator += int(valid)
    return numerator, denominator


def validate_manifest(manifest: dict[str, Any], catalog: Catalog) -> None:
    corpus = load_json(CORPUS_PATH)
    if manifest.get("schema_version") != 1 or manifest.get("status") != "frozen":
        raise PlanError("fixture manifest must be frozen schema version 1")
    if manifest.get("corpus_revision") != corpus.get("corpus_revision"):
        raise PlanError("fixture corpus revision drift")
    actual_revision = fixture_revision(manifest)
    if manifest.get("fixture_revision") != actual_revision:
        raise PlanError(f"fixture revision drift: expected {actual_revision}")
    records = manifest.get("records")
    structural = manifest.get("structural_records")
    if not isinstance(records, list) or not isinstance(structural, list):
        raise PlanError("fixture records must be arrays")
    ids = [item.get("fixture_id") for item in records + structural]
    if any(not isinstance(item, str) or not item for item in ids) or len(ids) != len(set(ids)):
        raise PlanError("unique fixture IDs required")
    if manifest.get("adapter_modes") != ["graph", "dataset"]:
        raise PlanError("Graph and Dataset modes are required")
    classification_records = {
        path.stem: load_json(path)
        for path in (ROOT / "phase0/corpus/classifications").glob("*.json")
    }
    accepted = {key for key, value in classification_records.items() if value["primary_classification"] in {"direct", "overlay"}}
    linked_list = [
        question_id
        for item in records if item.get("kind") == "corpus_question"
        for question_id in item.get("question_ids", [])
    ]
    linked = set(linked_list)
    if accepted != linked or len(linked_list) != len(linked) or len(linked) != 18:
        raise PlanError("accepted corpus questions must have exactly one fixture")
    if len(records) != 35 or sum(item.get("kind") == "semantic_conformance" for item in records) != 17:
        raise PlanError("expected 18 corpus and 17 semantic execution fixtures")
    required_features = {
        "direct_predicate", "inverse_predicate", "direct_type_selector", "iri_target_node_selector",
        "exact_iri_identity", "exact_datatype_identity", "exact_lexical_identity", "exact_language_identity",
        "ask_true", "ask_false", "empty_select", "multi_lens",
    }
    features = {feature for item in records for feature in item.get("features", [])}
    if not required_features <= features:
        raise PlanError(f"missing feature cells: {sorted(required_features - features)}")
    if any(not item.get("reviewed_by") for item in records + structural):
        raise PlanError("every fixture requires a reviewer")
    fixture_ids = {item["fixture_id"] for item in records}
    for question_id, classification in classification_records.items():
        if classification["primary_classification"] == "overlay":
            references = set(classification["overlay_burden"]["semantic_fixture_ids"])
            if not references <= fixture_ids or question_id not in references:
                raise PlanError("overlay qualification fixture reference drift")
    materialized = {path.stem: load_json(path) for path in (ROOT / "phase0/fixtures/plans").glob("*.json")}
    authored = authored_plans()
    if materialized != authored:
        raise PlanError("materialized plans drifted from the hand-authored definitions")
    declared_plans = {
        Path(path).stem for path in referenced_paths({"records": records, "structural_records": structural})
        if path.startswith("phase0/fixtures/plans/")
    }
    if declared_plans != set(materialized):
        raise PlanError("fixture manifest does not declare every materialized plan")
    if any(normalize(raw, catalog).catalog_revision != catalog.revision for raw in materialized.values()):
        raise PlanError("plan catalog revision drift")


def execute_matrix(manifest: dict[str, Any], catalog: Catalog) -> tuple[list[dict[str, Any]], int, int]:
    cells: list[dict[str, Any]] = []
    evidence_numerator = evidence_denominator = 0
    for record in manifest["records"]:
        raw = load_json(ROOT / record["plan_path"])
        plan = normalize(raw, catalog)
        compiled = compile_plan(plan, catalog)
        for mode in manifest["adapter_modes"]:
            graph = load_data(mode, record["data_paths"])
            expected_kind, expected = oracle(graph, record)
            outcome = execute(plan, catalog, graph)
            if expected_kind == "boolean":
                passed = outcome.kind == "boolean" and outcome.value is expected
                count = int(bool(expected))
            else:
                actual = Counter(tuple(term_key(term) for term in row) for row in outcome.rows)
                passed = actual == expected and outcome.kind == ("selected" if expected else "no_match")
                count = sum(expected.values())
            complete, positive = evidence_complete(outcome, compiled.atom_ids)
            evidence_numerator += complete
            evidence_denominator += positive
            cells.append({
                "fixture_id": record["fixture_id"],
                "mode": mode,
                "kind": record["kind"],
                "passed": passed,
                "expected_solution_count": count,
                "outcome": outcome.kind if outcome.value is None else f"{outcome.kind}:{str(outcome.value).lower()}",
                "supported_positive_rows": complete,
                "positive_rows": positive,
                "query_digest": digest(outcome.query),
            })
    return cells, evidence_numerator, evidence_denominator


def normalization_checks(catalog: Catalog) -> list[dict[str, Any]]:
    def compiled(name: str) -> Any:
        raw = load_json(ROOT / f"phase0/fixtures/plans/{name}.json")
        return compile_plan(normalize(raw, catalog), catalog)
    core = compiled("semantic-core-select")
    equivalent = compiled("semantic-normalization-equivalent-alt")
    near = compiled("semantic-normalization-near-miss")
    return [
        {
            "fixture_id": "normalization-equivalent",
            "passed": core.plan_digest == equivalent.plan_digest and core.query == equivalent.query and core.evidence_query == equivalent.evidence_query,
        },
        {
            "fixture_id": "normalization-near-miss",
            "passed": core.plan_digest != near.plan_digest and core.query != near.query,
        },
    ]


def rebuild_catalog(*, trusted: bool = True, qualified: bool = True) -> Catalog:
    paths = [
        "phase0/corpus/shapes/staffing-skills.ttl",
        "phase0/corpus/shapes/service-operations.ttl",
        "phase0/corpus/shapes/research-publication-catalog.ttl",
        "phase0/fixtures/artifacts/semantic-shapes.ttl",
    ]
    return Catalog.build(
        [Graph().parse(ROOT / path) for path in paths],
        trusted=trusted,
        qualified=qualified,
        scalar_overrides=SCALAR_OVERRIDES,
    )


def remap_core(raw: dict[str, Any], catalog: Catalog) -> dict[str, Any]:
    remapped = copy.deepcopy(raw)
    shape = "https://example.test/semantic/ServiceShape"
    predicate = "https://example.test/semantic/ownedBy"
    lens = next(item for item in catalog.lenses if item.shape_term == shape)
    selector = next(item for item in catalog.selectors if item.lens_key == lens.key and item.kind == "direct_type")
    prop = next(item for item in catalog.properties if item.lens_key == lens.key and item.predicate_iri == predicate)
    remapped["catalog_revision"] = catalog.revision
    remapped["lenses"][0]["key"] = lens.key
    remapped["selectors"][0]["key"] = selector.key
    remapped["edges"][0]["property_key"] = prop.key
    remapped["edges"][0]["branch_key"] = prop.branch_keys[0]
    remapped["filters"][0]["property_key"] = prop.key
    remapped["filters"][0]["branch_key"] = prop.branch_keys[0]
    return remapped


def structural_checks(catalog: Catalog) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    dumped = json.loads(json.dumps(catalog.dump()))
    reloaded = Catalog.reload(dumped)
    core = load_json(ROOT / "phase0/fixtures/plans/semantic-core-select.json")
    rebuilt = rebuild_catalog()
    stale = copy.deepcopy(core)
    stale["catalog_revision"] = rebuilt.revision
    try:
        normalize(stale, rebuilt)
        stale_rejected = False
    except PlanError:
        stale_rejected = True
    blank_node_properties = [item for item in catalog.properties if not item.source_term.startswith(("http:", "https:", "urn:"))]
    lifecycle = {
        "fixture_id": "blank-node-catalog-lifecycle",
        "passed": reloaded == catalog and rebuilt.revision != catalog.revision and stale_rejected and bool(blank_node_properties),
        "blank_node_property_count": len(blank_node_properties),
        "reload_revision_stable": reloaded.revision == catalog.revision,
        "rebuild_revision_changed": rebuilt.revision != catalog.revision,
        "stale_key_rejected": stale_rejected,
    }

    graph = load_data("graph", ["phase0/fixtures/artifacts/semantic-data.ttl"])
    plan = normalize(core, catalog)
    class MalformedGraph:
        def query(self, _: str) -> list[object]:
            return [object()]
    runtime = {
        "cancelled": execute(plan, catalog, graph, cancelled=True),
        "timeout": execute(plan, catalog, graph, timeout_seconds=-1),
        "malformed_result": execute(plan, catalog, MalformedGraph()),
        "byte_limit": execute(plan, catalog, graph, byte_limit=0),
        "interrupted_sentinel": execute(plan, catalog, graph, interrupted_sentinel=True),
    }
    failures = [
        {"case": name, "passed": outcome.kind == "failed", "outcome": outcome.kind, "reason": outcome.reason}
        for name, outcome in runtime.items()
    ]
    for name, candidate, remap in (
        ("stale_catalog_key", rebuilt, False),
        ("untrusted_source", rebuild_catalog(trusted=False), True),
        ("unqualified_semantics", rebuild_catalog(qualified=False), True),
    ):
        raw = remap_core(core, candidate) if remap else stale
        try:
            normalize(raw, candidate)
            rejected = False
        except PlanError:
            rejected = True
        failures.append({"case": name, "passed": rejected, "outcome": "rejected" if rejected else "accepted", "reason": "PlanError" if rejected else None})
    return lifecycle, failures


def inspectability_check(manifest: dict[str, Any]) -> dict[str, Any]:
    result = load_json(ROOT / "phase0/results/inspectability.json")
    if result.get("corpus_revision") != manifest["corpus_revision"] or result.get("fixture_revision") != manifest["fixture_revision"]:
        raise PlanError("inspectability result revision drift")
    review_record = next(item for item in manifest["structural_records"] if item["kind"] == "inspectability")
    for path in review_record["artifact_paths"]:
        actual = hashlib.sha256((ROOT / path).read_bytes()).hexdigest()
        if result["artifact_sha256"].get(path) != actual:
            raise PlanError(f"inspectability artifact drift: {path}")
    ratios = []
    for case in result["cases"]:
        for modality in ("shapelens", "sparql"):
            review = case[modality]
            elapsed = (review["end_ns"] - review["start_ns"]) / 1_000_000_000
            if abs(elapsed - review["elapsed_seconds"]) > 1e-12 or not review["correct"]:
                raise PlanError("invalid inspectability review record")
        ratio = case["shapelens"]["elapsed_seconds"] / case["sparql"]["elapsed_seconds"]
        if abs(ratio - case["time_ratio"]) > 1e-12:
            raise PlanError("invalid inspectability time ratio")
        ratios.append(ratio)
    median = statistics.median(ratios)
    passed = len(ratios) >= 5 and all(case["shapelens"]["correct"] for case in result["cases"]) and median <= 1
    if abs(median - result["median_review_time_ratio"]["value"]) > 1e-12 or result.get("pass") is not passed:
        raise PlanError("invalid inspectability aggregate")
    return {"numerator": sum(case["shapelens"]["correct"] for case in result["cases"]), "denominator": len(ratios), "median_time_ratio": median, "threshold_accuracy": 1.0, "threshold_time_ratio_max": 1.0, "passed": passed}


def run() -> dict[str, Any]:
    manifest = load_json(MANIFEST_PATH)
    catalog = Catalog.reload(load_json(CATALOG_PATH))
    validate_manifest(manifest, catalog)
    cells, evidence_num, evidence_den = execute_matrix(manifest, catalog)
    normal = normalization_checks(catalog)
    lifecycle, failures = structural_checks(catalog)
    inspectability = inspectability_check(manifest)
    early = load_json(ROOT / "phase0/results/early-gate.json")
    if early.get("corpus_revision") != manifest["corpus_revision"]:
        raise PlanError("early-gate corpus revision drift")
    compiler_num = sum(item["passed"] for item in cells)
    corpus_cells = [item for item in cells if item["kind"] == "corpus_question"]
    records = {item["fixture_id"]: item for item in manifest["records"]}
    graph_paths = {records[cell["fixture_id"]]["shape_graph_paths"][0] for cell in corpus_cells}
    graph_results = {
        path: all(
            cell["passed"] for cell in corpus_cells
            if records[cell["fixture_id"]]["shape_graph_paths"][0] == path
        )
        for path in graph_paths
    }
    compatible_graphs = sum(graph_results.values())
    all_pass = (
        compiler_num == len(cells)
        and all(item["passed"] for item in normal)
        and evidence_num == evidence_den
        and lifecycle["passed"]
        and all(item["passed"] for item in failures)
        and compatible_graphs == 3
        and inspectability["passed"]
        and early.get("pass") is True
    )
    return {
        "schema_version": 1,
        "corpus_revision": manifest["corpus_revision"],
        "fixture_revision": manifest["fixture_revision"],
        "metric_owner": manifest["owner"],
        "exclusions": [],
        "fixture_counts": {"corpus_questions": 18, "semantic_conformance": 17, "adapter_modes": 2, "execution_cells": len(cells)},
        "compiler_correctness": {"numerator": compiler_num, "denominator": len(cells), "threshold": 1.0, "passed": compiler_num == len(cells)},
        "normalization_correctness": {"numerator": sum(item["passed"] for item in normal), "denominator": len(normal), "threshold": 1.0, "passed": all(item["passed"] for item in normal), "cases": normal},
        "compiler_backed_shape_compatibility": {"numerator": compatible_graphs, "denominator": 3, "threshold": 0.7, "passed": compatible_graphs / 3 >= 0.7, "graph_results": graph_results, "rewritten_graphs": []},
        "evidence_completeness": {"numerator": evidence_num, "denominator": evidence_den, "threshold": 1.0, "passed": evidence_num == evidence_den, "empty_results_have_no_row_support": True},
        "failure_honesty": {"numerator_false_answers_or_no_matches": 0 if all(item["passed"] for item in failures) else 1, "denominator_cases": len(failures), "threshold": 0, "passed": all(item["passed"] for item in failures), "cases": failures},
        "inspectability": inspectability,
        "early_product_gate": {"direct_ratio": early["direct_ratio"], "combined_ratio": early["direct_plus_overlay_ratio"], "shape_compatibility_ratio": early["shape_compatibility_ratio"], "overlay_burden": early["overlay_burden"], "passed": early["pass"]},
        "catalog_lifecycle": lifecycle,
        "feature_matrix": sorted({feature for item in manifest["records"] for feature in item["features"]}),
        "execution_cells": cells,
        "pass": all_pass,
    }


if __name__ == "__main__":
    manifest = load_json(MANIFEST_PATH)
    if len(sys.argv) == 2 and sys.argv[1] == "revision":
        print(fixture_revision(manifest))
    elif len(sys.argv) == 1 or sys.argv[1:] == ["run"]:
        print(json.dumps(run(), indent=2, sort_keys=True))
    else:
        raise SystemExit("usage: run_fixtures.py [revision|run]")
