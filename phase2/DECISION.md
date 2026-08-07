# Phase 2 planner report and decision

**Date:** 2026-08-07

**Decision:** Revise and repeat only as a constrained template-selection experiment

**Current supported interface:** Caller-authored plans executed by `ShapeQueryEngine`

## Executive summary

The deterministic ShapeLens runtime remains sound, but `gpt-5.6-luna` has not shown that it can reliably author the complete low-level planning envelope. It repeatedly produced plausible-looking JSON that violated the contract: missing coverage atoms, invented or out-of-context card references, malformed RDF terms, incorrect entity coverage, and untrusted lens use.

The validator did the right thing by rejecting these outputs. There were no accepted false completions, but this safety came from deferring almost everything rather than from useful planning accuracy. The full benchmark achieved zero faithful completions for the 60 supported attempts, and three later five-case pilots achieved only one supported completion out of 12 opportunities. Every pilot attempt used the retry.

Do not weaken the validator and do not run another full benchmark with Luna authoring complete plans. Keep caller-authored plans as the supported interface. If model planning is pursued, start a new revision in which Luna only selects a reviewed plan template and supplies a few values; ordinary Python must resolve entities and construct the complete plan and coverage record.

This narrower design could become useful for graph-grounded retrieval and a later local GraphRAG flow. It is not, by itself, a general-purpose or Microsoft-style GraphRAG system.

## What was built

Phase 2 produced:

- a frozen 28-case benchmark: 20 representative cases and eight safety cases;
- reviewed planner cards and exact local entity labels;
- candidate retrieval, a bounded OpenAI planner adapter, one structured-output retry, coverage validation, and delegation to the unchanged `ShapeQueryEngine`;
- three baselines: always defer, flat catalog, and offline direct query;
- raw-attempt, direct-review, metric, gate, latency, and cost reporting;
- tests for candidate retrieval, entity ambiguity, provider handles, retry behavior, coverage validation, and report gates;
- a five-case pilot command for cheap iteration before a full benchmark.

The experiment did not add model planning to `ShapeQueryEngine`, accept raw model-authored SPARQL, widen the query algebra, weaken source qualification, or weaken authorization and validation.

## Full Luna benchmark

The retained diagnostic benchmark used `gpt-5.6-luna` with reasoning effort `none`. It ran 28 cases three times, for 84 candidate attempts. Its generated report made the decision `revise_and_repeat`.

| Measure | Result | Required |
|---|---:|---:|
| Faithful automation coverage | 0/60 (0%) | at least 80% overall |
| Critical faithful coverage | 0/15 (0%) | 100% |
| Internal coverage | 12/84 (14.3%) | 100% |
| Entity accuracy | 7/99 (7.1%) | 100% |
| Unsupported precision | 18/84 (21.4%) | 100% |
| Unsupported recall | 18/18 (100%) | 100% |
| False completions | 0 | 0 |
| Maximum model calls | 2 | at most 2 |
| p50 latency | 8.54 seconds | reported only |
| p95 latency | 11.39 seconds | at most 10 seconds |
| Mean provider cost | USD 0.00386 | at most USD 0.05 |
| Candidate-context token reduction | 41.8% | comparison only |
| Direct-query baseline accuracy | 37/84 (44.0%) | comparison only |

Only four of the 15 independent gates passed: unsupported recall, zero false completions, model-call limit, and cost. Nineteen attempts exceeded the latency threshold. Seventy-two attempts were rejected for invalid internal coverage, and all 60 supported attempts became false deferrals.

The raw attempts are in [`results/raw-none.json`](./results/raw-none.json), the completed direct-query reviews are in [`results/direct-reviews-none.json`](./results/direct-reviews-none.json), and the generated report is in [`results/report-none.json`](./results/report-none.json).

The exact matching manifest snapshot for benchmark revision `sha256:875482ff07c9bc5878227129c44abd66af97c9a8d6f19084f31f3731fd9dbbd8` was not retained. The generated report records the model, prompt, card, catalog, provider-transmission, price, machine, and artifact revisions, so the run remains useful diagnostic evidence, but this missing manifest is an additional reason it cannot authorize implementation.

## Subsequent five-case pilots

After the full run, three new prompt/serialization revisions were tested only against four supported cases and one ambiguous-entity safety case.

| Pilot | Supported completed | Safety correct | Retries | Worst latency | Typical rejection |
|---|---:|---:|---:|---:|---|
| A | 1/4 | 0/1 | 5/5 | 10.37 s | card outside context; omitted entity or projection atoms |
| B | 0/4 | 1/1 | 5/5 | 6.12 s | wrong coverage owner; untrusted lens; invalid planned coverage |
| C | 0/4 | 0/1 | 5/5 | 6.21 s | malformed RDF term; missing result extent; card outside context |

Across the pilots, Luna completed one of 12 supported opportunities and handled one of three ambiguous-entity opportunities correctly. All 15 attempts needed the retry. The faster later pilots therefore did not represent a reliability improvement.

## What the failures mean in practice

The current request asks Luna to do several tightly coupled jobs at once:

1. interpret the question;
2. identify every material intent;
3. select only cards present in the supplied context;
4. resolve graph roles and entities;
5. construct a typed graph plan with opaque identifiers;
6. create an exact bidirectional coverage proof for that plan.

Luna usually understood the broad question. It was unreliable at the bookkeeping needed to make that understanding safe and executable. A retry often changed the error rather than converging on a valid plan. Prompt changes and shorter opaque handles moved failures around without removing the underlying problem.

This does not show that Luna is useless for ShapeLens. It shows that complete low-level plan authorship is too large and brittle a contract for this model. Cost was comfortably within budget; correctness was the blocker.

## Practical value of a narrower planner

A constrained planner would act like a safe semantic menu over the graph. It would fit recurring, closed-domain questions such as:

- employees by project and expertise;
- incidents by service and severity;
- publications by contributor, grant, venue, or year;
- exact entity lookups and explicit ambiguity handling.

Its limitation would be intentional: a new relationship pattern requires a reviewed template. Unsupported questions remain unsupported instead of being approximated with an invented query.

The model output should be approximately this small:

```json
{
  "status": "selected",
  "template_id": "employees_by_project_and_skill",
  "slots": {
    "project": "Project Atlas",
    "skill": "artificial intelligence"
  }
}
```

Local code would own entity resolution, slot types, card keys, plan atoms, coverage, authorization, and final validation.

## GraphRAG fit

The narrower design would be useful as the trusted graph-retrieval layer of a GraphRAG system:

```text
question
  -> template selection and local entity resolution
  -> validated ShapeLens graph query
  -> answer entity IDs and linked document IDs
  -> retrieval restricted to those documents
  -> answer synthesis with graph and text evidence kept distinct
```

That supports local, entity-centered questions. For example, ShapeLens could identify employees matching a project and skill, return their linked report IDs, and allow a document retriever to find passages about project risks only in those reports. This follows the late-fusion design in [`SHAPELENS_DESIGN.md`](../SHAPELENS_DESIGN.md#14-hybrid-graph-and-document-retrieval).

It does not implement Microsoft GraphRAG's broader pipeline. Microsoft GraphRAG extracts entities and relationships from unstructured documents, creates graph-community reports, combines graph data with text chunks for local search, and uses community summaries for global corpus questions. See the official [indexing methods](https://github.com/microsoft/graphrag/blob/main/docs/index/methods.md) and [query overview](https://microsoft.github.io/graphrag/query/overview/).

ShapeLens should therefore describe this near-term capability as **graph-grounded retrieval** or **graph-guided RAG**, not as a complete general-purpose GraphRAG stack.

## Proposal

### 1. Preserve the current boundary

- Keep `ShapeQueryEngine.execute_plan()` and caller-authored plans as the supported product path.
- Retain the unchanged validator and all current trust, qualification, policy, and evidence rules.
- Treat the existing complete-plan Luna adapter as experimental evidence, not a product interface.
- Do not run the current 84-attempt benchmark again.

### 2. Create one new template-selection revision

- Derive a small template registry from the already accepted Phase 0 plans; add no new query algebra.
- Resolve exact labels and ambiguity locally before or immediately after model selection.
- Give Luna template descriptions and slot definitions, not catalog keys or a plan schema.
- Allow only `selected`, `unsupported`, or `ambiguous` output plus template ID and slot values.
- Compile the selected template deterministically into the existing `BoundQueryPlan`.
- Generate coverage mechanically from the template and filled slots.
- Pass the result through the unchanged validator and engine.
- Add no dependency, answer synthesizer, vector store, or document pipeline in this revision.

### 3. Gate it with the same five-case pilot

Run only the existing pilot first. Continue only if:

- all four supported cases complete with the correct plan and result;
- the ambiguous Priya case returns `ambiguous`;
- there are no structural validator rejections or false completions;
- no attempt exceeds two calls;
- p95 pilot latency is at most ten seconds.

If the pilot fails, stop model planning for this release and retain caller-authored plans. If it passes, freeze a new manifest and run the full 28-case, three-run benchmark once. The existing independent fidelity gates still apply.

### 4. Add one GraphRAG vertical slice only after planning passes

Use a single reviewed query template that returns entity and linked-document IDs, connect it to an existing document retriever, and require citations that label graph-backed and text-only claims separately. Do not add community detection, global search, or a general GraphRAG framework until measured user demand requires corpus-wide synthesis.

## Final decision

The complete-plan Luna experiment does not proceed. The only authorized next AI-planning work is a new, narrower template-selection pilot. Phase 3 remains closed, document retrieval remains deferred, and caller-authored plans remain the supported interface until a new frozen revision passes every gate.
