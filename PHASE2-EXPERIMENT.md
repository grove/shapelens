# Phase 2 experiment

**Status:** Complete-plan Luna trial finished with `revise_and_repeat`; only a new constrained template-selection revision is proposed

**Purpose:** Decide whether structured model planning adds enough faithful automation to justify a `ShapeRAG` composition around the stable 0.1 runtime

## Experiment boundary

Phase 2 tests question-to-plan fidelity. A planner may select only provider-approved cards for already qualified catalog operations and must return the existing catalog-bound plan type plus an intent-coverage record. `ShapeQueryEngine` remains the sole validator, compiler, executor, and evidence producer.

This experiment does not add natural-language handling to `ShapeQueryEngine`, widen the 0.1 algebra, generate unrestricted query text in the product path, promote hints into executable semantics, or add answer synthesis, documents, remote stores, protected-data claims, caches, or plugins. A successful run authorizes only the smallest graph-only `ShapeRAG` planning composition.

## 1. Freeze the benchmark before building the planner

Reuse the frozen Phase 0 corpus revision and its reviewed artifacts:

- all 20 representative questions across staffing, service operations, and research cataloging;
- the 18 accepted hand-authored plans and semantic oracles as answerable cases;
- `research-q04` and `research-q06` as required `unsupported` cases because absence and aggregation remain outside 0.1;
- the pinned 0.1 catalog, authorization scope, query policy, dataset fixtures, and expected Query Outcomes.

Add a focused safety set of at least eight cases: two ambiguous entity labels, two unknown entities, two questions mixing supported and unsupported intent, and two multi-condition questions whose partial plan would change the answer. These cases test failure honesty and never increase the representative-product numerator.

Before any model run, freeze a manifest containing:

- benchmark and catalog revisions;
- every question and human-reviewed label record;
- model provider and exact model identifier;
- prompt and card-serialization revisions;
- decoding settings, candidate limits, one optional structured-output retry, and a maximum of two model calls per attempt;
- provider-transmission classification for every field;
- metric owners, thresholds, price source and date, and the machine used for latency measurement.

Run every case three times in shuffled order. The planner receives no oracle plan, expected plan digest, baseline query, expected result, or prior attempt. A changed prompt, model, label, threshold, or candidate policy creates a new benchmark revision and retains earlier results.

This remains an internal representative benchmark. It does not claim external application-owner validation or generalization beyond the frozen questions and focused safety cases.

The inputs and dependency-free validation, run, and report commands live in [`phase2/`](./phase2/). The current outcome and next proposal are recorded in [`phase2/DECISION.md`](./phase2/DECISION.md); no `proceed` decision has been made.

## 2. Human labels

Each case records:

- material intent items for requested populations, relationships, conditions, projections, Boolean intent, and Result Extent;
- the required Shape Lenses, Population Selectors, Property Lenses, Value Contract Branches, and entity mentions;
- acceptable entity bindings or the required `ambiguous` or `unsupported` disposition;
- one or more acceptable normalized plan equivalence classes for answerable cases;
- the reviewed semantic oracle and expected outcome class;
- whether the case is representative or safety-only, and whether it is critical.

Intent items use semantic roles and catalog identities, not wording copied from a prompt. Every material question condition must have exactly one disposition. Every planner-authored restriction must point back to one material intent item. Authorization and Query Policy constraints are trusted runtime inputs and are not planner intent.

## 3. Fixed experiment answers to the Phase 2 open questions

These are conservative experiment controls, not broader production claims:

| ID | Experiment answer |
|---|---|
| OQ-001 | Compare the candidate with the three baselines below and apply the independent gates in section 6. No weighted score is allowed. |
| OQ-009 | Ontology and sampled-data hints are never promoted automatically. Reviewed descriptive aliases may affect retrieval; executable behavior still requires the existing trust and Semantic Qualification path. |
| OQ-010 | Entity binding is exact over normalized, authorized labels and reviewed aliases. One match binds, no match is `unsupported`, and multiple matches are `ambiguous`. Similarity ranking may order clarification choices but cannot silently bind an entity. |
| OQ-013 | An external planner may receive only the authoritative question and fields explicitly marked `provider_allowed` from authorized planner cards. Raw RDF data, evidence, source documents, hidden authorization metadata, policy reasons, and non-approved labels stay local. |
| OQ-017 | Phase 2 adds no model claim checker and no new public proof-strength label. It returns the validated 0.1 Query Outcome and deterministic rendering; answer synthesis remains deferred. |

Any less conservative behavior requires a new benchmark revision and an ADR before implementation.

## 4. Baselines

Use the same model, question order, provider-approved catalog material, and run count for model baselines.

| Baseline | Purpose |
|---|---|
| `always_defer` | Reports `unsupported` for every question; establishes that perfect failure precision without useful coverage has no product value. |
| `flat_catalog` | Produces the same structured envelope from all authorized cards, without schema retrieval or model-driven entity resolution; isolates the value and cost of candidate selection. |
| `direct_query` | Produces SPARQL from the same approved schema facts for offline comparison only; measures syntax, result equivalence, invented terms, omitted conditions, and added restrictions. It is never executed through the product API or treated as evidence-capable. |

The reviewed hand-authored plan is the semantic oracle and human fallback, not an automation baseline.

## 5. Measurements

Report every metric overall, by scenario, by question, by run, and separately for representative and safety cases.

| Metric | Measure |
|---|---|
| Intent extraction recall | Gold material intent items represented by the planning envelope divided by all gold material intent items |
| Intent restriction precision | Planner-authored semantic restrictions justified by a gold intent item divided by all planner-authored semantic restrictions |
| Internal coverage | Extracted material intent items with exactly one disposition and planner restrictions with exactly one intent source |
| Lens-retrieval recall | Required authorized catalog cards present in the candidate context divided by all required cards |
| Entity accuracy | Entity mentions given the exact gold binding or required ambiguous/unsupported disposition |
| Plan validity | Answerable envelopes accepted by the unchanged 0.1 validator after at most one structured-output retry |
| Faithful automation coverage | Supported attempts producing an accepted, semantically correct plan divided by all supported attempts |
| Completed-plan semantic precision | Semantically correct accepted plans divided by all accepted plans |
| Unsupported precision and recall | Correct unsupported dispositions over predicted and gold unsupported cases, reported separately |
| False completion count | Accepted plans or rendered outcomes that omit intent, add a user-semantic restriction, bind an ambiguous or unknown entity, or answer unsupported intent |
| Latency and cost | End-to-end p50/p95 latency, model calls, input/output tokens, and provider cost per attempt using the frozen price source |

A plan is semantically correct only when it belongs to a labelled acceptable equivalence class and its execution matches the reviewed oracle. Matching fixture rows alone cannot excuse an omitted or invented condition.

## 6. Independent gates

| Gate | Threshold |
|---|---:|
| Intent extraction recall | 100% for completed plans |
| Intent restriction precision | 100% for completed plans |
| Internal coverage | 100% |
| Lens-retrieval recall | 100% for every completed plan |
| Entity accuracy | 100% for every completed plan or explicit disposition |
| Plan validity | 100% of plans counted as completed |
| Faithful automation coverage | At least 80% of supported attempts overall and 100% of critical attempts |
| Completed-plan semantic precision | 100% |
| Unsupported precision | 100% |
| Unsupported recall | 100% |
| False completion count | Zero |
| Model calls | At most two per attempt, including one structured-output retry |
| Performance | p95 at most 10 seconds and mean provider cost at most USD 0.05 per attempt under the frozen measurement conditions |

Also report candidate-context token reduction against `flat_catalog` and semantic accuracy against `direct_query`; neither comparison can compensate for a failed gate. Cost and latency thresholds may be made stricter before the manifest freezes, never relaxed after results are known.

## 7. Decision

Proceed to a minimal Phase 2 implementation only when every gate passes in all three runs and no scenario has a false completion. The implementation may contain only:

- provider-approved planner-card serialization;
- deterministic candidate retrieval;
- exact label and alias entity resolution with explicit ambiguity;
- typed intent items and bidirectional coverage validation;
- one explicit planner adapter with one bounded structured-output retry;
- evaluation records needed to reproduce the passing benchmark;
- a graph-only `ShapeRAG` composition that delegates accepted plans to `ShapeQueryEngine` and returns its deterministic outcome.

If a gate fails, keep caller-authored plans as the supported interface. Fix a deterministic defect if one caused the failure; otherwise narrow the proposed planner or stop. Do not widen the algebra, add answer synthesis, or tune on failed evaluation cases and report the same revision as held-out evidence.

## 8. Required report

Publish the benchmark revision, model and prompt revisions, provider-transmission inventory, all raw attempts, metric numerators and denominators, baseline results, latency and cost conditions, failures by category, and exactly one decision: proceed with the minimal composition, revise and repeat under a new benchmark revision, or stop.
