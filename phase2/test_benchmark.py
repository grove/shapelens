import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

import benchmark


class BenchmarkTests(unittest.TestCase):
    def test_draft_inputs_and_candidate_recall_are_valid(self):
        errors, evidence = benchmark.validate()
        self.assertEqual([], errors)
        self.assertEqual(28, evidence["cases"])
        self.assertEqual(20, evidence["representative"])
        self.assertEqual(
            benchmark.load_json(benchmark.MANIFEST)["catalog_revision"],
            evidence["catalog_revision"],
        )

    def test_per_run_report_requires_direct_query_review(self):
        manifest = benchmark.load_json(benchmark.MANIFEST)
        catalog = benchmark.build_catalog(manifest["catalog_build_id"])
        cases = benchmark.load_json(benchmark.WORKSPACE / "cases.json")
        attempts = []
        for run_number in (1, 2, 3):
            for case in cases:
                completed = case["expected_disposition"] == "completed"
                intents = [
                    {
                        "role": item["role"],
                        "catalog_keys": list(benchmark.gold_intent_signature(item, catalog)[1]),
                        "value": item.get("value"),
                    }
                    for item in case["intent_items"]
                ]
                attempts.append(
                    {
                        "case_id": case["case_id"],
                        "scenario": case["scenario"],
                        "representative": case["representative"],
                        "critical": case["critical"],
                        "expected_disposition": case["expected_disposition"],
                        "run": run_number,
                        "candidate": {
                            "status": case["expected_disposition"],
                            "calls": 1,
                            "input_tokens": 10,
                            "output_tokens": 10,
                            "latency_seconds": 0.1,
                            "candidate_card_keys": ["required"],
                            "required_card_keys": ["required"] if completed else [],
                            "intent_items": intents if completed else [],
                            "coverage": [],
                            "entity_resolutions": benchmark.gold_entity_resolutions(
                                case, benchmark.load_entities()
                            ),
                            "internal_coverage_valid": True,
                            "semantic_correct": completed,
                        },
                        "flat_catalog": {
                            "status": case["expected_disposition"],
                            "input_tokens": 20,
                            "semantic_correct": completed,
                        },
                        "direct_query": {"value": {}, "semantic_correct": None},
                    }
                )
        first = next(row for row in attempts if row["case_id"] == "staffing-q02" and row["run"] == 1)
        second = next(row for row in attempts if row["case_id"] == "staffing-q03" and row["run"] == 1)
        first_entities = first["candidate"]["entity_resolutions"]
        second_entities = second["candidate"]["entity_resolutions"]
        first["candidate"]["entity_resolutions"], second["candidate"]["entity_resolutions"] = (
            second["candidate"]["entity_resolutions"],
            first["candidate"]["entity_resolutions"],
        )
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "raw.json"
            target = Path(directory) / "report.json"
            reviews = Path(directory) / "reviews.json"
            passing_target = Path(directory) / "passing-report.json"
            complete_reviews_path = Path(directory) / "complete-reviews.json"
            source.write_text(
                json.dumps(
                    {
                        "manifest_revision": manifest["benchmark_revision"],
                        "attempts": attempts,
                    }
                )
            )
            benchmark.direct_review_template(source, reviews)
            self.assertEqual(
                len(attempts),
                len(json.loads(reviews.read_text())["reviews"]),
            )
            benchmark.report(source, target)
            report = json.loads(target.read_text())
            first["candidate"]["entity_resolutions"] = first_entities
            second["candidate"]["entity_resolutions"] = second_entities
            workspace = Path(directory) / "frozen"
            workspace.mkdir()
            for name in (*benchmark.INPUT_FILES, *benchmark.HARNESS_FILES, "manifest.json"):
                shutil.copy(benchmark.WORKSPACE / name, workspace / name)
            draft_manifest = json.loads((workspace / "manifest.json").read_text())
            draft_manifest.update({"status": "draft", "benchmark_revision": None})
            (workspace / "manifest.json").write_text(json.dumps(draft_manifest))
            with (
                patch.object(benchmark, "WORKSPACE", workspace),
                patch.object(benchmark, "MANIFEST", workspace / "manifest.json"),
            ):
                benchmark.freeze("Test Reviewer", "test network")
                frozen = benchmark.load_json(benchmark.MANIFEST)
                source.write_text(
                    json.dumps(
                        {
                            "manifest_revision": frozen["benchmark_revision"],
                            "attempts": attempts,
                        }
                    )
                )
                benchmark.direct_review_template(source, complete_reviews_path)
                complete_reviews = json.loads(complete_reviews_path.read_text())
                for review in complete_reviews["reviews"]:
                    review["semantic_correct"] = True
                    review["reviewed_by"] = "Test Reviewer"
                complete_reviews_path.write_text(json.dumps(complete_reviews))
                benchmark.report(source, passing_target, complete_reviews_path)
                passing_report = json.loads(passing_target.read_text())
        self.assertEqual({"1", "2", "3"}, set(report["metrics"]["by_run"]))
        self.assertLess(report["metrics"]["overall"]["entity_accuracy"]["value"], 1)
        report["metrics"]["overall"]["plan_validity"]["value"] = None
        self.assertFalse(
            benchmark.gates_for(report["metrics"]["overall"], manifest["thresholds"])[
                "plan_validity"
            ]
        )
        self.assertFalse(report["direct_query_review_complete"])
        self.assertEqual("revise_and_repeat", report["decision"])
        self.assertTrue(frozen["benchmark_revision"].startswith("sha256:"))
        self.assertTrue(passing_report["direct_query_review_complete"])
        self.assertEqual("proceed", passing_report["decision"])


if __name__ == "__main__":
    unittest.main()
