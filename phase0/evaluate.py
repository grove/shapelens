#!/usr/bin/env python3
"""Validate Phase 0 classifications and calculate the frozen early product gate."""

from __future__ import annotations

import json
import re
import statistics
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from validate import object_pairs


ROOT = Path(__file__).resolve().parent.parent
CORPUS = ROOT / "phase0" / "corpus"
CLASSIFICATIONS = CORPUS / "classifications"
PRIMARY = {"direct", "overlay", "algebra_blocked", "shape_blocked", "ordinary_code"}


def load(path: Path) -> dict[str, Any]:
    value = json.loads(
        path.read_text(encoding="utf-8"),
        object_pairs_hook=object_pairs,
        parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)),
    )
    if not isinstance(value, dict):
        raise ValueError(f"{path.relative_to(ROOT)}: expected JSON object")
    return value


def strings(value: Any) -> list[str]:
    return value if isinstance(value, list) and value and all(
        isinstance(item, str) and item.strip() for item in value
    ) and len(value) == len(set(value)) else []


def string_array(value: Any, *, empty: bool = False) -> bool:
    return isinstance(value, list) and (empty or bool(value)) and all(
        isinstance(item, str) and item.strip() for item in value
    ) and len(value) == len(set(value))


def early_gate() -> tuple[dict[str, Any], list[str]]:
    errors: list[str] = []
    manifest = load(CORPUS / "manifest.json")
    questions = {
        question["question_id"]: question
        for path in manifest["question_files"]
        if (question := load(ROOT / path))["scope"] == "in_scope"
    }
    records: dict[str, dict[str, Any]] = {}
    classification_paths = sorted(
        path for path in CLASSIFICATIONS.rglob("*")
        if path.is_file() and path.suffix.lower() == ".json"
    )
    for path in classification_paths:
        try:
            record = load(path)
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
            errors.append(str(exc))
            continue
        question_id = record.get("question_id")
        if question_id in records:
            errors.append(f"{path.relative_to(ROOT)}: duplicate classification for {question_id}")
            continue
        records[question_id] = record
        question = questions.get(question_id)
        if not question:
            errors.append(f"{path.relative_to(ROOT)}: unknown or excluded question {question_id}")
            continue
        primary = record.get("primary_classification")
        reason_value = record.get("reason_codes")
        reasons = reason_value if string_array(reason_value, empty=True) else []
        affected = strings(record.get("affected_shape_graph_ids"))
        burden = record.get("overlay_burden")
        rewriting = record.get("shape_rewriting")
        if type(record.get("schema_version")) is not int or record["schema_version"] != 1:
            errors.append(f"{path.relative_to(ROOT)}: schema_version must be 1")
        if record.get("corpus_revision") != manifest["corpus_revision"]:
            errors.append(f"{path.relative_to(ROOT)}: corpus revision mismatch")
        if primary not in PRIMARY:
            errors.append(f"{path.relative_to(ROOT)}: invalid primary classification")
        if set(affected) != set(question["shape_graph_ids"]):
            errors.append(f"{path.relative_to(ROOT)}: affected shape graphs must match the question")
        if record.get("shape_source_trust") != "trusted":
            errors.append(f"{path.relative_to(ROOT)}: representative source must remain trusted")
        if not string_array(reason_value, empty=True):
            errors.append(f"{path.relative_to(ROOT)}: reason_codes must be a unique string array")
        if record.get("qualification_status") != "pending":
            errors.append(f"{path.relative_to(ROOT)}: qualification must remain pending at 0.0b")
        if not string_array(record.get("required_features")):
            errors.append(f"{path.relative_to(ROOT)}: required_features must be explicit")
        if primary in {"algebra_blocked", "shape_blocked", "ordinary_code"} and (
            not reasons or not isinstance(record.get("blocker_details"), str)
            or not record["blocker_details"].strip()
        ):
            errors.append(f"{path.relative_to(ROOT)}: blocked classification needs reasons and details")
        if primary == "direct" and (reasons or record.get("blocker_details") is not None):
            errors.append(f"{path.relative_to(ROOT)}: direct classification cannot carry blockers")
        if any(not re.fullmatch(r"[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*", code) for code in reasons):
            errors.append(f"{path.relative_to(ROOT)}: reason codes must be namespaced snake case")
        if not isinstance(burden, dict) or any(
            type(burden.get(key)) is not int or burden[key] < 0
            for key in ("descriptive_declarations", "executable_declarations")
        ):
            errors.append(f"{path.relative_to(ROOT)}: invalid overlay declaration counts")
        elif primary == "overlay" and burden["executable_declarations"] < 1:
            errors.append(f"{path.relative_to(ROOT)}: overlay requires executable declarations")
        elif primary != "overlay" and burden["executable_declarations"] != 0:
            errors.append(f"{path.relative_to(ROOT)}: non-overlay question cannot charge executable overlay")
        if isinstance(burden, dict):
            overlay_lists = (
                "executable_declaration_kinds", "declaration_references",
                "affected_lens_uses", "semantic_fixture_ids",
            )
            if primary == "overlay" and (
                any(not string_array(burden.get(key)) for key in overlay_lists)
                or burden.get("executable_declarations") != len(burden.get("declaration_references", ()))
                or not isinstance(burden.get("review_owner"), str)
                or not burden["review_owner"].strip()
            ):
                errors.append(f"{path.relative_to(ROOT)}: overlay declarations require references, lenses, fixtures, and review")
            if primary != "overlay" and any(burden.get(key) for key in overlay_lists):
                errors.append(f"{path.relative_to(ROOT)}: non-overlay question has executable overlay metadata")
            for reference in burden.get("declaration_references", ()):
                if not (ROOT / reference.split("#", 1)[0]).is_file():
                    errors.append(f"{path.relative_to(ROOT)}: missing overlay declaration {reference}")
        if not isinstance(rewriting, dict) or not isinstance(rewriting.get("required"), bool):
            errors.append(f"{path.relative_to(ROOT)}: invalid shape rewriting record")
        elif rewriting["required"] and not isinstance(rewriting.get("description"), str):
            errors.append(f"{path.relative_to(ROOT)}: required rewrite needs a description")
        if not isinstance(record.get("semantic_owner_reviewed_by"), str) or not record[
            "semantic_owner_reviewed_by"
        ].strip() or not strings(
            record.get("classified_by")
        ) or not strings(record.get("reviewed_by")):
            errors.append(f"{path.relative_to(ROOT)}: classification and semantic reviews required")

    missing = sorted(set(questions) - set(records))
    if missing:
        errors.append(f"missing classifications: {', '.join(missing)}")
    if errors:
        return {}, errors

    denominator = len(questions)
    direct = sum(record["primary_classification"] == "direct" for record in records.values())
    overlay = sum(record["primary_classification"] == "overlay" for record in records.values())
    coverage_gate = manifest["product_gates"]["question_coverage"]
    scenarios: dict[str, dict[str, Any]] = {}
    for scenario in manifest["scenarios"]:
        subset = [records[qid] for qid, question in questions.items() if question["scenario_id"] == scenario["scenario_id"]]
        combined = sum(record["primary_classification"] in {"direct", "overlay"} for record in subset)
        scenarios[scenario["scenario_id"]] = {
            "direct": sum(record["primary_classification"] == "direct" for record in subset),
            "direct_plus_overlay": combined,
            "denominator": len(subset),
            "combined_ratio": combined / len(subset),
        }
    scenario_passes = sum(
        result["combined_ratio"] >= coverage_gate["minimum_direct_plus_overlay_ratio"]
        for result in scenarios.values()
    )

    graph_results: dict[str, bool] = {}
    per_graph_overlay: Counter[str] = Counter()
    for shape in manifest["shape_graphs"]:
        graph_id = shape["shape_graph_id"]
        related = [
            records[qid] for qid, question in questions.items()
            if graph_id in question["shape_graph_ids"]
        ]
        graph_results[graph_id] = not shape["rewritten_for_experiment"] and all(
            record["primary_classification"] != "shape_blocked"
            and not record["shape_rewriting"]["required"]
            for record in related
        )
        for record in related:
            per_graph_overlay[graph_id] += record["overlay_burden"]["executable_declarations"]

    overlay_counts = [
        record["overlay_burden"]["executable_declarations"]
        for record in records.values() if record["primary_classification"] == "overlay"
    ]
    compatibility_gate = manifest["product_gates"]["shape_authoring_compatibility"]
    burden_gate = manifest["product_gates"]["overlay_burden"]
    direct_ratio = direct / denominator
    combined_ratio = (direct + overlay) / denominator
    compatibility_ratio = sum(graph_results.values()) / len(graph_results)
    median_overlay = statistics.median(overlay_counts) if overlay_counts else 0
    worst_overlay = max(overlay_counts, default=0)
    worst_graph_overlay = max(per_graph_overlay.values(), default=0)
    checks = {
        "direct_coverage": direct_ratio >= coverage_gate["minimum_direct_ratio"],
        "combined_coverage": combined_ratio >= coverage_gate["minimum_direct_plus_overlay_ratio"],
        "scenario_coverage": scenario_passes >= coverage_gate["minimum_scenarios_meeting_combined_threshold"],
        "shape_compatibility": compatibility_ratio >= compatibility_gate["minimum_pass_ratio"],
        "median_overlay_burden": median_overlay <= burden_gate["maximum_median_executable_declarations_per_overlay_question"],
        "worst_question_overlay_burden": worst_overlay <= burden_gate["maximum_worst_case_executable_declarations_per_overlay_question"],
        "worst_graph_overlay_burden": worst_graph_overlay <= burden_gate["maximum_executable_declarations_per_graph"],
    }
    return {
        "corpus_revision": manifest["corpus_revision"],
        "metric_owners": manifest["metric_owners"],
        "thresholds": manifest["product_gates"],
        "exclusions": sorted(
            question["question_id"] for path in manifest["question_files"]
            if (question := load(ROOT / path))["scope"] == "excluded"
        ),
        "question_count": denominator,
        "classification_counts": dict(sorted(Counter(
            record["primary_classification"] for record in records.values()
        ).items())),
        "direct_ratio": direct_ratio,
        "direct_plus_overlay_ratio": combined_ratio,
        "scenario_results": scenarios,
        "scenarios_meeting_combined_threshold": scenario_passes,
        "shape_graph_results": graph_results,
        "shape_compatibility_ratio": compatibility_ratio,
        "overlay_burden": {
            "question_median": median_overlay,
            "question_worst": worst_overlay,
            "graph_worst": worst_graph_overlay,
        },
        "blocker_distribution": dict(sorted(Counter(
            code for record in records.values()
            if record["primary_classification"] in {"algebra_blocked", "shape_blocked", "ordinary_code"}
            for code in record["reason_codes"]
        ).items())),
        "checks": checks,
        "pass": all(checks.values()),
    }, []


def main() -> int:
    try:
        result, errors = early_gate()
    except (OSError, UnicodeError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        errors = [str(exc)]
        result = {}
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
