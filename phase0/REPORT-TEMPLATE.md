# Phase 0 decision report

**Corpus revision:**
**Fixture revision:**
**Decision date:**
**Decision owners:**

## Corpus integrity

- Frozen question count:
- Application scenarios:
- Shape graphs and styles:
- Rewritten source material:
- Exclusions from the frozen denominator:

## Independent gates

| Gate | Owner | Numerator | Denominator | Threshold | Result | Notes |
|---|---|---:|---:|---:|---|---|
| Compiler correctness | | | | 100% | | |
| Normalization correctness | | | | 100% | | |
| Shape authoring compatibility | | | | manifest | | |
| Direct question coverage | | | | manifest | | |
| Direct + overlay coverage | | | | manifest | | |
| Overlay burden, question median / worst and graph worst | | | | manifest | | |
| Inspectability | | | | manifest | | |
| Evidence completeness | | | | 100% | | |
| Failure honesty | | | | zero false outcomes | | |

## Results by scenario and shape graph

Report coverage, rewriting, overlay burden, and blockers for each scenario and graph. Do not rely only on aggregate results.

## Comparative review

Record seeded defects, responsible-artifact localization, review time, authoring effort, and the corresponding direct-SPARQL or application-code baseline.

## Blocker distribution

List repeated algebra, identity, shape-structure, missing-semantics, and ordinary-code reasons. Recommend a model change only when a blocker repeats across valuable questions.

## Decision

Choose exactly one: proceed to version 0.1; narrow the intended users and repeat with a new corpus revision; revise one evidenced semantic boundary and repeat; stop.

No weighted aggregate may turn a failed gate into a pass.
