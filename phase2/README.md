# Phase 2 benchmark workspace

This directory implements the protocol in [`PHASE2-EXPERIMENT.md`](../PHASE2-EXPERIMENT.md). The complete-plan Luna trial has finished with a `revise_and_repeat` decision; see [`DECISION.md`](./DECISION.md). Caller-authored plans remain the supported interface. No replay or oracle-backed fake may authorize `ShapeRAG`.

The dependency-free command is the single path for checking, running, and reporting the benchmark:

```console
.venv/bin/python phase2/benchmark.py validate
.venv/bin/python phase2/benchmark.py freeze --reviewer "NAME" --network "MEASUREMENT NETWORK"
OPENAI_API_KEY=... .venv/bin/python phase2/benchmark.py run --output phase2/results/raw.json
.venv/bin/python phase2/benchmark.py direct-review-template phase2/results/raw.json --output phase2/results/direct-reviews.json
.venv/bin/python phase2/benchmark.py report phase2/results/raw.json --direct-reviews phase2/results/direct-reviews.json --output phase2/results/report.json
```

For a new benchmark revision, the reviewer must inspect every label before running `freeze`; that command records their name, the measurement machine, network and runtime, plus immutable input, harness, prompt, card, and benchmark revisions. Commit that freeze separately. After the model run, a reviewer fills every Boolean and failure category under `reviews` in `direct-reviews.json`; the file is bound to the exact raw-results digest, and the final report refuses to proceed without complete review. Artifact commands refuse to overwrite an existing path, so use a new filename for every revision or rerun.

Label review checks that every material condition and projection appears once, exact entity expectations are correct, supported cases point to an acceptable normalized plan and reviewed oracle, unsupported or ambiguous cases have no answer plan, critical flags are justified, and every provider-visible label or alias is approved. Direct-query review marks an attempt correct only when its syntax, operations, entity terms, conditions, projections, and result semantics match the labelled intent; invented terms, omitted conditions, added restrictions, or unsupported completion fail it even if fixture rows happen to match.

`benchmark.py` rebuilds the pinned catalog, remaps the accepted Phase 0 plans, validates all 28 cases, checks safety-set composition and deterministic candidate recall, shuffles each of three runs, limits the candidate planner to two calls, records end-to-end candidate latency and the three required baselines, and applies every independent gate. The direct-query baseline output is recorded but never executed.
