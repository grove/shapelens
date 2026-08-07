# ShapeLens Forge

## RDF- and SHACL-guided discovery of useful, parameterized SPARQL query templates

**Status:** Proposed design  
**Date:** 2026-08-07  
**Revision:** 2 — SHACL-optional discovery and observed-data promotion workflow  
**Intended audience:** ShapeLens maintainers, RDF and SHACL engineers, domain owners, security reviewers, and evaluation owners  
**Proposed location:** The ShapeLens repository as a separately packaged, offline design-time component  
**Working name:** ShapeLens Forge  

---

## 1. Executive summary

ShapeLens Forge is an offline system that proposes useful, reusable SPARQL query templates from four controlled inputs:

1. an RDF graph or a privacy-safe structural profile of that graph;
2. optional trusted and semantically qualified SHACL material or reviewed semantic overlays;
3. a detailed, application-owned domain dossier; and
4. explicit discovery, security, and execution policies.

SHACL is optional for discovery. When no shapes are available, deterministic profiling derives an Observed Semantic Profile from predicates, RDF types, literal kinds, directionality, co-occurrence, and cardinality distributions in the data. These observations are evidence about the pinned dataset, not trusted schema. They can support exploratory query generation and can identify semantic assumptions that require review.

The system uses GPT-5.6 Sol with xhigh reasoning to interpret domain goals and design candidate query templates. The model does not receive authority to publish executable queries, invent trusted graph semantics, make authorization decisions, or serialize unchecked SPARQL for runtime use. It emits a strict, typed Query Template Specification. Deterministic Python validates the proposed graph pattern and its provenance.

In qualified mode, every executable semantic reference resolves against a pinned Shape Catalog built from trusted, semantically qualified shapes or reviewed Executable Semantic Overlays. Forge then constructs a parameterized Bound Query Plan factory, compiles instantiated plans through the existing ShapeLens compiler, and executes test instances under policy limits.

In data-only exploratory mode, candidate operations may reference only structures literally observed in the pinned RDF profile. Forge may compile and execute these candidates in a separate local diagnostic sandbox, but they are not ShapeLens Bound Query Plans, do not receive ShapeLens evidence claims, and cannot be published to a runtime Template Registry. Publication requires explicit semantic promotion: a reviewer records the intended population, relationship meaning, direction, term contract, parameter role, and projection behavior as qualified SHACL material or a qualified Executable Semantic Overlay.

The output is therefore either an exploratory candidate catalog or a publishable reviewed catalog, depending on semantic support. A template can become Published only after deterministic validation, fixture execution, mutation testing, semantic promotion where needed, and explicit domain and RDF review decisions. Published templates are immutable, revisioned artifacts that applications can expose directly or make available to a later constrained template-selection planner.

This design deliberately moves model work to design time. The expensive model is used where broad semantic interpretation and creative coverage are valuable, while the existing ShapeLens runtime remains the authority for catalog meaning, RDF terms, authorization, plan validation, SPARQL compilation, execution, and evidence.

The first release supports only a conservative subset aligned with ShapeLens 0.1: SELECT and positive ASK; direct and inverse predicate relationships; connected positive conjunctions; exact RDF-term equality; positive existence; node projections; qualified scalar field projections for publication; apparent scalar projections marked as unresolved assumptions during exploration; and typed IRI or literal parameters. It excludes SPARQL Update, federation, raw query-fragment parameters, negation, absence claims, aggregation, arbitrary property paths, unbounded exploration, and automatic publication.

The central product claim is intentionally narrow:

> Given RDF data, a domain dossier, and any available reviewed semantic material, ShapeLens Forge can reduce the work required to discover, qualify, and author a high-value catalog of parameterized graph queries.

It does not claim that SHACL is required for discovery, that observed structure is a normative schema, that graph data is complete, or that a model can independently certify semantic correctness.

---

## 2. Motivation

### 2.1 The opportunity

Teams with RDF assets often possess a substantial amount of latent application knowledge:

- The RDF graph reveals predicates, RDF types, term kinds, relationship directions, recurring joins, and approximate cardinalities.
- When present, SHACL node and property shapes describe reviewed contextual structures, paths, value contracts, cardinalities, and targets.
- Domain experts know which decisions, investigations, and operational actions matter.

Turning those assets into an application-facing query catalog is still largely manual. An RDF engineer must inspect instance structure and any available shapes, understand the domain, identify useful graph patterns, decide which observed assumptions are legitimate, choose sensible parameters, write SPARQL, test it against realistic data, document limitations, and repeat the process for every domain.

ShapeLens Forge aims to accelerate that work without collapsing design, execution authority, and validation into one model call.

### 2.2 Why RDF data alone is useful but insufficient

RDF data is sufficient to discover many technically plausible queries. Forge can observe that resources of one type commonly use a predicate, that its objects have another type, that two predicates frequently co-occur, or that a literal is usually an integer. Those observations can support useful query ideation even when the project has no SHACL.

Observed structure is not a semantic contract. A pattern may be accidental, incomplete, historical, tenant-specific, or caused by one data-loading convention. An observed maximum cardinality of one does not prove that a property is normatively scalar. An object’s recurring RDF type does not establish that the predicate is intended to select that population. Missing triples do not establish real-world absence, and a sample cannot authorize access.

Occurrence is also not usefulness. High-frequency values may be operational noise, while rare relationships may be critical during an incident. The Domain Dossier therefore owns the definition of usefulness. It describes actors, decisions, recurring tasks, risks, desired result forms, and prohibited information flows. Data shows what is observed; reviewed semantics describe what operations mean; the dossier explains what is worth querying.

### 2.3 SHACL-optional operating modes

Forge supports three explicit semantic-support modes:

| Mode | Semantic basis | Permitted result |
|---|---|---|
| qualified_shape | Trusted and semantically qualified SHACL-derived catalog behavior | Eligible for normal ShapeLens compilation, review, and publication |
| qualified_overlay | Reviewed Executable Semantic Overlay, optionally informed by observed data, without requiring SHACL | Eligible for normal ShapeLens compilation, review, and publication |
| observed_data | Structures derived only from the pinned RDF graph or Graph Profile | Exploratory candidates and local diagnostic execution only |

The second mode is important: SHACL is not indirectly required for publication. A project may honestly represent query semantics in a reviewed Executable Semantic Overlay when those semantics are application behavior rather than validation constraints.

Forge may also propose draft SHACL from observed patterns, but only when a reviewer determines that the proposal describes a genuine validation contract. It must not manufacture SHACL merely to grant execution authority to a query. When an observation is useful for querying but is not a data constraint, an Executable Semantic Overlay is the correct promotion artifact.

### 2.4 Why this is an offline system

Query-template discovery is a design activity, not a user-request execution path. Offline operation provides four advantages:

- Model latency and cost are acceptable when runs are deliberate and reviewable.
- Candidates can be tested extensively before they reach an application.
- Human review can reject semantically plausible but operationally misleading templates.
- A model failure cannot directly affect a production query or user-visible answer.

This is a materially safer and more productive role for a frontier model than asking it to author complete low-level plans during every user request.

### 2.5 Relationship to the Phase 2 planner result

The Phase 2 complete-plan experiment failed because one small model was asked to interpret intent, resolve entities, select catalog material, construct a graph plan, manage opaque identifiers, and prove exact coverage simultaneously. ShapeLens Forge changes both the time horizon and the contract:

- generation happens offline;
- GPT-5.6 Sol is used for semantic design;
- the model emits stable semantic specifications rather than catalog-local bookkeeping;
- deterministic code performs resolution, compilation, coverage generation, and validation; and
- humans review candidates before publication.

Forge can create the reviewed template registry consumed by the narrower template-selection approach proposed after Phase 2. It does not itself reopen or bypass the Phase 2 gate for runtime natural-language planning.

---

## 3. Product placement and package boundary

ShapeLens Forge should initially live in the ShapeLens repository so that it can reuse fixtures, catalogs, conformance types, and review conventions. It should nevertheless be a separate Python package and command-line application.

Recommended dependency direction:

~~~text
shapelens-forge
    depends on
shapelens

shapelens
    does not import or depend on
shapelens-forge
~~~

The core ShapeLens package remains deterministic and usable without an OpenAI dependency, API key, model configuration, or discovery artifact. Forge may depend on the public ShapeLens catalog, plan, compiler, policy, and outcome types.

Recommended repository layout:

~~~text
forge/
  README.md
  SPEC.md
  pyproject.toml
  src/shapelens_forge/
    inputs.py
    domain.py
    profile.py
    semantic_ir.py
    model.py
    candidates.py
    compiler.py
    validation.py
    ranking.py
    review.py
    registry.py
    report.py
    cli.py
  schemas/
  prompts/
  tests/
  benchmarks/
~~~

The working name “Forge” emphasizes that the system manufactures and tests design artifacts. “Studio” would also be reasonable if a review UI becomes the dominant product surface.

---

## 4. Goals

Forge version 0.1 has the following goals.

1. Generate a diverse set of domain-relevant query ideas from RDF structure, a Domain Dossier, and any available reviewed semantic inputs.
2. Represent every candidate as a typed, parameterized Query Template Specification.
3. Operate in data-only exploratory mode when no SHACL or reviewed overlay is available.
4. Distinguish observed structural evidence from reviewed executable semantics in every candidate and report.
5. Ground every publishable relationship, selector, filter, and projection in trusted and semantically qualified Shape Catalog material derived from shapes or overlays.
6. Compile qualified specifications deterministically into the existing ShapeLens plan and SPARQL pipeline.
7. Prevent parameters from introducing predicates, paths, variable names, clauses, or other query syntax.
8. Execute generated candidates against controlled fixtures and record typed outcomes appropriate to their support mode.
9. Identify every observed assumption that requires semantic promotion before publication.
10. Rank candidates using explicit utility dimensions and deterministic quality signals.
11. Deduplicate semantically equivalent or operationally redundant templates.
12. Produce a complete review packet that explains why each template was proposed, how it is supported, what remains assumed, what parameters it accepts, and what limitations apply.
13. Publish only templates approved by named domain and RDF reviewers.
14. Preserve all inputs, prompts, model settings, responses, validation results, and revisions required to reproduce a discovery run.
15. Provide published registries that applications or a later constrained planner can consume without invoking Forge.

---

## 5. Non-goals

Forge version 0.1 will not:

- infer business usefulness from graph structure or SHACL alone;
- treat sampled graph structure as trusted schema, qualification, completeness, or authorization;
- infer normative cardinality from observed maximum cardinality;
- infer a permitted population solely from recurring RDF types;
- automatically promote an observation into SHACL or an Executable Semantic Overlay;
- automatically publish model output;
- add natural-language input to ShapeQueryEngine;
- accept raw model-authored SPARQL as an executable artifact;
- accept text interpolation into SPARQL;
- generate SPARQL Update, LOAD, CLEAR, CREATE, DROP, COPY, MOVE, or ADD;
- generate SERVICE or unrestricted federation;
- infer graph, row, or value-level authorization;
- prove real-world completeness or generate absence claims;
- support unrestricted OPTIONAL, UNION, MINUS, NOT EXISTS, subqueries, property paths, aggregates, grouping, ordering, or pagination;
- silently widen the existing ShapeLens query algebra;
- optimize production queries for a remote vendor-specific planner;
- claim that a non-empty result establishes semantic correctness;
- use model self-critique as acceptance evidence;
- expose private chain-of-thought;
- require a vector database, agent framework, or model tool loop; or
- make Phase 3 remote-store work permissible.

An offline raw-SPARQL model baseline may be retained for evaluation, but its output is never executed through the product path or published.

---

## 6. Design principles and invariants

### 6.1 Usefulness is contextual

A template is useful only relative to named domain tasks, actors, and decisions. Every candidate must reference at least one Domain Task in the frozen Domain Dossier. “The model believes this is useful” is not sufficient.

### 6.2 SHACL is optional and remains a local contract

Forge does not require SHACL to discover candidate queries. When SHACL is present, it preserves ShapeLens’s distinction between a contextual Shape Lens, a Population Selector, and a relationship Value Contract. It must not merge all shapes for one class into a universal schema or infer population enumeration from a relationship range.

### 6.3 Observed structure is evidence, not authority

Predicates, RDF types, term kinds, cardinalities, and joins derived from instance data are observations about a pinned Dataset Scope. Each observation records its query, count or band, sample boundary, and revision. An observation cannot by itself establish intended meaning, authorization, scalarity, completeness, or population semantics.

### 6.4 Semantic promotion is explicit

An observed operation becomes publishable only through a Semantic Promotion Record approved by the responsible domain and RDF reviewers. Promotion creates or references either:

- genuine trusted and semantically qualified SHACL-derived behavior; or
- a trusted and semantically qualified Executable Semantic Overlay.

Draft SHACL is appropriate only for an intended validation contract. An overlay is appropriate for application query semantics that should not be asserted as a data constraint.

### 6.5 Hints do not become executable semantics

Ontology terms and sampled graph statistics may influence ideation, exploratory candidate construction, ranking, or cost estimation. They cannot create publishable selectors, paths, joins, filters, projections, or parameter contracts. Runtime-executable behavior must resolve to trusted and semantically qualified catalog material.

### 6.6 The model designs; deterministic code authorizes

The model may propose a semantic query pattern and explain its utility hypothesis. It cannot:

- create or qualify catalog material;
- create RDF IRIs;
- decide source trust;
- authorize a query;
- author runtime policy;
- choose a named graph outside policy;
- introduce raw SPARQL syntax;
- publish a template; or
- declare its own output correct.

### 6.7 Parameters are RDF terms, never syntax

Every runtime parameter has a fixed role and RDF-term contract. Parameters may supply an IRI, a typed literal, or a language-tagged literal where explicitly supported. They cannot supply a predicate, property path, variable, projection list, ORDER BY expression, LIMIT, graph name, function, or query fragment.

### 6.8 Empty results are not automatically defects

Forge does not relax constraints to obtain a non-empty result. An empty fixture result may be correct and useful. Candidate validation compares behavior with a reviewed semantic oracle or test intention rather than rewarding row production.

### 6.9 All revisions are pinned

Every discovery run pins:

- the semantic-support mode;
- the Shape Catalog revision when applicable;
- the Observed Semantic Profile revision;
- source and overlay digests;
- Semantic Qualification revision;
- Semantic Promotion Record revisions;
- Domain Dossier revision;
- Graph Profile revision;
- Discovery Policy revision;
- Query Policy revision;
- prompt revision;
- structured-output schema revision;
- model identifier and reasoning configuration;
- compiler version;
- fixture revision; and
- price and measurement metadata used for reporting.

### 6.10 Publication is always reviewed

No confidence score, test result, or model rationale can replace the required publication decision. Domain usefulness and semantic correctness require named owners.

---

## 7. Terminology

Forge adds the following terms to the ShapeLens vocabulary.

**Domain Dossier**  
A versioned application-owned description of domain terminology, actors, decisions, recurring tasks, priorities, result expectations, risks, and prohibited information flows.

**Domain Task**  
One reviewable job or decision that a query may support. It has an owner, priority, expected result form, and acceptance notes.

**Graph Profile**  
A bounded, locally computed summary of observed graph structure and distribution. It is a sampled hint, not a schema, completeness claim, or authorization decision.

**Observed Semantic Profile**  
A versioned structural model derived from one pinned RDF Dataset Scope. It records observed predicates, RDF types, term kinds, relationship directions, co-occurrence, cardinality distributions, and join paths together with observation provenance.

**Observed Semantic Handle**  
A run-local reference to one structure in an Observed Semantic Profile. It proves only that the structure was observed under the recorded profile; it is not a Catalog key or executable authority.

**Semantic Support Level**  
One of qualified_shape, qualified_overlay, or observed_data, attached to every candidate operation and template.

**Semantic Promotion Record**  
A reviewed record that resolves an observed candidate operation to qualified SHACL-derived behavior or an Executable Semantic Overlay, including intended meaning, direction, population behavior, term contract, parameter role, fixtures, owners, and decision.

**Exploratory Template**  
A data-only candidate whose operations are supported by observed_data. It may be compiled and executed only in the bounded local discovery sandbox and cannot enter a runtime Template Registry.

**Exploratory Outcome**  
The typed diagnostic result of executing an Exploratory Query Blueprint against the pinned local fixture or Dataset Scope. It records rows or a Boolean value, limits, issues, and observation provenance, but it is not a ShapeLens Query Outcome and carries no Row Support Certificate or publication authority.

**Discovery Policy**  
The trusted configuration controlling which query forms, provider-visible fields, graph-profile features, candidate counts, budgets, and publication workflow are permitted.

**Discovery Run**  
One immutable attempt to produce and evaluate candidates from pinned inputs.

**Query Template Specification**  
A model-proposed, typed semantic description of a parameterized query. It may reference qualified provider handles or Observed Semantic Handles, but it does not contain executable catalog-local keys or trusted raw SPARQL.

**Plan Blueprint**  
A deterministic, catalog-bound plan factory produced from a validated, qualified Query Template Specification. It contains typed parameter positions but is not executable until all parameters are resolved. Data-only candidates instead receive an Exploratory Query Blueprint with no ShapeLens execution authority.

**Template Candidate**  
A specification plus its normalized blueprint, compiled previews, support trace, test results, utility signals, and review state.

**Support Trace**  
The exact mapping from every candidate operation to its observed evidence, qualified Shape Catalog material, and any Semantic Promotion Record. The trace states the Semantic Support Level explicitly.

**Utility Hypothesis**  
A testable explanation of which Domain Tasks a candidate supports, why the result would affect a decision, and what limitations apply.

**Utility Vector**  
The separate, non-aggregated measurements used to compare candidates, including task priority, owner value, reusability, selectivity, diversity, cost, and risk.

**Template Registry**  
An immutable published collection of reviewed Query Templates bound to compatible catalog and policy revisions.

**Review Decision**  
A named decision of approved, rejected, or changes_requested, with separate domain-value and RDF-semantic review roles.

---

## 8. System context

~~~mermaid
flowchart TD
    I["RDF graph, optional SHACL or overlays, domain dossier"] --> P["Profile and semantic preparation"]
    P --> M["GPT-5.6 Sol candidate design"]
    M --> V["Validate and test candidates"]
    V --> R["Review, promote semantics, and publish"]
    R --> T["Template Registry"]
    T --> X["ShapeLens runtime or template selector"]
~~~

The model is intentionally upstream of the executable boundary. A model response that cannot be validated becomes a rejected diagnostic artifact; it never becomes a partial query.

---

## 9. Inputs

### 9.1 Semantic source modes

Every run selects one semantic-support mode in its frozen manifest:

- qualified_shape;
- qualified_overlay; or
- observed_data.

A run may contain operations at several support levels while candidates are being reviewed, but each operation records exactly one current Semantic Support Level. The template’s level is the least-qualified level among its operations. A candidate containing any observed_data operation is exploratory until every such operation is promoted or removed.

The model receives distinct handle prefixes and descriptions for qualified and observed material. It cannot relabel an observed handle as qualified.

### 9.2 Optional shape package and reviewed overlays

When qualified semantic material is available, Forge consumes an immutable Shape Catalog or the same trusted inputs used to build one. It does not independently establish trust or qualification. A catalog can be built from semantically qualified SHACL behavior, qualified Executable Semantic Overlays, or both.

Provider-visible qualified material must be serialized into bounded semantic cards. A card may include:

- a stable provider handle;
- human-reviewed label and aliases;
- description;
- semantic kind: lens, selector, property, or branch;
- direct or inverse relationship orientation;
- allowed operation kinds;
- expected RDF-term kind;
- compatible target category;
- scalar projection status; and
- non-sensitive limitations.

Cards must not include:

- catalog-local hashes when a compact run-local handle is sufficient;
- hidden policy reasons;
- source credentials;
- unapproved labels;
- raw shape text containing executable or prompt-like instructions;
- authorization internals; or
- data values not approved for provider transmission.

The local mapping from provider handles to catalog identities is immutable for the run. The model never emits or sees a Catalog-Local Key as an authority-bearing value.

An overlay created from a data-only discovery run is not trusted merely because Forge proposed it. It enters a later catalog only after separate ownership, fixture, trust, and Semantic Qualification review.

### 9.3 RDF graph, Graph Profile, and Observed Semantic Profile

The RDF graph is inspected locally. The default provider mode transmits no raw RDF triples.

The Graph Profiler may compute:

- observed RDF types and candidate population clusters;
- property coverage bands;
- distinct-value count bands;
- direct and inverse edge occurrence;
- observed subject-type and object-type combinations;
- literal datatype and language-tag distributions;
- per-subject and per-object cardinality bands;
- property co-occurrence by observed node group;
- join fan-out bands;
- connected component observations;
- candidate label predicates;
- candidate entity-lookup fields;
- apparent scalarity together with counterexamples;
- qualified scalar-contract violations when shapes or overlays exist;
- empty qualified selectors;
- example result-shape sizes; and
- bounded cost estimates for candidate skeletons.

From these measurements Forge builds an Observed Semantic Profile. Its candidate operations include:

- observed node groups, never automatically authorized populations;
- observed direct and inverse predicate traversals;
- observed literal comparisons with exact term kinds;
- observed join paths;
- observed projection candidates; and
- observed parameter sources.

Every observed operation stores:

- the exact predicate or RDF type IRI already present in the graph;
- direction;
- subject and object term-kind observations;
- supporting profile query and digest;
- count or privacy-safe band;
- Dataset Scope and revision;
- counterexamples;
- confidence as an observation-quality measure; and
- explicit assumptions requiring review.

Confidence measures the strength and stability of the observation. It is not Semantic Qualification and cannot make an operation publishable.

Exact values, unique labels, rare identifiers, literal samples, and exact low counts can leak sensitive information. The Discovery Policy classifies every profile field as:

- local_only;
- provider_allowed_exact;
- provider_allowed_bucketed; or
- prohibited.

Provider-bound statistics should normally use bands such as zero, one, two-to-ten, eleven-to-one-hundred, or more-than-one-hundred. The profiler records its query budget, dataset scope, time boundary, and whether results are exact or sampled.

Graph Profile and Observed Semantic Profile material has Derivation Origin sampled_hint. It may drive exploratory candidate construction, ranking, and cost estimation. Only a Semantic Promotion Record can connect it to qualified executable behavior.

### 9.4 Domain Dossier

The Domain Dossier is mandatory. A minimal dossier contains:

- domain identifier and revision;
- purpose and business boundary;
- glossary;
- actors or personas;
- Domain Tasks;
- task priorities and criticality;
- expected result forms;
- useful filter dimensions;
- known data and completeness limitations;
- sensitive concepts;
- prohibited tasks and claims;
- example language and aliases;
- review owners; and
- provider-transmission classification.

Recommended YAML shape:

~~~yaml
schema_version: 1
domain_id: delivery-staffing
revision: sha256:...
purpose: Support staffing decisions using reviewed employee, project, and skill data.

personas:
  - id: workforce_planner
    description: Assigns people to delivery work.

tasks:
  - id: find_project_contributors
    persona_id: workforce_planner
    priority: critical
    decision: Identify employees who match both a project and a required skill.
    expected_result:
      kind: records
      fields: [employee, display_name]
    useful_parameters: [project, skill]
    prohibited_claims:
      - Do not claim an unreturned employee lacks the skill in the real world.

terminology:
  project:
    labels: [project, delivery initiative]
  skill:
    labels: [skill, expertise]

limitations:
  - The graph records approved assignments, not all work performed.

sensitivity:
  raw_employee_names: local_only
  task_descriptions: provider_allowed_exact
~~~

Domain Tasks should describe decisions without prescribing the expected SPARQL or catalog keys. For evaluation, a subset of tasks and competency questions is held out from the provider-visible dossier.

### 9.5 Discovery Policy

The Discovery Policy defines:

- supported query profile;
- maximum candidates per domain and task;
- maximum semantic entities, edges, filters, and projections;
- maximum model calls and retries;
- model input and output token ceilings;
- provider-visible fields;
- graph profiling budgets;
- fixture execution deadline and row/byte ceilings;
- deduplication thresholds;
- required reviewers;
- publication gates; and
- artifact retention and redaction.

The model cannot modify or relax this policy.

### 9.6 Review fixtures

Fixtures provide:

- representative local RDF data;
- expected positive, empty, and Boolean behaviors;
- semantic oracle queries or reviewed outcome descriptions;
- valid and invalid parameter examples;
- ambiguity cases;
- policy-limit cases; and
- seeded semantic defects.

Fixtures used to qualify executable semantics remain separate from model prompts. The model must not receive expected plan digests, oracle SPARQL, expected rows, or acceptance labels during a benchmark run.

### 9.7 Discovery manifest

Before any model call, Forge freezes a manifest containing all input and configuration digests. Commands must refuse to overwrite an existing manifest or results artifact. Any change to inputs, prompt, model, schema, thresholds, or policy creates a new revision.

---

## 10. Supported query profile

### 10.1 Version 0.1 operations

Forge 0.1 may propose templates containing:

- SELECT;
- positive ASK;
- explicitly qualified Population Selectors in qualified modes;
- observed node-group roots in data-only exploratory mode, always marked as assumptions requiring promotion;
- qualified or literally observed direct predicate relationships;
- qualified or literally observed inverse predicate relationships;
- connected positive conjunctions;
- exact IRI equality;
- exact typed-literal equality;
- positive existence;
- node projections;
- required qualified scalar projections;
- optional qualified scalar projections already supported by ShapeLens;
- several contextual Lens Uses on one Entity Variable; and
- a caller-declared Result Extent represented separately from execution ceilings.

Every publishable operation must already be representable by the ShapeLens 0.1 Bound Query Plan. Exploratory operations use the same small positive algebra but remain diagnostic until promotion.

### 10.2 Excluded operations

Forge 0.1 rejects:

- UPDATE operations;
- DESCRIBE and CONSTRUCT;
- SERVICE and federation;
- FROM or named-graph selection supplied by the model;
- arbitrary property paths;
- alternative and sequence paths;
- variable predicates;
- OPTIONAL graph patterns other than an existing qualified scalar-projection contract;
- UNION;
- MINUS;
- NOT EXISTS and other absence claims;
- FILTER expressions other than supported exact equality and positive existence;
- regex, lexical search, arithmetic, casts, functions, and language negotiation;
- aggregation and grouping;
- ORDER BY;
- OFFSET and stable pagination;
- subqueries;
- VALUES generated from an unbounded list;
- query hints or vendor extensions; and
- any raw SPARQL fragment.

Later revisions may add an operation only after its truth conditions, authorization behavior, evidence requirements, resource limits, and fixtures are specified in ShapeLens itself.

### 10.3 Parameter kinds

Version 0.1 supports:

| Parameter kind | Runtime value | Validation |
|---|---|---|
| entity_iri | Published: one authorized IRI from an application-owned resolver. Exploratory: one approved fixture IRI | Exact label/alias or explicit IRI admission; zero matches unsupported; multiple matches ambiguous |
| iri | Published: one IRI from trusted application configuration. Exploratory: one approved fixture IRI | Absolute IRI validation plus parameter allowlist or namespace policy |
| typed_literal | One literal with a fixed datatype | Parse and canonicalize using the declared datatype |
| language_literal | One literal with a fixed or allowed language tag | Validate language tag and preserve RDF identity |
| enum_literal | One member of a reviewed finite literal set | Exact membership |

All parameters are required in the Structured Outputs schema. Optional application inputs are represented as distinct templates in version 0.1 rather than nullable query structure.

Parameters cannot control result extent, query policy, graph scope, projection shape, or authorization.

### 10.4 Behavior by semantic-support mode

In qualified_shape and qualified_overlay modes, a valid candidate can proceed through Plan Blueprint construction, ShapeLens compilation, fixture evaluation, review, and publication.

In observed_data mode:

- predicates and RDF types must already occur in the pinned Observed Semantic Profile;
- every root, edge, filter, parameter role, and projection is marked observed_data;
- population, meaning, direction, scalarity, and disclosure assumptions are listed explicitly;
- deterministic code may generate a diagnostic SPARQL template for bounded local fixture execution;
- the result is an Exploratory Outcome, not a ShapeLens Query Outcome;
- no Row Support Certificate or ShapeLens evidence-strength claim is produced;
- the candidate cannot enter a runtime Template Registry; and
- promotion or rejection is required before the candidate can become publishable.

Mixed candidates inherit observed_data status until all observed operations have accepted Semantic Promotion Records and resolve to a rebuilt qualified Shape Catalog.

---

## 11. Architecture and components

### 11.1 Input Loader

The Input Loader:

- resolves local files without network imports by default;
- verifies digests;
- loads the pinned Shape Catalog when qualified semantic material exists;
- requires a pinned RDF Dataset Scope and Observed Semantic Profile in data-only mode;
- verifies the selected semantic-support mode;
- validates the Domain Dossier schema;
- loads Discovery and Query Policies;
- verifies fixture references; and
- creates the immutable Discovery Run Context.

It fails before any model call if a required revision, owner, or classification is missing.

### 11.2 Discovery Semantic IR Builder

The Discovery Semantic IR Builder creates a provider-neutral model context from two strictly separated namespaces.

The qualified namespace may contain:

- contextual lenses;
- population selectors;
- property operations;
- branch-preserving value contracts;
- direct and inverse join relationships;
- permitted projections; and
- stable run-local qualified handles.

The observed namespace may contain:

- observed node groups;
- observed RDF types;
- direct and inverse predicate occurrences;
- term-kind distributions;
- apparent cardinalities;
- property co-occurrences;
- join paths;
- projection candidates;
- stable run-local Observed Semantic Handles; and
- assumptions requiring promotion.

Every item carries its Semantic Support Level. The model may combine the namespaces for ideation but cannot upgrade an observed item. The IR excludes untrusted or prohibited material. Descriptive aliases may appear only when explicitly approved.

### 11.3 Graph Profiler

The Graph Profiler runs bounded local queries against the pinned Dataset Scope. It produces the Graph Profile and a privacy report showing which fields may leave the process.

The profiler never mutates the graph. A timeout, parser failure, or policy-limit event produces an incomplete profile with explicit issues; it does not silently substitute unknown values with zero. Data-only discovery requires sufficient profile coverage for every operation in a candidate; a missing observation cannot be filled by the model.

### 11.4 Domain Task Analyzer

The first model pass converts the Domain Dossier into a Task Portfolio. It may:

- restate tasks as competency questions;
- identify parameterizable dimensions;
- propose result forms;
- identify task overlaps;
- point out missing information; and
- mark a task unsupported by the supplied semantic cards.

The pass cannot propose executable graph operations. Its purpose is to separate “what would help” from “how to query it.”

### 11.5 Candidate Synthesizer

The second model pass receives:

- the approved Domain Dossier projection;
- the Task Portfolio;
- the Discovery Semantic IR;
- the approved Graph Profile projection;
- supported query-profile rules; and
- the Query Template Specification schema.

It returns candidate semantic specifications. It must use only supplied provider handles and task IDs.

Each operation must also carry the support level of its handle. If a candidate uses observed material, the model must enumerate the semantic assumptions that publication would require a reviewer to resolve.

### 11.6 Optional Candidate Critic

An optional third, independently prompted model pass may identify:

- omitted task conditions;
- misleading result interpretations;
- likely redundancy;
- parameterization weaknesses;
- sample-data overfitting; and
- stated limitations that should be added.

Criticism is advisory. It can route a candidate back for review or regeneration but cannot make a candidate valid, qualify semantics, or publish it. Evaluation reports separate first-pass and post-critique performance.

### 11.7 Specification Validator

The Specification Validator performs:

1. JSON-schema and type validation;
2. exact field and identifier checks;
3. qualified-handle or Observed Semantic Handle resolution;
4. Domain Task coverage checks;
5. query-profile checks;
6. connectedness checks;
7. parameter-position and type checks;
8. semantic-support-level propagation;
9. selector and contextual-lens separation for qualified material;
10. observed-root, direction, term-kind, and cardinality-evidence checks for data-only material;
11. branch compatibility checks;
12. scalar-projection checks or explicit apparent-scalarity assumptions;
13. complexity and policy checks; and
14. support-trace construction.

Any failure rejects the whole candidate. The validator never deletes a failing edge, filter, projection, or task intent to salvage a partial template.

### 11.8 Blueprint Compilers

Qualified candidates use the Plan Blueprint Compiler. It converts a validated specification into a canonical Plan Blueprint containing:

- one fixed normalized plan skeleton;
- typed parameter slots at approved entity or literal positions;
- resolved Catalog references;
- a mechanically generated operation-to-task map;
- the required Authorization Scope operations;
- a complexity summary; and
- a canonical digest.

The blueprint is not passed to ShapeQueryEngine until every parameter has become a validated RDF Term.

Observed candidates use a separate Exploratory Blueprint Compiler. It:

- accepts only predicates and RDF types present in the pinned Observed Semantic Profile;
- uses the same restricted positive query algebra;
- records every semantic assumption;
- emits diagnostic SPARQL through deterministic serialization;
- cannot construct a Bound Query Plan;
- cannot invoke ShapeQueryEngine; and
- labels all results exploratory and dataset-relative.

The two blueprint types are non-interchangeable and use different type identities and serialization schemas.

### 11.9 Published Template Instantiator

The Template Instantiator:

- checks registry, catalog, policy, and template revisions;
- validates the exact parameter set;
- resolves entity labels locally where applicable;
- creates RDF Term objects;
- fills parameter positions without string interpolation;
- constructs a concrete Bound Query Plan;
- generates intent and coverage records mechanically; and
- delegates to the unchanged ShapeLens validator and engine.

### 11.10 Execution Harness

The Execution Harness evaluates candidates against fixtures. It:

- instantiates declared test cases;
- compiles qualified candidates through ShapeLens;
- compiles observed candidates through the local Exploratory Blueprint Compiler;
- performs a second SPARQL parser and policy pass;
- executes under a shared deadline and byte/row ceilings;
- compares outcomes with semantic oracles;
- validates Row Support Certificates only for qualified ShapeLens outcomes;
- records observation provenance and explicit non-evidence status for Exploratory Outcomes;
- records empty and Boolean outcomes correctly; and
- runs mutations.

### 11.11 Semantic Promotion Workspace

For an exploratory candidate judged potentially useful, the workspace presents each observed operation and asks reviewers to decide:

- reject the operation;
- retain it as a descriptive or sampled hint;
- define or link genuine SHACL-derived behavior; or
- define an Executable Semantic Overlay.

An accepted Semantic Promotion Record fixes:

- intended domain meaning;
- permitted population behavior;
- predicate direction;
- subject and object term contracts;
- parameter roles and resolution policies;
- projection cardinality;
- applicable scenarios;
- sensitive-data classification;
- fixtures and counterexamples;
- review owners; and
- whether the behavior is a validation contract or application query semantics.

Forge then rebuilds the Shape Catalog from the reviewed material and recompiles the candidate from scratch. It must not mutate the exploratory blueprint into a qualified blueprint or reuse observation confidence as qualification.

### 11.12 Utility Analyzer and Deduplicator

The Utility Analyzer computes deterministic signals and collects human ratings. The Deduplicator groups candidates using:

- normalized blueprint digest;
- parameter-role signature;
- projected result signature;
- Domain Task overlap;
- graph-operation overlap; and
- reviewed semantic equivalence.

Candidates with the same blueprint but different wording become one template with multiple example questions. Similar templates with materially different projections or parameter contracts remain separate.

### 11.13 Review and Publisher

The review surface presents the candidate, utility hypothesis, domain tasks, parameter contract, support trace, compiled SPARQL previews, fixture outcomes, mutations, costs, and limitations.

Publication requires:

- all hard gates passing;
- every operation having qualified_shape or qualified_overlay support;
- no unresolved observed_data assumptions;
- a domain-value approval;
- an RDF-semantic approval;
- a security approval when the candidate uses sensitive operations; and
- a recorded registry version.

---

## 12. Discovery workflow

~~~mermaid
stateDiagram-v2
    [*] --> Frozen
    Frozen --> Proposed: model generation
    Proposed --> Rejected: structural failure
    Proposed --> Exploratory: observed-data checks
    Proposed --> Validated: qualified checks
    Exploratory --> Rejected: review rejection
    Exploratory --> Promoted: semantic promotion
    Promoted --> Validated: rebuild and revalidate
    Validated --> Rejected: semantic or policy failure
    Validated --> Reviewed: publication reviews
    Reviewed --> Published: all approvals
    Reviewed --> Rejected: review rejection
    Published --> Deprecated: incompatible or superseded
~~~

Detailed workflow:

1. Author and review the Domain Dossier.
2. Load the RDF fixture or dataset and any optional trusted Shape Catalog.
3. Profile the RDF data and build the Observed Semantic Profile.
4. Validate provider-transmission classifications.
5. Freeze the Discovery Manifest.
6. Generate the Task Portfolio.
7. Generate Query Template Specifications.
8. Retain raw model outputs and usage metadata.
9. Validate each specification and propagate its Semantic Support Level without repair.
10. Optionally perform one bounded structured-output retry for transport, refusal, or incomplete-output conditions.
11. Compile qualified specifications into Plan Blueprints and data-only specifications into Exploratory Query Blueprints.
12. Instantiate declared fixture parameters.
13. Execute qualified candidates through ShapeLens and observed candidates through the local diagnostic sandbox.
14. Run semantic, policy, evidence, and mutation checks.
15. Compute utility signals and deduplicate.
16. Perform blinded usefulness and semantic-assumption review.
17. For promising observed candidates, create reviewed Semantic Promotion Records and corresponding SHACL or overlay material.
18. Rebuild the Shape Catalog and recompile promoted candidates from scratch.
19. Perform publication review on fully qualified candidates.
20. Publish approved templates to an immutable registry.
21. Generate a complete discovery report including rejected and unpromoted exploratory candidates.

There is no unbounded agent loop and no iterative relaxation of constraints.

---

## 13. OpenAI model integration

### 13.1 Model configuration

The initial candidate model is:

~~~json
{
  "model": "gpt-5.6-sol",
  "reasoning": {
    "mode": "standard",
    "effort": "xhigh"
  }
}
~~~

The official OpenAI model page lists Structured Outputs support for GPT-5.6 Sol. OpenAI’s reasoning guidance describes xhigh as suitable for deep, asynchronous, long-running work and recommends using evaluations to justify its additional latency and cost. Forge is an offline workload, but the benchmark must still compare at least one lower reasoning setting before xhigh becomes the permanent default.

The exact model snapshot or alias behavior, reasoning mode, effort, SDK version, and API endpoint are recorded in the frozen manifest. Standard mode is the initial choice so that the experiment isolates the requested xhigh effort. A later benchmark may compare pro mode as a separate revision; it must not silently replace standard mode.

### 13.2 Responses API

Forge uses the Responses API for model calls. The request uses strict Structured Outputs through text.format with a JSON Schema generated from the same Python types used to validate the response.

Illustrative configuration:

~~~json
{
  "model": "gpt-5.6-sol",
  "reasoning": {
    "mode": "standard",
    "effort": "xhigh"
  },
  "text": {
    "format": {
      "type": "json_schema",
      "name": "shapelens_forge_candidates_v1",
      "strict": true,
      "schema": {}
    }
  }
}
~~~

The implementation fills schema with the generated JSON Schema. Every object sets additionalProperties to false. Every field is required; logically optional values use an explicit null union. Refusals, incomplete responses, content filtering, and token exhaustion are handled as typed attempt outcomes.

Structured Outputs guarantee schema shape, not semantic correctness. All semantic, catalog, policy, and execution checks remain local.

### 13.3 Prompt layout

The developer instruction contains:

- the role and non-authoritative boundary;
- supported query-profile rules;
- the definition of a useful candidate;
- the requirement to use only supplied handles and task IDs;
- the prohibition on raw SPARQL, invented semantics, and partial intent;
- instructions for unsupported tasks; and
- output-field semantics.

The user input contains clearly delimited data sections:

1. approved Domain Dossier projection;
2. Task Portfolio;
3. selected semantic-support mode;
4. qualified semantic cards when available;
5. Observed Semantic Profile cards;
6. approved Graph Profile projection;
7. candidate-count budget; and
8. previous structured-output error, only on the one permitted retry.

All labels, descriptions, shape text, observed predicates, domain prose, and graph-profile fields are treated as quoted data, never as instructions. Sanitization removes control-like wrapper text and preserves the original digest for audit.

### 13.4 Provider transmission

The provider-transmission manifest records every field class and one of:

- provider_allowed;
- provider_allowed_after_redaction;
- local_only; or
- prohibited.

Raw RDF triples are local_only by default. Hidden authorization metadata, policy reasons, credentials, expected answers, oracle queries, review labels, and evidence packets are prohibited.

The run report records whether external provider access occurred, the approved payload digest, token usage, latency, and cost. Raw sensitive provider payloads are stored only according to the configured retention policy.

### 13.5 Retry policy

At most one retry is allowed per pass. A retry may address:

- refusal handling when policy permits;
- incomplete or truncated output;
- transport failure; or
- a strict schema failure.

A semantic rejection does not trigger prompt repair in the benchmark. Semantic failures are evidence about candidate quality and remain rejected. Production discovery may offer an explicitly new run with a revised prompt or dossier, but it receives a new revision and cannot overwrite the failed evidence.

### 13.6 Reasoning privacy

Forge records reasoning-token usage and any provider-supplied summary allowed by policy. It does not request, store, expose, or depend on private chain-of-thought. Reviewers receive the model’s explicit Utility Hypothesis and limitation fields, which are ordinary output subject to validation.

---

## 14. Query Template Specification

### 14.1 Top-level schema

Every model candidate has these fields:

| Field | Meaning |
|---|---|
| schema_version | Exact output schema version |
| candidate_id | Run-local identifier |
| title | Short human-readable title |
| description | What the query returns |
| task_ids | Domain Tasks the candidate claims to support |
| example_questions | Natural-language examples, not executable input |
| semantic_support_level | qualified_shape, qualified_overlay, or observed_data |
| assumptions_requiring_promotion | Explicit assumptions for every observed_data operation; empty for a fully qualified candidate |
| result_kind | select or ask |
| result_extent | complete or examples, subject to policy |
| parameters | Exact typed runtime parameter contract |
| entities | Logical RDF nodes |
| selectors | Qualified population selections or observed root assumptions |
| lens_uses | Qualified contextual semantic views; empty or observed contexts in data-only mode |
| edges | Direct or inverse relationships |
| filters | Exact equality or positive existence |
| projections | Node or qualified scalar projections |
| utility_hypothesis | Decision value and expected use |
| limitations | Dataset-relative and semantic limitations |
| support_claims | Supplied qualified or observed handles, their support levels, and claimed operation |

The model does not emit catalog revisions, catalog-local keys, RDF bindings, plan-atom coverage, Authorization Scope, Query Policy, graph selection, or executable SPARQL.

### 14.2 Parameter specification

Each parameter contains:

- id;
- label;
- description;
- kind;
- RDF term kind;
- fixed datatype or language policy where applicable;
- expected entity category where applicable;
- value source;
- resolution policy;
- sensitivity classification;
- example values approved for model output; and
- every blueprint position filled by the parameter.

Parameter IDs are unique and cannot equal entity, edge, filter, projection, or provider-handle IDs.

### 14.3 Example candidate

~~~json
{
  "schema_version": 1,
  "candidate_id": "candidate-001",
  "title": "Employees matching a project and skill",
  "description": "Return employees assigned to one project who have one required skill.",
  "task_ids": [
    "find_project_contributors"
  ],
  "example_questions": [
    "Which employees worked on Project Atlas and have artificial-intelligence expertise?"
  ],
  "semantic_support_level": "qualified_shape",
  "assumptions_requiring_promotion": [],
  "result_kind": "select",
  "result_extent": "complete",
  "parameters": [
    {
      "id": "project",
      "label": "Project",
      "description": "The project whose assignments are inspected.",
      "kind": "entity_iri",
      "rdf_term_kind": "iri",
      "datatype": null,
      "entity_category": "project",
      "value_source": "authorized_entity_index",
      "resolution_policy": "exact_label_or_alias",
      "sensitivity": "provider_allowed",
      "example_values": [
        "Project Atlas"
      ],
      "positions": [
        "entity:project"
      ]
    },
    {
      "id": "skill",
      "label": "Skill",
      "description": "The required skill.",
      "kind": "entity_iri",
      "rdf_term_kind": "iri",
      "datatype": null,
      "entity_category": "skill",
      "value_source": "authorized_entity_index",
      "resolution_policy": "exact_label_or_alias",
      "sensitivity": "provider_allowed",
      "example_values": [
        "Artificial intelligence"
      ],
      "positions": [
        "entity:skill"
      ]
    }
  ],
  "entities": [
    {
      "id": "employee",
      "binding": "unbound"
    },
    {
      "id": "project",
      "binding": "parameter:project"
    },
    {
      "id": "skill",
      "binding": "parameter:skill"
    }
  ],
  "selectors": [
    {
      "id": "employee_population",
      "entity_id": "employee",
      "selector_handle": "S_EMPLOYEE"
    }
  ],
  "lens_uses": [
    {
      "id": "staffing",
      "entity_id": "employee",
      "lens_handle": "L_STAFFING"
    },
    {
      "id": "directory",
      "entity_id": "employee",
      "lens_handle": "L_DIRECTORY"
    }
  ],
  "edges": [
    {
      "id": "worked_on",
      "source_lens_use_id": "staffing",
      "property_handle": "P_WORKED_ON",
      "branch_handle": "B_WORKED_ON_PROJECT",
      "target_entity_id": "project"
    },
    {
      "id": "expertise",
      "source_lens_use_id": "staffing",
      "property_handle": "P_EXPERTISE",
      "branch_handle": "B_EXPERTISE_SKILL",
      "target_entity_id": "skill"
    }
  ],
  "filters": [],
  "projections": [
    {
      "id": "employee",
      "kind": "node",
      "entity_id": "employee",
      "lens_use_id": null,
      "property_handle": null,
      "branch_handle": null,
      "required": true
    },
    {
      "id": "name",
      "kind": "field",
      "entity_id": null,
      "lens_use_id": "directory",
      "property_handle": "P_DISPLAY_NAME",
      "branch_handle": "B_DISPLAY_NAME",
      "required": true
    }
  ],
  "utility_hypothesis": {
    "decision": "Identify immediately usable contributors for a delivery project.",
    "why_parameterized": "The same graph pattern applies to every reviewed project and skill.",
    "expected_frequency": "weekly",
    "priority": "critical"
  },
  "limitations": [
    "Results describe recorded assignments and skills within the pinned Dataset Scope.",
    "A missing employee is not evidence that the employee lacks the skill in the real world."
  ],
  "support_claims": [
    {
      "operation_id": "worked_on",
      "support_level": "qualified_shape",
      "handles": [
        "L_STAFFING",
        "P_WORKED_ON",
        "B_WORKED_ON_PROJECT"
      ]
    },
    {
      "operation_id": "expertise",
      "support_level": "qualified_shape",
      "handles": [
        "L_STAFFING",
        "P_EXPERTISE",
        "B_EXPERTISE_SKILL"
      ]
    },
    {
      "operation_id": "name",
      "support_level": "qualified_shape",
      "handles": [
        "L_DIRECTORY",
        "P_DISPLAY_NAME",
        "B_DISPLAY_NAME"
      ]
    }
  ]
}
~~~

The actual JSON Schema uses fixed required fields and additionalProperties false throughout. The example is illustrative of the semantic contract.

### 14.4 Data-only candidate support

A data-only candidate uses the same high-level fields but references Observed Semantic Handles and lists every unresolved semantic assumption. A shortened support fragment may look like:

~~~json
{
  "semantic_support_level": "observed_data",
  "assumptions_requiring_promotion": [
    {
      "operation_id": "employee_population",
      "assumption": "Resources observed with rdf:type Employee form the intended application query population."
    },
    {
      "operation_id": "worked_on",
      "assumption": "The observed workedOn predicate means an employee assignment to a project and is permitted for traversal."
    },
    {
      "operation_id": "name",
      "assumption": "The observed displayName predicate is an application-approved scalar projection."
    }
  ],
  "support_claims": [
    {
      "operation_id": "worked_on",
      "support_level": "observed_data",
      "handles": [
        "O_EDGE_WORKED_ON"
      ]
    },
    {
      "operation_id": "name",
      "support_level": "observed_data",
      "handles": [
        "O_LITERAL_DISPLAY_NAME"
      ]
    }
  ]
}
~~~

Observation support proves that the terms and pattern occurred in the pinned data. It does not prove the assumptions. The review packet shows both separately.

### 14.5 Example Semantic Promotion Record

One reviewed promotion for the worked-on relationship might be:

~~~json
{
  "schema_version": 1,
  "promotion_id": "promotion-worked-on-v1",
  "observed_handle": "O_EDGE_WORKED_ON",
  "observation_revision": "sha256:observed-profile-revision",
  "decision": "qualified_overlay",
  "intended_behavior": {
    "label": "employee worked on project",
    "predicate": "https://example.org/staffing/workedOn",
    "direction": "direct",
    "source_role": "employee",
    "target_role": "project",
    "population_behavior": "none",
    "affordances": [
      "traverse"
    ],
    "parameter_roles": [
      "project"
    ]
  },
  "why_overlay_not_shacl": "This records an application query relationship and does not assert a new validation constraint.",
  "fixture_ids": [
    "staffing-worked-on-positive",
    "staffing-worked-on-direction-mutation"
  ],
  "domain_review": {
    "reviewer": "workforce-operations",
    "decision": "approved"
  },
  "rdf_review": {
    "reviewer": "rdf-reviewer",
    "decision": "approved"
  }
}
~~~

The record is an input to the normal overlay admission and Semantic Qualification process. It is not itself a Catalog item. After the overlay is admitted, Forge rebuilds the catalog, resolves the new qualified handles, and reconstructs the candidate.

---

## 15. Deterministic compilation

### 15.1 Handle resolution

The compiler resolves run-local handles only through the pinned Discovery Semantic IR. Unknown or wrong-kind handles fail. A property handle cannot occupy a lens or branch position, and an Observed Semantic Handle cannot occupy a qualified handle field.

For a qualified handle, the resolved catalog item must be:

- present in the pinned Catalog Revision;
- derived from an eligible origin;
- backed by a trusted complete source closure;
- semantically qualified for the intended scenario;
- permitted by Discovery Policy; and
- compatible with the referenced entity and branch.

For an observed handle, deterministic code verifies:

- the exact predicate or RDF type is present in the pinned Observed Semantic Profile;
- direction and term kinds match the observation;
- the profile query completed without a contradictory issue;
- any claimed cardinality is described as apparent rather than normative;
- the operation’s assumptions are complete; and
- the candidate remains observed_data.

Observed-handle resolution never returns a Catalog key.

### 15.2 Qualified portable and catalog-local identity

When a behavior has a Portable Logical Key, the published template may declare that key plus a catalog compatibility range. It is still resolved and revalidated for each catalog revision.

Blank-node-backed or otherwise catalog-local behavior binds the template to an exact Catalog Revision. Forge must not infer cross-revision equivalence from blank-node labels or structural similarity. Rebuilding such a template for a new catalog requires deterministic resolution followed by renewed review or an explicitly approved migration.

### 15.3 Qualified Plan Blueprint construction

The compiler:

1. creates normalized Entity Variables;
2. attaches only explicit Selector Uses;
3. attaches only named contextual Lens Uses;
4. resolves relationship direction and branch;
5. places typed parameter slots;
6. adds supported filters and projections;
7. derives the Result Extent;
8. computes the complete operation set;
9. maps operations to Domain Tasks mechanically;
10. computes complexity;
11. canonicalizes collection order and identifiers; and
12. produces a blueprint digest.

Model-provided identifiers become local labels only. They do not affect semantic identity.

### 15.4 Exploratory Query Blueprint construction

For observed_data candidates, deterministic code:

1. creates a diagnostic positive query graph from only observed predicates and RDF types;
2. fixes every parameter to a validated RDF-term position;
3. carries all observation provenance and semantic assumptions;
4. computes a diagnostic operation set and complexity summary;
5. canonicalizes the exploratory blueprint;
6. emits an exploratory digest in a namespace distinct from Plan Blueprint digests; and
7. marks the artifact non-publishable.

The compiler does not invent selectors, lenses, value-contract branches, scalar contracts, or authorization from the profile. An observed root is represented as an explicit root assumption, and an apparently scalar projection remains a projection assumption until promoted.

### 15.5 Published-template instantiation

At runtime, a caller supplies:

~~~json
{
  "template_id": "staffing.employees_by_project_and_skill",
  "parameters": {
    "project": "Project Atlas",
    "skill": "Artificial intelligence"
  }
}
~~~

The application resolves the labels through an authorized entity source:

~~~json
{
  "project": {
    "kind": "iri",
    "value": "https://example.org/staffing/project-atlas"
  },
  "skill": {
    "kind": "iri",
    "value": "https://example.org/staffing/skill-ai"
  }
}
~~~

Zero exact matches produce Unsupported. Multiple exact matches produce Ambiguous. Similarity may order clarification choices but cannot silently bind an entity.

Exploratory templates do not have a public runtime instantiation API. Forge may instantiate their fixture parameters internally for diagnostic execution only.

### 15.6 SPARQL generation

For a qualified template, the concrete Bound Query Plan is passed to the existing deterministic ShapeLens SPARQL compiler. For an exploratory template, a separate deterministic diagnostic compiler emits the same restricted positive SPARQL subset but attaches no ShapeLens authority or evidence semantics. A human-readable preview may resemble:

~~~sparql
SELECT ?employee ?name
WHERE {
  VALUES ?project { <https://example.org/staffing/project-atlas> }
  VALUES ?skill { <https://example.org/staffing/skill-ai> }

  ?employee <https://example.org/staffing/workedOn> ?project .
  ?employee <https://example.org/staffing/expertise> ?skill .
  ?employee <https://example.org/staffing/displayName> ?name .
}
~~~

The preview is generated, never parsed from model output. RDF terms are serialized by the relevant deterministic compiler from validated Term objects. User text is never concatenated into the query. Every exploratory preview is visibly labeled “observed-data diagnostic; not publishable.”

### 15.7 Second policy pass

After rendering, the query is parsed again and checked for:

- allowed query form;
- allowed predicates and graph scopes;
- AST size;
- prohibited operations;
- variable and projection consistency;
- bounded VALUES size;
- Query Policy limits; and
- correspondence with the canonical Plan Blueprint or Exploratory Query Blueprint digest.

The rendered-query check is defense in depth; it does not replace plan validation.

---

## 16. Validation

### 16.1 Validation layers

| Layer | Main checks |
|---|---|
| Input | Digests, schemas, owners, classifications, revisions |
| Model envelope | Structured-output schema, refusal, completeness, exact fields |
| Referential | Known task IDs and semantic handles of the correct kind |
| Observation | Observed predicate/type occurrence, direction, term kinds, profile provenance, counterexamples |
| Semantic | Connectedness, direction, branch compatibility, selector/context separation, complete assumptions |
| Support level | Exact propagation of qualified_shape, qualified_overlay, and observed_data |
| Parameter | Exact set, RDF types, positions, resolution policy, no syntax parameters |
| Qualification | Trusted closure and field-level Semantic Qualification for publishable operations |
| Promotion | Accepted Semantic Promotion Records and rebuilt catalog resolution |
| Authorization | Required operations permitted for the review and runtime profile |
| Complexity | Entity, edge, filter, projection, AST, row, byte, and deadline limits |
| Compilation | Canonical blueprint and deterministic SPARQL generation |
| Rendered query | Parser and policy verification |
| Execution | Typed outcome, fixture oracle, no silent relaxation |
| Evidence | Qualified: complete Row Support Certificates and scope consistency. Exploratory: observation provenance plus an explicit no-ShapeLens-evidence status |
| Utility | Domain owner rating and task coverage |
| Publication | Named approvals and immutable registry write |

### 16.2 Structural checks

Structural validation rejects:

- duplicate IDs;
- missing or extra fields;
- empty task coverage;
- unreferenced parameters;
- parameters in multiple incompatible positions;
- missing lens context in qualified candidates;
- selectors used as lenses in qualified candidates;
- observed roots represented as qualified selectors;
- observed handles placed in qualified fields;
- edges with incompatible qualified branches or contradictory observed term kinds;
- disconnected positive graph patterns;
- projections that cannot be derived;
- observed projections with no declared scalarity or multiplicity assumption;
- incomplete assumptions_requiring_promotion;
- unbounded result requests;
- and any query feature outside the supported profile.

### 16.3 Semantic checks

Each candidate is compared with a human-authored semantic intention. Matching fixture rows is insufficient because a defective query may coincidentally produce the same rows.

Review checks include:

- population correctness;
- relationship direction;
- every material task condition;
- absence of invented restrictions;
- parameter meaning;
- projection meaning;
- Boolean versus record intent;
- Result Extent;
- dataset-relative limitations; and
- whether the template’s title and example questions faithfully describe the plan.

For observed_data candidates, review also checks:

- whether each observed pattern is stable enough to investigate;
- which claims are observations versus intended application semantics;
- whether apparent scalarity is real, merely convenient, or false;
- whether recurring RDF types form an intended population;
- whether the relationship meaning and direction are correctly understood;
- whether the operation belongs in SHACL, an Executable Semantic Overlay, or neither; and
- whether promotion would expose sensitive information.

### 16.4 Fixture matrix

Every publishable template requires:

1. at least one positive fixture;
2. at least one valid no-match fixture where meaningful;
3. one invalid parameter-kind fixture;
4. one unknown-entity fixture for entity parameters;
5. one ambiguous-entity fixture where aliases can collide;
6. one stale catalog or template revision fixture;
7. one policy-limit fixture;
8. one seeded relationship-direction or predicate-neighbor defect;
9. one projection mutation; and
10. one condition-removal mutation.

Critical templates require scenario-specific authorization and disclosure tests.

Exploratory templates run an analogous diagnostic fixture matrix but do not satisfy publication gates. After semantic promotion, all qualified fixture and mutation tests are rerun from a rebuilt catalog; exploratory results are not reused as proof.

### 16.5 Mutation testing

Mutation testing changes one semantic element at a time:

- swap a property with a neighboring property;
- reverse an edge;
- change a branch;
- remove a selector;
- add an unintended selector;
- remove a filter;
- change parameter placement;
- drop a projection;
- add an unrelated projection;
- change SELECT to ASK;
- alter Result Extent; or
- attempt a raw fragment as a parameter.

Data-only mutations additionally:

- replace an observed predicate with an unobserved IRI;
- claim a normative scalar contract from an observed maximum of one;
- convert an observed node group into a qualified population;
- drop an assumption requiring promotion;
- relabel observed_data as qualified_overlay; and
- reuse a profile handle against a different Dataset Scope.

Every mutation that changes semantics must be rejected or produce a deliberately different reviewed template identity.

### 16.6 Model-output errors

Strict Structured Outputs reduce envelope errors but do not guarantee:

- correct task interpretation;
- correct semantic handles;
- correct Semantic Support Levels;
- complete promotion assumptions;
- complete conditions;
- useful parameter choices;
- absence of redundant candidates; or
- accurate limitations.

The report separates schema adherence, observation validity, semantic qualification, and utility.

---

## 17. Defining and ranking usefulness

### 17.1 Hard gates before ranking

Forge maintains separate exploratory and publishable ranking pools.

An exploratory candidate is eligible for usefulness review only after it:

- validates structurally;
- resolves every observed operation to the pinned profile;
- declares all assumptions requiring promotion;
- compiles in the diagnostic sandbox;
- passes rendered-query policy checks;
- has safe parameters; and
- executes within fixture budgets.

A publishable candidate is eligible for registry ranking only after it:

- validates structurally;
- grounds every executable operation in qualified Shape Catalog material;
- has no observed_data operation;
- compiles through ShapeLens;
- passes rendered-query policy checks;
- has safe parameters;
- executes within fixture budgets; and
- has no known false semantic completion.

Exploratory rank can prioritize promotion work but cannot be compared as though it were publication readiness. An invalid or unqualified candidate cannot outrank a qualified candidate through a high utility score.

### 17.2 Utility Vector

Forge reports these dimensions independently:

| Dimension | Source |
|---|---|
| task_priority | Frozen Domain Dossier |
| critical_task_coverage | Deterministic mapping plus reviewer |
| domain_value | Blinded domain-owner rating |
| semantic_precision | RDF reviewer |
| parameter_reusability | Number and breadth of approved parameter values |
| expected_frequency | Domain Dossier or application telemetry classification |
| result_actionability | Domain-owner rubric |
| selectivity_band | Graph Profile and fixture execution |
| execution_cost | Local measured plan and query metrics |
| diversity | Distance from accepted candidates |
| review_burden | Review time and requested changes |
| risk | Security and disclosure classification |
| semantic_support_level | Qualified shape, qualified overlay, or observed data |
| promotion_burden | Number and severity of unresolved semantic assumptions |
| evidence_quality | ShapeLens outcome and certificate checks, or explicitly not_applicable for exploratory candidates |

The registry may use a configurable lexicographic ordering for presentation:

1. critical-task coverage;
2. approved domain value;
3. semantic correctness;
4. lower risk;
5. reusability;
6. diversity;
7. lower execution cost.

Forge does not use a weighted aggregate to authorize publication.

### 17.3 Domain-owner rubric

For each candidate, a domain owner answers:

1. Does this support a real recurring decision?
2. Would the result change or accelerate an action?
3. Are the parameters natural application controls?
4. Is the result shape understandable?
5. Are limitations accurately stated?
6. Is this materially distinct from another candidate?
7. Would you expose it to the intended persona?

Ratings use useful, useful_with_changes, not_useful, or unable_to_assess, plus a reason.

### 17.4 Avoiding sample-data bias

Forge must not rank a candidate as useful merely because it returns many rows. High row counts may indicate an unselective or expensive query. A zero-row fixture may still represent a critical alerting or compliance check.

The Graph Profile contributes selectivity and feasibility signals, not the definition of value.

### 17.5 Deduplication

Candidates are grouped by normalized plan skeleton before language similarity. One blueprint may retain:

- several example questions;
- several domain aliases; and
- several display descriptions.

Two candidates remain distinct when they have materially different parameters, result forms, required projections, truth conditions, or disclosure risks.

---

## 18. Security and privacy

### 18.1 Threat model

| Threat | Example | Mitigation |
|---|---|---|
| Prompt injection from semantic inputs | A label says to ignore policy and emit a SERVICE query | Treat all source text as delimited data; allowlisted fields; strict output schema; deterministic profile checks |
| Untrusted shape expansion | An imported shape introduces a sensitive predicate | Reuse Shape Source Trust and complete-closure admission; exclude unqualified behavior |
| Observed-schema laundering | A frequent predicate is treated as trusted semantics | Distinct observed handles and artifact types; support-level propagation; publication rejects observed_data |
| Accidental scalar inference | A property has one value in the sample and is published as scalar | Cardinality distributions and counterexamples; explicit assumption; qualification fixture required |
| Incorrect population inference | Recurring rdf:type values are treated as an authorized root | Observed roots remain assumptions; reviewed Population Selector or overlay required |
| Dishonest SHACL generation | Forge creates a shape solely to authorize a query | Reviewer must classify the behavior as a genuine validation contract or use an overlay |
| Sample-data exfiltration | Rare literals or identifiers are sent to the provider | Local profiling by default; field classification; bucketing; transmission manifest |
| Authorization invention | The model assumes a lens is a security view | Authorization remains trusted runtime configuration and is never model output |
| Query injection | A parameter contains SPARQL syntax | Typed RDF Terms; no fragment parameters; deterministic serialization |
| Semantic overreach | The model treats a value class as a query population | Explicit Population Selector validation |
| False absence claim | Empty results are described as non-existence | Positive-only profile; Dataset Scope wording; reviewed limitations |
| Resource exhaustion | Candidate creates a high-fan-out join | Complexity ceilings; profile estimates; fixture deadlines; row/byte limits |
| Review bypass | A high score auto-publishes a candidate | Required named approvals; immutable publication state machine |
| Model drift | Alias behavior changes between runs | Pin model configuration and artifacts; repeated benchmark; registry independent of model at runtime |
| Poisoned Domain Dossier | Untrusted prose requests prohibited data | Application-owned dossier admission; provider projection; Discovery Policy |
| Oracle leakage | Expected plans are included in the prompt | Freeze prompt payload inventory; separate fixtures and evaluation labels |

### 18.2 Data minimization

The provider receives only the minimum semantic and domain material needed for ideation. Default behavior:

- no raw RDF triples;
- no evidence packets;
- no credentials or endpoint URLs;
- no hidden authorization conditions;
- no unique sensitive values;
- no expected answers;
- no benchmark labels; and
- no prior human review results.

If a deployment elects to transmit approved RDF examples, that is a named profile with separate review, retention, and evaluation. It is not the default.

### 18.3 Local execution profile

Forge 0.1 executes only against trusted local RDFLib Graph or Dataset fixtures. Qualified candidates use the existing ShapeLens 0.1 security profile. Exploratory candidates use a separate local diagnostic sandbox with at least the same query-form, AST, deadline, row, and byte ceilings, but they do not produce ShapeLens Query Outcomes or evidence. Remote production endpoints remain outside scope.

### 18.4 Secrets

The OpenAI API key is supplied through the configured environment or secret manager. It is never placed in a manifest, prompt, report, fixture, registry, or error message. Provider errors are normalized before storage.

### 18.5 Audit

An operator can determine:

- which exact inputs were used;
- which fields left the process;
- which model and settings were called;
- what the model returned;
- why a candidate failed;
- which operations were merely observed;
- which Semantic Promotion Records were accepted or rejected;
- whether draft SHACL or an overlay was chosen and why;
- which deterministic artifacts were generated;
- which reviewers approved publication; and
- which applications may consume the registry.

---

## 19. Registry and lifecycle

### 19.1 Candidate states

Allowed states:

- proposed;
- structurally_rejected;
- exploratory_validated;
- promotion_requested;
- promoted;
- validated;
- changes_requested;
- approved;
- published;
- rejected;
- deprecated.

State transitions are append-only audit events. A published template is immutable. Changes create a new template revision.

### 19.2 Published template artifact

A published artifact contains:

- stable template ID;
- template revision;
- compatible Catalog Revision or compatibility declaration;
- Plan Blueprint and digest;
- parameter contracts;
- task and persona references;
- titles, descriptions, and example questions;
- deterministic support trace;
- qualified_shape or qualified_overlay support for every operation;
- accepted Semantic Promotion Records when the template originated in data-only discovery;
- required authorization operations;
- complexity summary;
- limitations;
- fixture and mutation-test digests;
- review decisions;
- publication time and owner; and
- deprecation information when applicable.

Raw model output and prompts remain discovery evidence and are not required by runtime consumers.

Exploratory Templates are stored in discovery reports, not in the runtime Template Registry.

### 19.3 Compatibility

At invocation, the runtime verifies:

- registry revision;
- template revision;
- Catalog Revision compatibility;
- Query Policy compatibility;
- Authorization Scope;
- parameter schema;
- entity-resolution revision where applicable; and
- compiler version.

An incompatible or stale template fails explicitly. The runtime does not silently rebind it to a neighboring catalog item.

### 19.4 Deprecation

A template is deprecated when:

- its semantic behavior is removed or changed;
- a source or qualification is revoked;
- a security review changes;
- a better template supersedes it;
- observed execution violates its scalar or resource assumptions; or
- the domain owner no longer considers the task valid.

Deprecation does not delete historical discovery and execution records.

---

## 20. Public interfaces

### 20.1 Python design

Illustrative interfaces:

~~~python
from shapelens_forge import (
    DiscoveryConfig,
    DiscoveryInputs,
    DiscoveryRunner,
    TemplateRegistry,
)

runner = DiscoveryRunner(config=DiscoveryConfig.load("forge-config.json"))

report = runner.discover(
    DiscoveryInputs(
        catalog=catalog_or_none,
        data=data,
        domain_dossier="domain.yaml",
        fixtures="fixtures/",
        manifest="manifest.json",
    )
)

for candidate in report.exploratory_candidates:
    print(candidate.assumptions_requiring_promotion)

registry = TemplateRegistry.load("registry.json")
request = registry.instantiate(
    template_id="staffing.employees_by_project_and_skill",
    parameters={
        "project": "Project Atlas",
        "skill": "Artificial intelligence",
    },
    entity_resolver=resolver,
    run_context=run_context,
)

outcome = engine.execute_plan(request.plan)
~~~

The exact API should follow existing ShapeLens immutable dataclass and typed-outcome conventions.

DiscoveryInputs requires data and a Domain Dossier. Catalog is optional. When catalog is absent, the run is observed_data and cannot produce a published registry without a later promotion and catalog-rebuild workflow.

### 20.2 CLI

Proposed commands:

~~~console
shapelens-forge validate-inputs --config forge-config.json
shapelens-forge profile --config forge-config.json --output graph-profile.json --observed-output observed-semantics.json
shapelens-forge freeze --config forge-config.json --reviewer "NAME"
shapelens-forge discover --manifest manifest.json --output raw-attempts.json
shapelens-forge validate --manifest manifest.json --attempts raw-attempts.json
shapelens-forge review-template --candidate candidate-001
shapelens-forge promote --candidate candidate-001 --decision promotion.json
shapelens-forge rebuild-catalog --promotion promotion.json --output catalog.json
shapelens-forge report --manifest manifest.json --output report.json
shapelens-forge publish --report report.json --output registry.json
shapelens-forge verify-registry registry.json
~~~

Commands refuse to overwrite artifacts. Publishing requires complete review records and every hard gate.

### 20.3 Runtime consumption

Runtime consumers need no OpenAI client. They load a published Template Registry, select a template through application code or a separately authorized constrained selector, resolve parameters, instantiate a Bound Query Plan, and delegate to ShapeQueryEngine.

---

## 21. Observability and operations

Each Discovery Run reports:

- model calls by pass;
- first-pass and retry success;
- refusals and incomplete responses;
- input, cached input, reasoning, and output tokens where available;
- latency by pass;
- provider cost under a dated price manifest;
- number of tasks considered;
- candidates proposed;
- schema-valid candidates;
- candidates by Semantic Support Level;
- observed operations and assumptions;
- exploratory candidates compiled and fixture-tested;
- promotion requests, approvals, rejections, and chosen artifact types;
- qualified grounded candidates;
- qualified and exploratory compilation counts;
- fixture-passing candidates;
- unique candidates after deduplication;
- candidates approved and published;
- rejection categories;
- review time;
- provider-visible payload classes;
- profiler query count and duration; and
- local execution p50 and p95.

Budgets are absolute and centrally managed. Cancellation propagates through profiling, model calls, compilation, and fixture execution. Retries share the same budget.

Cost and latency are reported separately from semantic quality. A cheap or fast run cannot compensate for an unsafe or incorrect template.

---

## 22. Evaluation plan

### 22.1 Hypotheses

**H1 — Domain value:** Adding a reviewed Domain Dossier materially improves the utility of the top-ranked templates over RDF structure alone and over RDF structure plus SHACL.

**H2 — Semantic grounding:** Deterministic support-level propagation and compilation can ensure that every operation in a published candidate is backed by trusted and semantically qualified shape or overlay material.

**H3 — Parameter safety:** Typed template parameters can eliminate query-fragment injection and preserve exact RDF identity.

**H4 — Review acceleration:** Forge reduces expert time required to produce a useful template catalog compared with manual authoring.

**H5 — Model value:** GPT-5.6 Sol with xhigh reasoning produces better task coverage or top-k utility than lower-effort and deterministic baselines at an acceptable offline cost.

**H6 — SHACL optionality:** Data-only discovery can recover a useful portion of the gold task portfolio and produce reviewable promotion candidates without laundering observed structure into trusted semantics.

**H7 — SHACL value:** When qualified SHACL exists, it reduces semantic-promotion burden and rejection rates relative to data-only discovery.

### 22.2 Evaluation domains

The first benchmark uses the three existing ShapeLens domains:

- delivery staffing;
- service operations; and
- research publication cataloging.

Each domain receives a reviewed Domain Dossier authored before candidate generation. At least one later external or newly authored domain is required before making a cross-domain generalization claim.

Each domain is evaluated in two semantic conditions:

1. qualified condition, using its existing reviewed shapes and overlays; and
2. data-only condition, withholding all shape and qualification material from discovery while retaining it privately for gold review.

The data-only run must not receive hints derived from the hidden qualified artifacts.

### 22.3 Gold portfolio

Domain owners independently author:

- high-value competency questions;
- critical task conditions;
- expected result forms;
- natural parameters;
- prohibited questions;
- useful template equivalence classes; and
- semantic oracles.

A held-out portion is not included in provider-visible examples. Gold material is frozen before model runs.

### 22.4 Baselines

| System | Purpose |
|---|---|
| deterministic_observed_enumeration | Enumerate small positive patterns from observed RDF terms without a model |
| deterministic_qualified_enumeration | Enumerate small qualified selector/property patterns without a model |
| sol_data_profile | Measure model output from observed structure without SHACL or a Domain Dossier |
| sol_data_dossier | Data-only candidate system with observed structure and the Domain Dossier |
| sol_qualified_dossier | Full candidate system with qualified semantics, observed profile, and the Domain Dossier |
| human_authored | Estimate quality ceiling and review effort |
| raw_sparql_offline | Diagnostic only; measure defects in direct model-authored SPARQL |

All model baselines use the same model and frozen run settings except for the intentionally varied inputs or reasoning effort.

### 22.5 Metrics

**Task recall at K**  
Gold Domain Tasks represented by at least one semantically correct candidate among the top K.

**Critical task recall**  
Critical gold tasks represented by a correct candidate.

**Useful precision at K**  
Candidates rated useful by domain owners divided by candidates reviewed in the top K.

**Semantic precision**  
Semantically correct candidates divided by candidates presented as executable.

**Grounding precision**  
Executable operations resolving to the exact reviewed catalog behavior divided by all executable operations.

**Observation precision**  
Data-only operations that exactly match the predicate, direction, term kinds, and Dataset Scope in the Observed Semantic Profile divided by all proposed observed operations.

**Support-level precision**  
Operations and templates carrying the correct qualified_shape, qualified_overlay, or observed_data label divided by all operations and templates.

**Promotion yield**  
Exploratory top-k candidates receiving an accepted Semantic Promotion Record and later passing qualified compilation divided by exploratory top-k candidates reviewed.

**Promotion burden**  
Reviewer minutes and number of semantic decisions required per promoted template.

**Qualification advantage**  
Difference between qualified and data-only conditions in useful precision, task recall, rejection rate, and review burden.

**Parameter safety**  
Parameter mutations rejected or safely represented divided by all parameter mutations.

**Compilation success**  
Validated specifications that compile deterministically.

**Execution fidelity**  
Compiled templates whose instantiated outcomes match semantic oracles across fixtures.

**False executable candidates**  
Candidates that reach qualified Plan Blueprint status or publication while omitting a material task condition, adding an unjustified restriction, using unsupported semantics, carrying observed_data support, or permitting unsafe parameterization. A correctly labeled Exploratory Query Blueprint is not counted as executable.

**Diversity at K**  
Reviewed distinct semantic equivalence classes among the top K.

**Review burden**  
Domain and RDF reviewer minutes per published template and per rejected top-k candidate.

**Discovery efficiency**  
Published useful templates per model call, token, cost unit, and reviewer hour.

### 22.6 Proposed independent gates

Thresholds are frozen before the first retained run. Proposed initial gates:

| Gate | Threshold |
|---|---:|
| Grounding precision for executable candidates | 100% |
| Observation precision for exploratory candidates | 100% |
| Support-level precision | 100% |
| Published operations with observed_data support | 0 |
| Accepted promotions that fail to resolve in the rebuilt catalog | 0 |
| Parameter safety | 100% |
| Compilation success for validated candidates | 100% |
| Execution fidelity for publishable candidates | 100% |
| Semantic precision for published candidates | 100% |
| False executable candidates | 0 |
| Prohibited or unauthorized query publication | 0 |
| Critical task recall at 20 | 100% in every domain |
| Overall task recall at 20 | At least 80% |
| Useful precision at 10 | At least 80% in every domain |
| Duplicate semantic templates in top 10 | At most 20% before deduplication; 0 after publication |
| Required review completion | 100% |
| Model retries | At most one per pass |
| Provider-transmission violations | 0 |

Latency, cost, and reviewer effort are reported in the first benchmark. Numeric product ceilings are set only after the measurement environment and expected catalog size are frozen.

No weighted aggregate score can compensate for a failed correctness, security, or critical-task gate.

### 22.7 Repeated runs

Run every model configuration three times with shuffled semantic-card and task order. Report:

- stability of top-k candidates;
- task coverage by run;
- semantic defect categories;
- first-pass versus retry results;
- latency and cost distributions; and
- review agreement.

### 22.8 Decision outcomes

Exactly one decision is recorded:

- **proceed:** all independent gates pass; build the minimal reviewed registry workflow;
- **revise_and_repeat:** a bounded deterministic or input-contract defect has a credible fix under a new revision; or
- **stop:** usefulness, semantic quality, or review economics do not justify continued model generation.

Repeated prompt tuning against the same held-out labels does not remain held-out evidence.

---

## 23. Test strategy

### 23.1 Unit tests

- Domain Dossier validation.
- Provider-transmission projection.
- Graph Profile bucketing and issue handling.
- Observed Semantic Profile construction and provenance.
- Qualified and observed semantic namespace construction.
- Handle type safety.
- Semantic Support Level propagation.
- Query Template Specification validation.
- Plan Blueprint normalization.
- Exploratory Query Blueprint normalization and namespace separation.
- Semantic Promotion Record validation.
- Parameter term construction.
- Entity ambiguity and unsupported resolution.
- Catalog revision mismatch.
- Query-profile enforcement.
- Deduplication.
- Registry serialization and integrity.
- Review state transitions.

### 23.2 Property and mutation tests

- Arbitrary strings cannot become query syntax.
- Every parameter position accepts only its declared RDF term kind.
- Reordering model collections does not change blueprint identity.
- Changing a semantic operation changes template identity.
- Removing a material operation invalidates task coverage.
- An observed handle can never resolve as a qualified handle.
- Observation confidence can never satisfy Semantic Qualification.
- Apparently scalar data cannot create a scalar projection contract.
- Removing a promotion assumption rejects an exploratory candidate.
- Promotion rebuilds rather than mutates a blueprint.
- Stale catalog keys never resolve by proximity.
- Blank-node labels never create portable identity.
- Every published projection has complete support.

### 23.3 Integration tests

- End-to-end discovery with a fake model.
- Structured-output refusal and incomplete response.
- One bounded retry.
- Data-only discovery with no Shape Catalog.
- Qualified discovery with shapes, overlays, or both.
- Exploratory candidate compile and bounded diagnostic execution.
- Promotion to an Executable Semantic Overlay and catalog rebuild.
- Promotion to genuine draft SHACL and catalog rebuild.
- Rejection of dishonest or incomplete promotions.
- Full qualified candidate compile and ShapeLens execution.
- Positive, no-match, and Boolean outcomes.
- Policy-limited and failed outcomes remain distinct.
- Published registry consumption without OpenAI installed.
- Existing ShapeLens conformance suite remains unchanged.

### 23.4 Security tests

- Prompt-like instructions in labels and descriptions.
- Malicious literal and IRI parameter strings.
- Sensitive profile fields excluded from provider payloads.
- Untrusted imported shapes excluded from semantic cards.
- Observed predicates never exposed as qualified semantic cards.
- Rare RDF types and apparent populations respect profile privacy bands.
- Attempts to publish observed_data candidates fail.
- Attempts to generate SHACL solely as an execution bypass fail review.
- Authorization and policy fields absent from model output.
- Attempted SERVICE, UPDATE, variable predicate, and graph-scope generation.
- Oversized candidate collections and VALUES sets.
- Cross-domain sensitive template proposal.

### 23.5 Golden tests

Golden artifacts pin:

- provider card serialization;
- Observed Semantic Profile serialization;
- observed-card serialization and support-level labels;
- prompt payload projection;
- Structured Outputs schema;
- normalized Plan Blueprints;
- normalized Exploratory Query Blueprints;
- Semantic Promotion Records;
- compiled SPARQL;
- registry JSON; and
- reports.

Golden changes require explicit review because they can change model behavior or executable semantics.

---

## 24. Delivery plan

### Milestone 0 — Experiment specification

Deliver:

- this design refined into a normative Forge experiment specification;
- three reviewed Domain Dossiers;
- frozen gold task portfolios;
- qualified and data-only benchmark conditions;
- semantic-promotion rubric and owners;
- provider-transmission policy;
- evaluation formulas and owners; and
- initial ADRs.

Exit:

- no model implementation starts until inputs, gates, and review roles are frozen.

### Milestone 1 — Deterministic foundation

Deliver:

- package skeleton;
- Domain Dossier types;
- Graph Profiler;
- Observed Semantic Profile and observed-handle types;
- Discovery Semantic IR;
- Query Template Specification types;
- validator;
- qualified Plan Blueprint Compiler;
- Exploratory Query Blueprint Compiler;
- Semantic Promotion Record types and catalog-rebuild path;
- registry format; and
- fake-model end-to-end tests.

Exit:

- every hand-authored qualified specification compiles and executes through ShapeLens;
- every hand-authored observed specification compiles only through the diagnostic sandbox;
- no exploratory artifact is accepted by the runtime registry;
- every seeded invalid specification fails;
- the core ShapeLens suite remains green.

### Milestone 2 — Model adapter

Deliver:

- Responses API adapter;
- strict Structured Outputs;
- xhigh configuration;
- bounded retry handling;
- payload and usage recording;
- Task Portfolio pass; and
- Candidate Synthesizer pass.

Exit:

- a five-task pilot produces fully recorded attempts without any publication.

### Milestone 3 — Candidate evaluation and review

Deliver:

- fixture harness;
- mutation tests;
- utility vector;
- deduplication;
- semantic-promotion workspace;
- draft-overlay and draft-SHACL review outputs;
- review records;
- HTML or terminal review view; and
- report generator.

Exit:

- reviewers can approve or reject candidates without inspecting raw internal Python objects.

### Milestone 4 — Frozen benchmark

Deliver:

- all baselines;
- paired qualified and data-only conditions;
- three repeated runs;
- blinded reviews;
- cost, latency, and review-burden report; and
- proceed, revise_and_repeat, or stop decision.

Exit:

- every independent gate is reported with numerator and denominator.

### Milestone 5 — Minimal publication

Begins only after proceed.

Deliver:

- immutable Template Registry;
- registry verification;
- runtime instantiation API;
- one application-facing registry integration; and
- operational documentation.

Exit:

- runtime consumption needs no model dependency and preserves every ShapeLens validation and evidence invariant.

### Milestone 6 — Optional constrained selector

This is separate Phase 2 work. It may begin only under the Phase 2 decision and benchmark gates. It selects among published templates and fills small slot values; it does not consume draft Forge candidates.

---

## 25. Alternatives considered

### 25.1 Let GPT-5.6 Sol emit raw SPARQL

Rejected for the product path. Structured Outputs can constrain an envelope but cannot make arbitrary query text semantically grounded or safe. Raw SPARQL also bypasses the existing ShapeLens plan, policy, and support boundaries.

Retained only as an offline diagnostic baseline.

### 25.2 Deterministic RDF and shape-pattern enumeration only

Useful as a baseline and candidate supplement. Enumeration can operate over qualified shape material or literally observed RDF patterns. It is strong at structural coverage but weak at identifying which patterns support real domain decisions, which observed assumptions are legitimate, and how queries should be parameterized and presented.

### 25.3 Put discovery inside ShapeQueryEngine

Rejected. ShapeQueryEngine is the deterministic execution authority. Adding model calls or design-time ranking would weaken its package boundary and deployment profile.

### 25.4 Runtime agent with catalog-inspection tools

Rejected for version 0.1. An agent loop increases latency, cost, prompt-injection exposure, and reproducibility problems. The semantic context should be prepared deterministically and sent in bounded passes.

### 25.5 Use raw graph samples as model context

Rejected as the default. Raw samples can expose sensitive values and encourage overfitting to observed instances. Local, classified Graph Profiles are the default. Approved examples can be evaluated later as a named profile.

### 25.6 Automatically publish candidates that pass tests

Rejected. Fixtures and deterministic checks cannot establish business usefulness or fully rule out misleading semantics. Named domain and RDF review remain required.

### 25.7 Separate repository immediately

Deferred. A separate package within the same repository provides a strong dependency boundary while allowing rapid reuse of ShapeLens fixtures and types. Repository separation can occur after the interface stabilizes.

### 25.8 Require SHACL for all discovery

Rejected. RDF instance structure contains enough information to propose many useful graph patterns, and requiring SHACL would exclude valuable datasets. SHACL remains a high-quality semantic source and can reduce review burden, but it is not a discovery prerequisite.

### 25.9 Infer and trust SHACL automatically from RDF data

Rejected. Observed structure cannot establish normative constraints, authorized populations, or intended application semantics. Forge may propose draft SHACL for review only when the pattern is genuinely intended as a validation contract. Query-only meaning belongs in an Executable Semantic Overlay.

---

## 26. Architectural decisions

**FD-001 — Forge is offline design-time tooling.**  
Model generation is not part of query execution.

**FD-002 — The model emits semantic specifications, not executable SPARQL.**  
Deterministic code produces the final SPARQL.

**FD-003 — A Domain Dossier is mandatory.**  
Usefulness cannot be derived from shape and data structure alone.

**FD-004 — Raw RDF remains local by default.**  
The provider receives an approved semantic projection and classified graph profile.

**FD-005 — Published templates use typed RDF-term parameters only.**  
No parameter may introduce syntax.

**FD-006 — Forge reuses the ShapeLens trust, qualification, plan, compiler, policy, and evidence boundaries.**

**FD-007 — Publication always requires named human review.**

**FD-008 — Utility is evaluated as independent dimensions.**  
No aggregate score overrides correctness or security gates.

**FD-009 — Model configuration is GPT-5.6 Sol with xhigh effort for the initial candidate experiment.**  
The benchmark must demonstrate that the setting improves value enough to justify its cost and latency.

**FD-010 — Forge and ShapeLens are separate packages with one-way dependency.**

**FD-011 — Runtime template selection remains separate Phase 2 work.**

**FD-012 — Existing ShapeLens query semantics do not expand implicitly.**

**FD-013 — SHACL is optional for discovery.**  
An RDF graph, Domain Dossier, and Discovery Policy are sufficient to produce exploratory candidates.

**FD-014 — Observed RDF structure has a separate semantic-support level and artifact type.**  
Observed Semantic Handles and Exploratory Query Blueprints cannot be consumed as Catalog keys or Plan Blueprints.

**FD-015 — Data-only publication requires explicit semantic promotion.**  
Each observed operation must be rejected, retained as a hint, or promoted through genuine qualified SHACL behavior or an Executable Semantic Overlay.

**FD-016 — Forge does not generate trusted SHACL merely to authorize a query.**

---

## 27. Open questions

1. Should the first benchmark use standard or pro reasoning mode with xhigh effort? This design starts with standard and treats pro as a separate comparison.
2. How much of the Domain Dossier should be provider-visible in sensitive deployments?
3. Which Graph Profile bands provide useful selectivity signals without exposing rare populations?
4. Should exact non-sensitive example values be allowed, or should all examples be synthetic?
5. Who owns the final domain-value approval when several application teams share a graph?
6. What compatibility promise can be made for IRI-backed templates across Catalog Revisions?
7. Should useful but currently unsupported model proposals be retained as product-backlog evidence?
8. How should review time be measured without making reviewers rush?
9. Is an optional independent model critic worth its additional cost and correlated-error risk?
10. Which fourth domain should serve as external or newly authored validation?
11. Should a later revision admit CONSTRUCT templates for application-owned projections?
12. When, if ever, should aggregates or absence claims enter Forge?
13. Does the review surface belong in the CLI, a static report, or a small local web application?
14. What registry-signing mechanism is appropriate for production deployment?
15. Should registry publication require a separate security reviewer for all templates or only sensitive profiles?
16. How should observed node groups be formed when RDF types are absent, sparse, or polymorphic?
17. May reviewed RDFS or OWL material supplement the Observed Semantic Profile, and under which support level?
18. What minimum observation coverage is required before a predicate can be shown to the model?
19. Which counterexamples should force an observed scalar or type pattern to be hidden rather than presented with low confidence?
20. Should a reviewer be able to promote several observed operations in one overlay record, or must qualification remain field-level?
21. How should data-only discovery behave when the graph contains multiple tenant or named-graph scopes with different structures?
22. Which exploratory artifacts should be retained after reviewers reject their semantic assumptions?

These questions must be resolved before their associated behavior is implemented. They do not block the deterministic Milestone 1 foundation unless explicitly noted.

---

## 28. Acceptance criteria for version 0.1

Forge 0.1 is complete only when:

- the package has no reverse dependency from ShapeLens core;
- all discovery inputs are schema-validated and revision-pinned;
- discovery succeeds without SHACL and produces explicitly exploratory artifacts;
- qualified discovery accepts semantically qualified SHACL, Executable Semantic Overlays, or both;
- every observed operation resolves exactly to the pinned Observed Semantic Profile;
- every candidate and operation carries the correct Semantic Support Level;
- raw RDF is not provider-visible under the default profile;
- model output uses strict Structured Outputs;
- every publishable operation resolves to trusted and qualified catalog material;
- no observed_data operation enters a runtime Template Registry;
- observed candidates compile only through the deterministic diagnostic compiler;
- promoted candidates are rebuilt from a qualified Shape Catalog rather than mutated in place;
- every candidate compiles through the deterministic compiler appropriate to its support mode;
- parameters cannot introduce SPARQL syntax;
- all publishable templates pass the fixture and mutation matrix;
- no model output is automatically published;
- registry artifacts are immutable and integrity checked;
- runtime consumption does not require OpenAI;
- existing ShapeLens conformance tests pass unchanged;
- the frozen benchmark reports every independent gate;
- critical task recall and top-k utility meet the frozen thresholds;
- false executable candidates and provider-transmission violations are zero; and
- the final decision is recorded as proceed, revise_and_repeat, or stop.

---

## 29. References

ShapeLens project material:

- [ShapeLens reference design](https://github.com/grove/shapelens/blob/main/SHAPELENS_DESIGN.md)
- [ShapeLens vision](https://github.com/grove/shapelens/blob/main/VISION.md)
- [ShapeLens 0.1 specification](https://github.com/grove/shapelens/blob/main/SPEC-0.1.md)
- [ShapeLens security profile](https://github.com/grove/shapelens/blob/main/SECURITY.md)
- [ShapeLens domain vocabulary](https://github.com/grove/shapelens/blob/main/CONTEXT.md)
- [Phase 2 planner decision](https://github.com/grove/shapelens/blob/main/phase2/DECISION.md)

OpenAI documentation:

- [GPT-5.6 Sol model](https://developers.openai.com/api/docs/models/gpt-5.6-sol)
- [Reasoning models and effort](https://developers.openai.com/api/docs/guides/reasoning)
- [Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs)

Standards context:

- [SHACL, W3C Recommendation](https://www.w3.org/TR/shacl/)
- [SPARQL 1.1 Query Language, W3C Recommendation](https://www.w3.org/TR/sparql11-query/)

---

## 30. Recommendation

Proceed with Milestone 0 and Milestone 1 before making any live model call.

The immediate deliverable should be a frozen experiment specification plus three reviewed Domain Dossiers and paired qualified/data-only benchmark conditions. Implement the Graph Profiler, Observed Semantic Profile, support-level types, Query Template Specification, both deterministic blueprint compilers, Semantic Promotion Record, fixture harness, and fake-model tests before adding the GPT-5.6 Sol xhigh adapter.

The first live pilot should run both with and without SHACL. It should measure not only query usefulness but also how often data-only candidates can be promoted honestly, whether overlays or genuine SHACL are the appropriate artifacts, and how much qualified shapes reduce review burden.

This order tests the most important architectural claim first: SHACL can improve discovery without being mandatory, but regardless of how creative or capable the model is, only deterministic, qualified, policy-compliant, reviewed templates can reach the ShapeLens runtime.
