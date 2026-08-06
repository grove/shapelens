import unittest

import evaluate


class EvaluateTests(unittest.TestCase):
    def test_frozen_early_gate(self):
        result, errors = evaluate.early_gate()
        self.assertEqual(errors, [])
        self.assertTrue(result["pass"])
        self.assertEqual(result["classification_counts"], {
            "algebra_blocked": 2, "direct": 14, "overlay": 4,
        })
        self.assertEqual(result["blocker_distribution"], {"algebra.absence": 1, "algebra.aggregate": 1})


if __name__ == "__main__":
    unittest.main()
