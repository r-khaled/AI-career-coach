import json
from pathlib import Path
import unittest
from scripts.estimate_cost import estimate


class CostModelTests(unittest.TestCase):
    def setUp(self):
        self.config = json.loads((Path(__file__).resolve().parents[1] / "docs/cost-model.json").read_text())

    def test_no_requests_still_incur_search_capacity(self):
        usage = {**self.config["assumptions"], "requests": 0}
        result = estimate(self.config, usage)
        self.assertAlmostEqual(result["breakdown"]["opensearch_compute"], 175.20)
        self.assertEqual(result["breakdown"]["nova_generation"], 0)
        self.assertGreater(result["total_usd"], 175.20)

    def test_fractional_kib_writes_round_up_and_request_work_scales(self):
        usage = {**self.config["assumptions"], "requests": 1000, "item_kib": 1.01}
        first = estimate(self.config, usage)
        second = estimate(self.config, {**usage, "requests": 2000})
        self.assertAlmostEqual(first["breakdown"]["dynamodb_writes"], 0.00125)
        self.assertAlmostEqual(second["breakdown"]["nova_generation"], 2 * first["breakdown"]["nova_generation"])
        self.assertEqual(first["breakdown"]["opensearch_compute"], second["breakdown"]["opensearch_compute"])

    def test_invalid_usage_is_rejected(self):
        for value in [-1, "NaN", "Infinity"]:
            with self.assertRaises(ValueError):
                estimate(self.config, {**self.config["assumptions"], "hours": value})


if __name__ == "__main__":
    unittest.main()
