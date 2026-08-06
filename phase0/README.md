# Phase 0 workspace

This directory contains the working records for the experiment defined in [`PHASE0-EXPERIMENT.md`](../PHASE0-EXPERIMENT.md). It is experiment infrastructure, not the `shapelens` package or a public API.

## The sequencing boundary

Phase 0 deliberately separates product inputs from evaluation outputs:

1. Application owners author questions without seeing ShapeLens plans or classifications.
2. The team records representative shape graphs, RDF fixtures, reviewed baselines, metric owners, and numeric product thresholds.
3. `freeze-check` validates those inputs while `classifications/` is still empty.
4. The frozen corpus is committed before any classification or typed-plan work begins.
5. Questions are classified and overlay/rewrite burden is recorded.
6. Focused semantic fixtures, hand-authored plans, and semantic-oracle queries are created separately.
7. The eight gates are reported independently using the frozen denominators and thresholds.

Focused conformance cases must not be added to the product-question corpus. They test the compiler; they do not improve question coverage.

## Files

- `corpus/manifest.json` owns corpus membership, scenario and shape-graph records, metric owners, and product thresholds.
- `templates/manifest-records.json` shows the embedded scenario and shape-graph record shapes.
- `corpus/questions/` receives one JSON record per application question, based on `templates/question.json`.
- `corpus/classifications/` receives one post-freeze record per question, based on `templates/classification.json`.
- `fixtures/` receives semantic and corpus-question fixture records based on `templates/fixture.json`.
- `REPORT-TEMPLATE.md` preserves the independent gates and reporting denominators.
- `validate.py` performs only the dependency-free corpus freeze and drift checks needed for milestone 0.0a.

Paths stored in records are repository-relative. Keep application-owned source material unchanged where possible; record rewrites explicitly rather than replacing the original.

## Stage A: freeze product inputs

Copy `templates/question.json` into `corpus/questions/<question-id>.json` for each question and add its path to `manifest.json`. Populate 20–30 questions across at least three materially different scenarios. Add the referenced SHACL, RDF, and reviewed baseline files under `corpus/` or point to their repository-relative locations.

The manifest contains starting product thresholds for this experiment. They remain proposals while `status` is `draft`; metric and application owners must review them before freezing. The supported shape-compatibility rule, `no_shape_blocked_or_rewrite`, counts an eligible graph as passing when no in-scope question that references it is `shape_blocked` or requires a rewrite. List every graph referenced by an in-scope question as eligible so the denominator cannot be chosen after results are known.

Run the draft check as often as needed:

```console
python3 phase0/validate.py draft-check
```

When the inputs are ready, run the freeze check while the manifest is still a draft:

```console
python3 phase0/validate.py freeze-check
```

`freeze-check` fails if any classification JSON already exists. After it passes, assign an immutable corpus revision, set `status` to `frozen`, fill `frozen_at` and `frozen_by`, and commit those frozen inputs before continuing. `frozen-check` detects later content drift. Later corrections create a new corpus revision; do not silently edit the denominator used by an existing report.

The printed revision is a SHA-256 digest over the stable manifest fields and the content of every listed question, shape graph, dataset fixture, and application baseline. Classification and semantic-fixture outputs bind to that revision but are not part of it.

```console
python3 phase0/validate.py frozen-check
```

## Stage B: classify, then build the semantic spike

Create exactly one classification record for each frozen in-scope question. Record one primary classification, precise namespaced blocker reasons, affected shape graphs, descriptive and executable overlay counts and kinds, declaration references, rewrite burden, source trust, owner semantic review, and reviewers. Overlay declarations are charged to each affected graph for the conservative per-graph burden limit. The milestone 0.0 record keeps `qualification_status` as `pending`; milestone 0.1 fixtures decide whether the candidate behavior qualifies.

If product coverage and burden remain credible, create semantic fixtures. The minimal spike is:

```text
qualified SHACL → minimal catalog → hand-authored typed plan
                → validation and normalization → SPARQL
                → RDFLib Graph/Dataset → typed outcome + atom/witness map
```

The atom/witness representation is internal to Phase 0. It must map the complete Row Atom Set exactly once but need not establish the public evidence API.

Classification calculations and fixture validators are deliberately not prebuilt. Add only the automation that the frozen corpus and accepted semantic spike actually require.

## Stage C: compare and decide

Use `REPORT-TEMPLATE.md` to report correctness, normalization, compatibility, coverage, overlay burden, inspectability, evidence completeness, and failure honesty separately. Compare authoring and defect-localization work with the frozen direct-SPARQL or application-code baselines.

Proceed to a version 0.1 library only if every non-negotiable rule passes and the predeclared product thresholds pass in more than one scenario. Otherwise narrow the intended users, revise the repeatedly observed blocker, or stop.
