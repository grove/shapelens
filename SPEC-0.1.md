# ShapeLens 0.1 specification

**Status:** Normative
**Version:** 0.1.0
**Conformance command:** `.venv/bin/python -m unittest discover -s tests -v`

This is the only normative ShapeLens 0.1 document. The key words **MUST**, **MUST NOT**, **REQUIRED**, **SHOULD**, **SHOULD NOT**, and **MAY** are interpreted as described by RFC 2119 and RFC 8174 only when they appear in uppercase here.

## Scope

ShapeLens 0.1 is a deterministic Python runtime for executing caller-authored, catalog-bound positive graph-query plans over an in-process RDFLib `Graph` or `Dataset`. It does not interpret natural-language questions and makes no question-to-plan fidelity claim.

The supported algebra contains `select` and `ask`, IRI entity bindings, explicit Population Selector Uses, contextual Lens Uses, required direct or inverse edges, exact RDF-term equality, positive existence, node projection, and qualified scalar field projection. It excludes raw SPARQL, negation, absence claims, aggregation, ordering, pagination, remote execution, model planning, documents, plugins, and portable blank-node identity.

## Requirements

### SL-001 — RDF terms

IRIs MUST be absolute and syntactically valid for SPARQL IRI references. Entity bindings MUST be IRIs. Literals MAY have either an absolute datatype IRI or a valid, lowercase-normalized language tag, but MUST NOT have both. Lexical forms MUST be preserved. Equality MUST compile to `sameTerm`; numeric coercion, collation, Unicode normalization, and language fallback MUST NOT occur.

### SL-002 — Query algebra

A plan MUST contain only the operations listed in Scope. Every input collection and every local identifier MUST pass structural validation. Unknown variants and unknown fields MUST fail closed. A `select` plan MUST project at least one value; an `ask` plan MUST project none. Raw graph patterns, variable names, predicates, functions, and query fragments MUST NOT be accepted from a plan.

### SL-003 — Canonical plans

Caller-selected local IDs and collection ordering MUST NOT affect the normalized plan digest or compiled query. Semantic duplicates, dangling references, unused Lens Uses, duplicate entity/lens pairs, and disconnected multi-entity plans MUST be rejected. The pinned Catalog Revision MUST participate in validation and the plan digest.

### SL-004 — Population selection

A Population Selector MUST be applied only through an explicit Selector Use. An unbound root MUST have one trusted, qualified, authorized Selector Use. At most one Selector Use per entity is supported. `sh:targetClass` uses direct `rdf:type` matching only. `sh:targetNode` accepts IRI targets only. A targetless lens MUST NOT enumerate an unbound root.

### SL-005 — Contextual lenses and contracts

One Entity Variable MAY carry several Lens Uses; their Shape Lenses MUST remain separate. Every property operation MUST name the Lens Use whose lens owns that property. A relationship Value Contract MUST NOT import a target lens's Population Selector. Direct and inverse predicate paths are executable. Unsupported paths remain diagnostic-only. Contract branches from `sh:or` and `sh:in` MUST retain separate identities. An equality term MUST satisfy its named contract branch; an incompatible term MUST be rejected rather than executed outside the reviewed contract.

### SL-006 — Compilation

The compiler MUST accept only a validated canonical plan and MUST emit a library-owned typed AST. The renderer MUST emit only SPARQL 1.1 `SELECT` or `ASK`, direct or inverse triples, `VALUES`, `sameTerm`, `OPTIONAL` scalar fields, selector union where required, named-dataset clauses, `DISTINCT`, and a policy-owned limit. The rendered query MUST parse successfully before execution. Update forms, `SERVICE`, custom functions, repeating paths, and caller-authored syntax MUST NOT be emitted.

### SL-007 — Local execution

The 0.1 store profile MUST use an in-process RDFLib `Graph` or `Dataset`. Both adapters MUST produce the same accepted solution mappings. A named-graph scope MUST use an RDFLib `Dataset`, compile only the named allowed graphs into the dataset clause, and use the same graph scope for evidence lookup. Default execution uses the store-default graph mode.

### SL-008 — Typed outcomes

Execution MUST return one of `Selected`, `BooleanResult`, `NoMatch`, `PolicyLimited`, `Unsupported`, or `Failed`. `BooleanResult` is valid only for a completed true `ask`; a completed false `ask` uses `NoMatch`. `NoMatch` MUST describe a completed empty or false positive query relative to the pinned Dataset Scope and Authorization Scope. It MUST NOT claim real-world absence.

### SL-009 — Evidence and certificates

Every execution packet MUST contain exactly one `QueryResultEvidence` bound to its execution, canonical plan digest, rendered query digest, Dataset Scope, and Authorization Scope. Every positive selected row MUST have exactly one `RowEvidence` and one `RowSupportCertificate`. The certificate MUST map every selector, edge, filter, and projection in the complete Row Atom Set exactly once and MUST contain no other atom.

Direct-type selectors, direct and inverse edges, existence and equality filters, and bound field projections MUST link compatible physical triple witnesses. Target-node selectors and node projections MUST derive from the correct entity binding. An unbound optional scalar projection MUST use `optional_unbound` with no evidence or derivation references. Physical evidence for an inverse edge MUST preserve RDF subject-predicate-object orientation.

### SL-010 — Failure honesty

Cancellation, deadline expiry, malformed result envelopes, result parsing failure, byte-limit failure, scalar-contract violation, and incomplete execution MUST produce `Failed`, never `NoMatch`. A complete-set request that exceeds the policy row ceiling MUST produce `PolicyLimited`. Empty and Boolean outcomes MUST NOT carry row certificates. Packet completeness fields MUST be computed by the runtime and contradictory combinations MUST be rejected.

### SL-011 — Executable admission

Shape Source Trust and Semantic Qualification MUST be separate inputs. A source contributes executable behavior only when it and every declared closure member are `trusted`. Qualification MUST identify exact selector, property, or scalar-projection behavior and at least one reviewed fixture. Scalar-overlay qualification MUST bind the property direction and branch contract, not only its shape and predicate. Trust MUST NOT qualify behavior, qualification MUST NOT establish trust, and either state MUST NOT bypass runtime authorization. `quarantined` sources MUST NOT enter the catalog.

### SL-012 — Selector/context separation

A joined entity MUST receive only the selected relationship branch and its explicitly named Lens Uses. Its contextual target declarations MUST NOT be imported unless the plan contains a separate Selector Use for that entity.

### SL-013 — Diagnostic-only material

Non-IRI `sh:targetNode` or `sh:targetClass` values and unsupported paths MUST NOT create executable selectors or properties. They MUST be retained as catalog diagnostics. Invalid bounded RDF lists and invalid executable constraint terms MUST fail catalog construction.

### SL-014 — Catalog identity and artifacts

A catalog MUST be immutable and carry a schema version and integrity-checked revision. Serialization followed by reload MUST preserve the revision and every Catalog-Local Key. A stale plan revision or stale local key MUST fail. IRI-backed node shapes and IRI-backed property shapes MAY receive Portable Logical Keys. Blank-node-backed declarations MUST receive only Catalog-Local Keys, and a rebuild MAY assign them a new revision and keys.

### SL-015 — Scalar projection

A field projection MUST reference a trusted, qualified property and branch with either reviewed `sh:maxCount 1` semantics or a separately trusted and qualified executable scalar overlay. Potentially multi-valued fields MUST be rejected. If execution observes more than one distinct value despite a scalar contract, the result MUST fail validation. Optional scalar fields MAY be unbound; required scalar fields MUST be bound.

### SL-016 — Evidence validation

Evidence validation MUST reject missing, duplicated, extra, wrong-row, wrong-execution, wrong-plan, and wrong-query support. It MUST reject unknown support states, invalid evidence/derivation combinations, entity-binding mismatches, and packet/query scope contradictions. Evidence identifiers alone MUST NOT establish support.

### SL-017 — Deterministic presentation and explanation

`render_result` MUST render only the typed outcome and MUST disclose truncation, policy limitation, unsupported behavior, and failure. It MUST NOT assert question fidelity. `explain_plan` MUST validate and authorize without execution and return the canonical plan digest, compiled query, atom identifiers, pinned policy and authorization identities, and catalog diagnostics.

### SL-018 — Local security profile

Authorization MUST be trusted engine configuration, not plan content. It MUST apply independently to every Lens Use, Selector Use, property operation, and named graph. Query Policy MUST own finite limits for plan collections, AST nodes, result rows, result bytes, deadline, retries, and auxiliary queries. Catalog Policy MUST own finite limits for source bytes, source triples, RDF-list length, recursion, paths, and lens-card material. The 0.1 profile MUST NOT claim generic row- or value-level authorization.

## Conformance mapping

| Requirements | Authoritative test |
|---|---|
| SL-001–SL-010 | `test_sl_001_to_010_accepted_kernel_matrix` — 35 frozen plans in RDFLib Graph and Dataset modes: 68 executed cells match reviewed oracles and 2 out-of-contract datatype cells fail closed; plus `test_sl_001_to_010_validation_boundaries` |
| SL-011 | `test_sl_011_catalog_trust_qualification_and_authorization` |
| SL-012 | `test_sl_012_population_and_context_are_separate` |
| SL-013 | `test_sl_013_targetless_and_invalid_targets_fail_closed` |
| SL-014 | `test_sl_014_canonicalization_and_catalog_identity` |
| SL-015 | `test_sl_015_scalar_and_optional_projection_rules` |
| SL-016 | `test_sl_016_evidence_mutations_are_rejected` |
| SL-017 | `test_sl_017_outcomes_failure_honesty_and_rendering` |
| SL-018 | `test_sl_018_named_graph_scope_is_enforced_end_to_end`, `test_sl_018_policy_limits_fail_closed`, and `test_sl_011_catalog_trust_qualification_and_authorization` |

The earlier Phase 0 suite remains a regression gate for the accepted corpus, experiment revisions, normalization, inspectability arithmetic, and failure-honesty proof.
