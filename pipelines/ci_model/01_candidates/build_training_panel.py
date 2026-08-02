from __future__ import annotations

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "shared"))

import pandas as pd

from config import DISCOVERY_TIER, TIER_COL


PROJECT_TYPE_FEATURE_COLUMNS = [
    "rule_based_primary_project_type_v1",
    "project_type_source",
    "project_type_rule",
]


def add_low_bid_labels(panel: pd.DataFrame, near_low_threshold: float = 0.05) -> pd.DataFrame:
    result = panel.copy()
    result["bid_amount"] = pd.to_numeric(result["bid_amount"], errors="coerce")

    low_bid = (
        result.loc[result["did_bid"] == 1]
        .groupby(["candidate_rule_version", "project_natural_key"])["bid_amount"]
        .min()
        .rename("low_bid_amount")
    )
    result = result.merge(low_bid, on=["candidate_rule_version", "project_natural_key"], how="left")
    valid_low = result["low_bid_amount"].notna() & (result["low_bid_amount"] > 0)
    result["gap_to_low"] = pd.NA
    result.loc[valid_low, "gap_to_low"] = (
        result.loc[valid_low, "bid_amount"] - result.loc[valid_low, "low_bid_amount"]
    ) / result.loc[valid_low, "low_bid_amount"]
    result["gap_to_low"] = pd.to_numeric(result["gap_to_low"], errors="coerce")
    result["did_win"] = (
        (result["did_bid"] == 1)
        & result["gap_to_low"].notna()
        & (result["gap_to_low"] == 0)
    ).astype(int)
    result["is_near_low"] = (
        (result["did_bid"] == 1)
        & result["gap_to_low"].notna()
        & (result["gap_to_low"] <= near_low_threshold)
    ).astype(int)
    return result


def build_training_audit_panel(
    rule_candidate_set: pd.DataFrame,
    projects: pd.DataFrame,
    bidder_results: pd.DataFrame,
    near_low_threshold: float = 0.05,
    rule_versions: list[str] | None = None,
) -> pd.DataFrame:
    """Build audit panel = rule candidates + missed actual bidders."""

    candidate_keys = [
        "candidate_rule_version",
        "project_natural_key",
        "competitor_unit_id",
    ]
    project_cols = [
        "project_natural_key",
        "bid_date",
        "state",
        "county",
        "project_type",
        *PROJECT_TYPE_FEATURE_COLUMNS,
        "mix_tons",
        "grading_yards",
        "base_tons",
        "shldr_tons",
        "mill_sy",
        "crush_tons",
        "stock_tons",
        "low_bid_amount",
    ]
    available_project_cols = [col for col in project_cols if col in projects.columns]
    # Renamed on the way in: add_low_bid_labels() below computes its own low_bid_amount (min
    # bid_amount among rule candidates, scoped to candidate_rule_version+project_natural_key) --
    # this project-level one (min bid_amount across ALL bidders, from projects.csv) would collide
    # into low_bid_amount_x/_y on the merge in add_low_bid_labels() otherwise.
    project_lookup = projects[available_project_cols].drop_duplicates("project_natural_key").rename(
        columns={"low_bid_amount": "project_low_bid_amount"}
    )

    # bidder_results already carries project_natural_key (assigned in
    # build_project_competitor_panel.py's build_bidder_results()) -- it's also project_lookup's
    # merge key now, so pandas uses it directly rather than producing an _x/_y suffix pair.
    actual = bidder_results.merge(project_lookup, on="project_natural_key", how="left")
    actual = actual[
        [
            "project_natural_key",
            "bid_date",
            "state",
            "county",
            "project_type",
            *[col for col in PROJECT_TYPE_FEATURE_COLUMNS if col in actual.columns],
            "mix_tons",
            "grading_yards",
            "base_tons",
            "shldr_tons",
            "mill_sy",
            "crush_tons",
            "stock_tons",
            "project_low_bid_amount",
            "competitor_unit_id",
            "bid_amount",
            "bid_rank",
        ]
    ].copy()
    actual["did_bid"] = 1

    frames = []
    if rule_versions is None:
        rule_names = sorted(rule_candidate_set["candidate_rule_version"].dropna().unique())
    else:
        rule_names = rule_versions

    for rule_name in rule_names:
        rule_candidates = rule_candidate_set[
            rule_candidate_set["candidate_rule_version"] == rule_name
        ].copy()
        rule_candidates = rule_candidates.merge(
            actual[
                [
                    "project_natural_key",
                    "competitor_unit_id",
                    "bid_amount",
                    "bid_rank",
                    "did_bid",
                ]
            ],
            on=["project_natural_key", "competitor_unit_id"],
            how="left",
        )
        rule_candidates["did_bid"] = rule_candidates["did_bid"].fillna(0).astype(int)
        rule_candidates["candidate_inclusion_type"] = "rule_candidate"

        actual_for_rule = actual.copy()
        actual_for_rule["candidate_rule_version"] = rule_name
        actual_for_rule = actual_for_rule.merge(
            rule_candidates[candidate_keys],
            on=candidate_keys,
            how="left",
            indicator=True,
        )
        missed_actual = actual_for_rule[actual_for_rule["_merge"] == "left_only"].copy()
        missed_actual = missed_actual.drop(columns="_merge")
        missed_actual["was_rule_candidate"] = 0
        missed_actual["source_same_state"] = False
        missed_actual["source_same_county"] = False
        missed_actual["source_same_state_type"] = False
        missed_actual["source_recent_activity"] = False
        missed_actual["source_priority"] = False
        missed_actual["source_regional"] = False
        missed_actual["candidate_source"] = "missed_actual_bidder"
        missed_actual["candidate_inclusion_type"] = "missed_actual_bidder"
        if TIER_COL in rule_candidates.columns:
            missed_actual[TIER_COL] = DISCOVERY_TIER

        frames.append(rule_candidates)
        frames.append(missed_actual)

    audit_panel = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    audit_panel["bid_date"] = pd.to_datetime(audit_panel["bid_date"], errors="coerce")
    for col in ["mix_tons", "grading_yards", "project_low_bid_amount", "bid_amount", "bid_rank"]:
        if col in audit_panel.columns:
            audit_panel[col] = pd.to_numeric(audit_panel[col], errors="coerce")

    audit_panel["did_bid"] = pd.to_numeric(
        audit_panel["did_bid"], errors="coerce"
    ).fillna(0).astype(int)
    audit_panel["was_rule_candidate"] = pd.to_numeric(
        audit_panel["was_rule_candidate"], errors="coerce"
    ).fillna(0).astype(int)

    for col in [
        "source_same_state",
        "source_same_county",
        "source_same_state_type",
        "source_recent_activity",
        "source_priority",
        "source_regional",
    ]:
        audit_panel[col] = audit_panel[col].astype("boolean").fillna(False).astype(bool)

    audit_panel = add_low_bid_labels(audit_panel, near_low_threshold=near_low_threshold)
    return audit_panel.sort_values(
        ["candidate_rule_version", "project_natural_key", "was_rule_candidate", "competitor_unit_id"],
        ascending=[True, True, False, True],
    ).reset_index(drop=True)


def build_ranking_training_panel(training_audit_panel: pd.DataFrame) -> pd.DataFrame:
    """Ranking training input: only rows available at future inference time."""

    return training_audit_panel[
        training_audit_panel["was_rule_candidate"] == 1
    ].copy().reset_index(drop=True)
