# Phase 0 decision

**Decision:** Proceed to the version 0.1 library shell

**Decision date:** 2026-08-07

**Corpus revision:** `sha256:eb5f404fa730af7348b156d15813271925f5175cb973e8a076a97127054d9fa6`

**Fixture revision:** `sha256:c35149a9543e911b05599272819fe4759906df4c8ee37a00eff9da3f2153b458`

**Decision owners:** ShapeLens project, Phase 0 evaluation owner, workforce operations, platform operations, and research information office

All eight independent gates passed. This authorizes the deterministic version 0.1 library work described in the roadmap. It does not validate model planning, external applications, protected data, remote stores, or production authorization.

## Corpus integrity

- 20 project-owned representative questions were frozen before classification across delivery staffing, service operations, and research cataloging.
- Three independently represented SHACL graphs use inline blank-node property shapes; the staffing graph also uses an inverse path.
- No frozen shape graph was rewritten and no question was excluded from the denominator.
- The corpus remains valid under `phase0/validate.py frozen-check`.
- These are internal representative inputs. They are not owner-authored evidence from external applications.

## Independent gates

| Gate | Owner | Numerator | Denominator | Threshold | Result |
|---|---|---:|---:|---:|---|
| Compiler correctness | Phase 0 evaluation owner | 70 matching fixture-mode pairs | 70 | 100% | Pass |
| Normalization correctness | Phase 0 evaluation owner | 2 equivalence/near-miss cases | 2 | 100% | Pass |
| Shape authoring compatibility, structural | Phase 0 evaluation owner | 3 graphs | 3 | ≥70% | Pass |
| Shape authoring compatibility, compiler-backed | Phase 0 evaluation owner | 3 graphs | 3 | ≥70% | Pass |
| Direct question coverage | Phase 0 evaluation owner | 14 questions | 20 | ≥50% | Pass: 70% |
| Direct + overlay coverage | Phase 0 evaluation owner | 18 questions | 20 | ≥70%, in at least 2 scenarios | Pass: 90%, 2 scenarios |
| Overlay burden | Phase 0 evaluation owner | median 1 / question worst 1 / graph worst 4 | 4 overlay questions / 1 graph | ≤1 / ≤3 / ≤10 | Pass |
| Inspectability | Phase 0 evaluation owner | 5 correct ShapeLens localizations | 5 | 100%; ≥5 cases; median time ratio ≤1.0 | Pass: ratio 0.992 |
| Evidence completeness | Phase 0 evaluation owner | 78 complete positive-row maps | 78 positive rows | 100% | Pass |
| Failure honesty | Phase 0 evaluation owner | 0 false answers or false `NoMatch` outcomes | 8 injected failure/admission cases | 0 | Pass |

No weighted score was used. Every non-negotiable gate and every predeclared product threshold passed independently.

## Scenario and graph results

| Scenario | Direct | Overlay | Blocked | Combined coverage | Compiler-backed accepted questions |
|---|---:|---:|---:|---:|---:|
| Delivery staffing | 7 | 0 | 0 | 7/7 (100%) | 7/7 in both modes |
| Service operations | 7 | 0 | 0 | 7/7 (100%) | 7/7 in both modes |
| Research cataloging | 0 | 4 | 2 | 4/6 (66.7%) | 4/4 in both modes |

All three graphs passed the no-rewrite rule and all accepted questions linked to each graph matched their reviewed oracle in RDFLib `Graph` and `Dataset` modes. Research cataloging did not individually reach the 70% combined threshold; the frozen rule requires at least two scenarios to reach it, and both staffing and operations did.

The four research overlays each add one reviewed scalar-projection declaration. Their median and worst per-question burden is 1; the graph total is 4. Descriptive labels and aliases are excluded.

## Semantic and failure proof

The 35 executable fixtures comprise 18 accepted corpus questions and 17 focused semantic cases. Each ran in both local adapter modes. The focused cases cover direct and inverse predicates, direct-type and IRI target-node selectors, exact IRI/datatype/lexical/language identity, positive and empty `SELECT`, true and false `ASK`, connected joins, one entity with two lenses, and required scalar fields.

The classification records intentionally retain `qualification_status: pending` as the milestone 0.0b snapshot. The pinned final catalog and fixture manifest carry the later trusted/qualified execution proof; changing the early records would erase the experiment sequence.

Equivalent local IDs/orderings produced the same plan digest and query; the near miss remained distinct. Blank-node-backed property keys survived catalog artifact reload, changed on rebuild, and failed closed when stale. Every positive row or true Boolean witness covered its complete selector/edge/filter/projection atom set exactly once. Empty and false results had no row support.

Cancellation, timeout, malformed result, byte limit, interrupted sentinel, stale catalog keys, untrusted sources, and unqualified semantics all failed or were rejected. None became an answer or `NoMatch`.

## Comparative review

Two distinct internal evaluator agents reviewed one artifact at a time with monotonic timestamps. Modalities were assigned to different reviewers and counterbalanced. Both ShapeLens and SPARQL localized all five seeded defects.

| Defect | ShapeLens seconds | SPARQL seconds | Ratio | Both correct |
|---|---:|---:|---:|---|
| Relationship direction | 6.885 | 6.605 | 1.043 | Yes |
| Exact RDF term | 8.060 | 6.581 | 1.225 | Yes |
| Omitted condition | 5.286 | 5.329 | 0.992 | Yes |
| Wrong population | 5.356 | 5.564 | 0.963 | Yes |
| Wrong property | 4.927 | 5.923 | 0.832 | Yes |

The median of the five paired ratios is 0.992. The raw ledger, answer key, timestamps, limitations, and artifact hashes are in [`results/inspectability.json`](./results/inspectability.json). This is an internal AI-assisted evaluator proxy, not external-user or human-usability evidence.

## Blockers

Two research questions remain outside the Phase 0 algebra:

- `research-q04`: absence/negation over deposit status.
- `research-q06`: grouped distinct publication counts by department.

Each blocker category occurs once. Phase 0 therefore provides no frequency evidence for adding either operator next. There were no shape-blocked or ordinary-code questions.

## Reproduce

From the repository root with the pinned dependency installed:

```console
python3 phase0/validate.py frozen-check
.venv/bin/python phase0/evaluate.py
PYTHONPATH=phase0 .venv/bin/python phase0/run_fixtures.py run
.venv/bin/python -m unittest discover -s phase0 -v
```

The full fixture command verifies the frozen revisions, materialized hand-authored plans, semantic-oracle equivalence, evidence maps, catalog lifecycle, failure outcomes, artifact hashes, inspectability arithmetic, and final aggregate pass.

## Decision boundary

Proceed to the deterministic version 0.1 shell. Keep absence, aggregation, model planning, remote execution, portable blank-node identity, documents, plugins, authorization frameworks, and production scaling out until separately justified and specified. The post-Phase-0 specification/security/design split is version 0.1 entry work, not evidence retrofitted into this experiment.
