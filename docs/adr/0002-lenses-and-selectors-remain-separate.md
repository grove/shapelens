# ADR-0002: lenses and selectors remain separate

**Status:** Accepted for 0.1

## Decision

An Entity Variable can use several contextual Shape Lenses. Population Selectors are separate plan atoms and arrive only through explicit Selector Uses. Relationship value contracts never import a target lens's population.

## Consequences

Context-specific shapes are not merged into a universal class schema. Targetless contracts can describe joined values but cannot enumerate roots. Plans are slightly more explicit, which makes population mistakes visible in review and evidence.
