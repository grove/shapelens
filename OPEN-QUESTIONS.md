# Open questions after version 0.1

Normative behavior is fixed in [SPEC-0.1.md](./SPEC-0.1.md). These questions remain intentionally unresolved.

| ID | Question | Resolve before |
|---|---|---|
| OQ-001 | Which planner baselines, fidelity labels, and thresholds establish value for model planning? | Phase 2 |
| OQ-002 | Which additional SHACL target declarations receive selector identity, composition, cost, and evidence semantics? | Phase 4 |
| OQ-003 | Which lexical, comparison, Boolean, union, traversal, aggregate, grouping, negative, or pagination nodes enter the algebra? | Each feature phase |
| OQ-004 | Which remote authorization deployments are supported: endpoint ACLs, graph partitions, injected predicates, or a tested combination? | Phase 3 |
| OQ-005 | How are mandatory authorization predicates represented without exposing policy details? | Phase 3 |
| OQ-006 | Which named Completeness Profiles can authorize negative operators and absence evidence? | Phase 4 |
| OQ-007 | Which auxiliary queries need one store snapshot, and where is disclosed best-effort consistency sufficient? | Phase 3 |
| OQ-008 | What extraction boundary and algorithm provide portable RDFC-1.0 blank-node identity? | Phase 5 |
| OQ-009 | Can ontology or sampled hints ever be promoted automatically? | Phase 2 |
| OQ-010 | Which ambiguity threshold and interaction model govern entity resolution? | Phase 2 |
| OQ-011 | Which partial-enrichment failures still permit an answered outcome? | Phase 3 |
| OQ-012 | Which tenant, encryption, retention, invalidation, and re-authorization rules apply to caches? | Phase 3 |
| OQ-013 | Which schema and evidence classes can be sent to external model providers? | Phase 2 |
| OQ-014 | Which catalog publication and rollback protocol supports multiple workers? | Phase 3 |
| OQ-015 | Which remote endpoint assumptions about graphs, entailment, identity, isolation, and revisions are supportable? | Phase 3 |
| OQ-016 | Is out-of-process plugin isolation a product goal? | Phase 5 |
| OQ-017 | Which proof-strength labels are public, and is model-based claim checking worthwhile? | Phase 2 |
| OQ-018 | Which SHACL 1.2 and SPARQL 1.2 features are portable enough to leave experimental profiles? | Ongoing |

An answer moves out of this file only with tests, specification changes, and an ADR when the trade-off is difficult to reverse.
