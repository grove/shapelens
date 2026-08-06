#!/usr/bin/env python3
"""Dependency-free freeze checks for the Phase 0 question corpus."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
CORPUS = ROOT / "phase0" / "corpus"
MANIFEST_PATH = CORPUS / "manifest.json"
CLASSIFICATIONS = CORPUS / "classifications"
METRICS = {
    "compiler_correctness", "normalization_correctness",
    "shape_authoring_compatibility", "question_coverage", "overlay_burden",
    "inspectability", "evidence_completeness", "failure_honesty",
}


def object_pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in items:
        if key in result:
            raise ValueError(f"duplicate key {key!r}")
        result[key] = value
    return result


def read_json(path: Path, errors: list[str]) -> dict[str, Any]:
    try:
        value = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=object_pairs,
            parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)),
        )
        if not isinstance(value, dict):
            raise ValueError("top-level value must be an object")
        return value
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        errors.append(f"{path.relative_to(ROOT)}: {exc}")
        return {}


def nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def string_list(value: Any) -> list[str]:
    if isinstance(value, list) and all(nonempty(item) for item in value):
        return value
    return []


def ratio(value: Any) -> bool:
    return (
        not isinstance(value, bool)
        and isinstance(value, (int, float))
        and math.isfinite(value)
        and 0 <= value <= 1
    )


def repo_file(value: Any, label: str, errors: list[str]) -> Path | None:
    if not nonempty(value):
        errors.append(f"{label}: expected a repository-relative file path")
        return None
    raw = Path(value)
    if raw.is_absolute() or ".." in raw.parts:
        errors.append(f"{label}: absolute paths and '..' are forbidden")
        return None
    path = (ROOT / raw).resolve()
    try:
        path.relative_to(ROOT.resolve())
    except ValueError:
        errors.append(f"{label}: path escapes the repository")
        return None
    if not path.is_file():
        errors.append(f"{label}: file does not exist: {value}")
        return None
    return path


def validate(mode: str) -> tuple[dict[str, Any], set[Path], int, list[str]]:
    errors: list[str] = []
    artifacts: set[Path] = set()
    manifest = read_json(MANIFEST_PATH, errors)
    if not manifest:
        return manifest, artifacts, 0, errors
    if manifest.get("schema_version") != 1:
        errors.append("manifest.schema_version: expected 1")
    if mode == "freeze-check" and manifest.get("status") != "draft":
        errors.append("manifest.status: freeze-check requires draft")
    if mode == "frozen-check" and manifest.get("status") != "frozen":
        errors.append("manifest.status: frozen-check requires frozen")

    scenarios = manifest.get("scenarios")
    shapes = manifest.get("shape_graphs")
    question_files = manifest.get("question_files")
    if not all(isinstance(value, list) for value in (scenarios, shapes, question_files)):
        errors.append("manifest: scenarios, shape_graphs, and question_files must be arrays")
        return manifest, artifacts, 0, errors
    scenario_ids = {
        item.get("scenario_id") for item in scenarios
        if isinstance(item, dict) and isinstance(item.get("scenario_id"), str)
    }
    shape_ids = {
        item.get("shape_graph_id") for item in shapes
        if isinstance(item, dict) and isinstance(item.get("shape_graph_id"), str)
    }
    if len(scenario_ids) != len(scenarios) or None in scenario_ids:
        errors.append("manifest.scenarios: IDs must be present and unique")
    if len(shape_ids) != len(shapes) or None in shape_ids:
        errors.append("manifest.shape_graphs: IDs must be present and unique")
    for index, scenario in enumerate(scenarios):
        required = ("scenario_id", "name", "owner", "description", "material_difference")
        if not isinstance(scenario, dict) or not all(nonempty(scenario.get(key)) for key in required):
            errors.append(f"manifest.scenarios[{index}]: incomplete scenario record")
    for index, shape in enumerate(shapes):
        required = (
            "shape_graph_id", "owner", "provenance_kind", "provenance_description",
            "source_trust", "trust_assessed_by",
        )
        if not isinstance(shape, dict) or not all(nonempty(shape.get(key)) for key in required):
            errors.append(f"manifest.shape_graphs[{index}]: incomplete shape record")
            continue
        shape_scenarios = set(string_list(shape.get("scenario_ids")))
        if not shape_scenarios or not shape_scenarios <= scenario_ids:
            errors.append(f"manifest.shape_graphs[{index}]: unknown or missing scenario")
        if not string_list(shape.get("shape_styles")):
            errors.append(f"manifest.shape_graphs[{index}]: shape_styles required")
        if shape.get("provenance_kind") not in {"independently_authored", "representative"}:
            errors.append(f"manifest.shape_graphs[{index}]: invalid provenance kind")
        if shape.get("source_trust") not in {"trusted", "untrusted", "quarantined"}:
            errors.append(f"manifest.shape_graphs[{index}]: invalid source trust")
        if not isinstance(shape.get("rewritten_for_experiment"), bool):
            errors.append(f"manifest.shape_graphs[{index}]: rewritten_for_experiment must be Boolean")
        if shape.get("rewritten_for_experiment") is True and not nonempty(
            shape.get("rewrite_description")
        ):
            errors.append(f"manifest.shape_graphs[{index}]: rewrite description required")
        path = repo_file(shape.get("path"), f"manifest.shape_graphs[{index}].path", errors)
        if path:
            artifacts.add(path)

    questions: list[dict[str, Any]] = []
    question_ids: set[str] = set()
    if not all(nonempty(path) for path in question_files) or len(question_files) != len(set(question_files)):
        errors.append("manifest.question_files: paths must be unique strings")
    for index, raw in enumerate(question_files):
        path = repo_file(raw, f"manifest.question_files[{index}]", errors)
        if not path:
            continue
        try:
            path.relative_to((CORPUS / "questions").resolve())
        except ValueError:
            errors.append(f"manifest.question_files[{index}]: must live under corpus/questions")
        question = read_json(path, errors)
        artifacts.add(path)
        question_id = question.get("question_id")
        if question.get("schema_version") != 1 or not nonempty(question_id):
            errors.append(f"{path.relative_to(ROOT)}: schema or question ID invalid")
        elif question_id in question_ids:
            errors.append(f"{path.relative_to(ROOT)}: duplicate question ID")
        else:
            question_ids.add(question_id)
        if question.get("scenario_id") not in scenario_ids:
            errors.append(f"{path.relative_to(ROOT)}: unknown scenario")
        if not all(nonempty(question.get(key)) for key in (
            "owner", "priority_rationale", "question", "scope_reason"
        )) or question.get("priority") not in {"critical", "high", "medium"}:
            errors.append(f"{path.relative_to(ROOT)}: owner, value rationale, text, scope reason, and priority required")
        if question.get("scope") not in {"in_scope", "excluded"}:
            errors.append(f"{path.relative_to(ROOT)}: scope must be in_scope or excluded")
        if question.get("authored_before_plan_design") is not True:
            errors.append(f"{path.relative_to(ROOT)}: authored_before_plan_design must be true")
        expected = question.get("expected_answer")
        if not isinstance(expected, dict) or expected.get("form") not in {
            "entity_set", "records", "boolean", "scalar", "document", "other"
        } or not nonempty(expected.get("description")):
            errors.append(f"{path.relative_to(ROOT)}: expected answer form and description required")
        refs = set(string_list(question.get("shape_graph_ids")))
        if not refs or not refs <= shape_ids:
            errors.append(f"{path.relative_to(ROOT)}: unknown or missing shape graph")
        data = repo_file(question.get("dataset_fixture"), f"{path.relative_to(ROOT)}.dataset", errors)
        if data:
            artifacts.add(data)
        baseline = question.get("baseline")
        kind = baseline.get("kind") if isinstance(baseline, dict) else None
        if kind in {"direct_sparql", "application_code"}:
            baseline_path = repo_file(baseline.get("path"), f"{path.relative_to(ROOT)}.baseline", errors)
            if baseline_path:
                artifacts.add(baseline_path)
            if not string_list(baseline.get("reviewed_by")):
                errors.append(f"{path.relative_to(ROOT)}: baseline reviewer required")
        elif kind == "not_meaningful":
            if not nonempty(baseline.get("not_meaningful_reason")):
                errors.append(f"{path.relative_to(ROOT)}: baseline reason required")
        else:
            errors.append(f"{path.relative_to(ROOT)}: invalid baseline kind")
        questions.append(question)

    in_scope = [item for item in questions if item.get("scope") == "in_scope"]
    if mode != "draft-check":
        if not nonempty(manifest.get("corpus_id")) or not nonempty(manifest.get("corpus_owner")):
            errors.append("manifest: corpus_id and corpus_owner required before freeze")
        scope = manifest.get("scope")
        if not isinstance(scope, dict) or not all(
            nonempty(scope.get(key)) for key in ("statement", "denominator_rule", "exclusion_rule")
        ):
            errors.append("manifest.scope: statement and denominator/exclusion rules required")
        owners = manifest.get("metric_owners")
        if not isinstance(owners, dict) or set(owners) != METRICS or not all(
            map(nonempty, owners.values())
        ):
            errors.append("manifest.metric_owners: all eight named owners required")
        represented = {item.get("scenario_id") for item in in_scope}
        referenced_shapes = {
            shape_id for item in in_scope for shape_id in string_list(item.get("shape_graph_ids"))
        }
        if not 20 <= len(in_scope) <= 30:
            errors.append(f"corpus: expected 20-30 in-scope questions; found {len(in_scope)}")
        if len(represented) < 3:
            errors.append(f"corpus: expected at least 3 scenarios; found {len(represented)}")
        gates = manifest.get("product_gates", {})
        coverage = gates.get("question_coverage", {}) if isinstance(gates, dict) else {}
        compatibility = gates.get("shape_authoring_compatibility", {}) if isinstance(gates, dict) else {}
        overlay = gates.get("overlay_burden", {}) if isinstance(gates, dict) else {}
        inspectability = gates.get("inspectability", {}) if isinstance(gates, dict) else {}
        if not all(ratio(coverage.get(key)) for key in (
            "minimum_direct_ratio", "minimum_direct_plus_overlay_ratio"
        )) or coverage.get("minimum_direct_plus_overlay_ratio", 0) < coverage.get(
            "minimum_direct_ratio", 0
        ):
            errors.append("product_gates.question_coverage: invalid ratios")
        minimum_scenarios = coverage.get("minimum_scenarios_meeting_combined_threshold")
        if not isinstance(minimum_scenarios, int) or not 2 <= minimum_scenarios <= len(represented):
            errors.append("product_gates.question_coverage: invalid scenario threshold")
        if set(string_list(compatibility.get("eligible_shape_graph_ids"))) != referenced_shapes:
            errors.append("product_gates.shape_authoring_compatibility: eligible graph set is incomplete")
        if compatibility.get("pass_rule") != "no_shape_blocked_or_rewrite" or not ratio(
            compatibility.get("minimum_pass_ratio")
        ):
            errors.append("product_gates.shape_authoring_compatibility: invalid rule or ratio")
        limits = (
            overlay.get("maximum_median_executable_declarations_per_overlay_question"),
            overlay.get("maximum_worst_case_executable_declarations_per_overlay_question"),
            overlay.get("maximum_executable_declarations_per_graph"),
        )
        if not all(isinstance(value, int) and value >= 0 for value in limits) or limits[1] < limits[0]:
            errors.append("product_gates.overlay_burden: invalid limits")
        if inspectability.get("responsible_artifact_accuracy_min") != 1.0:
            errors.append("product_gates.inspectability: responsible-artifact accuracy is fixed at 1.0")
        if not isinstance(inspectability.get("minimum_review_cases"), int) or inspectability.get(
            "minimum_review_cases", 0
        ) < 1 or not isinstance(inspectability.get("median_review_time_ratio_max"), (int, float)) or inspectability.get(
            "median_review_time_ratio_max", 0
        ) <= 0:
            errors.append("product_gates.inspectability: review count and positive time ratio required")

    if mode == "freeze-check":
        if manifest.get("corpus_revision") is not None or manifest.get("frozen_at") is not None or manifest.get("frozen_by") != []:
            errors.append("manifest: revision and freeze fields must be empty before freeze")
        if list(CLASSIFICATIONS.glob("*.json")):
            errors.append("freeze-check: classifications already exist")
    if mode == "frozen-check":
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", str(manifest.get("corpus_revision"))):
            errors.append("manifest.corpus_revision: expected sha256:<64 lowercase hex>")
        try:
            timestamp = datetime.fromisoformat(str(manifest.get("frozen_at")).replace("Z", "+00:00"))
            if timestamp.tzinfo is None:
                raise ValueError
        except ValueError:
            errors.append("manifest.frozen_at: timestamp with timezone required")
        if not string_list(manifest.get("frozen_by")):
            errors.append("manifest.frozen_by: at least one approver required")
    return manifest, artifacts, len(questions), errors


def revision(manifest: dict[str, Any], artifacts: set[Path]) -> str:
    stable = {
        key: value for key, value in manifest.items()
        if key not in {"status", "corpus_revision", "frozen_at", "frozen_by"}
    }
    digest = hashlib.sha256(json.dumps(stable, sort_keys=True, separators=(",", ":")).encode())
    for path in sorted(artifacts):
        digest.update(str(path.relative_to(ROOT)).encode() + b"\0")
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    return f"sha256:{digest.hexdigest()}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("draft-check", "freeze-check", "frozen-check"))
    command = parser.parse_args().command
    manifest, artifacts, question_count, errors = validate(command)
    for error in errors:
        print(f"ERROR: {error}", file=sys.stderr)
    if errors:
        print(f"{len(errors)} error(s)", file=sys.stderr)
        return 1
    computed = revision(manifest, artifacts)
    if command == "freeze-check":
        print(f"Freeze-ready: {question_count} records; set corpus_revision to {computed}")
    elif command == "frozen-check":
        if manifest.get("corpus_revision") != computed:
            print("ERROR: frozen corpus content drifted from its recorded revision", file=sys.stderr)
            return 1
        print(f"Frozen corpus valid: {computed}")
    else:
        print(f"Draft structure valid: {question_count} question records")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
