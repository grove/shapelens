# ADR-0001: deterministic runtime first

**Status:** Accepted for 0.1

## Decision

The initial product is `ShapeQueryEngine.execute_plan()`. It accepts a caller-authored typed plan, never raw SPARQL or a natural-language question, and makes no question-fidelity claim. Model planning, retrieval, remote stores, and answer generation remain later compositions.

## Consequences

The complete 0.1 path is testable without a model provider or network. Applications own the meaning of caller-authored plans. A future planner has to pass the same deterministic boundary and add its own fidelity evidence.
