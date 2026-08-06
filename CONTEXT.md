# ShapeLens

ShapeLens is the domain concerned with turning contextual SHACL descriptions into bounded graph-query operations and evidence-backed answers. This glossary defines the project’s core domain language without prescribing implementation details.

## Semantic views

**Shape Lens**:
A contextual semantic view compiled from one primary SHACL node shape with a supported target or a Trusted Overlay that supplies an application target. It defines the meanings and query operations available in that context.
_Avoid_: Class schema, universal shape, security view

**Property Lens**:
A contextual property within a Shape Lens that has a path, value contract, and permitted query operations.
_Avoid_: Field, predicate wrapper

**Value Contract**:
A branch-preserving description of the RDF terms accepted by a Property Lens.
_Avoid_: Python type, database column type

**Affordance**:
A query operation that a Property Lens is permitted to expose, such as equality, traversal, or existence.
_Avoid_: Capability, tool

**Lens Origin**:
The authority category of a lens statement: normative shape, trusted overlay, ontology hint, or sampled hint.
_Avoid_: Confidence score, provenance

**Trusted Overlay**:
An application-approved addition that gives a shape explicit query meaning or metadata not supplied by the shapes graph.
_Avoid_: Inference, hint, prompt instruction

## Catalog and planning

**Shape Catalog**:
An immutable, versioned collection of Shape Lenses, Property Lenses, source references, and their join relationships.
_Avoid_: Registry, index

**Catalog Revision**:
One immutable version of a Shape Catalog and all trusted inputs that determine its meaning.
_Avoid_: Build timestamp, deployment version

**Shape Registry**:
The lookup view over one Shape Catalog revision.
_Avoid_: Catalog, search index

**Shape Index**:
A retrieval structure that ranks Shape Lenses for a question.
_Avoid_: Catalog, registry, document index

**Join Graph**:
The directed relationships among Shape Lenses established by their Property Lenses.
_Avoid_: Data graph, knowledge graph

**Bound Query Plan**:
A typed, schema-bound expression of a question that refers only to known lenses, operations, and validated RDF terms.
_Avoid_: SPARQL, prompt, query string

**Authorization Scope**:
The trusted boundary describing which semantic operations and data a requester may use.
_Avoid_: Shape Lens, prompt role, query preference

**Query Policy**:
The safety ceiling that limits query forms, complexity, resource use, and evidence behavior independently of authorization.
_Avoid_: Authorization Scope, planner instruction

**Run Context**:
The pinned catalog, authorization, policy, data scope, budget, and trace identity under which one question is handled.
_Avoid_: Prompt context, global configuration

## Results and truth conditions

**Dataset Scope**:
The graph selection, entailment regime, revision, consistency, and completeness assumptions under which a query result has meaning.
_Avoid_: Database, endpoint

**Evidence Item**:
A typed observation that states both what the system observed and the conditions under which it was observed.
_Avoid_: Fact, citation

**Evidence Packet**:
The bounded, versioned collection of evidence and limitations supplied to answer rendering.
_Avoid_: Model context, result set

**Grounded Claim**:
An answer statement linked to compatible evidence and labeled with the level of support validation applied to it.
_Avoid_: Verified fact, citation-only claim

**Ask Outcome**:
The typed result of a question, such as answered, no match, ambiguous, policy limited, unsupported, or failed.
_Avoid_: Answer string, exception
