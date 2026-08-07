# ShapeLens

ShapeLens is a Python runtime for asking useful questions of RDF data through the semantic structure already captured in SHACL—without handing unrestricted SPARQL to an application caller or a language model. It turns carefully qualified shapes into a small, typed set of graph operations, validates each requested operation in ordinary code, and returns results alongside the evidence needed to understand why each result appeared. The aim is not to make graph querying look magical; it is to make it bounded, inspectable, and easier to trust in applications where the meaning of a query matters as much as the answer.

**Phase 1 is complete.** ShapeLens 0.1 implements the deterministic local `ShapeQueryEngine`, a stable normative specification, typed outcomes and row-support certificates, and a conformance suite that runs every frozen Phase 0 plan in both RDFLib modes. Of the 70 adapter cells, 68 match their reviewed oracles and two requests whose equality term falls outside every declared datatype branch fail closed as `Unsupported`. The frozen product experiment remains recorded in [`phase0/DECISION.md`](./phase0/DECISION.md).

## Install and verify

```console
python3 -m venv .venv
.venv/bin/python -m pip install .
.venv/bin/python -m unittest discover -s tests -v
```

The primary API is `ShapeQueryEngine.execute_plan()`. Applications construct trusted `ShapeSource` descriptors and exact `SemanticQualification` records, inspect the resulting immutable catalog, and submit a caller-authored plan bound to that catalog revision. See [the conformance suite](./tests/test_conformance.py) for complete local examples.

## Why ShapeLens exists

RDF graphs are expressive, but the flexibility that makes them valuable also makes them easy to query incorrectly. A natural-language-to-SPARQL system can invent a predicate that sounds right, point a relationship in the wrong direction, treat a SHACL constraint as though it were an access-control rule, or turn incomplete data into an overly confident answer. Even a valid query can be expensive, hard to review, or impossible to explain clearly after the fact.

ShapeLens addresses a narrower and more practical problem: how can a Python or RDF team expose a helpful graph-query interface when it already maintains SHACL, while keeping the meaning of every operation visible and controlled? Rather than accepting arbitrary query text, ShapeLens is designed to admit only operations derived from trusted, reviewed shape material and application overlays. A caller submits a typed, catalog-bound plan; deterministic code checks it against authorization, policy, and resource limits; and the runtime compiles the accepted plan into a deliberately small SPARQL subset. The result is a typed outcome, not a free-form answer string.

This boundary is particularly important when AI is involved. In ShapeLens’ later architecture, a model may help choose among known lenses and approved operations, but it never becomes the authority for schema meaning, RDF identifiers, access rules, query syntax, execution, or factual support. That work stays in deterministic code, where it can be tested and reviewed.

## What the approach looks like

SHACL is not treated as a complete database schema or as proof that a fact is true. Instead, ShapeLens derives a contextual **Shape Lens** from a primary node shape and, where appropriate, a reviewed application overlay. A lens exposes a small set of permitted operations—such as traversing an approved relationship, matching an exact RDF term, or checking positive existence—and keeps population selection separate from the value contract of a relationship. That separation avoids a common source of subtle graph-query mistakes: assuming that a relationship’s target declaration silently defines the population being queried.

At build time, trusted shape sources are normalized into an immutable, versioned catalog. At query time, a **Bound Query Plan** can refer only to catalog items, supported operations, and validated RDF terms. The runtime validates the plan, applies policy and resource ceilings, executes the resulting query, and records typed evidence. Version 0.1 exposes positive-row support through a Row Support Certificate covering every selector, relationship, filter, and projection.

## Example use cases

**Staffing and skills discovery.** A team with employee, project, and skills data might ask which employees worked on a particular project and have a particular expertise. ShapeLens can express the question as two approved graph relationships attached to one employee variable, with the employee’s public-directory name used only for display. The returned rows can show the specific graph observations that support the project and skill relationships, instead of leaving a reviewer to infer what a generated query meant.

**Regulated or policy-sensitive knowledge systems.** Organizations often need a reliable way to query product, service, research, or case-management graphs without allowing every caller to compose arbitrary joins and filters. ShapeLens is designed to keep authorization scopes, query policy, catalog revision, dataset scope, and execution budgets explicit. It does not make sensitive data safe by itself, but it gives an application a much clearer enforcement and audit boundary than a prompt that happens to contain a schema description.

**A reviewable AI assistant around an RDF graph.** In a later phase, an assistant could retrieve relevant shape lenses and propose a typed plan for a user’s question. The assistant’s proposal would still need to pass the same deterministic validation as a hand-authored plan, and its final wording would be separate from the underlying Query Outcome. This creates room for helpful conversational interfaces without confusing fluent language with query authority or evidence.

**Improving existing SHACL investments.** Teams that already use SHACL for validation often have useful domain language embedded in their shapes, but that material is not automatically a safe query API. ShapeLens explores when those shapes can support a query interface directly, when a small reviewed executable overlay is justified, and when ordinary application code is the more honest solution. An explicit `Unsupported` result is a feature here: it records a real boundary instead of pretending every graph question should be answered by the same mechanism.

## Scope and deliberate limits

The experiment is intentionally conservative. Its fixed execution profile is trusted, in-process RDFLib `Graph` and `Dataset` data with qualified local shape material, explicit population selectors, direct and inverse predicate paths, connected positive queries, exact RDF-term identity, positive existence, and evidence-backed `SELECT` and `ASK` outcomes. It is not intended to be a general SHACL-to-query translator, a replacement for straightforward application code, a general-purpose GraphRAG stack, an authorization solution, or an unrestricted natural-language analytics product.

Capabilities that sound attractive but require stronger semantics—absence claims, aggregation, lexical search, ordered comparisons, stable pagination, remote endpoints, generic row-level authorization, document retrieval, embeddings, and model planning—are deliberately deferred. The project’s position is that these should be added only when their truth conditions, policy boundaries, resource costs, and evidence requirements are specified and tested, not merely because a query engine can render corresponding SPARQL.

## Project status and next steps

Phase 0 tested two independent questions: whether representative SHACL graphs can support valuable application questions without excessive rewriting, and whether the accepted operations compile and produce complete evidence. Its frozen corpus, hand-authored typed plans, reviewed semantic oracles, and eight independent gates all passed. No aggregate score was used to hide a failed trust or correctness boundary.

ShapeLens 0.1 is a packaged Python library. `ShapeQueryEngine` is deterministic and useful on its own; richer retrieval and AI-assisted planning belong to a later `ShapeRAG` composition, not to the runtime contract.

The next phase is not automatic. Structured planning starts only after its fidelity baselines and thresholds are resolved and the deterministic runtime remains stable.

## Learn more

- [Vision](./VISION.md) explains the product thesis, intended users, and non-negotiable trust boundary.
- [Reference design](./SHAPELENS_DESIGN.md) describes the proposed architecture, query algebra, evidence model, and security considerations.
- [Domain vocabulary](./CONTEXT.md) defines terms such as Shape Lens, Population Selector, Bound Query Plan, and Query Outcome.
- [Phase 0 experiment](./PHASE0-EXPERIMENT.md) sets out the validation protocol and decision gates.
- [Phase 0 workspace](./phase0/README.md) contains the corpus templates, fixture conventions, report template, and validation commands.
- [Phase 0 decision](./phase0/DECISION.md) reports every gate, raw denominator, limitation, and the approved next boundary.
- [Roadmap](./ROADMAP.md) describes the milestone-based path from validation to a deterministic runtime and later capabilities.
- [Version 0.1 specification](./SPEC-0.1.md) is the normative behavior and conformance map.
- [Security profile](./SECURITY.md) declares the supported trusted-local boundary.
- [Open questions](./OPEN-QUESTIONS.md) and [future design](./FUTURE-DESIGN.md) keep deferred work outside 0.1.

## License

This project is licensed under the terms in [LICENSE](./LICENSE).
