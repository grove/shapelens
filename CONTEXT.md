# ShapeLens

ShapeLens is the domain concerned with turning contextual SHACL descriptions into bounded graph-query operations and evidence-backed answers. This glossary defines the project’s core domain language without prescribing implementation details.

## Semantic views

**Shape Lens**:
A contextual semantic view compiled from one primary SHACL node shape and optional Application Overlay. It defines meanings and query operations without by itself selecting a population.
_Avoid_: Class schema, universal shape, security view

**Property Lens**:
A contextual property within a Shape Lens that has a path, value contract, and permitted query operations.
_Avoid_: Field, predicate wrapper

**Value Contract**:
A branch-preserving description of the RDF terms accepted by a Property Lens.
_Avoid_: Python type, database column type

**Value Contract Branch**:
One preserved alternative within a Value Contract whose correlated constraints must be interpreted together.
_Avoid_: Flattened type set, implicit branch

**Population Selector**:
A rule that enumerates the nodes considered members of a query population, independently of the Value Contract used to interpret a relationship value.
_Avoid_: Value Contract, authorization filter, implicit lens target

**Affordance**:
A query operation that a Property Lens is permitted to expose, such as equality, traversal, or existence.
_Avoid_: Capability, tool

**Derivation Origin**:
The way a lens statement was obtained: directly from a shape, from an Application Overlay, from an ontology hint, or from sampled data.
_Avoid_: Source trust, authorization, confidence score

**Shape Source Trust**:
The application-approved trust status of a source from which shape statements are compiled.
_Avoid_: Parse validity, Derivation Origin, SHACL conformance

**Application Overlay**:
A versioned application-authored addition that gives a shape explicit query meaning or metadata not supplied by the shapes graph and is independently subject to Shape Source Trust.
_Avoid_: Inference, hint, prompt instruction, implicit trust

## Catalog and planning

**Shape Catalog**:
An immutable, versioned collection of Shape Lenses, Population Selectors, Property Lenses, source references, and their join relationships.
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
A typed, schema-bound expression of a question that refers only to known lenses, selectors, operations, Value Contract Branches, and validated RDF terms.
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

**Answer Extent**:
The user-requested breadth of an answer, such as a complete set or a stated number of examples, kept separate from execution resource ceilings.
_Avoid_: Page size, store row limit, planner preference

## Results and truth conditions

**Dataset Scope**:
The graph selection, entailment regime, revision, consistency, and completeness assumptions under which a query result has meaning.
_Avoid_: Database, endpoint

**Completeness Profile**:
A declaration that identifies the exact dataset slice, population, properties, authorization view, and time boundary for which a stated completeness assumption is accepted.
_Avoid_: Global completeness Boolean, real-world truth

**Evidence Item**:
A typed observation that states both what the system observed and the conditions under which it was observed.
_Avoid_: Fact, citation

**Evidence Packet**:
The bounded, versioned collection of evidence and limitations supplied to answer rendering.
_Avoid_: Model context, result set

**Grounded Claim**:
An answer statement linked to compatible evidence and labeled with the level of support validation applied to it.
_Avoid_: Verified fact, citation-only claim

**Answer Outcome**:
The typed result of a question, such as answered, no match, ambiguous, policy limited, unsupported, or failed.
_Avoid_: Answer string, exception
