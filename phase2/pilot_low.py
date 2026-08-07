#!/usr/bin/env python3
"""Run five representative candidate-planner requests."""

from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import time

from rdflib import Graph

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from phase2 import benchmark
from phase2.planning import OpenAIPlanner, ShapeRAG
from shapelens import AuthorizationScope, DatasetScope, QueryPolicy, ShapeQueryEngine


IDS = ("staffing-q01", "ops-q01", "research-q01", "staffing-q06", "safety-ambiguous-priya")


def main() -> None:
    manifest = benchmark.load_json(benchmark.MANIFEST)
    effort = sys.argv[1] if len(sys.argv) > 1 else manifest["decoding"]["reasoning_effort"]
    if not os.environ.get(manifest["model"]["api_key_env"]):
        raise SystemExit(f"missing {manifest['model']['api_key_env']}")
    catalog = benchmark.build_catalog(manifest["catalog_build_id"])
    cards, entities = benchmark.load_cards(catalog), benchmark.load_entities()
    cases = {case["case_id"]: case for case in benchmark.load_json(benchmark.WORKSPACE / "cases.json")}
    planner = OpenAIPlanner(
        os.environ[manifest["model"]["api_key_env"]],
        manifest["model"]["identifier"],
        (benchmark.WORKSPACE / "prompt.txt").read_text(),
        reasoning_effort=effort,
    )
    for case_id in IDS:
        case = cases[case_id]
        engine = ShapeQueryEngine(
            data=Graph().parse(benchmark.ROOT / case["dataset_path"]),
            catalog=catalog,
            authorization=AuthorizationScope.allow_all(manifest["authorization_scope"]),
            dataset_scope=DatasetScope(f"{case_id}:pilot-low"),
            policy=QueryPolicy(**manifest["query_policy"]),
        )
        started = time.monotonic()
        result = ShapeRAG(
            engine,
            planner,
            cards,
            entities,
            candidate_limit=manifest["decoding"]["candidate_limit"],
        ).ask(benchmark.question(case))
        print(json.dumps({
            "case_id": case_id,
            "status": result.status,
            "internal_coverage_valid": result.internal_coverage_valid,
            "calls": result.calls,
            "latency_seconds": round(time.monotonic() - started, 3),
            "reason": result.reason,
        }))


if __name__ == "__main__":
    main()
