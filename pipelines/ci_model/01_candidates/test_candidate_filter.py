from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "shared"))

from candidate_filter import build_v3_candidate_set
from config import DEFAULT_CANDIDATE_RULE


class CandidatePoolV3Test(unittest.TestCase):
    def setUp(self) -> None:
        # mix_tons/grading_yards/base_tons carry distinct, non-uniform values per row so a
        # pass-through test can assert an exact value round-trips for a known project_natural_key (see
        # test_quantity_columns_pass_through below) — the column being present but empty
        # wouldn't catch a splice-list omission the way a specific value does.
        self.projects = pd.DataFrame(
            [
                ("J0", "2023-01-01", "MN", "OLD CO", "old", 100, 0, 0),
                ("J1", "2023-01-02", "MN", "OLD CO", "old", 0, 200, 0),
                ("J2", "2023-01-03", "MN", "OLD CO", "old", 0, 0, 50),
                ("JW", "2023-06-01", "MN", "WARM CO", "warm", 300, 0, 0),
                ("JC", "2024-05-01", "MN", "RECENT CO", "recent", 0, 400, 0),
                ("JP", "2024-06-15", "MN", "TARGET CO", "target", 500, 0, 250),
                ("JF", "2024-07-01", "MN", "FUTURE CO", "future", 0, 0, 0),
            ],
            columns=["project_natural_key", "bid_date", "state", "county", "project_type",
                     "mix_tons", "grading_yards", "base_tons"],
        )
        self.bids = pd.DataFrame(
            [
                ("J0", "A_COUNTY", 0),
                ("J0", "B_TYPE", 0),
                ("J0", "D_WARMUP", 0),
                ("J0", "E_WINNER", 1),
                ("J0", "F_RECURRING", 0),
                ("J1", "F_RECURRING", 0),
                ("J2", "F_RECURRING", 0),
                ("JC", "C_RECENT", 0),
                ("JF", "Q_FUTURE", 1),
            ],
            columns=["project_natural_key", "competitor_unit_id", "did_win"],
        )
        # Put A/B on synthetic projects to isolate each intended signal.
        extra = pd.DataFrame(
            [
                ("JA", "2023-01-04", "MN", "TARGET CO", "other", 0, 0, 0),
                ("JB", "2023-01-05", "MN", "OTHER CO", "target", 0, 0, 0),
            ],
            columns=self.projects.columns,
        )
        self.projects = pd.concat([self.projects, extra], ignore_index=True)
        self.bids.loc[self.bids.competitor_unit_id == "A_COUNTY", "project_natural_key"] = "JA"
        self.bids.loc[self.bids.competitor_unit_id == "B_TYPE", "project_natural_key"] = "JB"
        all_ids = set(self.bids.competitor_unit_id) | {"P_PRIORITY", "I_INACTIVE"}
        self.entities = pd.DataFrame(
            {
                "competitor_unit_id": sorted(all_ids),
                "active_flag": [0 if value == "I_INACTIVE" else 1 for value in sorted(all_ids)],
            }
        )
        self.priority = pd.DataFrame(
            {"competitor_unit_id": ["P_PRIORITY", "I_INACTIVE"], "effective_from": [pd.NA, pd.NA]}
        )

    def test_v3_entry_logic_and_active_gate(self) -> None:
        result = build_v3_candidate_set(
            self.projects, self.bids, self.priority, self.entities
        )
        jp = result[result.project_natural_key == "JP"].set_index("competitor_unit_id")

        self.assertEqual(set(result.candidate_rule_version), {DEFAULT_CANDIDATE_RULE})
        for expected in ["A_COUNTY", "B_TYPE", "C_RECENT", "E_WINNER", "F_RECURRING", "P_PRIORITY"]:
            self.assertIn(expected, jp.index)
        self.assertNotIn("D_WARMUP", jp.index)       # warmup is no longer active
        self.assertNotIn("I_INACTIVE", jp.index)    # active gate applies to priority
        self.assertNotIn("Q_FUTURE", jp.index)      # no future-data leakage
        self.assertEqual(jp.loc["E_WINNER", "fallback_score"], 2.0)
        self.assertEqual(jp.loc["F_RECURRING", "fallback_score"], 1.5)

    def test_warmup_restores_same_state_12m(self) -> None:
        result = build_v3_candidate_set(
            self.projects, self.bids, self.priority, self.entities
        )
        warmup = result[result.project_natural_key == "JW"].set_index("competitor_unit_id")
        self.assertIn("D_WARMUP", warmup.index)
        self.assertEqual(warmup.loc["D_WARMUP", "v3_in_warmup_12m"], 1)
        self.assertEqual(warmup.loc["D_WARMUP", "v3_in_default_90d"], 0)

    def test_quantity_columns_pass_through(self) -> None:
        # Regression guard for the bug where rule_candidate_set never carried mix_tons/
        # grading_yards/etc. at all: PROJECT_QUANTITY_COLUMNS existing on `projects` but being
        # omitted from the splice-and-select lists in candidate_filter.py would silently drop
        # these columns with no error (the `if col in projects.columns` guard tolerates missing
        # columns by design, so only an explicit presence+value assertion catches this).
        result = build_v3_candidate_set(
            self.projects, self.bids, self.priority, self.entities
        )
        for col in ("mix_tons", "grading_yards", "base_tons"):
            self.assertIn(col, result.columns)

        jp = result[result.project_natural_key == "JP"]
        self.assertEqual(jp["mix_tons"].iloc[0], 500)
        self.assertEqual(jp["grading_yards"].iloc[0], 0)
        self.assertEqual(jp["base_tons"].iloc[0], 250)

        jc = result[result.project_natural_key == "JC"]
        self.assertEqual(jc["mix_tons"].iloc[0], 0)
        self.assertEqual(jc["grading_yards"].iloc[0], 400)


if __name__ == "__main__":
    unittest.main()
