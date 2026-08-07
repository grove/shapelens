# ADR-0003: trust, qualification, and authorization are independent

**Status:** Accepted for 0.1

## Decision

Shape Source Trust admits a source. Semantic Qualification approves exact executable behaviors with fixture coverage. Authorization permits those behaviors for a run. Query Policy bounds their form and cost. No one state implies another.

## Consequences

Trusted validation-oriented shapes do not automatically become query APIs. Untrusted or partly untrusted closures fail closed. Applications keep source admission and authorization outside RDF content and caller plans.
