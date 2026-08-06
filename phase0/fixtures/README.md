# Fixture records

[`manifest.json`](./manifest.json) freezes 18 accepted corpus-question fixtures, 17 semantic-conformance fixtures, structural cases, both RDFLib adapter modes, and every referenced input under one fixture revision. `semantic_conformance` cases never count toward product coverage.

Run `PYTHONPATH=phase0 .venv/bin/python phase0/run_fixtures.py run` from the repository root to verify the revision and all final gates.
