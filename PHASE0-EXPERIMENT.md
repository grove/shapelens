# Phase 0 experiment

**Status:** Complete; all gates passed in [`phase0/DECISION.md`](./phase0/DECISION.md)

**Purpose:** Test the ShapeLens product thesis and semantic kernel as separate claims

## Experiment scope

Phase 0 uses trusted local RDFLib `Graph` and `Dataset` data, trusted local shape material whose exact executable behaviors are qualified by semantic fixtures, plus negative admission fixtures. The candidate algebra contains direct and inverse predicate paths, explicit direct-type and IRI target-node Population Selectors, connected positive joins, exact RDF-term identity, positive existence, `SELECT`, `ASK`, and minimal internal atom-to-witness support. Phase 0 does not stabilize a package layout, public API, evidence taxonomy, or authorization framework. It performs no network I/O and excludes model planning, GraphRAG, remote stores, absence claims, aggregation, pagination, documents, plugins, and production infrastructure.

## 1. Freeze the corpus before measuring it

Assemble a versioned corpus of 20–30 high-value questions across at least three materially different application scenarios and their independently authored or representative SHACL graphs. Prefer four or five materially different shape graphs when they are available without manufacturing examples around the proposed algebra. Record each graph’s owner, application scenario, shape provenance, shape style, and whether any material was rewritten for the experiment.

Scenario owners provide the questions in their own language before seeing ShapeLens plans or classifications. For the recorded internal Phase 0 run, project maintainers acted as scenario owners and supplied representative project-owned questions; this is not external application-owner validation. Each question records its priority, expected answer form, relevant dataset fixture, and a reviewed direct-SPARQL or application-code baseline where one is meaningful. Corpus membership, question text, baselines, metric owners, and numeric product thresholds are frozen in the corpus manifest before classification begins. The natural question corpus measures product coverage; focused semantic fixtures added later test correctness and never increase the product-coverage numerator or denominator.

## 2. Classify every question

Each question receives exactly one primary classification:

| Classification | Meaning |
|---|---|
| `direct` | Structurally expressible from the frozen shape material with the Phase 0 candidate algebra, without an Executable Semantic Overlay or shape rewrite |
| `overlay` | Structurally expressible only after a reviewed Executable Semantic Overlay, without rewriting the frozen shape material |
| `algebra_blocked` | Requires an operation outside the current algebra |
| `shape_blocked` | Blocked by shape identity, structure, ambiguity, or missing query meaning |
| `ordinary_code` | More honestly or simply handled by ordinary application code |

Secondary reason codes identify the exact operator, identity restriction, missing selector, missing lens use, semantic declaration, or ordinary-code advantage responsible. Use namespaced codes such as `algebra.aggregate`, `shape.missing_population_selector`, `overlay.join_mapping`, or `ordinary_code.simpler`. `Unsupported` is a measured honest result, not a failed attempt to force coverage.

These milestone 0.0 classifications measure structural product coverage; they do not declare operations runtime-executable. Shape Source Trust and owner semantic review are recorded during classification, while field-level Semantic Qualification remains `pending` until the exact behavior passes its milestone 0.1 semantic fixture.

## 3. Record overlay and rewriting burden

For every `overlay` case, record the number and kind of application-authored executable declarations, affected lenses, review owner, and supporting semantic fixtures. Descriptive labels and aliases are reported separately because they do not expand executable behavior. Rewriting an existing shape for the experiment is reported separately from adding an overlay; neither may be counted as direct coverage.

Shape Source Trust and Semantic Qualification are evaluated independently. A source may be trusted yet unfit as a query interface. Every candidate executable selector, join mapping, projection declaration, or Affordance states whether it was directly derived or application-authored and identifies its planned semantic fixture. It becomes semantically qualified only after that fixture is reviewed and passes.

After classification, apply an early product gate using the frozen direct coverage, combined coverage, structural shape compatibility, and overlay-burden thresholds. Do not build typed semantics or a compiler when this gate fails; narrow the users, revise the product hypothesis with a new corpus revision, or stop.

## 4. Required semantic fixtures

After the corpus is frozen and the early product gate passes, create hand-authored plans and reviewed semantic-oracle queries. An application baseline captures how the original question is answered today and supports the later comparative review; a semantic oracle establishes exact solution-mapping behavior for one accepted plan. One artifact may serve both roles only when both roles and reviews are explicit. The fixture matrix includes:

- direct and inverse predicate orientation;
- direct-type and IRI target-node Population Selectors;
- exact IRI, datatype, lexical-form, and language-tag identity;
- connected positive selection and Boolean queries, including true, false, and empty results;
- one Entity Variable using two distinct Lens Uses without merging their Shape Lenses;
- at least one executable blank-node-backed property shape referenced by a Catalog-Local Key, including artifact reload, rebuild, and stale-key behavior;
- equivalent plan orderings and local identifiers, plus deliberately non-equivalent near misses;
- a minimal internal atom-to-witness map with exactly one entry for every selector, edge, filter, and projection in the normalized Row Atom Set;
- cancellation, timeout, malformed result, byte limit, and interrupted sentinel checks that never become answers or `NoMatch`.

The Phase 0 representation need not become the public evidence API. It must nevertheless prove the complete-row support semantics that a later Row Support Certificate may wrap. Empty positive results create query-level result evidence only; they never fabricate row certificates or property-level negative evidence.

## 5. Measure separate gates

Every report publishes the corpus revision, fixture revision, metric owner, numerator, denominator, exclusions, and predeclared threshold. The following gates remain separate:

| Gate | Measure | Minimum decision rule |
|---|---|---|
| Compiler correctness | Compiled and reviewed semantic-oracle queries return equivalent RDF solution mappings for every accepted feature-matrix cell in RDFLib Graph and Dataset modes | 100% of accepted semantic fixtures and declared local adapter modes |
| Normalization correctness | Declared equivalent inputs share a digest and query; declared non-equivalent inputs remain distinct | 100% of equivalence and near-miss fixtures |
| Shape authoring compatibility | Structural no-rewrite compatibility at the early product gate, then compiler-backed compatibility at the final gate, reported by graph, shape style, and unsupported construct | Meet the frozen corpus-manifest rule at both stages; no hidden rewriting |
| Question coverage | `direct` and `overlay` questions divided by all in-scope high-value questions | Meet the predeclared direct and combined coverage thresholds |
| Overlay burden | Executable declarations per `overlay` question and per graph, reported as median and worst case | Meet the predeclared burden limits; labels and aliases excluded |
| Inspectability | Paired seeded-defect reviews over ShapeLens artifacts and the reviewed direct-SPARQL or application-code baseline, recording correct localization and review time | 100% responsible-artifact identification for ShapeLens and the predeclared comparative time or accuracy threshold |
| Evidence completeness | Positive rows whose internal support map covers the complete Row Atom Set exactly once | 100%; empty results have no row support map |
| Failure honesty | Interrupted, ambiguous, policy-limited, or unsupported cases emitted as an answer or `NoMatch` | Zero false answer or false `NoMatch` outcomes |

Correctness, evidence completeness, and failure honesty are non-negotiable. Product thresholds for coverage, shape authoring compatibility, overlay burden, and review time are application decisions and must be declared before results are known. No weighted aggregate can turn a failed gate into a pass.

## 6. Decision

Proceed to the version 0.1 library shell only when every non-negotiable gate passes and the predeclared product thresholds are met in more than one application scenario. Otherwise narrow the target users, revise the algebra or identity model, improve the shapes and overlays with an explicit burden report, or stop. Repeated blocker categories, rather than the existing future roadmap, determine which semantic feature is considered next. Model planning is not part of this decision.

## 7. Start here

Use the dependency-free workspace in [`phase0/`](./phase0/README.md). Its manifest and record templates keep preclassification inputs separate from later classifications and semantic fixtures. The `freeze-check` command enforces the 20–30-question, three-scenario, baseline, metric-owner, and threshold requirements and refuses to freeze a corpus that already contains classifications.
