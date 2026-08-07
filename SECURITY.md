# ShapeLens 0.1 security profile

This document describes the supported deployment boundary. Normative conformance requirements live only in [SPEC-0.1.md](./SPEC-0.1.md).

## Supported profile

Version 0.1 supports trusted application code, trusted local RDF data, explicitly described local shape sources, and in-process RDFLib execution. Authorization is supplied to the engine by trusted application configuration. It can allowlist catalog lenses, selectors, property operations, and named graphs. A Shape Lens or catalog policy tag is not itself an access-control boundary.

Named-graph restrictions use explicit RDFLib `Dataset` scopes and are applied to both query compilation and evidence lookup. An authorization graph allowlist does not accept an unscoped default dataset. The default profile operates on the RDFLib store-default graph only.

This profile does not claim generic row-level or value-level authorization, safe remote endpoints, protected-data isolation, multi-tenant cache safety, credentials management, source fetching, import resolution, or plugin isolation.

## Executable source admission

The application supplies each `ShapeSource` descriptor; RDF content cannot mark itself trusted. Executable behavior requires all of the following independent conditions:

- the source and its declared closure are trusted;
- the exact selector, property, or scalar-projection behavior has a qualification record with fixture coverage;
- the runtime Authorization Scope permits the operation;
- Query Policy permits the plan and resource cost.

Untrusted sources remain diagnostic. Quarantined sources are excluded. Descriptive and policy overlays cannot add executable behavior. An executable overlay can add the supported scalar-projection contract only when it is trusted and exactly qualified.

Remote URL loading, `owl:imports`, JSON-LD remote contexts, SHACL-JS, arbitrary extensions, model planning, and raw caller-authored SPARQL are absent from this release.

## Query and resource controls

The compiler owns a small typed AST and renders read-only `SELECT` or `ASK`. RDF terms pass through trusted codecs. The rendered query is parsed again before local execution. Finite catalog and query policies bound input triples and bytes, RDF lists, plan collections, AST nodes, result rows and bytes, and execution time. Retries are disabled.

RDFLib execution is synchronous; the deadline is checked immediately after the local call. This prevents an overdue result from becoming an outcome, but it does not preempt CPU time inside RDFLib. Deployments needing hard interruption or hostile-data isolation need a later out-of-process profile.

## Evidence and disclosure

Evidence is scoped to one execution, plan, query, catalog, dataset, and authorization digest. Physical triple witnesses are reported with assertion status `unknown`; the local adapter does not claim asserted-versus-entailed provenance. Empty and false results are described only as no visible solution in the pinned scopes. They do not create negative evidence or real-world absence claims.

Debug explanations contain compiled SPARQL and catalog diagnostics. Applications should treat those as operator-facing material because IRIs and allowed semantic structure may be sensitive.

## Reporting

Security reports should include a minimal reproduction, the affected version, the configured local profile, and whether untrusted shape or data input is involved. Avoid including protected RDF data in public issue reports.
