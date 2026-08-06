# ShapeLens

ShapeLens is the domain concerned with turning contextual SHACL descriptions into bounded graph-query operations and evidence-backed results. This glossary defines the project’s core domain language without prescribing implementation details.

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
The application-approved status that permits a source to influence catalog construction. It establishes admission, not whether the source describes a fit query interface.
_Avoid_: Parse validity, Derivation Origin, Semantic Qualification, SHACL conformance

**Application Overlay**:
A versioned application-authored addition to shape-derived material, classified as a Descriptive Overlay, Executable Semantic Overlay, or Policy Metadata Overlay.
_Avoid_: Inference, hint, prompt instruction, implicit trust

**Descriptive Overlay**:
An Application Overlay containing retrieval or presentation metadata, such as labels and aliases, that cannot expand executable behavior.
_Avoid_: Executable Semantic Overlay, Policy Metadata Overlay

**Executable Semantic Overlay**:
An Application Overlay that adds query meaning, such as a Population Selector, join mapping, projection contract, or Affordance, and therefore requires Semantic Qualification.
_Avoid_: Descriptive Overlay, ontology hint, implicit inference

**Policy Metadata Overlay**:
Catalog-time tags and classifications owned by the application’s policy authority. It changes the Catalog Revision but does not itself enforce access or replace the independently revisioned Query Policy.
_Avoid_: Shape constraint, Executable Semantic Overlay, Query Policy, authorization decision

**Semantic Qualification**:
A reviewed determination that one executable lens behavior is fit for an intended application scenario, with its derivation and fixture coverage recorded.
_Avoid_: Shape Source Trust, confidence score, parse validity

## Catalog and planning

**Shape Catalog**:
An immutable, versioned collection of Shape Lenses, Population Selectors, Property Lenses, source references, and their join relationships.
_Avoid_: Registry, index

**Catalog Revision**:
One immutable version of a Shape Catalog and all trusted inputs that determine its meaning.
_Avoid_: Build timestamp, deployment version

**Catalog-Local Key**:
An opaque reference to a catalog item that is valid only within one Catalog Revision. Blank-node-backed shapes may receive this identity without any cross-revision promise.
_Avoid_: Portable Logical Key, RDF blank-node label

**Portable Logical Key**:
A reference intended to identify the same logical catalog item across Catalog Revisions. Version 0.1 grants this identity only where an admitted IRI-backed declaration supports it.
_Avoid_: Catalog-Local Key, revision digest

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
A typed, schema-bound graph request that refers only to known lenses, selectors, operations, Value Contract Branches, and validated RDF terms.
_Avoid_: SPARQL, prompt, query string

**Entity Variable**:
One logical RDF node in a Bound Query Plan, with a binding but no single privileged contextual view or implicit population.
_Avoid_: Shape Lens, Lens Use, class instance

**Lens Use**:
The application of one Shape Lens to one Entity Variable for a specific set of contextual property operations. An Entity Variable may have several Lens Uses without merging their Shape Lenses.
_Avoid_: Composite lens, Entity Variable, universal class view

**Selector Use**:
The explicit application of one Population Selector to one Entity Variable. It is independently identified so population evidence never arrives implicitly through a Lens Use.
_Avoid_: Lens Use, implicit target, Value Contract

**Plan Atom**:
One independently supportable selector, edge, filter, or projection occurrence in a Bound Query Plan.
_Avoid_: SPARQL fragment, evidence item

**Row Atom Set**:
The mechanically derived set containing every Selector Use, edge, filter, and projection occurrence in a normalized SelectPlan for each positive row. Optional projections remain members even when unbound.
_Avoid_: Relevant atoms, cited atoms, planner-selected support

**Atom-Witness Map**:
A row-specific exact mapping from every member of a Row Atom Set to supporting physical observations, entity bindings, deterministic derivations, or an explicit optional-unbound state.
_Avoid_: Evidence list, citation list, public evidence API

**Authorization Scope**:
The trusted boundary describing which semantic operations and data a requester may use.
_Avoid_: Shape Lens, prompt role, query preference

**Query Policy**:
The safety ceiling that limits query forms, complexity, resource use, and evidence behavior independently of authorization.
_Avoid_: Authorization Scope, planner instruction

**Run Context**:
The pinned catalog, authorization, policy, data scope, budget, and trace identity under which one plan is executed or later question is handled.
_Avoid_: Prompt context, global configuration

**Result Extent**:
The caller- or user-requested breadth of query results, such as a complete set or a stated number of examples, kept separate from execution resource ceilings.
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
The bounded, versioned collection of evidence and limitations supplied to Query Outcome construction and any later answer rendering.
_Avoid_: Model context, untyped result set

**Row Support Certificate**:
An identity-bearing record that binds an Atom-Witness Map to one execution, plan, query, result row, and set of evidence identities.
_Avoid_: Evidence list, citation list, negative proof

**Grounded Claim**:
An answer statement linked to compatible evidence and labeled with the level of support validation applied to it.
_Avoid_: Verified fact, citation-only claim

**Query Outcome**:
The typed result of executing a Bound Query Plan, such as selected rows, a Boolean result, no match, policy limited, unsupported, or failed. It makes no claim that the plan faithfully represents natural-language prose.
_Avoid_: Answer string, Answer Outcome, exception

**Answer Outcome**:
The later typed result of interpreting and answering a question, linked to a validated Query Outcome and question-to-plan fidelity records.
_Avoid_: Query Outcome, answer string, unchecked prose
