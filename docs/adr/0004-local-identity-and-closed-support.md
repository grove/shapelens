# ADR-0004: catalog-local identity and closed row support

**Status:** Accepted for 0.1

## Decision

Every executable catalog item has a revision-scoped local key. IRI-backed declarations may also have a portable key; blank nodes do not. Every positive selected row has a certificate covering its complete selector, edge, filter, and projection atom set exactly once.

## Consequences

Serialized catalog artifacts preserve local keys, while rebuilding blank-node material can publish new ones. Stored plans stay revision-bound. Evidence is a closed support map rather than an open citation bag, so missing and cross-query support are detectable.
