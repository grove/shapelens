import unittest
import copy
import json
from pathlib import Path

from run_fixtures import run
from kernel import Catalog, PlanError, Term, normalize


class FixtureTests(unittest.TestCase):
    def test_frozen_phase0_matrix(self):
        result = run()
        self.assertTrue(result["pass"])

    def test_plan_boundary_is_strict(self):
        root = Path(__file__).parent
        catalog = Catalog.reload(json.loads((root / "fixtures/catalog.json").read_text()))
        raw = json.loads((root / "fixtures/plans/semantic-multi-lens.json").read_text())
        malformed = copy.deepcopy(raw)
        next(item for item in malformed["projections"] if item["kind"] == "field")["required"] = "true"
        with self.assertRaises(PlanError):
            normalize(malformed, catalog)
        escaped = Term.load({"kind": "literal", "value": "a\tb\bc\f"}).sparql()
        self.assertEqual(escaped, '"a\\tb\\bc\\f"')


if __name__ == "__main__":
    unittest.main()
