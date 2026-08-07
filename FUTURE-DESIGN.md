# ShapeLens future design

Version 0.1 ends at deterministic local execution and typed evidence. The earlier [reference design](./SHAPELENS_DESIGN.md) remains an informative research record; future work is gated by [open questions](./OPEN-QUESTIONS.md), a focused specification change, and conformance evidence.

## Structured planning

A later `ShapeRAG` composition can retrieve schema, resolve entities, and propose the same bound plan type. It needs an explicit planner, question-to-plan coverage records, a human-labelled fidelity benchmark, and honest unsupported or ambiguous outcomes. A model still receives no raw SPARQL tool or authority over source trust, qualification, policy, or authorization.

## Remote and production execution

Remote stores require a separate asynchronous adapter profile covering credentials, protocol parsing, bytes, deadlines, cancellation, retries, graph semantics, entailment, revisions, consistency, operational limits, and at least two materially different implementations. Protected-data claims wait for tested authorization and tenancy profiles.

## Richer semantics

Negation and absence arrive only with named Completeness Profiles. Aggregation needs explicit operands, grouping, distinctness, empty-input behavior, and evidence. Lexical search, ordering, stable pagination, unions, and richer paths each need portable truth conditions, resource rules, and row-support semantics.

## Hybrid retrieval and scale

Documents, persistent indexes, embeddings, caches, portable blank-node identity, and plugins remain deferred. Each adds a separate identity, authorization, retention, consistency, or isolation boundary and should enter only after the deterministic runtime shows a concrete need.
