#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "shared"))

import argparse

import pandas as pd

from io_utils import read_table


def main() -> None:
    parser = argparse.ArgumentParser(description="QA Model 1 candidate panels.")
    parser.add_argument(
        "--rule-candidates",
        default="data/processed/model1/rule_candidate_set.parquet",
    )
    parser.add_argument(
        "--audit-panel",
        default="data/processed/model1/training_audit_panel.parquet",
    )
    parser.add_argument(
        "--ranking-panel",
        default="data/processed/model1/ranking_training_panel.parquet",
    )
    args = parser.parse_args()

    rule_candidates = read_table(args.rule_candidates)
    audit_panel = read_table(args.audit_panel)
    ranking_panel = read_table(args.ranking_panel)

    assert ranking_panel["was_rule_candidate"].eq(1).all(), (
        "ranking_training_panel contains rows that were not rule candidates"
    )

    ranking_missed_actuals = (
        (ranking_panel["did_bid"] == 1)
        & (ranking_panel["was_rule_candidate"] == 0)
    ).sum()
    assert ranking_missed_actuals == 0, (
        "missed actual bidders leaked into ranking_training_panel"
    )

    key_cols = ["candidate_rule_version", "project_natural_key", "competitor_unit_id"]
    assert not rule_candidates.duplicated(key_cols).any(), (
        "rule_candidate_set has duplicate candidate keys"
    )
    assert not ranking_panel.duplicated(key_cols).any(), (
        "ranking_training_panel has duplicate candidate keys"
    )
    assert not audit_panel.duplicated(key_cols).any(), (
        "training_audit_panel has duplicate candidate keys"
    )

    assert audit_panel["competitor_unit_id"].notna().all(), (
        "training_audit_panel contains missing competitor_unit_id"
    )

    invalid_near_low = audit_panel[
        (audit_panel["is_near_low"] == 1)
        & (
            (audit_panel["did_bid"] != 1)
            | audit_panel["gap_to_low"].isna()
            | (audit_panel["gap_to_low"] > 0.05)
        )
    ]
    assert invalid_near_low.empty, "is_near_low contains invalid rows"

    invalid_winner = audit_panel[
        (audit_panel["did_win"] == 1)
        & ((audit_panel["did_bid"] != 1) | (audit_panel["gap_to_low"] != 0))
    ]
    assert invalid_winner.empty, "did_win contains invalid rows"

    missed_actuals = audit_panel[
        (audit_panel["did_bid"] == 1)
        & (audit_panel["was_rule_candidate"] == 0)
    ]

    print("Model 1 candidate panel QA passed")
    print(f"  rule_candidate_set rows:       {len(rule_candidates):,}")
    print(f"  training_audit_panel rows:     {len(audit_panel):,}")
    print(f"  ranking_training_panel rows:   {len(ranking_panel):,}")
    print(f"  missed actual bidders in audit:{len(missed_actuals):,}")
    print("  ranking panel missed actuals:  0")


if __name__ == "__main__":
    main()
