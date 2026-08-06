# Phase 0 experiment

**Status:** Protocol to instantiate before implementation
**Purpose:** Test the ShapeLens product thesis and semantic kernel as separate claims

## 1. Freeze the corpus before measuring it

Assemble a small, versioned corpus of independently authored or representative SHACL graphs from the applications ShapeLens intends to serve. Record each graph’s owner, application scenario, shape provenance, shape style, and whether any material was rewritten for the experiment. The initial corpus must include at least three materially different application scenarios; a larger corpus is preferred when it is available without manufacturing examples around the proposed algebra.

Application owners provide high-value questions in their own language before seeing ShapeLens plans. Each question records its priority, expected answer form, relevant dataset fixture, and a reviewed direct-SPARQL or application-code baseline where one is meaningful. Corpus membership, metric owners, and numeric product thresholds are frozen in the corpus manifest before classification results are calculated.

## 2. Classify every question

Each question receives exactly one primary classification:

| Classification | Meaning |
|---|---|
| `direct` | Expressible from admitted and semantically qualified SHACL material with the version 0.1 algebra |
| `overlay` | Expressible only after a reviewed Executable Semantic Overlay |
| `algebra_blocked` | Requires an operation outside the current algebra |
| `shape_blocked` | Blocked by shape identity, structure, ambiguity, or missing query meaning |
| `ordinary_code` | More honestly or simply handled by ordinary application code |

Secondary reason codes identify the exact operator, identity restriction, missing selector, missing lens use, or semantic declaration responsible. `Unsupported` is a measured honest result, not a failed attempt to force coverage.

## 3. Record overlay and rewriting burden

For every `overlay` case, record the number and kind of application-authored executable declarations, affected lenses, review owner, and supporting semantic fixtures. Descriptive labels and aliases are reported separately because they do not expand executable behavior. Rewriting an existing shape for the experiment is reported separately from adding an overlay; neither may be counted as direct coverage.

Shape Source Trust and Semantic Qualification are evaluated independently. A source may be trusted yet unfit as a query interface. Every executable selector, join mapping, projection declaration, or Affordance must state whether it was directly derived or application-authored and which reviewed fixture qualifies it for the intended use.

## 4. Required semantic fixtures

After the question corpus is frozen, create hand-authored plans and reviewed reference queries. The fixture matrix includes:

- direct and inverse predicate orientation;
- direct-type and IRI target-node Population Selectors;
- exact IRI, datatype, lexical-form, and language-tag identity;
- connected positive selection and Boolean queries, including true, false, and empty results;
- one Entity Variable using two distinct Lens Uses without merging their Shape Lenses;
- at least one executable blank-node-backed property shape referenced by a Catalog-Local Key, including artifact reload, rebuild, and stale-key behavior;
- equivalent plan orderings and local identifiers, plus deliberately non-equivalent near misses;
- a Row Support Certificate with exactly one entry for every selector, edge, filter, and projection in the normalized Row Atom Set;
- cancellation, timeout, malformed result, byte limit, and interrupted sentinel checks that never become answers or `NoMatch`.

Empty positive results create query-level result evidence only. They never fabricate row certificates or property-level negative evidence.

## 5. Measure separate gates

Every report publishes the corpus revision, fixture revision, metric owner, numerator, denominator, exclusions, and predeclared threshold. The following gates remain separate:

| Gate | Measure | Minimum decision rule |
|---|---|---|
| Compiler correctness | Compiled and reviewed reference queries return equivalent RDF solution mappings for every accepted feature-matrix cell in RDFLib Graph and Dataset modes | 100% of accepted semantic fixtures and declared local adapter modes |
| Normalization correctness | Declared equivalent inputs share a digest and query; declared non-equivalent inputs remain distinct | 100% of equivalence and near-miss fixtures |
| Shape authoring compatibility | Operations compiling from representative shape graphs without semantic rewrites, reported by graph, shape style, and unsupported construct | Meet the corpus-manifest threshold; no hidden rewriting |
| Question coverage | `direct` and `overlay` questions divided by all in-scope high-value questions | Meet the predeclared direct and combined coverage thresholds |
| Overlay burden | Executable declarations per `overlay` question and per graph, reported as median and worst case | Meet the predeclared burden limits; labels and aliases excluded |
| Inspectability | Paired seeded-defect reviews over ShapeLens artifacts and the reviewed direct-SPARQL or application-code baseline, recording correct localization and review time | 100% responsible-artifact identification for ShapeLens and the predeclared comparative time or accuracy threshold |
| Evidence completeness | Positive rows whose certificate maps the complete Row Atom Set exactly once | 100%; empty results have no row certificate |
| Failure honesty | Interrupted, ambiguous, policy-limited, or unsupported cases emitted as an answer or `NoMatch` | Zero false answer or false `NoMatch` outcomes |

Correctness, evidence completeness, and failure honesty are non-negotiable. Product thresholds for coverage, shape authoring compatibility, overlay burden, and review time are application decisions and must be declared before results are known. No weighted aggregate can turn a failed gate into a pass.

## 6. Decision

Proceed to the version 0.1 library shell only when every non-negotiable gate passes and the predeclared product thresholds are met. Otherwise narrow the target users, revise the algebra or identity model, improve the shapes and overlays with an explicit burden report, or stop. Model planning is not part of this decision.
