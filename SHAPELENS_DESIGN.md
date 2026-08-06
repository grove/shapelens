# ShapeLens GraphRAG

## A SHACL-native, typed GraphRAG architecture for Python

**Document status:** Reference design and decision backlog; not yet the normative version 0.1 specification
**Working library name:** `shapelens`
**Target runtime:** Python 3.11+
**Primary technologies:** RDF, SHACL, SPARQL, Pydantic, and optional Pydantic AI
**Standards baseline:** SHACL 1.0 source vocabulary and SPARQL 1.1 query target
**Last reviewed:** 6 August 2026

This document describes the proposed architecture and the decisions that must be settled before a public version 0.1 contract is frozen. It is implementation-ready only for the explicitly scoped semantic spikes in Phase 0. Requirements written as **MUST**, **SHOULD**, and **MAY** are candidate conformance rules: they become release requirements only when copied into `SPEC-0.1.md`, assigned stable requirement IDs, and mapped to tests after the Phase 0 semantics are accepted. Rationale, security guidance, roadmap material, and unresolved questions remain informative here. The project’s canonical domain vocabulary is recorded separately in [`CONTEXT.md`](./CONTEXT.md).

---

## Contents

1. [Executive summary](#1-executive-summary)
2. [Assessment of the design](#2-assessment-of-the-design)
3. [Problem, goals, and boundaries](#3-problem-goals-and-boundaries)
4. [Semantic assumptions and system invariants](#4-semantic-assumptions-and-system-invariants)
5. [Shape Lenses](#5-shape-lenses)
6. [A small end-to-end example](#6-a-small-end-to-end-example)
7. [Architecture and lifecycle](#7-architecture-and-lifecycle)
8. [Catalog construction](#8-catalog-construction)
9. [Schema retrieval and entity resolution](#9-schema-retrieval-and-entity-resolution)
10. [The version 0.1 query algebra](#10-the-version-01-query-algebra)
11. [Planning and plan validation](#11-planning-and-plan-validation)
12. [Compilation, execution, and repair](#12-compilation-execution-and-repair)
13. [Evidence and answer semantics](#13-evidence-and-answer-semantics)
14. [Hybrid graph and document retrieval](#14-hybrid-graph-and-document-retrieval)
15. [Public API](#15-public-api)
16. [Extensibility and package boundaries](#16-extensibility-and-package-boundaries)
17. [Security and privacy](#17-security-and-privacy)
18. [Operations, observability, and performance](#18-operations-observability-and-performance)
19. [Testing and evaluation](#19-testing-and-evaluation)
20. [Delivery plan](#20-delivery-plan)
21. [Risks and mitigations](#21-risks-and-mitigations)
22. [Architectural decisions](#22-architectural-decisions)
23. [Open questions](#23-open-questions)
24. [Recommendation and references](#24-recommendation-and-references)

---

## 1. Executive summary

ShapeLens GraphRAG is a proposed Python library for answering natural-language questions over RDF graphs without allowing a language model to invent unrestricted SPARQL. The library compiles selected SHACL shapes into **Shape Lenses**, which are query-oriented semantic views of a graph. A planner chooses operations exposed by those lenses and returns a typed `BoundQueryPlan`; ordinary Python validates that plan, compiles it into a small and controlled SPARQL subset, executes it under policy and resource limits, and turns the result into typed evidence. A deterministic renderer or a separately constrained answer model then produces an answer whose citations refer to that evidence.

The architecture is deliberately compiler-like. The model decides which known semantic operations match the question, but it never becomes the authority for schema, access, query syntax, or factual truth. Shape catalog construction, schema retrieval, entity resolution, authorization, plan validation, SPARQL rendering, endpoint policy, result normalization, provenance handling, and citation checks remain explicit program logic. This separation makes a failed run inspectable: the caller can see the retrieved lenses, entity candidates, bound plan, generated queries, execution diagnostics, evidence, and answer outcome without seeing or depending on private chain-of-thought.

The first release is intentionally narrower than the long-term architecture. Version 0.1 proves the central idea with trusted local IRI-backed node and property shapes, separate direct-type and target-node Population Selectors, direct and inverse predicate paths, connected positive conjunctions, RDF-term identity and positive existence filters, node projection, tightly constrained scalar field projection, `SELECT` and positive `ASK`, an RDFLib store, and typed query-result, row, and triple-pattern-match evidence. Sequence and alternative paths may be parsed for diagnostics but are not queryable in version 0.1. Absence, public blank-node shape identity, lexical text search, ordered comparison, aggregation, grouping, stable pagination, generic row-level authorization injection, full SHACL class semantics, formal focused SHACL validation, remote endpoints, document retrieval, embeddings, and dialect plugins arrive only after the positive algebra and evidence semantics have been validated. Narrowing the release in this way keeps the safety claims honest and makes the value of Shape Lenses independently measurable.

---

## 2. Assessment of the design

The design’s strongest idea is the typed boundary between natural-language interpretation and graph execution. Keeping schema retrieval separate from evidence retrieval, compiling a small plan instead of accepting raw SPARQL, treating evidence as a first-class artifact, and diagnosing empty results without silently dropping user constraints are all sound choices. The proposed structural expansion of retrieved lenses is particularly useful because an embedding search can find the concepts named by a question but miss the relationship that connects them. The design also correctly recognizes that validation of a deliberately partial evidence graph is not equivalent to validation of the source dataset.

The original proposal nevertheless overclaimed in four important places. First, it sometimes treated SHACL as if it were an exhaustive database schema, although a SHACL shape is a constraint applied to selected focus nodes and does not by itself establish authorization, completeness, or real-world truth. Second, the advertised query features exceeded the semantics represented by `BoundQueryPlan`; boolean queries, grouping, aggregate operands, nested Boolean filters, pagination, and optional-edge behavior were either missing or ambiguous. Third, a single `FactEvidence` type could not honestly describe asserted triples, property-path reachability, absence under `NOT EXISTS`, aggregate derivations, and validation findings. Fourth, lens allowlists and graph scopes did not provide a complete authorization model because filtering, joining, aggregation, auxiliary queries, and document retrieval could still leak protected information.

This revision addresses those weaknesses directly. Every derived lens field records both how it was derived and whether its complete shape-source closure is trusted; neither fact alone authorizes execution. Population selection is separate from relationship value compatibility, so choosing a context-specific lens cannot silently narrow a joined value population. A run pins immutable catalog, policy, capability, and Dataset Scope descriptions from retrieval through answering. Version 0.1 has a deliberately small positive query algebra with explicit `SELECT` and Boolean plans and precisely defined conjunctive semantics. Evidence is a discriminated family whose members describe their proof strength and query scope. Authorization constraints are trusted inputs that the planner cannot remove, and the public result is a typed outcome rather than a string plus an underspecified error field.

---

## 3. Problem, goals, and boundaries

Natural-language-to-SPARQL systems fail in recurring ways. A model may invent plausible classes or predicates, reverse the direction of a relation, bind a phrase to the wrong entity, generate an expensive or unsafe query, or produce fluent prose from results that do not support it. Even valid SPARQL can be misleading when the queried dataset is incomplete, an endpoint applies an unexpected entailment regime, a named-graph scope differs from the user’s assumption, or an empty result is phrased as a statement about the real world. These failures are related: they arise when semantic interpretation, query authority, execution, and evidence are collapsed into one model call.

SHACL contains useful local knowledge for separating those responsibilities. Node and property shapes can describe targets, paths, value classes, datatypes, cardinalities, labels, descriptions, and constraints. That information can guide a planner toward schema-backed operations, but it is not automatically a natural-language query grammar and an arbitrary constraint is not invertible into a useful retrieval operation. ShapeLens therefore compiles a conservative, provenance-aware query interface from supported shape features rather than claiming to translate every shape into SPARQL.

The library’s primary goals are to answer questions over local and remote RDF stores, make SHACL the principal source of query affordances, provide useful behavior without embeddings, preserve RDF identity and available provenance, expose typed debug artifacts, and keep model-provider integrations replaceable. It should support graph-only answers first and graph-guided document retrieval later. Pydantic models protect every boundary where model output, endpoint output, plugin output, or untrusted configuration enters the deterministic core.

Several concerns are explicitly outside the initial boundary. ShapeLens will not infer a complete ontology from arbitrary data, turn every SHACL-SPARQL constraint into a query, generate SPARQL Update, accept model-authored query fragments, silently relax a question to get non-empty results, or claim that SHACL conformance proves real-world truth. It will not treat a context-specific lens as an authorization boundary by itself, and it will not promise perfect portability across SPARQL implementations. Fine-tuning, unrestricted federation, and a mandatory vector database are also non-goals.

---

## 4. Semantic assumptions and system invariants

### 4.1 SHACL is a local contract, not a complete world model

A Shape Lens is compiled from SHACL, but its meaning is narrower than “the schema of a class.” A shape constrains focus nodes selected for a particular validation or application context. It may describe only part of a resource, may coexist with other shapes for the same class, and may encode data-quality expectations rather than query semantics. The catalog MUST preserve this context and MUST NOT merge every shape for a class into one universal lens.

A lens contract and a Population Selector are distinct. The contract defines contextual property operations and compatible relationship values. A Population Selector defines which nodes may be enumerated as a query population and is compiled from a supported SHACL target declaration or an eligible Application Overlay. A targetless contract may be used to validate a bound relationship value or support further contextual operations, but it MUST NOT introduce an unbound root. Conversely, a property value contract such as `sh:class ex:Employee` MUST NOT be treated as permission to enumerate every employee. Constraints on focus nodes and population selection remain separate even when they originated in the same node shape.

Every derived statement records a **Derivation Origin**, which says how it was obtained, and a **Shape Source Trust** assessment, which says whether the complete source and import closure is eligible to influence executable behavior. These are independent axes.

| Derivation origin | Meaning | Executable eligibility |
|---|---|---|
| `shape_constraint` | Directly derived from a supported SHACL constraint or target declaration | Eligible only when the shape-source closure is `trusted` |
| `application_overlay` | Supplied by reviewed application configuration | Eligible only when the complete overlay, referenced-shape, and dependency closure is `trusted` |
| `ontology_hint` | Inferred from labels, `rdfs:domain`, `rdfs:range`, or similar ontology terms | Ranking and explanation only |
| `sampled_hint` | Inferred from bounded inspection of instance data or statistics | Ranking and cost estimation only |

Shape Source Trust has three states. `trusted` closures may contribute executable statements subject to Derivation Origin and runtime authorization. `untrusted` closures may be parsed into bounded diagnostic material but cannot expand retrieval cards, joins, selectors, or affordances visible to a planner. `quarantined` sources are excluded after a failed integrity, admission, or safety check. Parsing, bounded compilation, SHACL conformance, transport security, and a familiar graph IRI do not establish source trust. An executable affordance requires a trusted closure, an eligible Derivation Origin, and authorization for the current run. A deployment MAY explicitly promote an ontology mapping into an Application Overlay, but promotion and source admission are separate reviewed policy changes with revisions, audit records, and tests.

### 4.2 Negative results have explicit strength

RDF normally follows an open-world interpretation, so a failed match is not proof that the corresponding real-world relationship does not exist. ShapeLens distinguishes three claims: no solution was observed for a completed query; no solution was visible within the caller's Authorization Scope; and no solution exists in a declared complete dataset slice. The first two are query-result observations and MUST be worded relative to the pinned Dataset and Authorization Scopes. The third is a stronger absence claim and requires a named `CompletenessProfile` that identifies the relevant dataset, graph selection, population, properties, authorization view, and time boundary.

Version 0.1 may return `NoMatch` for a completed positive query, but it does not compile `NOT EXISTS`, create `AbsenceEvidence`, or claim property-level completeness. Those features enter together in a later profile only after their algebra, authorization-relative wording, and completeness rules are specified. A global Boolean such as `absence_claims_allowed` is not sufficient.

### 4.3 Every run observes pinned revisions

At the beginning of a run, the engine obtains immutable handles or immutable descriptions for the catalog revision, query-policy revision, Authorization Scope, endpoint-capability revision, compiler version, and Dataset Scope. All later stages use those pinned values, including retries, probes, label lookups, provenance lookups, validation queries, document retrieval, and cache keys. Catalog rebuilds publish a new revision atomically and never mutate an object used by an in-flight run. When a store cannot provide snapshot consistency across multiple queries, the evidence packet records that limitation instead of implying that all enrichment came from one snapshot.

### 4.4 The trust boundary is explicit

The planner may select only catalog operations and Population Selectors shown in its candidate context or retrieved through a typed inspection tool. It cannot create IRIs, property paths, authorization predicates, graph scopes, functions, raw query fragments, or source-trust decisions. The plan validator checks semantic references and policy, the SPARQL compiler accepts only validated models, and a second parser and policy pass checks the rendered query. Endpoint results are parsed into RDF terms before use. The answerer receives only a bounded evidence packet and cannot invent citation identifiers or source URLs.

### 4.5 Evidence strength is not the same as citation validity

A citation is referentially valid when its ID exists, but that alone does not establish that the cited item supports a claim. ShapeLens distinguishes four levels of answer checking: ID existence, compatibility between evidence and claim type, deterministic support for template-rendered claims, and optional semantic support assessment for free prose. The library MUST describe which level was applied. It MUST NOT label a claim “verified” merely because the model returned an existing evidence ID.

---

## 5. Shape Lenses

A **Shape Lens** is an immutable, versioned semantic view compiled from one primary SHACL node shape. An Application Overlay may augment that primary shape but does not merge several shapes into one lens; a future composite-lens feature would need separate identity and conflict rules. The lens tells retrieval what the view is about, tells the planner which contextual property operations are available, tells validation which values are compatible with those operations, and provides source references that explain every derived field. It may own zero or more independently identified **Population Selectors** compiled from supported target declarations or Application Overlays. A **Property Lens** is an operation-bearing property within a Shape Lens; property shapes remain Property Lenses or nested contracts rather than becoming populations merely because their values have a class.

One RDF class may have several Shape Lenses. An employee might have a public-directory lens, a project-staffing lens, and a data-quality lens. These lenses may expose different properties and may carry different policy tags, but those tags do not themselves enforce security. Enforcement occurs through the authorization and query-policy layers across every primary and auxiliary operation.

The central objects have distinct responsibilities. A `ShapeCatalog` is the immutable, serializable build artifact for one revision. It contains Shape Lenses, Property Lenses, source references, logical constraints, and the directed join graph. A `ShapeRegistry` is the runtime lookup interface over one catalog revision. A `ShapeIndex` is a replaceable retrieval structure built from that catalog. These names are not interchangeable: the catalog owns data, the registry exposes lookup behavior, and an index returns ranked candidates.

### 5.1 Lens contents

Each Shape Lens has a stable logical key, an immutable revision digest, the original shape term, the shapes-graph identity, labels and descriptions by language, descriptive focus-class metadata, property lenses, query and policy tags, a compact retrieval card, and exact source references. Each Population Selector has its own key and revision, selector profile, graph-scope assumptions, cost and evidence semantics, Derivation Origin, Shape Source Trust assessment, and source references. A Property Lens has its own logical key and revision digest, a canonical path, a branch-preserving value contract, allowed operations, expected cardinality, evidence requirements, and Derivation Origin, Shape Source Trust assessment, and source references for every derived field.

The value contract MUST preserve logical correlations. For example, `sh:or` branches cannot be flattened into independent sets of datatypes and classes because doing so could create combinations that no branch permits. The normalized representation is therefore a small Boolean constraint expression whose leaves describe node kind, datatype, class, allowed values, patterns, cardinality, and nested shapes. Unsupported expressions remain attached as validation-only source material and cannot authorize query operations.

### 5.2 Canonical paths and affordances

SHACL property paths are parsed once into a cycle-safe abstract syntax tree. Version 0.1 renders direct predicates and inverse predicates only. Sequence, alternative, zero-or-more, one-or-more, and zero-or-one paths are recognized so the catalog can report them accurately, but they are marked `validation_only` until their planning, cost, and evidence-witness semantics are implemented. This is intentionally more conservative than accepting any path simply because SPARQL can render it.

An affordance is an operation that a planner may request. In the long-term design, a string-valued property can expose lexical matching, an ordered literal can expose comparisons, an IRI-valued property can expose a join or entity identity, and a supported property can expose positive existence or scoped absence. Version 0.1 implements exact RDF-term identity, joins, and positive existence. Lexical matching, ordered comparison, and absence wait for typed nodes with portable semantics and evidence rules. Cardinality informs validation and result shape but does not decide query semantics on its own. A complex custom constraint adds no affordance unless a trusted plugin implements normalization, validation, compilation, evidence construction, and tests for the complete trust chain.

### 5.3 Identity

ShapeLens separates logical identity from content identity. In version 0.1, an IRI-backed node shape receives a catalog-scoped `lens_key` derived from the shapes-graph key and shape IRI, while `lens_revision` is a digest of its normalized, relevant source, source-trust assessment, and compiler settings. A Population Selector key combines its owning lens key with the normalized supported target declaration. A Property Lens key combines the owning lens key with an IRI-backed property-shape identity, so a shared property shape used in different contexts does not collapse those contexts accidentally. Public identity for blank-node node or property shapes is deferred until OQ-008 defines the extraction boundary and migration guarantee for a future RDFC-1.0 profile.

Catalog parsing still applies byte, triple, blank-node, recursion, and time budgets to adversarial source graphs. Blank-node node and property shapes may be retained for diagnostics or nested validation but do not receive public plan keys in version 0.1. This deliberate restriction is less convenient than ordinary SHACL authoring and is part of the experiment's narrow scope. A later RDFC-1.0 identity profile must define its extraction boundary, computational budget, and migration behavior before blank-node keys become public contracts.

---

## 6. A small end-to-end example

Assume a staffing graph contains employees, projects, and skills. Its SHACL graph has an employee staffing shape with direct properties for `ex:name`, `ex:workedOn`, and `ex:expertise`; project and skill shapes provide class contracts and labels. The employee shape's `sh:targetClass` produces a direct-type Population Selector. The catalog produces three Shape Lenses, two joinable Property Lenses from employee to project and skill, and a scalar name property. The question “Which employees worked on Project X and have artificial-intelligence expertise?” retrieves those lenses and resolves the two quoted concepts to type-compatible IRIs.

The planner returns a `SelectPlan` that contains an unbound employee node with the explicit employee Population Selector, a project node bound to `ex:project-x`, a skill node bound to `ex:skill-ai`, two required edges with selected value-contract branches, and projections for the employee IRI and its contractually single-valued optional name. The project and skill bindings are checked against their incoming Property Lens contracts; their context-specific target declarations are not imported into the joins. The plan contains only catalog keys and parsed RDF terms; it contains no predicate IRI, variable name, or SPARQL fragment supplied by the model. For a model-authored plan, separate intent coverage records map the two requested conditions to the two edges.

The deterministic compiler can then produce a query equivalent to the following:

```sparql
PREFIX ex: <https://example.org/>

SELECT DISTINCT ?employee ?employee_name
WHERE {
  VALUES ?project { <https://example.org/id/project-x> }
  VALUES ?skill { <https://example.org/id/skill-ai> }

  ?employee a ex:Employee ;
            ex:workedOn ?project ;
            ex:expertise ?skill .

  OPTIONAL { ?employee ex:name ?employee_name . }
}
LIMIT 100
```

If the endpoint returns Alice and Omar, the evidence builder records the triple-pattern matches that connect each employee to the project and skill, the result rows, the selector, query and catalog revisions, and any available graph provenance or entailment status. A deterministic renderer can produce “Alice and Omar match both conditions” and associate each name with its two connecting matches. If the completed query returns no rows, the outcome is `NoMatch`, worded as “No employees visible in this authorization scope matched both conditions in the queried data.” Version 0.1 does not run absence probes or relax a condition to obtain a result.

This example also shows what version 0.1 does not attempt. It does not interpret a sequence path, compute an aggregate, compile a negative relationship condition, prove the real-world absence of an assignment, or search documents. Those capabilities require additional algebra and evidence types and are introduced only in later phases.

---

## 7. Architecture and lifecycle

ShapeLens has two lifecycles. Catalog build time ingests shape-source descriptors and optional ontology material, verifies each complete source closure against application trust policy, normalizes supported constructs, records diagnostic-only material, compiles lens contracts and Population Selectors, builds the join graph, creates lexical retrieval documents, and publishes an immutable catalog revision. Question time pins that revision, normalizes the question, retrieves a small connected lens subgraph and eligible selectors, resolves mentioned entities, creates and validates a plan, applies trusted authorization, compiles and checks SPARQL, executes it under a shared deadline, constructs evidence, and renders or synthesizes a typed outcome.

```mermaid
flowchart LR
    SH[SHACL and application overlays] --> SC[Shape compiler]
    SC --> CAT[Immutable ShapeCatalog]
    CAT --> IDX[Lexical and optional vector indexes]

    Q[Question] --> RET[Schema retrieval]
    IDX --> RET
    RET --> ER[Entity resolution]
    ER --> PL[Typed planner]
    PL --> VAL[Plan and policy validation]
    CAT --> VAL
    VAL --> AUTH[Inject authorization scope]
    AUTH --> SPC[SPARQL compiler and policy check]
    SPC --> STORE[Graph store]
    STORE --> EV[Evidence builder]
    EV --> ANS[Deterministic renderer or typed answerer]
    ANS --> OUT[Typed AnswerOutcome]
```

The workflow is an explicit state machine even if the implementation uses ordinary functions rather than a graph library. Every model call and I/O operation consumes a centrally managed `RunBudget`, observes the same absolute deadline, and supports cancellation. Optional enrichments such as labels, provenance, or documents may run concurrently after core rows are available, but their failures produce a degraded outcome with issues rather than erasing valid core evidence. Retries are classified and bounded; there is no open-ended agent tool loop.

The main trust transitions are easy to name. Untrusted shape and ontology content may become diagnostic catalog material after bounded parsing, but only a source closure assessed as `trusted` may expand the executable surface. Untrusted model output becomes executable only after structural, semantic, intent-coverage, authorization, capability, and complexity validation. Endpoint bytes become evidence only after content-type, size, parser, RDF-term, and result-contract checks. Model-authored prose becomes a public answer only after evidence-reference and claim-policy validation.

---

## 8. Catalog construction

### 8.1 Loading, imports, and profiles

Catalog sources may be RDFLib graphs or datasets, local files, application-provided byte streams, or an application-provided `ShapeSource`. Every input is accompanied by a trusted `ShapeSourceDescriptor` that identifies its owner, source kind and location, content digest, review or admission status, and import policy. The descriptor is deployment configuration and cannot be supplied or altered by the shape document or an ordinary request. A byte stream is not trusted merely because the application supplied it. Remote URL loading, `owl:imports`, JSON-LD remote contexts, SHACL-JS, and arbitrary extension execution are disabled by default. When network loading is enabled, the application supplies allowed schemes and hosts, redirect limits, byte and triple limits, timeouts, content-type rules, and an import-depth budget. Imports are resolved into a recorded closure; one `untrusted` or `quarantined` member makes executable statements derived from that closure ineligible. Closure digests and trust assessments contribute to the catalog revision.

The source-vocabulary baseline is the 2017 SHACL Recommendation, while the queryable subset is the explicit ShapeLens feature matrix below and must not be mistaken for full SHACL query equivalence. SHACL 1.2 material is treated as a capability-gated extension because, as of this review, SHACL 1.2 Core remains a W3C Working Draft. The catalog records both features observed and features actually implemented; seeing a version label never activates behavior. Unsupported syntax is never silently ignored. It either fails the build because safe normalization is impossible or remains preserved as validation-only metadata with a diagnostic.

### 8.2 Proposed version 0.1 feature matrix

The following table is the candidate implementation contract to be copied into `SPEC-0.1.md` after Phase 0. “Population selection” means that a supported target declaration may compile into a separately identified Population Selector. “Queryable” means a supported construct may create a property affordance. “Contract only” means it can restrict or describe a value but does not create a query operation or population. “Diagnostic only” means it is parsed or preserved, but any lens that depends on it for the requested operation is rejected.

| SHACL construct | Version 0.1 treatment | Query meaning |
|---|---|---|
| `sh:targetClass` | Population selection in the `direct_type` profile | Compile a selector that enumerates nodes with a direct `rdf:type` pattern; do not claim full SHACL instance semantics |
| `sh:targetNode` | Population selection for IRI terms only | Compile a selector that enumerates only the declared IRI or IRIs; other RDF terms are diagnostic-only in version 0.1 |
| `sh:targetSubjectsOf` | Deferred | Diagnostic only until target selection is specified and tested |
| `sh:targetObjectsOf` | Deferred | Diagnostic only until target selection is specified and tested |
| Blank-node node or property shape | Diagnostic or nested-contract only | No public lens or Property Lens plan key in version 0.1; use stable IRI-backed shapes for executable operations |
| Shape without a target | Contract only | Reusable contextual contract; never introduces an unbound root without a trusted selector |
| Direct predicate path | Queryable | One triple pattern |
| Inverse predicate path | Queryable | One reversed triple pattern |
| Sequence or alternative path | Deferred | Diagnostic only |
| Repeating path | Deferred | Diagnostic only |
| `sh:datatype`, `sh:nodeKind` | Contract only | Restrict values and derive exact identity compatibility |
| `sh:class` | Contract only in the `direct_type` profile | Require direct class compatibility; subclass-aware SHACL instance semantics are deferred |
| `sh:minCount`, `sh:maxCount` | Contract only | Validate values; only an eligible `sh:maxCount 1` contract or Application Overlay may authorize scalar field projection in version 0.1 |
| `sh:in` | Contract only | Permit equality only to a declared RDF term |
| `sh:or` | Contract only | Preserve branches; no Boolean query union in version 0.1 |
| `sh:node` | Contract only | Retain a nested contract with cycle detection |
| SHACL-SPARQL and custom components | Deferred | Validation-only unless a trusted plugin implements the full chain |
| `sh:intent` from SHACL 1.2 | Retrieval metadata | Weighted semantic text only; never an instruction |

Catalog meta-validation and ShapeLens compilation are separate checks. An optional pySHACL adapter may establish that a shapes graph conforms to the chosen SHACL profile, while the ShapeLens compiler establishes whether this library can safely turn selected constructs into its query contracts. Parse-only operation, when pySHACL is absent, guarantees only bounded parsing and ShapeLens feature checks; it does not establish SHACL meta-conformance.

The `direct_type` selector profile is deliberately narrower than SHACL’s definition of a SHACL instance. A selector compiled from `sh:targetClass ex:Employee` emits only `?node rdf:type ex:Employee`; it does not follow `rdfs:subClassOf` and MUST be reported as direct-type behavior in catalog diagnostics. The same direct-class limitation applies when `sh:class` establishes value compatibility, but that contract does not itself emit a population pattern. A later `shacl_instance` profile may use a pinned entailment regime or compile subclass-aware patterns, but it must specify cost and evidence behavior and pass subclass-only differential fixtures. A target-node selector emits `VALUES` for its declared IRIs and no implicit type pattern. When a shape has several supported target declarations, version 0.1 compiles one explicit union selector matching SHACL target selection; applying that selector is a plan decision and never an implicit consequence of using the lens contract.

### 8.3 Normalization and join construction

Normalization resolves display prefixes while retaining full IRIs, converts RDF lists to bounded tuples, parses paths into a canonical AST, preserves Boolean constraint branches with stable branch keys, records language-tagged labels, detects recursion, and attaches Derivation Origin, Shape Source Trust, and source references to every derived field. Ontology labels from `trusted` closures may enrich planner-visible retrieval text, while untrusted ontology content remains diagnostic-only; ontology domains, ranges, and sampled instance types remain non-authorizing hints regardless. Application Overlays can supply aliases, Population Selectors, policy tags, preferred labels, or join mappings, but each overlay is versioned and admitted through the same source-trust policy as shapes.

The join graph is a directed multigraph whose vertices are Shape Lenses and whose edges are Property Lenses whose Value Contract Branches can accept nodes described by another lens. An eligible `sh:class` or supported nested `sh:node` constraint can establish a candidate join. Population Selectors do not create joins and are not imported when a relationship value is checked. Ontology range and sampled type information can increase a retrieval score but cannot create an executable join unless promoted through a separately admitted Application Overlay. Multiple context-specific lenses and selectors remain separate candidates; retrieval and policy decide which may participate in a run.

### 8.4 Publication and incremental rebuild

A catalog revision is a digest over normalized source revisions, import closure, Shape Source Trust assessments and policy revision, overlays, feature settings, identity profile, and ShapeLens compiler version. A rebuild creates a complete candidate artifact, validates it, warms required indexes, and publishes it atomically. If publication fails, the previous revision remains active. Incremental implementation may reuse unchanged lens and index fragments internally, but the externally visible catalog is immutable and complete.

Multi-worker deployments need one publisher or a compare-and-swap publication protocol, artifact checksums, compatibility checks, and rollback to a known-good revision. These operational choices are not required for the local prototype, but the artifact format must reserve a schema version and refuse unknown incompatible versions rather than loading them optimistically.

---

## 9. Schema retrieval and entity resolution

Schema retrieval answers “which semantic views and relationships can express this question?” while entity resolution answers “which graph nodes or literal values do the phrases refer to?” They are different tasks and use different indexes and diagnostics. A document embedding index is not a substitute for either one.

The first implementation uses a field-weighted in-memory lexical index over labels, aliases, local names, descriptions, and trusted intent text. When every eligible compact lens card fits the configured context budget, the system SHOULD include all of them rather than introduce retrieval error. Larger catalogs use ranked lexical retrieval, optional embedding fusion, and bounded structural expansion through the join graph. The selection threshold is based on packed context size and policy, not a hard number of shapes.

Structural expansion begins with semantically strong lens hits, searches for bounded connecting paths in the contract-derived join graph, adds bridge lenses within an explicit configured maximum, and prunes candidates by authorization, path support, estimated cost, and context budget. Population Selectors are retrieved and authorized separately for nodes the question must enumerate. Diagnostics record the lexical, vector, and structural contributions, the catalog revision, selected and discarded contracts and selectors, and any bridge that was added even though its label did not appear in the question.

Entity resolution recognizes explicit IRIs or CURIEs, exact and normalized labels, aliases, local indexes, and later endpoint-native search. Expected lens keys constrain the candidate type. Version 0.1 binds automatically only when one candidate passes a configured dominance threshold and is type-compatible. Material ambiguity produces an `Ambiguous` outcome with candidates; it does not use a vague “candidate set” whose implicit union could change the answer. A later algebra may add an explicit `one_of` binding when the user or application requests union semantics.

Literal-versus-entity interpretation is governed by the Property Lens. A string contract expects a literal, an IRI-valued class contract expects a resolved entity, and a preserved union requires an explicit supported Value Contract Branch. If the catalog cannot distinguish the intended branch or operation, the correct outcome is `Unsupported` or `Ambiguous`, not a guessed filter.

---

## 10. The version 0.1 query algebra

The query algebra is the most important executable contract in the design. It is intentionally smaller than SPARQL and has a precise meaning independent of any model provider. Version 0.1 supports two query kinds: `SelectPlan`, which returns entity or scalar-field rows, and `BooleanPlan`, which returns whether at least one positive solution exists. Both use a connected conjunction of required positive edges and filters. There is no negation, general Boolean expression, union, subquery, grouping, aggregation, ordering, pagination, arbitrary expression, or raw graph pattern in this version.

The following models illustrate the candidate semantics to be tested in Phase 0; the normative specification may refine their Python syntax and names before version 0.1 is frozen.

```python
from typing import Annotated, Literal
from pydantic import BaseModel, Field


class IriTerm(BaseModel):
    kind: Literal["iri"] = "iri"
    value: str


class LiteralTerm(BaseModel):
    kind: Literal["literal"] = "literal"
    value: str
    datatype: str | None = None
    language: str | None = None


RDFTerm = Annotated[IriTerm | LiteralTerm, Field(discriminator="kind")]


class UnboundBinding(BaseModel):
    kind: Literal["unbound"] = "unbound"


class IriBinding(BaseModel):
    kind: Literal["iri"] = "iri"
    iri: IriTerm


NodeBinding = Annotated[
    UnboundBinding | IriBinding,
    Field(discriminator="kind"),
]


class PlanNode(BaseModel):
    id: str
    lens_key: str
    binding: NodeBinding
    population_selector_key: str | None = None


class RequiredEdge(BaseModel):
    kind: Literal["required"] = "required"
    id: str
    source_node: str
    property_lens_key: str
    contract_branch_id: str
    target_node: str


class PropertyRef(BaseModel):
    node_id: str
    property_lens_key: str


class ValueFieldRef(BaseModel):
    node_id: str
    property_lens_key: str
    contract_branch_id: str


class EqFilter(BaseModel):
    kind: Literal["eq"] = "eq"
    field: ValueFieldRef
    value: RDFTerm


class ExistsFilter(BaseModel):
    kind: Literal["exists"] = "exists"
    property: PropertyRef


FilterExpr = Annotated[
    EqFilter | ExistsFilter,
    Field(discriminator="kind"),
]


class NodeProjection(BaseModel):
    id: str
    kind: Literal["node"] = "node"
    node_id: str


class FieldProjection(BaseModel):
    id: str
    kind: Literal["field"] = "field"
    field: ValueFieldRef
    required: bool = False


Projection = Annotated[
    NodeProjection | FieldProjection,
    Field(discriminator="kind"),
]


class SelectPlan(BaseModel):
    kind: Literal["select"] = "select"
    nodes: tuple[PlanNode, ...]
    edges: tuple[RequiredEdge, ...] = ()
    filters: tuple[FilterExpr, ...] = ()
    projections: tuple[Projection, ...]


class BooleanPlan(BaseModel):
    kind: Literal["boolean"] = "boolean"
    nodes: tuple[PlanNode, ...]
    edges: tuple[RequiredEdge, ...] = ()
    filters: tuple[FilterExpr, ...] = ()


BoundQueryPlan = Annotated[SelectPlan | BooleanPlan, Field(discriminator="kind")]
```

All edges and filters are conjoined. `RequiredEdge` means that a matching path must exist and names the exact compatible Value Contract Branch. A Population Selector is compiled only when its key appears explicitly on a plan node; selecting a lens for its property operations never imports its selector. Every unbound positive root that is not introduced by an incoming edge requires an eligible Population Selector. A bound IRI and every joined target are checked against their applicable contracts independently of population selection.

`ExistsFilter` is the sole field-existence operation in version 0.1 and means that at least one matching value is bound. It is branch-independent and is legal for a multi-branch property only when every eligible branch exposes the same positive-existence affordance. Required joins are used only when the value participates as a plan node; anonymous traversals are normalized to `ExistsFilter` rather than represented a second way. Negative existence and `NOT EXISTS` are deferred. Equality filters and field projections name an exact Value Contract Branch through `ValueFieldRef`. Field projections are optional by default and use `OPTIONAL`, while `required=True` makes the scalar field part of the required graph pattern. A field projection is legal in version 0.1 only when an eligible contract or Application Overlay declares it single-valued; otherwise it returns `Unsupported`. If execution observes multiple values despite that contract, result validation reports a contract violation instead of flattening or choosing one. This prevents independent many-valued projections from creating misleading Cartesian products.

`EqFilter` means RDF-term identity and compiles with `sameTerm`, not SPARQL value equality. Literals therefore match only when lexical form, datatype, and language tag identify the same RDF term; numeric coercion, language fallback, case folding, Unicode normalization, and collation are outside version 0.1. This strict meaning is portable and makes datatype errors predictable. Lexical text search and ordered value comparison will require their own typed filters when their semantics are agreed.

The first release supports only one declared traversal binding for each property reference and selected branch from a node. Validation rejects duplicate edges, filters, projections, or mixed required/optional uses that could assign different meanings to the same reference. If a later plan needs the same property in two independently bound traversals, the algebra will add explicit traversal references instead of guessing which occurrence a filter means. Every projected or bound node must belong to one connected positive component.

A version 0.1 `SelectPlan` always applies `DISTINCT` to the canonical internal answer tuple, which contains the public projections plus hidden node identities needed to distinguish resources and construct evidence. Evidence-enrichment variables are excluded from that tuple by construction. The execution layer fixes the limited result before optional enrichment so hidden evidence variables cannot multiply rows or change the result bound.

Answer extent is not authored inside `BoundQueryPlan`. The authoritative request records either a complete-set requirement or an explicitly requested number of examples, with provenance to the user request. Query Policy separately supplies safe row and byte ceilings. A model may extract a requested example count as an intent item, but validation must link it to the authoritative question before it can narrow the answer. Without such an item, the model cannot weaken a complete-set request.

Version 0.1 supports one unordered limited result, not pagination. When policy permits a limited result, execution requests one row beyond the effective bound to determine whether more solutions exist. A successfully observed sentinel row proves truncation; absence of a sentinel proves answer-set completion only when the query itself completed without a row, byte, parser, cancellation, or deadline interruption. There is no continuation token, stable membership, “top,” “first,” or “latest” semantics. Questions requiring those semantics return `Unsupported`. If the request requires a complete set and policy or execution cannot establish it, the outcome is `PolicyLimited` or `Failed`, never a silently narrowed answer.

Before validation and digesting, the bound plan is normalized into a canonical form with canonical RDF terms, path identities, collection order, deterministic local-ID renaming, explicit Value Contract Branches, and rejected duplicates. The user-plan digest excludes trusted authorization constraints, which are injected and normalized later in the internal AST. Semantically equivalent input ordering and model-chosen local IDs must produce the same plan digest and query.

Aggregation is intentionally deferred. When introduced, an aggregate node will explicitly name its operand, distinctness, grouping keys, empty-input semantics, and optional `HAVING` expression. Deferring it avoids pretending that a `Projection(kind="count")` is sufficient to define correct SPARQL in the presence of many-valued joins.

---

## 11. Planning and plan validation

### 11.1 Planner roles

The optional model planner introduced after version 0.1 receives the authoritative question, candidate lens and selector cards, legal operations, entity-resolution results, endpoint restrictions relevant to semantics, and non-sensitive policy constraints. It returns a structured planning envelope under a fixed output-retry budget. The envelope contains stable intent-item IDs, the `BoundQueryPlan`, and a coverage mapping from every material intent item to an edge, filter, projection, answer-extent request, or explicit `unsupported`, `ambiguous`, or `policy_limited` disposition. Every restrictive plan element must map back to an intent item; trusted authorization constraints are outside this comparison. The plan itself does not echo the question, and the run context remains its authoritative source.

Intent extraction and binding may happen in one structured response or in two stages through a schema-unbound `SemanticIntent`, but coverage is mandatory for every model-authored plan. It establishes **internal coverage** of extracted intent, not equivalence to the original question. **Plan legality** is deterministically validated; **question fidelity** remains an empirical property measured against human-labelled cases. A plan cannot yield `Answered` or `NoMatch` while a material intent item is unsupported, ambiguous, policy-limited, or unrepresented. Deterministic application rules and caller-authored fixtures may produce the same plan type without a model call or intent envelope.

Pydantic AI is the recommended optional adapter because it supports typed dependencies, structured output, tools, and output validation, but the deterministic core depends on a small `Planner` protocol rather than the framework itself. Model identifiers and provider configuration belong to the application and examples MUST NOT bake in a supposedly current model name.

The planner may inspect a candidate lens, search for additional lenses, or resolve an entity through typed tools. It never receives a general SPARQL execution tool. Any future probe tool accepts a typed plan and passes through the same validation, authorization, policy, and budget path as the main query.

### 11.2 Validation layers

Structural validation checks discriminated variants, bounded collection sizes, unique IDs, reference integrity, field formats, duplicate semantics, and canonical form. Catalog validation then proves that every lens, selector, property, and contract-branch key belongs to the pinned revision; every selector belongs to the node's lens; every property belongs to the source node's lens; every edge target and value operation is compatible with the explicitly selected Value Contract Branch; every unbound root has an eligible Population Selector; and every referenced artifact appeared in the candidate context or a recorded inspection result. Operator validation checks that the property or selector has an eligible Derivation Origin, `trusted` Shape Source Trust, and a permitted operation.

Connectivity validation rejects accidental Cartesian products by requiring every projected or bound node to belong to one connected positive component. Model-planner validation proves bidirectional internal coverage: every extracted material intent item has a disposition, and every user-semantic restriction has an intent source. It does not claim that extraction captured the whole question. Capability validation proves that the pinned store and compiler profile can implement the plan without a semantic substitution.

### 11.3 Authorization and policy

Authorization is a trusted input, not a planner suggestion. Version 0.1 supports only a declared local deployment profile with trusted local data plus lens-operation and graph allowlists; it does not claim generic row- or value-level authorization. Later profiles may add endpoint-native credentials, graph partitioning, or compiler-injected mandatory subject or value restrictions only after OQ-004 and OQ-005 are resolved. Such restrictions are represented as trusted internal AST, never model plan content; cannot be removed by repair; apply to every auxiliary and diagnostic query; and participate in all cache keys.

`QueryPolicy` is a separate safety ceiling that owns safe result ceilings and controls query forms, graph and function allowlists, path features, regex, maximum plan and AST complexity, deadlines, and result bytes. Filtering a lens or selector card out of the planner context is useful defense in depth but is never the sole enforcement mechanism. Policy rejection produces a typed `PolicyLimited` outcome and is not sent to the model as an invitation to find a workaround. A later absence profile uses named Completeness Profiles rather than a policy Boolean.

Every conformance requirement described as bounded MUST map to a named configuration field with a finite safe default owned by catalog-build policy, Query Policy, or Run Budget. The version 0.1 specification must enumerate at least source bytes and triples, RDF-list length, recursion depth, path depth, lens-card bytes, structural-expansion depth, plan nodes and edges, AST nodes, result rows and bytes, absolute deadline, retry count, and auxiliary-query count. Words such as “small,” “minimal,” and “compact” are rationale, not testable requirements, unless the corresponding configured limit is named.

---

## 12. Compilation, execution, and repair

### 12.1 Deterministic SPARQL compilation

The SPARQL compiler resolves catalog and selector keys, allocates stable internal variables, compiles only explicitly selected population patterns, creates edge patterns from Property Lenses, applies entity bindings with `VALUES`, compiles positive filters, adds projections, applies the supported authorization profile and graph scope, and produces a small library-owned SPARQL AST. Value-contract compatibility alone never emits a population pattern. User text never becomes a variable name or syntax fragment. RDF terms are parsed and rendered by trusted codecs; there is no assumption that remote SPARQL offers relational-style prepared statements.

After conservative rewrites, a dialect renderer produces SPARQL 1.1 text. The library parses that text again and checks that the query form, constants, functions, graph IRIs, structural complexity, and limits correspond to the validated plan, trusted catalog, authorization scope, and policy. This second pass protects against compiler and plugin defects. Version 0.1 emits `SELECT` and `ASK`; it does not emit `DESCRIBE`, `CONSTRUCT`, `SERVICE`, update operations, custom functions, or property-path repetition.

Population selection follows the explicitly selected profile rather than a global “always add a type” rule. A `direct_type` selector emits an explicit `rdf:type` pattern, while a target-node selector emits `VALUES` and no implicit type pattern. Joined nodes receive only their edge and selected value-contract constraints unless the plan explicitly includes a separately justified Population Selector. A later subclass-aware strategy may use a broader pattern or omit it only when the pinned `DatasetScope` names an entailment regime that the adapter proves equivalent. Named-graph provenance is similarly explicit: the compiler MUST NOT rewrite a default-union query as `GRAPH ?g` unless the store’s Dataset Scope makes that transformation valid.

The compiler emits an `EvidenceMap` together with each query and obtains any hidden node identities required for row keys as part of the core answer relation. After the limited result is fixed, it may issue a bounded evidence query keyed by those identities to retrieve edge endpoints and provenance without changing answer multiplicity or result-bound semantics. Hidden bindings count against row and byte budgets. `TriplePatternMatchEvidence` always records physical RDF triple orientation, so an inverse Property Lens reverses the plan traversal when it writes the evidence item. Evidence also records the Population Selector used for each enumerated root.

### 12.2 Graph store contract

All store operations receive the pinned run context so deadline, cancellation, authorization identity, graph scope, response limits, and trace identity remain consistent. A local RDFLib adapter and a remote endpoint adapter implement the same semantic contract even though only the latter speaks the SPARQL Protocol.

```python
class GraphStore(Protocol):
    async def capabilities(self, *, context: RunContext) -> EndpointCapabilities: ...
    async def select(
        self,
        query: CompiledQuery,
        *,
        context: RunContext,
        max_rows: int,
        max_bytes: int,
    ) -> SelectResult: ...
    async def ask(
        self,
        query: CompiledQuery,
        *,
        context: RunContext,
        max_bytes: int,
    ) -> AskResult: ...
```

`SelectResult` and `AskResult` are immutable execution envelopes. Both contain the execution and query identities, completion status, normalized issues, byte and row limits, interruption reason, available store revision, and the pinned scope or its digest. `AskResult` additionally contains `value: bool | None`; `None` is required when execution did not complete far enough to establish a Boolean. Evidence construction MUST NOT infer completion merely because no exception was raised.

The remote adapter uses an injected asynchronous HTTP client, read-only credentials, connection pooling, content negotiation, compressed and uncompressed byte limits, streaming parsers where practical, and normalized errors. Authentication refresh, `Retry-After`, jitter, and transport retries are adapter concerns governed by a shared retry classification. The local adapter restricts parser and query features that could read files or network resources when data is untrusted.

### 12.3 Diagnosis and bounded repair

Syntax failure after local parsing normally indicates a dialect or renderer defect. The engine first classifies the endpoint error, compares the query with pinned capabilities, and applies only semantics-preserving deterministic rewrites. A planner repair is considered only when the operation itself cannot be implemented as bound. Timeout and result-limit failures may move labels to a secondary query, request fewer hidden variables, or reorder selective patterns, but they cannot drop a user constraint or weaken the authoritative Answer Extent. A policy ceiling that prevents a required complete answer produces `PolicyLimited`.

An empty result is a valid result only when the exact positive core query completed. Version 0.1 does not run absence probes or semantic repair. It returns `NoMatch` with Dataset and Authorization Scope wording only when the core execution is complete, no condition was relaxed, and—when a model authored the plan—all material intent items are represented. Diagnostic probes may be introduced later, but their failure can never strengthen or replace the core outcome.

Model-provider failures, authorization failures, cancellation, parser exhaustion, optional enrichment failures, and inconsistent split-query observations are represented in a stage result envelope. Optional enrichment failure may produce an answered-but-degraded outcome; core query or authorization failure cannot. Circuit breakers are scoped by endpoint and credential or tenant boundary so one failing deployment does not suppress unrelated traffic.

---

## 13. Evidence and answer semantics

### 13.1 Evidence variants

Evidence is a family of typed observations, not a bag of strings called facts. Endpoint terms are first normalized into a discriminated union of IRIs, blank nodes, literals, and capability-gated triple terms instead of being coerced immediately into ambiguous Python primitives; the narrower plan-value union in section 10 deliberately excludes blank nodes and triple terms. The evidence type says what the engine observed and prevents a query-level result from being presented as a source assertion.

| Evidence type | Meaning |
|---|---|
| `QueryResultEvidence` | A completed `ASK` result or the presence or absence of `SELECT` solutions, with query digest, Dataset Scope, Authorization Scope digest, execution identity, and completeness. It does not identify any particular edge. |
| `TriplePatternMatchEvidence` | A subject, predicate, and object satisfied a direct triple pattern. Its assertion status is `unknown` unless an adapter-specific proof establishes `asserted` or `entailed`; a source graph is present only when established. |
| `RowEvidence` | A normalized answer row plus the evidence IDs that support the row. |
| `PathReachabilityEvidence` | Two terms matched a catalog path, with an explicit indication of whether intermediate witness triples were materialized. This is deferred beyond version 0.1. |
| `AbsenceEvidence` | A correlated pattern had no match under a precise Dataset Scope, Authorization Scope, revision, and execution. |
| `AggregateEvidence` | An operator was applied to a declared operand and source row set with explicit distinctness, grouping, and truncation semantics. This is introduced with the future aggregate algebra. |
| `ValidationFindingEvidence` | A value-contract or SHACL validation operation produced a stated finding. |
| `TextChunkEvidence` | A bounded document excerpt was retrieved from a recorded source under a document policy. |

Version 0.1 always creates `QueryResultEvidence`. A false positive `ASK` or empty positive `SELECT` means only that the completed validated query had no visible solution in the pinned Dataset and Authorization Scopes; it does not manufacture `AbsenceEvidence` for any individual edge. A true `ASK` supports the deterministic statement that the query found a solution in those scopes. If an application needs edge-level positive evidence, the compiler runs a bounded witness `SELECT` under the same plan, scope, and budget. Direct and inverse predicate queries may also create `TriplePatternMatchEvidence`, whose items use physical RDF subject-predicate-object orientation even when the Property Lens traverses the predicate in reverse. `AbsenceEvidence` remains a reserved later-profile type.

The safe assertion status for ordinary SPARQL results is `unknown`. An adapter may emit `asserted` only when a provenance-aware operation establishes that the physical triple occurs in the selected graph, and it may emit `entailed` only when the store can distinguish an entailed match from an assertion. A projected label is presentation evidence and does not replace the resource IRI as identity. Evidence and row IDs are deterministic within the Dataset Scope and execution identity declared by the packet, while source responses may be retained in protected debug storage subject to policy.

```python
class DatasetScope(BaseModel):
    dataset_id: str
    graph_scope: tuple[IriTerm, ...]
    default_graph_mode: Literal["store_default", "explicit_default", "union"]
    entailment_regime: Literal["none", "simple", "rdfs", "declared_custom"]
    entailment_profile_id: str | None = None
    dataset_revision: str | None = None
    consistency: Literal["snapshot", "single_query", "best_effort"]
    completeness_profile_id: str | None = None


class EvidencePacket(BaseModel):
    execution_id: str
    authoritative_question: str
    catalog_revision: str
    policy_revision: str
    authorization_scope_digest: str
    capability_revision: str
    dataset_scope: DatasetScope
    intent_digest: str | None = None
    plan_digest: str
    result_request_digest: str
    query_digests: tuple[str, ...]
    evidence: tuple[EvidenceItem, ...]
    issues: tuple[ValidationIssue, ...] = ()
    execution_complete: bool
    answer_extent_satisfied: bool
    answer_set_completeness: Literal["complete", "incomplete", "unknown"]
    ordering: Literal["unordered"] = "unordered"
    continuation: Literal["unsupported"] = "unsupported"
    enrichment_complete: bool
```

`entailment_profile_id` is required exactly when `entailment_regime="declared_custom"`; the typed regime label alone is never enough to identify custom semantics. `execution_complete` means that the core query completed without a transport, parser, byte, row, cancellation, or deadline interruption. `answer_extent_satisfied` means that every row requested by the authoritative Answer Extent was returned; for an examples request this may be true even though more matches exist. For a `SelectPlan`, `answer_set_completeness` is `complete` only when a complete-set request finished within policy or a successfully completed sentinel check establishes that the answer set ended within the limited result. For a `BooleanPlan`, a completed `AskResult` with either `True` or `False` establishes the complete Boolean answer even though it does not enumerate solution mappings. None of these fields means that the dataset describes the whole real world. `enrichment_complete` concerns optional labels and provenance in version 0.1 and later validation or documents. When a store lacks revision metadata, a limited result is unordered, or split queries are not snapshot-consistent, the packet records that limitation and result caching is disabled by default unless an application explicitly accepts the weaker semantics.

The evidence and outcome models enforce these legal state combinations:

| State or outcome | Required invariants |
|---|---|
| `Answered` | Core `execution_complete=True`; `answer_extent_satisfied=True`; every claim backed by compatible core evidence; incomplete `SelectPlan` answer sets disclosed and permitted only for an explicit examples request |
| `NoMatch` | Core `execution_complete=True`; completed `QueryResultEvidence` showing an empty `SelectPlan` or false `BooleanPlan`; `answer_set_completeness="complete"`; all material model intent represented when applicable; wording relative to Dataset and Authorization Scopes |
| `PolicyLimited` | A required operation or complete Answer Extent was refused; MUST NOT carry an apparently complete answer |
| `Failed` | Core execution or parsing could not establish a result; false or missing Boolean values and partial empty rows MUST NOT become `NoMatch` |
| `answer_set_completeness="complete"` | Accepted complete `SelectPlan`, a successfully completed no-sentinel check, or a completed `BooleanPlan` result |
| `answer_extent_satisfied=False` | `Answered` and `NoMatch` are prohibited; for a `SelectPlan`, answer-set completeness is not `complete` |
| `enrichment_complete=False` | Core evidence remains valid and only an explicitly degraded `Answered` may be returned |
| Future `AbsenceEvidence` | Completed correlated check plus a named compatible Completeness Profile; version 0.1 never emits it |

All evidence items in a packet share its pinned revisions and scopes unless an auxiliary item names a compatible subquery execution identity. Mixed-dataset, mixed-authorization, or unpinned evidence is rejected.

### 13.2 Validation taxonomy

Result validation first parses endpoint bindings into RDF terms and checks each projection’s term kind, datatype, requiredness, and source mapping. Evidence validation then checks that evidence items correspond to compiler-produced evidence maps and the pinned query scope. Optional focused SHACL validation may later fetch the properties required for a selected shape and focus node before invoking pySHACL; running a minimum-cardinality shape over a partial result subgraph would otherwise create false failures. Answer validation finally checks evidence IDs, claim/evidence compatibility, completeness language, policy-sensitive locators, and any deterministic claim templates.

These stages have different guarantees and should not be collapsed under the word “validation.” Value-contract validation can show that an endpoint value contradicts the compiled contract. Focused SHACL validation can show conformance within the fetched closure and selected shapes. Citation validation can show that a claim refers to existing compatible evidence. None of them alone proves real-world truth.

### 13.3 Typed outcomes

The public `AnswerOutcome` is a discriminated union so applications can respond without parsing prose. `Answered` contains a grounded answer and evidence. `NoMatch` contains valid empty-result evidence and scope wording. `Ambiguous` contains unresolved entity or schema candidates. `PolicyLimited` identifies a disallowed operation or a complete Answer Extent that policy cannot satisfy without exposing protected details. `Unsupported` identifies a semantic feature the algebra or endpoint cannot represent. `Failed` contains a safe normalized failure for provider, store, parser, or internal errors. An answered outcome may also be marked degraded when optional enrichment failed.

A grounded claim has text, evidence IDs, a claim kind, and the validation level applied. Simple booleans, entity lists, and tables SHOULD use deterministic rendering so the mapping from row evidence to claim is exact. A model answerer is useful for explanation and summarization, but it receives only the evidence packet, must preserve graph-versus-text distinctions, and must mention truncation, ambiguity, missing provenance, or best-effort consistency.

---

## 14. Hybrid graph and document retrieval

Document retrieval is optional and subordinate to the graph plan. In the recommended late-fusion flow, the core SPARQL query identifies answer entities and document IDs, a `DocumentLinkResolver` converts those graph results into filters, and a retriever searches only the linked documents. Graph evidence determines set membership and numerical results; text can explain those graph observations or support separately labeled text-only claims. Applications may prohibit text-only claims entirely.

Early fusion is permitted only for entity discovery. A document or entity embedding may suggest candidate IRIs when a phrase is absent from the graph’s label index, but those candidates still pass type checks, ambiguity policy, plan validation, authorization, and graph confirmation before they become evidence. Retrieved chunks are untrusted data, not instructions, and include stable IDs, source locators, linked entities, scores, and source-policy tags.

Document access follows the same `AuthorizationScope` as graph access. Every filter, chunk, cache entry, prompt, citation, and trace is partitioned by tenant and policy scope. A model provider receives document or evidence content only when the application has explicitly configured provider transmission, data residency, retention, and redaction rules.

---

## 15. Public API

The high-level API should be easy for local use while keeping every security-critical input explicit. Constructors are synchronous because they assemble configuration and adapters; catalog construction and I/O remain asynchronous. `answer()` returns an `AnswerOutcome` and never raises for an expected ambiguity, no-match, policy, or unsupported condition. Programmer errors and unrecoverable initialization defects may still raise documented exceptions.

```python
from shapelens import (
    AnswerRequest,
    LocalAuthorizationProvider,
    LocalDataset,
    LocalShapeFile,
    QueryPolicy,
    ShapeRAG,
    TrustedSourceAdmission,
)

rag = ShapeRAG.from_rdflib(
    data=LocalDataset.from_file("data.ttl"),
    shapes=LocalShapeFile(
        path="shapes.ttl",
        admission=TrustedSourceAdmission(manifest="shapes.lock"),
    ),
    authorization=LocalAuthorizationProvider(),
    policy=QueryPolicy.safe_local_defaults(),
)

await rag.build_catalog()
outcome = await rag.answer(
    AnswerRequest.complete(
        "Which employees worked on Project X and have AI expertise?"
    ),
    security_context=security_context_provider.current(),
)
```

A remote store uses the same facade but an explicit adapter:

```python
rag = ShapeRAG.from_endpoint(
    endpoint_url="https://kg.example/sparql",
    shapes=LocalShapeFile(
        path="company-shapes.ttl",
        admission=TrustedSourceAdmission(manifest="company-shapes.lock"),
    ),
    credentials=read_only_credentials,
    authorization=endpoint_authorization_provider,
    dataset_scope=declared_dataset_scope,
    policy=QueryPolicy.safe_remote_defaults(),
    planner=planner,
)
```

The remote constructor is a later-profile API, not part of version 0.1. Shape sources use explicit discriminated types; a bare string never ambiguously means a path, URL, RDF document, or identifier. `security_context` comes from a trusted authentication integration. User-controlled language, answer extent, and presentation preferences belong to `AnswerRequest` and cannot construct their own Authorization or Dataset Scope.

The proposed staged API uses consistent inputs. `retrieve_schema(question, context)` returns candidates pinned to a catalog revision. `plan(question, candidates, context)` returns a bound plan. `compile(plan, context)` returns a compiled execution plan and evidence map. `execute(compiled, context)` returns normalized core results. `build_evidence(plan, compiled, execution, context)` returns an evidence packet. `render_answer(question, evidence, context)` returns an `AnswerOutcome`. The engine constructs `RunContext` from trusted providers plus user-controlled presentation options; an ordinary caller does not author its Authorization or Dataset Scope. The context pins revisions, budget, deadline, cancellation scope, authorization, language, and trace identity and is threaded through every I/O boundary.

```python
candidates = await rag.retrieve_schema(question, context=context)
plan = await rag.plan(question, candidates=candidates, context=context)
compiled = rag.compile(plan, context=context)
execution = await rag.execute(compiled, context=context)
evidence = await rag.build_evidence(
    plan,
    compiled,
    execution,
    context=context,
)
outcome = await rag.render_answer(question, evidence=evidence, context=context)
```

`explain(request, security_context)` performs retrieval, resolution, planning, validation, authorization description, and compilation without execution by default. It returns structured interpretations, candidate scores, the bound plan, policy and capability decisions, generated SPARQL, and warnings, but never hidden model reasoning. `answer_stream()` emits typed stage events followed by buffered or validated answer content; applications that cannot retract text SHOULD buffer prose until answer validation finishes.

---

## 16. Extensibility and package boundaries

The core depends on small protocols for shape sources, indexes, planners, graph stores, document retrievers, query dialects, provenance strategies, caches, and trace sinks. Pydantic is a core dependency because the models are part of the trust boundary. Pydantic AI, pySHACL, persistent indexes, remote-store authentication packages, embeddings, and vendor dialects are optional extras. An application can therefore use caller-authored plans and deterministic rendering without installing a model framework.

The proposed package structure follows the lifecycle rather than mirroring every class. `shapes` owns loading, normalization, compilation, catalog identity, and publication. `retrieval` owns shape indexing, structural expansion, context packing, and entity resolution. `planning` owns intent extraction, plan creation, validation, and coverage. `sparql` owns the internal AST, authorization injection, compilation, policy, optimization, rendering, and dialects. `stores` owns local and remote execution. `evidence` owns normalization, evidence maps, provenance, and validation. `answering` owns deterministic rendering, optional model synthesis, and outcome validation. `pipeline` owns revisions, budgets, cancellation, stage results, and repair.

Constraint and dialect plugins may add operations only by implementing the full typed chain from recognized source construct through plan validation, AST compilation, evidence construction, and conformance tests. In-process plugins are fully trusted application code: a post-render policy check limits their query output but cannot stop arbitrary Python from reading files, using the network, consuming resources, or accessing secrets. Untrusted extensions are out of scope unless a future release defines an out-of-process protocol and isolation boundary.

Third-party plugin discovery through Python entry points is opt-in. Security-sensitive deployments SHOULD pass an explicit plugin list and SHOULD pin package versions and hashes. Catalog artifacts contain data only and never executable plugin code.

---

## 17. Security and privacy

The threat model assumes an attacker can control user text and may also control graph, shape, or document content. Injection threats include instructions hidden in labels or descriptions, SPARQL syntax smuggled through terms, destructive query forms, and SSRF through imports, parsers, or federation. The design must also tolerate a malicious or compromised endpoint and a trusted but defective plugin.

Resource and privacy threats are equally important. Paths, regex, canonicalization, recursive shapes, huge or compressed responses, and Cartesian products can exhaust compute or memory, while caches, traces, citations, optional documents, and model-provider retention can disclose data across tenants or jurisdictions. These risks are controlled at several boundaries rather than delegated to a prompt.

Shape metadata and evidence are always delimited as untrusted data in prompts, even when their source was admitted to influence the executable catalog. Source trust authorizes deterministic compilation; it does not make labels or descriptions safe instructions. Legal operations are conveyed structurally, and model output is independently validated. Credentials, raw HTTP clients, unrestricted store tools, source-admission controls, and configuration authority never enter a model dependency. The query surface is read-only, AST-based, and bounded; `SERVICE`, updates, remote imports, custom functions, regex, and negation are disabled in the first release.

Authorization is enforced before lens cards reach the planner, during plan validation, in compiler-injected constraints or endpoint credentials, in every diagnostic or enrichment query, before content reaches an answer model, and again during citation and trace rendering. Policy distinguishes projection, filtering, joining, existence testing, and later aggregation because hiding a sensitive value while allowing a count or existence test can still leak it. Minimum cohort and inference controls are future policy features and are listed as an open question rather than implied by a `sensitive` Boolean.

Caches are separate by purpose. A public schema cache may be shared only when its catalog and policy scope are identical. Plan-template, entity-resolution, result, evidence, and model-response caches include catalog, compiler, capability, graph, tenant, authorization, policy, and dataset revision as appropriate; sensitive caches require encryption and retention limits, and cache hits are re-authorized. When a dataset revision is unavailable, result and evidence caching are off by default or use an explicitly accepted freshness window.

Default logs contain stable IDs, digests, counts, durations, issue codes, and redacted endpoint names rather than query literals, entity values, rows, document text, credentials, or source locators. Debug capture is explicit, access-controlled, encrypted where required, and independently retained. Provider transmission of schema or evidence is also explicit and governed by application configuration for redaction, residency, retention, and acceptable data classes.

---

## 18. Operations, observability, and performance

Every run produces spans for catalog lookup, schema retrieval, entity resolution, each model request, plan validation, authorization injection, compilation, each store query, evidence construction, optional validation and document retrieval, answer rendering, and outcome validation. Attributes contain revisions, counts, durations, cache decisions, retry classes, completeness flags, and issue codes, not hidden chain-of-thought. A reproducibility record retains the plan and query digests, model and prompt-template identifiers, catalog and policy revisions, Dataset Scope, evidence IDs, and renderer version subject to retention policy.

Useful service metrics include catalog publication success and duration, retrieval recall on evaluation cases, ambiguity rate, plan rejection reasons, query complexity, endpoint latency and failure class, empty-result diagnoses, evidence completeness, claim-validation level, cache isolation, end-to-end cost, and deadline exhaustion. Production phases must define SLOs and alerts for endpoint availability, planner availability, p95 latency, policy failures, catalog age, cache health, and degraded outcomes rather than merely emitting raw telemetry.

The expected model-enabled fast path has one schema lookup, zero or one batched entity-resolution query, one planner call, one core graph query, and deterministic rendering for simple results; version 0.1 substitutes a caller-authored plan and makes no model call. Optional labels, provenance, and documents may run concurrently after core results in later profiles. Remote results are parsed incrementally where possible, and byte and row limits are enforced before building large Pydantic object trees. Backpressure limits concurrent model, endpoint, parser, and enrichment work per tenant and per process.

Catalog artifacts have a versioned non-executable format, checksums, compatibility rules, and migration hooks. Deployment warms a new artifact before atomic publication and preserves a rollback artifact. Multi-worker coordination, credential rotation, graceful shutdown, request draining, resource-pool sizing, corruption recovery, and refresh scheduling become phase exit criteria before the library is described as production-ready.

---

## 19. Testing and evaluation

Unit tests cover RDF term parsing and rendering, path normalization and cycle limits, Boolean constraint preservation, Population Selector semantics, Derivation Origin and Shape Source Trust gates, stable IRI-backed identity, join construction, plan normalization, retrieval scoring, every validator rule, AST rendering and parse round trips, authorization application, typed store-result envelopes, evidence IDs, evidence-state invariants, typed outcomes, and citation policy. Property-based tests generate RDF terms, safe path ASTs, connected plans, literal escapes, bounded shape structures, and semantically equivalent plan orderings. Fuzzers target RDF parsers, SPARQL Results parsers, compressed responses, cyclic RDF lists, invalid Unicode, and oversized literals and IRIs. Canonicalization fuzzing enters only with the later blank-node identity profile.

Golden query tests are useful but insufficient because matching text or syntax does not prove semantic equivalence. Differential tests execute a compiled plan and a reviewed reference query over generated datasets and compare solution mappings. Version 0.1 regression fixtures cover subclass-only instances under the `direct_type` selector profile, true and false positive `ASK`, empty positive `SELECT`, RDF terms that differ under `sameTerm` and value equality, rejection of potentially multi-valued scalar projections, successful and interrupted sentinel checks, and inverse edges whose evidence must use physical RDF orientation. Metamorphic tests prove that canonical ordering and optimizer rewrites preserve results under their declared assumptions. Mutation tests alter source trust, authorization, and validation rules to ensure the test suite detects weakened policy.

The following cases are explicit release gates for the applicable phase:

1. An otherwise valid constraint from an `untrusted` shape source attempts to expose a protected predicate and never becomes executable; assessing the same digest as `trusted` changes the catalog revision and eligibility.
2. An untrusted member of an import or Application Overlay closure prevents that closure from authorizing operations.
3. A targetless lens contract may validate a bound relationship value but cannot introduce an unbound root.
4. A property class contract joins to a context-specific lens with a target-node selector without importing that selector or narrowing the value population.
5. An unbound root with a missing or unauthorized selector is rejected, and non-IRI `sh:targetNode` declarations remain diagnostic-only.
6. Duplicate existence representations, edges, filters, projections, and ambiguous field reuse are rejected or canonicalized according to the single normative rule; equivalent input order yields the same digest and query.
7. Two potentially multi-valued field projections are rejected in version 0.1 rather than producing a Cartesian product.
8. A model-authored plan that omits a user condition, invents a restrictive condition, or inserts an unjustified example count fails coverage validation; these tests gate Phase 2 rather than the deterministic kernel.
9. A false `ASK` or empty `SELECT` caused by Authorization Scope is worded as no visible match and never as a stronger property-completeness claim.
10. A false or missing Boolean after partial, malformed, byte-limited, cancelled, or timed-out execution cannot become `NoMatch`.
11. Contradictory evidence completeness flags, incompatible auxiliary-query scopes, and a complete claim over an interrupted sentinel check are rejected.
12. When absence is later introduced, an empty positive query cannot be converted into property-level `AbsenceEvidence`, and every negative operator requires a compatible named Completeness Profile.

The shared store suite runs against RDFLib graph and dataset modes first, then at least two materially different remote implementations. It covers named-graph semantics, endpoint errors, compressed and oversized responses, deadlines, cancellation, retry classification, partial enrichment, hot catalog swaps, cache isolation, authorization on every auxiliary query, and best-effort split-query inconsistency. Plugin packages must pass contract tests for normalization, validation, compilation, policy, evidence construction, and failure behavior.

End-to-end cases record the question, data and shape fixtures, expected intent constraints, acceptable lens set, entity resolution, plan equivalence class, expected solution mappings, evidence relations, outcome variant, and allowed answer claims. Evaluation reports schema-retrieval recall, entity accuracy, plan validity and semantic accuracy, execution accuracy, evidence completeness, deterministic claim correctness, free-prose support, latency, and cost separately. A single end-answer score would hide which trust boundary failed.

---

## 20. Delivery plan

### Phase 0: semantic spikes

The first phase validates one claim before a package architecture hardens around it: trusted SHACL-derived contextual operations can compile into a small typed algebra with correct, inspectable query semantics. It uses one fixed, trusted, local RDFLib dataset and IRI-backed node and property shape fixture; direct and inverse predicates; direct-type and IRI target-node Population Selectors; hand-authored connected positive `SelectPlan` and `BooleanPlan` cases; typed `SelectResult` and `AskResult`; exact RDF-term normalization; and reviewed differential queries. There is no catalog retrieval, model provider, absence, blank-node public shape identity, generic row-level authorization, remote store, documents, plugins, or canonicalization experiment. The exit criterion is reviewed executable semantics and passing differential tests for selection, joins, direct/inverse orientation, positive true and false Boolean results, empty results, and interrupted execution.

### Phase 1: deterministic kernel and version 0.1

After the Phase 0 semantics are accepted, the first release adds trusted source descriptors and admission, an IRI-backed catalog, a minimal in-memory lexical index, separate Population Selectors, canonical typed plans and validators, the declared local Authorization Scope profile, portable SPARQL AST and renderer, RDFLib store, query-result, row, and triple-pattern-match evidence, evidence-state validators, deterministic answer rendering, `AnswerOutcome`, and debug explanation. Scalar field projection is limited to eligible single-valued contracts. Plans are fixtures or caller-authored; no model is required. The accepted semantics are extracted into `SPEC-0.1.md` with stable requirement IDs mapped to unit, property, differential, metamorphic, adversarial, source-trust, and authorization tests.

### Phase 2: structured planning

After resolving OQ-001, OQ-009, OQ-010, OQ-013, and OQ-017, this phase adds the candidate context packer, label-based entity resolver, mandatory intent items and coverage mapping, Pydantic AI planner adapter, bounded output retry, fake-model tests, prompt versioning, and evaluation tooling. A human-labelled benchmark must separately establish extraction fidelity, internal coverage, lens-retrieval recall, entity accuracy, plan semantic accuracy, unsupported-outcome precision, latency, and cost against declared thresholds before the planner becomes the recommended path.

### Phase 3: remote stores and production controls

After resolving OQ-004, OQ-005, OQ-007, OQ-011, OQ-012, OQ-014, and OQ-015, the remote phase declares the supported protected-data deployment profiles and adds an asynchronous SPARQL Protocol client, capability configuration and safe probing, authentication hooks, result streaming, normalized failures, deadlines and cancellation, retry classification, circuit breakers, named-graph scopes, catalog publication, readiness, backpressure, and operational SLOs. The same behavioral suite runs against at least two remote stores, and authorization-relative results and limitations of snapshot consistency are surfaced in evidence.

### Phase 4: richer evidence and validation

After resolving OQ-006 and the relevant parts of OQ-002, OQ-003, and OQ-018, this phase may add a separately specified negative algebra with named Completeness Profiles and authorization-relative `AbsenceEvidence`. It also adds optional pySHACL meta-validation, focused shape-aware evidence closure, validation-finding evidence, provenance strategies, and carefully bounded `CONSTRUCT` support if needed, followed by separately specified aggregate algebra and evidence. Each new feature updates the normative matrix, threat model, compiler, evidence types, differential tests, and answer policy together.

### Phase 5: hybrid retrieval and scale

After resolving OQ-008, OQ-016, and any still-relevant provider or cache questions, the final planned phase may add a budgeted RDFC-1.0 blank-node identity profile, graph-guided document retrieval, provider-transmission policy, typed model answering, persistent catalogs, SQLite FTS, optional embedding indexes, incremental rebuild, graph statistics, revision-aware caches, and supported dialect plugins. Sequence, alternative, and repeating paths are considered only after path witness, cost, and endpoint portability semantics are agreed.

---

## 21. Risks and mitigations

**Incomplete, hostile, or validation-oriented shapes.** A shapes graph may omit queryable relationships, expose a protected predicate, or contain constraints meaningful only during validation. ShapeLens reports these gaps, admits executable statements only from `trusted` source closures, and never elevates ontology or sampled hints to executable authority by default. `untrusted` shapes may be retained for diagnostics but cannot expand the planner-visible surface. The practical mitigation is explicit source admission, better shape metadata, and stable IRI-backed shapes, not optimistic inference.

**Context-specific shapes and accidental disclosure.** Several shapes may describe the same class for different audiences. The catalog preserves each context and authorization applies to every operation, including filters, existence, auxiliary queries, documents, and citations. A lens is a semantic view, not a security view unless the full enforcement path makes it one.

**Context selector accidentally narrows a join.** A public-directory or target-node selector may describe only part of the values accepted by a relationship contract. Plans name Population Selectors independently, joined nodes receive only their selected Value Contract Branch by default, and differential tests reject hidden selector import.

**An algebra that is too small.** Users may encounter questions that version 0.1 cannot express. The system returns `Unsupported`, measures those intent categories, and extends the algebra with typed nodes only when their relational semantics, authorization, evidence, and tests are understood. Raw SPARQL remains a separate trusted expert API and never a model-output escape hatch.

**Endpoint variance and inconsistent snapshots.** SPARQL syntax, performance, entailment, default graphs, and consistency differ. Conservative 1.1 queries, pinned capabilities, dialect tests, and an explicit Dataset Scope reduce surprises. When a store cannot provide a revision or snapshot across split queries, ShapeLens records best-effort consistency and avoids claims that require stronger proof.

**Evidence that is valid but insufficient.** A query row can be well typed without supporting the wording of an answer. Distinct evidence variants, claim kinds, deterministic rendering, proof-strength labels, and completeness flags prevent citation existence from masquerading as entailment. Free prose remains a weaker, explicitly described validation level.

**Cost and retry amplification.** Model repairs, endpoint probes, and enrichments can multiply latency during failure. A central deadline and query/model budgets, deterministic diagnosis before repair, classified retries, circuit breakers, and deterministic answers keep amplification bounded. Optional enrichments fail independently from core evidence.

**Adversarial shape graphs and endpoint responses.** Recursive blank nodes, future canonicalization work, imports, huge literals, compressed payloads, and malicious metadata can exhaust resources or inject instructions. Bounded parsing, budgeted canonicalization when enabled, network denial by default, streaming size checks, structured prompts, and parser fuzzing are required controls.

**Plugin trust.** In-process Python plugins can bypass application controls regardless of AST checks. They are treated as fully trusted deployment code, explicitly loaded and pinned. Supporting untrusted plugins would require process isolation and is not promised by this design.

---

## 22. Architectural decisions

### ADR-001: Models do not generate raw SPARQL

**Decision.** A model returns a typed, lens-bound plan, and ordinary Python compiles it. This reduces schema invention, makes authorization and policy enforceable, supports deterministic testing, and isolates endpoint dialects. A trusted caller may use a separate expert SPARQL API, but that API is outside the agent path.

### ADR-002: Lens contracts and population selectors are separate

**Decision.** Shapes for the same class remain separate contextual lens contracts. Supported target declarations compile into independently identified Population Selectors, and a selector is applied only when a plan names it. Joined values receive their selected Property Lens contract branch, not the target selector of a context lens. An Application Overlay may augment one primary shape or supply a selector, but it does not merge several primary shapes into one lens. The alternative would let a public-directory or target-node context silently narrow unrelated joins.

### ADR-003: Executable fields require eligible derivation and trusted source

**Decision.** Every derived field records a Derivation Origin, source references, and a Shape Source Trust assessment for its complete source closure. A supported shape constraint is executable only when its source and import closure are `trusted`; an Application Overlay additionally requires its complete referenced-shape and dependency closure to be `trusted`. Ontology and sampled hints may rank or explain but do not authorize by default. Parsing success and SHACL conformance do not establish trust. The alternative would let a syntactically valid hostile shape or untrusted dependency expand the query surface.

### ADR-004: The library owns a small query algebra

**Decision.** Version 0.1 implements canonically normalized connected positive conjunctive `SELECT` and Boolean plans with direct and inverse edges, exact identity and positive existence filters, node projections, and eligible single-valued scalar projections. Negation and richer SPARQL enter through typed additions with defined semantics rather than generic syntax trees supplied by a model. Plan digests exclude later trusted authorization injection.

### ADR-005: Evidence is typed by proof kind

**Decision.** Query results, triple-pattern matches, reachability, absence, aggregates, validation findings, rows, and text chunks are distinct evidence variants. A single generic fact type cannot state the truth conditions of all of them and would encourage answers stronger than the observations support. Reserved variants such as absence are not emitted until their algebra and completeness profiles exist.

### ADR-006: Every run pins revisions and Dataset Scope

**Decision.** Catalog, source-trust policy, policy, authorization, capabilities, compiler, and available dataset revision are fixed for a run. Atomic catalog publication and explicit best-effort consistency make retries, split queries, caches, and audits understandable. Strong property-level absence later requires a named Completeness Profile rather than a dataset-wide Boolean.

### ADR-007: Authorization is outside model control

**Decision.** Authorization is trusted runtime input applied to primary and auxiliary work. Version 0.1 claims only its declared trusted-local profile. Endpoint credentials, graph partitions, and compiler-injected mandatory constraints require separately specified and tested deployment profiles; lens filtering alone is defense in depth, not an authorization model.

### ADR-008: Pydantic AI is an optional adapter

**Decision.** Pydantic remains core because typed models protect trust boundaries, while Pydantic AI is the recommended optional planner and answerer integration. The deterministic kernel, tests, and caller-authored plans work without a model provider.

### ADR-009: New standards are capability-gated

**Decision.** SHACL 1.0 defines the source-vocabulary baseline, the ShapeLens feature matrix defines the queryable subset, and SPARQL 1.1 defines the portable query target. SHACL 1.2 and SPARQL 1.2 features remain explicit capabilities because their specifications and implementation coverage continue to evolve. RDFC-1.0 is reserved for a later blank-node identity profile after its extraction boundary and resource budgets are specified.

### ADR-010: Answer extent is outside model control

**Decision.** The authoritative request records whether the user requires a complete set or explicitly requested a bounded number of examples, while Query Policy owns safe execution ceilings. `BoundQueryPlan` contains neither a free planner limit nor an `exhaustive` switch. A model may extract an extent only with an intent item linked to the authoritative question. This prevents an otherwise legal plan from silently weakening the requested answer.

---

## 23. Open questions

The following questions are intentionally unresolved. They are decisions that can materially change correctness, security, or public compatibility, so implementation should not bury them in defaults. “Resolve before” identifies the phase that cannot begin until the question is answered.

| ID | Open question | Why it matters | Resolve before |
|---|---|---|---|
| OQ-001 | Which human-labelled application scenarios, fidelity labels, baselines, and thresholds establish that lens-based retrieval and planning outperform static schema descriptions or direct query generation? | Valid compilation proves legality, not question understanding or comparative planning value. | Phase 2 |
| OQ-002 | Which additional SHACL target declarations compile into Population Selectors, and what selector identity, composition, graph-scope, cost, and evidence rules accompany them? | Population selection changes enumeration semantics and must remain separate from Value Contracts. | Phase 4 |
| OQ-003 | Which lexical search, ordered comparison, Boolean filter, union, optional traversal, aggregation, grouping, negative, and stable-pagination nodes enter the next algebra, and what are their formal multiset and normalization semantics? | Pagination additionally requires total ordering, tie-break identity, cursor, and snapshot guarantees; ambiguous algebra produces subtly wrong SPARQL even when types validate. | Each feature phase |
| OQ-004 | Which post-0.1 authorization deployments are officially supported: endpoint-native ACLs, graph partitioning, compiler-injected row predicates, or a tested combination? | The answer determines whether row- and value-level restrictions can be guaranteed beyond the trusted-local profile. | Phase 3 |
| OQ-005 | How are mandatory authorization predicates represented without exposing sensitive policy details to plans, traces, or error messages? | Enforcement must be inspectable to operators without leaking it to users or models. | Phase 3 |
| OQ-006 | Which named, property- and population-specific Completeness Profiles may authorize negative operators and absence evidence, and how do they account for Authorization Scope and time? | `NOT EXISTS` and strong absence wording are meaningful only relative to a declared complete dataset slice. | Phase 4 |
| OQ-007 | Must split label, provenance, validation, and document queries share a store snapshot, or is disclosed best-effort consistency sufficient for each evidence class? | Stronger consistency may be unavailable or expensive on remote endpoints. | Phase 3 |
| OQ-008 | What exact extraction algorithm and source boundary feed RDFC-1.0 for blank-node occurrences, and what migration support is promised when those keys change? | Plans and external references need a clear stability guarantee. | Phase 5 |
| OQ-009 | May ontology or sampled hints ever be promoted automatically, or are derivation promotion and source admission always separate explicit application decisions? | Automatic promotion must not bypass either semantic review or Shape Source Trust. | Phase 2 |
| OQ-010 | Which ambiguity threshold and interaction model should resolvers use, and when may an application request union-of-candidates semantics? | A silent union can materially change an answer, while clarification affects API flow. | Phase 2 |
| OQ-011 | Which partial-enrichment failures still permit `Answered`, and how are degradation and retryability represented to applications? | Labels, provenance, validation, and documents have different importance. | Phase 3 |
| OQ-012 | What tenant keys, encryption, retention, invalidation, and re-authorization rules apply to each cache class? | A generic “policy revision” key is insufficient to prevent cross-tenant disclosure. | Phase 3 |
| OQ-013 | Which schema and evidence classes may be sent to external model providers by default, if any? | Provider retention, residency, and confidentiality requirements vary by deployment. | Phase 2 |
| OQ-014 | What catalog publication, coordination, migration, and rollback mechanism is required for multi-worker deployments? | In-flight revision consistency and safe recovery depend on it. | Phase 3 |
| OQ-015 | Which endpoint assumptions about default graphs, entailment, blank-node identity, transaction isolation, and revision metadata can adapters promise? | These assumptions determine query equivalence and evidence truth conditions. | Phase 3 |
| OQ-016 | Is out-of-process plugin isolation a product goal, or are plugins permanently documented as trusted code? | The answer changes the extension protocol and hosting threat model. | Phase 5 |
| OQ-017 | What proof-strength labels are public, and is model-based claim support checking worth its cost and uncertainty? | Applications need an honest, understandable grounding guarantee. | Phase 2 |
| OQ-018 | Which SHACL 1.2 and SPARQL 1.2 features have enough implementation support to leave experimental profiles? | Version labels alone do not establish portable behavior. | Ongoing |

Resolved questions should be removed from this table only after the decision is added to the appropriate normative section and, when the choice is hard to reverse and genuinely trade-off driven, recorded as an ADR. The implementation should also link tests and evaluation cases to the relevant decision.

---

## 24. Recommendation and references

ShapeLens should proceed as a compiler architecture with a narrow, positive local kernel. Admit trusted shape-source closures, compile supported SHACL into context-specific Shape Lenses and separate Population Selectors, preserve explicit Value Contract Branches, and validate caller-authored plans before compiling conservative SPARQL. Execute within a pinned run context, return typed store envelopes, construct evidence whose type states what was actually observed, and produce an `AnswerOutcome` whose wording does not exceed that evidence. Add model planning only after intent coverage and empirical fidelity evaluation exist; add absence only after named Completeness Profiles exist.

The most important rule remains simple: **the model chooses among semantic operations, while ordinary Python proves that those operations are legal and turns them into graph queries.** The qualifications are equally important: legality is not proof of question fidelity; direct SHACL derivation is not source trust; a Value Contract is not a Population Selector; and a completed empty result is not a real-world completeness claim.

The following primary specifications and official project documentation informed this design and were reviewed on 6 August 2026:

- [Shapes Constraint Language (SHACL), W3C Recommendation](https://www.w3.org/TR/shacl/)
- [SHACL 1.2 Core, W3C Working Draft](https://www.w3.org/TR/shacl12-core/)
- [SHACL 1.2 SPARQL Extensions](https://www.w3.org/TR/shacl12-sparql/)
- [SHACL 1.2 Profiling](https://www.w3.org/TR/shacl12-profiling/)
- [SPARQL 1.1 Query Language](https://www.w3.org/TR/sparql11-query/)
- [SPARQL 1.1 Protocol](https://www.w3.org/TR/sparql11-protocol/)
- [SPARQL 1.2 Query Language, W3C Working Draft](https://www.w3.org/TR/sparql12-query/)
- [SPARQL 1.2 Protocol](https://www.w3.org/TR/sparql12-protocol/)
- [SPARQL 1.2 Service Description](https://www.w3.org/TR/sparql12-service-description/)
- [RDF Dataset Canonicalization 1.0, W3C Recommendation](https://www.w3.org/TR/rdf-canon/)
- [Pydantic models](https://docs.pydantic.dev/latest/concepts/models/)
- [Pydantic discriminated unions](https://docs.pydantic.dev/latest/concepts/unions/#discriminated-unions)
- [Pydantic `TypeAdapter`](https://docs.pydantic.dev/latest/concepts/type_adapter/)
- [Pydantic AI agents](https://ai.pydantic.dev/agents/)
- [Pydantic AI dependencies](https://ai.pydantic.dev/dependencies/)
- [Pydantic AI structured output](https://ai.pydantic.dev/output/)
- [RDFLib documentation](https://rdflib.readthedocs.io/en/stable/)
- [pySHACL official repository](https://github.com/RDFLib/pySHACL)

SHACL 1.2 and SPARQL 1.2 remain evolving Working Drafts at the time of review. ShapeLens should therefore advertise individual tested capabilities and feature profiles rather than infer support from a version number.
