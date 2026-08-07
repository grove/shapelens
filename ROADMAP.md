# ShapeLens roadmap

**Status:** Execution guide for the current reference design  
**Current phase:** Phase 1 complete — deterministic version 0.1 runtime

## Direction

ShapeLens first tests whether representative SHACL graphs can support a valuable, inspectable query interface without excessive rewriting. Only then does it prove that the accepted operations compile correctly. The product hypothesis is defined in [`VISION.md`](./VISION.md), the experiment and separate gates in [`PHASE0-EXPERIMENT.md`](./PHASE0-EXPERIMENT.md), and the candidate architecture in [`SHAPELENS_DESIGN.md`](./SHAPELENS_DESIGN.md).

This roadmap is milestone-based rather than date-based. Complexity is earned one capability at a time; semantics, policy boundaries, evidence, and tests advance together.

The reference design is frozen as a decision backlog during Phase 0. New design work is justified only by an observed corpus blocker, a failed semantic fixture, or a necessary clarification of the experiment protocol.

## Phase 0 — validate usefulness and the semantic kernel

| Milestone | Deliverable | Exit check |
|---|---|---|
| 0.0a Corpus freeze | Freeze 20–30 project-owned representative questions, shape graphs, application baselines, metric formulas and owners, exclusions, and product thresholds before classification or plan design | At least three materially different application scenarios are represented and the dependency-free `freeze-check` passes with no classifications present; external owner validation is not claimed |
| 0.0b Classification and product gate | Classifications, structural no-rewrite compatibility, overlay/rewrite burden, and blocker distribution against the frozen denominator | Every in-scope question is classified; the direct, combined, compatibility, and burden thresholds pass before semantic-spike work begins |
| 0.1 Fixtures and oracle | Local RDFLib datasets, hand-authored plans, reviewed semantic-oracle queries, qualification fixtures, and structural fixtures kept separate from the product-question corpus | Cases cover selection, joins, multi-lens use of one entity, blank-node Catalog-Local Keys, direct/inverse orientation, Boolean and empty results, atom support, and interruption |
| 0.2 Typed semantics | Minimal Entity Variable, Selector Use, Lens Use, RDF-term, normalization, result-record, and internal Atom-Witness Map types | Invalid, ambiguous, or unsupported inputs fail explicitly; declared equivalent plans normalize identically and near misses remain distinct |
| 0.3 Compiler and local execution | Deterministic SPARQL compiler plus the RDFLib adapter | Compiled plans execute without accepting raw model- or caller-authored SPARQL |
| 0.4 Differential and inspection proof | Automated solution-mapping comparison, Atom-Witness Map validation, compiler-backed compatibility, seeded-defect review, and failure-honesty cases | Every non-negotiable gate passes and each predeclared product threshold is met |

Phase 0 is fixed to in-process RDFLib `Graph` and `Dataset` execution with trusted local data and explicit fixture inputs for Shape Source Trust and Semantic Qualification. It makes no protected-data or generic authorization claim and performs no network I/O. It deliberately excludes AI planning, remote databases, absence claims, stable pagination, portable blank-node identity, documents, plugins, and production scaling. It permits revision-scoped Catalog-Local Keys for blank-node shapes because runtime usability and cross-revision identity are separate questions.

**Gate:** use the eight independent gates in `PHASE0-EXPERIMENT.md`: compiler correctness, normalization correctness, shape authoring compatibility, question coverage, overlay burden, inspectability, evidence completeness, and failure honesty. No aggregate score or compiler-only success can authorize Phase 1.

## Phase 1 — ship the deterministic 0.1 runtime (complete)

Build `ShapeQueryEngine` around the accepted kernel: qualified source admission, the immutable catalog, Population Selectors, canonical caller-authored plans, validation, the local security profile, RDFLib execution, row support certificates, typed Query Outcomes, deterministic result rendering, and debugging explanations. The release does not depend on a model and does not claim question-to-plan fidelity.

After Phase 0, split the reference design by responsibility: `SPEC-0.1.md` contains only normative, tested behavior with stable requirement IDs; `SECURITY.md` declares supported trust and deployment profiles; `docs/adr/` records accepted trade-offs; `OPEN-QUESTIONS.md` holds unresolved decisions; and `FUTURE-DESIGN.md` holds later architecture. Outside `SPEC-0.1.md`, RFC-style words are informative only.

**Gate:** release 0.1 only when caller-authored plans work end to end, untrusted or unqualified semantics cannot become executable, every positive row maps its complete Row Atom Set exactly once, result and evidence states cannot contradict each other, and the conformance suite passes.

## Candidate later phases

The sequence below is provisional. Phase 0 blocker frequency and application value determine which semantic capability is considered next; richer traversal is not an automatic next step.

| Phase | Outcome | Starts when |
|---|---|---|
| 2 — Structured planning | AI selects only approved operations, with mandatory intent coverage and a separate human-labelled planner benchmark | The deterministic runtime is stable and planner baselines and thresholds are defined |
| 3 — Remote and production | Supported remote stores, explicit protected-data deployment profiles, operational controls, and honest consistency limits | Authorization and remote-store open questions are resolved |
| 4 — Richer semantics | Carefully specified negative queries, Completeness Profiles, validation evidence, and later aggregates | Each feature has agreed truth conditions, evidence, and policy rules |
| 5 — Hybrid and scale | Add document retrieval, persistent indexes, portable blank-node identity, caching, and supported plugins to the ShapeRAG composition introduced in Phase 2 | The graph-only composition demonstrates value and the remaining retrieval and scale decisions are settled |

## Immediate next action

Keep version 0.1 stable and use [`OPEN-QUESTIONS.md`](./OPEN-QUESTIONS.md) to resolve the planner benchmark and fidelity thresholds before Phase 2 begins. Do not add model planning to `ShapeQueryEngine`.
