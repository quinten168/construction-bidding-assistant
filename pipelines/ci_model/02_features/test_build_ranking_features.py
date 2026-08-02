from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "shared"))

from build_ranking_features import build_ranking_features


class QuantityMatchTest(unittest.TestCase):
    """Regression guard for the pure-quantity, one-per-material rebuild of the old
    paving_match/grading_match/base_match trio.

    Before this fix, `_match` was computed off has_paving/has_grading/has_base — HYBRID flags
    that can be true from a keyword match on the project name alone, with zero real tonnage, and
    grouped 3 categories together (base_tons + shldr_tons sharing one "base_match") even though
    each has its own quantity column. The rewrite keys strictly off the quantity columns, one
    match feature per material (mix_tons_match, grading_yards_match, base_tons_match, ...), for
    both the current project and each competitor's prior-bid history. This test proves a
    competitor whose only prior activity has zero real base tonnage does NOT get base_tons_match,
    while one with real prior base tonnage does — the exact distinction the rewrite exists to make.
    """

    def setUp(self) -> None:
        self.candidate_rule = "test_rule"

        # Two prior projects (both before the target's bid_date): one with real base tonnage,
        # one without (has a different, non-base quantity instead, so its bidder isn't simply
        # "inactive").
        self.projects = pd.DataFrame(
            [
                ("J_PRIOR_BASE", "2024-01-01", "MN", "X CO", "other", 0, 0, 80),
                ("J_PRIOR_NOBASE", "2024-01-02", "MN", "X CO", "other", 50, 0, 0),
            ],
            columns=["project_natural_key", "bid_date", "state", "county", "project_type",
                     "mix_tons", "grading_yards", "base_tons"],
        )
        self.bidder_results = pd.DataFrame(
            [
                ("J_PRIOR_BASE", "REAL_BASE", 0),
                ("J_PRIOR_NOBASE", "NO_BASE", 0),
            ],
            columns=["project_natural_key", "competitor_unit_id", "did_win"],
        )

        # The target project itself: real base scope (base_tons=250), both competitors are
        # candidates on it.
        self.ranking_panel = pd.DataFrame(
            [
                {
                    "candidate_rule_version": self.candidate_rule,
                    "project_natural_key": "J_TARGET",
                    "competitor_unit_id": comp,
                    "bid_date": "2024-06-01",
                    "state": "MN",
                    "county": "X CO",
                    "project_type": "other",
                    "was_rule_candidate": 1,
                    "mix_tons": 0,
                    "grading_yards": 0,
                    "base_tons": 250,
                    "shldr_tons": 0,
                    "mill_sy": 0,
                    "crush_tons": 0,
                    "stock_tons": 0,
                }
                for comp in ("REAL_BASE", "NO_BASE")
            ]
        )

    def test_base_tons_match_requires_real_prior_quantity(self) -> None:
        result = build_ranking_features(
            ranking_panel=self.ranking_panel,
            projects=self.projects,
            bidder_results=self.bidder_results,
            candidate_rule=self.candidate_rule,
        ).set_index("competitor_unit_id")

        self.assertEqual(result.loc["REAL_BASE", "base_tons_match"], 1)
        self.assertEqual(result.loc["NO_BASE", "base_tons_match"], 0)
        # shldr_tons_match is now a SEPARATE feature from base_tons_match (previously grouped
        # into one "base_match") -- neither competitor has real shldr_tons history, so both 0.
        self.assertEqual(result.loc["REAL_BASE", "shldr_tons_match"], 0)
        self.assertEqual(result.loc["NO_BASE", "shldr_tons_match"], 0)

    def test_project_size_proxy_averages_only_present_quantities(self) -> None:
        # J_TARGET has exactly one non-zero quantity (base_tons=250) — the average over the
        # "present" set is just that one value, not diluted by the other 6 legitimately-zero
        # quantities (a milling-only-style project shouldn't look "small" for lacking mix/grading).
        result = build_ranking_features(
            ranking_panel=self.ranking_panel,
            projects=self.projects,
            bidder_results=self.bidder_results,
            candidate_rule=self.candidate_rule,
        )
        expected = np.log1p(250)
        for value in result["project_size_proxy"]:
            self.assertAlmostEqual(value, expected, places=6)


if __name__ == "__main__":
    unittest.main()
