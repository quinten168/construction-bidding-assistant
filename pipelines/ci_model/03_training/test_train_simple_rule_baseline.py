from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "shared"))

from train_simple_rule_baseline import FALLBACK_WEIGHTS, MIN_FIT_ROWS, fit_primary_weights


class FitPrimaryWeightsTest(unittest.TestCase):
    def test_falls_back_on_small_train_split(self) -> None:
        # Fewer rows than MIN_FIT_ROWS -- should not attempt a fit at all.
        n = MIN_FIT_ROWS - 1
        features = pd.DataFrame({
            "county": np.random.rand(n), "type": np.random.rand(n),
            "state": np.random.rand(n), "size_fit": np.random.rand(n),
        })
        did_bid = np.random.randint(0, 2, n)
        train_mask = np.ones(n, dtype=bool)

        weights, meta = fit_primary_weights(features, did_bid, train_mask)

        self.assertEqual(weights, FALLBACK_WEIGHTS)
        self.assertFalse(meta["fit"])

    def test_falls_back_on_single_class_train_split(self) -> None:
        n = MIN_FIT_ROWS + 10
        features = pd.DataFrame({
            "county": np.random.rand(n), "type": np.random.rand(n),
            "state": np.random.rand(n), "size_fit": np.random.rand(n),
        })
        did_bid = np.zeros(n, dtype=int)  # only one class present
        train_mask = np.ones(n, dtype=bool)

        weights, meta = fit_primary_weights(features, did_bid, train_mask)

        self.assertEqual(weights, FALLBACK_WEIGHTS)
        self.assertFalse(meta["fit"])

    def test_fits_and_learns_informative_feature_direction(self) -> None:
        # `county` cleanly separates the classes; the other three are pure noise. A correct fit
        # should learn a positive, non-trivial weight on `county` and produce a real (not
        # fallback) result.
        rng = np.random.default_rng(0)
        n = 2000
        county = rng.normal(size=n)
        noise_type = rng.normal(size=n)
        noise_state = rng.normal(size=n)
        noise_size_fit = rng.normal(size=n)
        # Higher `county` value -> much more likely did_bid=1.
        prob = 1.0 / (1.0 + np.exp(-3.0 * county))
        did_bid = (rng.random(n) < prob).astype(int)

        features = pd.DataFrame({
            "county": county, "type": noise_type, "state": noise_state, "size_fit": noise_size_fit,
        })
        train_mask = np.ones(n, dtype=bool)

        weights, meta = fit_primary_weights(features, did_bid, train_mask)

        self.assertTrue(meta["fit"])
        self.assertGreater(weights["county"], 0)
        # county's learned weight should dominate the three uninformative features.
        self.assertGreater(weights["county"], abs(weights["type"]))
        self.assertGreater(weights["county"], abs(weights["state"]))
        self.assertGreater(weights["county"], abs(weights["size_fit"]))


if __name__ == "__main__":
    unittest.main()
