# Phase 3 readiness

**Status:** Decision dossier prepared; Phase 3 is not authorized

**Entry gate:** Phase 2 must publish a passing, human-reviewed benchmark report and a `proceed` decision before remote or protected-data code is added. The current [`Phase 2 decision`](./phase2/DECISION.md) does not pass this gate.

## Boundary

Phase 3 is the remote-store and production-controls phase. It does not widen the query algebra, add absence or aggregation, introduce documents or caches, or weaken the deterministic `ShapeQueryEngine` boundary. A remote adapter must execute the same accepted Bound Query Plan and preserve the same Query Outcome and evidence invariants, with its Dataset Scope and consistency limits made explicit.

The first remote implementation starts only after OQ-004, OQ-005, OQ-007, OQ-011, OQ-012, OQ-014, and OQ-015 each has one reviewed decision, its supported profile is named, and its falsifying tests are listed. Difficult-to-reverse trade-offs receive ADRs; profile details and testable behavior belong in a focused specification.

## Decision dossier

| Question | Decision must fix | Evidence required before implementation |
|---|---|---|
| OQ-004 remote authorization | Named supported deployment profiles; enforcement owner for endpoint ACLs, graph partitions, or compiler-injected constraints; unsupported combinations | Cross-profile tests showing every primary and auxiliary query is authorization-relative, including denied projections, filters, existence, named graphs, diagnostics, and evidence lookup |
| OQ-005 mandatory predicates | A representation that cannot be authored or removed by a planner and cannot expose policy details in plans, traces, retries, or user errors | Mutation tests for omission, replacement, contradiction, logging, retry, and explanation paths; operator inspection remains possible through a protected channel |
| OQ-007 split-query consistency | Which evidence classes require one snapshot and which may disclose `best_effort` consistency | Two-store tests that change data between primary and auxiliary queries and verify the resulting Dataset Scope, evidence limitations, and prohibited claims |
| OQ-011 partial enrichment | Core versus optional enrichment classes, degradation rules, retryability, and the Query or Answer Outcome exposed to applications | Failure matrix for labels, provenance, validation, and later documents; no optional failure may change core rows or silently strengthen a claim |
| OQ-012 caches | Whether any cache exists in Phase 3; if so, tenant keys, encryption, retention, invalidation, revision keys, and re-authorization | Cross-tenant and stale-authorization tests for every admitted cache class. Default is no result, evidence, entity, or model-response cache until this evidence exists |
| OQ-014 catalog publication | Atomic publication, worker coordination, in-flight revision pinning, migration, rollback, and readiness behavior | Multi-worker hot-swap and rollback tests proving one Run Context never mixes Catalog Revisions |
| OQ-015 endpoint contract | Default and named graph behavior, entailment, blank-node scope, transaction isolation, revision metadata, supported result media types, and capability configuration | The same behavioral suite against two materially different SPARQL Protocol stores, with every divergence represented as a capability or unsupported profile |

## Minimum implementation authorized by passing decisions

- one asynchronous SPARQL Protocol adapter with explicit credentials and endpoint configuration;
- configured capabilities plus bounded, non-sensitive probes where a decision permits probing;
- streaming response parsing with compressed and uncompressed byte ceilings;
- one end-to-end deadline with cancellation propagation;
- retry classification limited to reviewed idempotent failures, with a bounded attempt budget;
- normalized safe failures, circuit breaking, readiness, and backpressure;
- explicit Dataset Scope for default or named graphs, entailment, revision, and consistency;
- atomic catalog publication under the chosen coordination profile;
- metrics and SLOs for endpoint availability, p95 latency, deadline exhaustion, policy failures, catalog age, and degraded outcomes;
- the shared behavior suite against at least two remote stores.

No cache, generic row-level authorization claim, automatic capability discovery, raw SPARQL escape hatch, dialect plugin system, document enrichment, or stronger snapshot claim is implied by this list.

## Required remote behavior matrix

The Phase 3 test plan must cover, for both stores:

1. `SELECT`, `ASK`, empty results, Boolean false, exact RDF terms, direct and inverse edges, named-graph scopes, and complete row support.
2. Endpoint authentication denial, protocol and media-type errors, malformed terms, oversized and compressed responses, slow headers, slow bodies, disconnects, and cancellation.
3. Retryable versus terminal failures, deadline exhaustion across retries, circuit opening and recovery, concurrency limits, and backpressure.
4. Authorization on planning cards, plan validation, compilation constraints, primary execution, every auxiliary query, evidence, explanations, traces, and any admitted cache.
5. Snapshot or revision behavior across split queries, including disclosed best-effort inconsistency.
6. Catalog publish, readiness, concurrent in-flight runs, rollback, and worker restart without mixed revisions.

## Phase 3 start record

When the entry gate passes, replace this readiness status with a short start record linking:

- the Phase 2 decision and immutable benchmark revision;
- each resolved OQ and any ADR;
- the named protected-data and endpoint profiles;
- the two selected remote-store versions and test environments;
- the focused specification revision, threat-model update, owners, and numeric SLOs.

Until then, `SECURITY.md` remains authoritative: only the trusted local RDFLib profile is supported.
