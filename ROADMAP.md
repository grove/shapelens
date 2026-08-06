# ShapeLens roadmap

**Status:** Execution guide for the current reference design  
**Current phase:** Phase 0 — prove the semantic kernel

## Direction

ShapeLens will first prove one claim: trusted SHACL descriptions can become a small set of typed, context-specific query operations whose behavior is correct, inspectable, and deterministic. The project will earn complexity one capability at a time; a feature advances only when its semantics, policy boundaries, evidence, and tests advance together.

This roadmap is milestone-based rather than date-based. [`SHAPELENS_DESIGN.md`](./SHAPELENS_DESIGN.md) explains the architecture and unresolved decisions; the future `SPEC-0.1.md` will define the release contract.

## Phase 0 — prove the semantic kernel

Use one trusted local RDFLib dataset and trusted, IRI-backed node and property shapes. Support direct and inverse predicates, direct-type and IRI target-node Population Selectors, hand-authored connected positive selection and Boolean plans, exact RDF-term matching, deterministic SPARQL, and typed store results.

| Milestone | Deliverable | Exit check |
|---|---|---|
| 0.1 Fixtures and oracle | A small representative dataset, shapes, hand-authored plans, and reviewed reference queries | Cases cover selection, joins, direct/inverse orientation, true and false Boolean results, empty results, and interrupted execution |
| 0.2 Typed semantics | Minimal plan, RDF-term, normalization, selector, and result-envelope types | Invalid, ambiguous, or unsupported inputs fail explicitly; equivalent plans normalize identically |
| 0.3 Compiler and local execution | Deterministic SPARQL compiler plus the RDFLib adapter | Compiled plans execute without accepting raw model- or caller-authored SPARQL |
| 0.4 Differential proof | Automated comparison of compiled results with the reviewed reference queries | All agreed fixtures pass, failures are diagnosable, and the semantics receive human review |

Phase 0 deliberately excludes AI planning, remote databases, absence claims, stable pagination, public blank-node shape identity, generic row-level authorization, documents, plugins, and production scaling.

**Gate:** proceed only if the compiled operations are predictably correct and easier to inspect than direct query construction. Otherwise revise the algebra, selector boundaries, or scope before building the library around them.

## Phase 1 — ship the deterministic 0.1 kernel

Build the trusted shape-source admission process, IRI-backed catalog, Population Selectors, canonical plans and validators, local security profile, portable query representation, RDFLib execution, typed evidence, deterministic answers, and debugging explanations. Extract the accepted behavior into `SPEC-0.1.md`, give every requirement a stable ID, and map it to tests.

**Gate:** release 0.1 when caller-authored plans work end to end, untrusted semantics cannot become executable, result and evidence states cannot contradict each other, and the conformance suite passes. The release does not depend on an AI model.

## Later phases

| Phase | Outcome | Starts when |
|---|---|---|
| 2 — Structured planning | AI selects only approved operations, with mandatory intent coverage and measured question fidelity | The deterministic kernel is stable and the planning benchmark and thresholds are defined |
| 3 — Remote and production | Supported remote stores, explicit protected-data deployment profiles, operational controls, and honest consistency limits | Authorization and remote-store open questions are resolved |
| 4 — Richer semantics | Carefully specified negative queries, Completeness Profiles, validation evidence, and later aggregates | Each feature has agreed truth conditions, evidence, and policy rules |
| 5 — Hybrid and scale | Document retrieval, typed model answering, persistent indexes, blank-node identity profile, caching, and supported plugins | The simpler system demonstrates value and the remaining scale decisions are settled |

## Immediate next action

Create the Phase 0 fixture and differential-test matrix before choosing the full package structure. Those examples are the executable definition of the experiment: they will expose semantic mistakes early and provide the acceptance criteria for the first implementation work.
