# ShapeLens vision

## Product thesis

ShapeLens should earn the right to become a larger retrieval-and-answering system. Its initial product is a deterministic, typed SHACL-derived query runtime for RDF applications: callers submit a bounded plan, ordinary code validates and compiles it, and the runtime returns results with atom-level support. A language model may later choose among approved operations, but it is never the query authority.

The first intended users are Python and RDF teams that already maintain SHACL and need read-only positive graph queries to be auditable, policy-constrained, and easier to review than application-specific SPARQL. Version 0.1 is not aimed at arbitrary natural-language analytics, complete SHACL-to-query translation, general GraphRAG, or replacing straightforward application code.

Phase 0 exercises only trusted local RDFLib data and makes no protected-data or production-authorization claim. Broader security profiles require separate specifications and tests after the product and semantic gates pass.

## Value hypothesis

The project proceeds beyond the semantic spike only if representative applications show all three of the following:

1. existing SHACL graphs produce useful query operations without disproportionate rewriting or executable overlay material;
2. the small algebra covers an agreed share of valuable questions and returns honest `Unsupported` outcomes for the rest;
3. reviewers can trace a result or defect to the responsible entity, lens use, selector, plan atom, and evidence witness more reliably than with reviewed direct SPARQL.

Compiler legality and product usefulness are separate gates. Neither may compensate for failure of the other, and no aggregate end-answer score is used to hide a weak trust boundary.

## Product layers

`ShapeQueryEngine` is the initial deterministic runtime. It admits qualified shape material, validates caller-authored plans, compiles the accepted algebra, executes it, and returns typed Query Outcomes and evidence. It does not claim that caller-authored plans faithfully represent accompanying prose.

`ShapeRAG` is a later composition that may add schema retrieval, entity resolution, model planning, document retrieval, and answer synthesis around that runtime. It exists only when the configured components justify the name; it does not define the version 0.1 contract.

## Non-negotiable boundary

Models choose among approved semantic operations. Deterministic code owns source admission, semantic qualification, RDF terms, identifiers, authorization, policy, compilation, execution, evidence construction, and outcome validation.

## Document lifecycle

Phase 0 is complete, but [`SHAPELENS_DESIGN.md`](./SHAPELENS_DESIGN.md) remains a non-normative reference design and decision backlog until accepted behavior is extracted into the version 0.1 documents. Its RFC-style words express proposals only.

Phase 0 did not stabilize the package layout, public API, detailed evidence taxonomy, or future architecture. Observed coverage, burden, blocker frequency, and comparative value determine later priorities rather than the numeric order of the future roadmap.

After Phase 0, accepted and observed behavior is extracted into `SPEC-0.1.md` with stable requirement IDs and test mappings. Security profiles move to `SECURITY.md`; accepted trade-offs move to `docs/adr/`; unresolved decisions move to `OPEN-QUESTIONS.md`; and later architecture moves to `FUTURE-DESIGN.md`. Normative RFC language belongs only in the specification.
