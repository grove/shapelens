import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import validate


class ValidateTests(unittest.TestCase):
    def test_complete_corpus_freezes_and_detects_drift(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            corpus = root / "phase0" / "corpus"
            questions = corpus / "questions"
            classifications = corpus / "classifications"
            questions.mkdir(parents=True)
            classifications.mkdir()
            shape = corpus / "shapes.ttl"
            data = corpus / "data.ttl"
            baseline = corpus / "baseline.rq"
            for path, content in (
                (shape, "# shapes\n"),
                (data, "# data\n"),
                (baseline, "SELECT * WHERE {}\n"),
            ):
                path.write_text(content, encoding="utf-8")

            scenario_ids = ["one", "two", "three"]
            question_files = []
            for index in range(20):
                question_path = questions / f"q-{index}.json"
                question_path.write_text(json.dumps({
                    "schema_version": 1,
                    "question_id": f"q-{index}",
                    "scenario_id": scenario_ids[index % 3],
                    "owner": f"owner-{index % 3}",
                    "priority": "high",
                    "priority_rationale": "valuable",
                    "question": f"Question {index}?",
                    "scope": "in_scope",
                    "scope_reason": "representative",
                    "expected_answer": {"form": "records", "description": "records"},
                    "dataset_fixture": "phase0/corpus/data.ttl",
                    "shape_graph_ids": ["shapes"],
                    "baseline": {
                        "kind": "direct_sparql",
                        "path": "phase0/corpus/baseline.rq",
                        "reviewed_by": ["reviewer"],
                    },
                    "authored_before_plan_design": True,
                }), encoding="utf-8")
                question_files.append(f"phase0/corpus/questions/{question_path.name}")

            metric_owners = {metric: "metric-owner" for metric in validate.METRICS}
            manifest = {
                "schema_version": 1,
                "corpus_id": "corpus",
                "corpus_revision": None,
                "status": "draft",
                "corpus_owner": "owner",
                "scope": {
                    "statement": "scope",
                    "denominator_rule": "all in scope",
                    "exclusion_rule": "frozen exclusions",
                },
                "frozen_at": None,
                "frozen_by": [],
                "scenarios": [{
                    "scenario_id": scenario_id,
                    "name": scenario_id,
                    "owner": f"owner-{index}",
                    "description": "scenario",
                    "material_difference": "different",
                } for index, scenario_id in enumerate(scenario_ids)],
                "shape_graphs": [{
                    "shape_graph_id": "shapes",
                    "scenario_ids": scenario_ids,
                    "owner": "shape-owner",
                    "path": "phase0/corpus/shapes.ttl",
                    "provenance_kind": "representative",
                    "provenance_description": "source",
                    "shape_styles": ["node_shapes"],
                    "rewritten_for_experiment": False,
                    "source_trust": "trusted",
                    "trust_assessed_by": "trust-owner",
                }],
                "question_files": question_files,
                "metric_owners": metric_owners,
                "threshold_approvals": {
                    "application_owners": ["owner-0", "owner-1", "owner-2"],
                    "metric_owners": ["metric-owner"],
                },
                "product_gates": {
                    "question_coverage": {
                        "minimum_direct_ratio": 0.5,
                        "minimum_direct_plus_overlay_ratio": 0.7,
                        "minimum_scenarios_meeting_combined_threshold": 2,
                    },
                    "shape_authoring_compatibility": {
                        "eligible_shape_graph_ids": ["shapes"],
                        "pass_rule": "no_shape_blocked_or_rewrite",
                        "minimum_pass_ratio": 0.7,
                    },
                    "overlay_burden": {
                        "maximum_median_executable_declarations_per_overlay_question": 1,
                        "maximum_worst_case_executable_declarations_per_overlay_question": 3,
                        "maximum_executable_declarations_per_graph": 10,
                    },
                    "inspectability": {
                        "minimum_review_cases": 5,
                        "responsible_artifact_accuracy_min": 1.0,
                        "median_review_time_ratio_max": 1.0,
                    },
                },
            }
            manifest_path = corpus / "manifest.json"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            with patch.multiple(
                validate,
                ROOT=root,
                CORPUS=corpus,
                MANIFEST_PATH=manifest_path,
                CLASSIFICATIONS=classifications,
            ):
                loaded, artifacts, count, errors = validate.validate("freeze-check")
                self.assertEqual((count, errors), (20, []))
                before = validate.revision(loaded, artifacts)
                data.write_text("# changed data\n", encoding="utf-8")
                self.assertNotEqual(before, validate.revision(loaded, artifacts))

    def test_json_booleans_are_not_numbers(self):
        self.assertFalse(validate.schema_version(True))
        self.assertFalse(validate.nonnegative_integer(False))
        self.assertFalse(validate.positive_number(True))
        self.assertFalse(validate.ratio(True))
        self.assertEqual(validate.string_list(["duplicate", "duplicate"]), [])

    def test_nested_classification_blocks_freeze(self):
        with tempfile.TemporaryDirectory() as directory:
            classifications = Path(directory) / "nested"
            classifications.mkdir()
            (classifications / "result.JSON").write_text("{}", encoding="utf-8")
            with patch.object(validate, "CLASSIFICATIONS", Path(directory)):
                errors = validate.validate("freeze-check")[3]
            self.assertIn("freeze-check: classifications already exist", errors)

    def test_boolean_schema_version_is_rejected(self):
        manifest = json.loads(validate.MANIFEST_PATH.read_text(encoding="utf-8"))
        manifest["schema_version"] = True
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "manifest.json"
            path.write_text(json.dumps(manifest), encoding="utf-8")
            with patch.object(validate, "MANIFEST_PATH", path):
                errors = validate.validate("draft-check")[3]
        self.assertIn("manifest.schema_version: expected 1", errors)


if __name__ == "__main__":
    unittest.main()
