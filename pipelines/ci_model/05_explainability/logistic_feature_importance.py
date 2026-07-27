#!/usr/bin/env python3
"""
Feature importance table for the logistic baseline model.

The logistic model z-scores all inputs before training, so the raw coefficients
are already on a comparable scale: |weight| directly measures how much a
one-standard-deviation shift in that feature moves the log-odds of bidding.

Outputs:
    05_explainability/outputs/logistic_feature_importance.csv
    05_explainability/outputs/logistic_feature_importance.txt  (formatted table)

Usage:
    python 05_explainability/logistic_feature_importance.py
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

# ── Paths ─────────────────────────────────────────────────────────────────────
HERE          = Path(__file__).resolve().parent
MODEL_PATH    = HERE.parent / "03_training/outputs/logistic_baseline_model.json"
MANIFEST_PATH = HERE.parent / "02_features/outputs/features_manifest.csv"
OUT_DIR       = HERE / "outputs"

FEATURE_LABELS = {
    # Activity
    "prior_bid_count":              "Total Bids (All Time)",
    "prior_bid_rate":               "Overall Bid Rate",
    "mix_ton_capacity_ratio":       "Mix Ton Capacity Ratio",
    "recent_3m_bid_count":          "Bids in Last 3 Months",
    "recent_6m_bid_count":          "Bids in Last 6 Months",
    "recent_9m_bid_count":          "Bids in Last 9 Months",
    "recent_12m_bid_count":         "Bids in Last 12 Months",
    "recent_24m_bid_count":         "Bids in Last 24 Months",
    "days_since_last_bid":          "Days Since Last Bid",
    # Geography
    "same_state_prior_bid_count":   "Prior Bids — Same State",
    "same_county_prior_bid_count":  "Prior Bids — Same County",
    # Project type match
    "same_project_type_bid_count":  "Prior Bids — Same Project Type",
    "ever_bid_same_project_type":   "Ever Bid Same Project Type (0/1)",
    # Scope match — one per bid-schedule quantity
    "mix_tons_match":               "Mix Tons Scope Match",
    "grading_yards_match":          "Grading Yards Scope Match",
    "base_tons_match":              "Base Tons Scope Match",
    "shldr_tons_match":             "Shoulder Tons Scope Match",
    "mill_sy_match":                "Mill SY Scope Match",
    "crush_tons_match":             "Crush Tons Scope Match",
    "stock_tons_match":             "Stock Tons Scope Match",
    # Project size
    "log_mix_tons":                 "Asphalt Tonnage (log scale)",
    "log_grading_yards":            "Grading Yards (log scale)",
    "log_base_tons":                "Base Tons (log scale)",
    "log_shldr_tons":               "Shoulder Tons (log scale)",
    "log_mill_sy":                  "Milling SY (log scale)",
    "log_crush_tons":               "Crush Tons (log scale)",
    "log_stock_tons":               "Stock Tons (log scale)",
    "project_size_proxy":           "Project Size Proxy",
    # Project flags
    "has_paving":                   "Project Has Paving",
    "has_grading":                  "Project Has Grading",
    "has_base":                     "Project Has Base",
    "has_utility":                  "Project Has Utility",
    "has_structure":                "Project Has Structure",
    "has_drainage":                 "Project Has Drainage",
    "has_reclamation":              "Project Has Reclamation",
    "has_trail":                    "Project Has Trail",
    "is_reconstruction":            "Is Reconstruction",
    "is_structure_replacement":     "Is Structure Replacement",
    # Pit geography
    "pit_applicable":                                   "Pit Data Applicable (MN only)",
    "project_location_missing":                         "Project Location Missing",
    "nearest_open_pit_miles":                           "Nearest Open Pit (miles)",
    "open_pits_lt_10mi":                                "Open Pits Within 10 mi",
    "open_pits_10_25mi":                                "Open Pits 10–25 mi",
    "open_pits_25_50mi":                                "Open Pits 25–50 mi",
    "best_open_pit_rating_within_25mi":                 "Best Open Pit Rating (25 mi)",
    "avg_open_pit_rating_within_25mi":                  "Avg Open Pit Rating (25 mi)",
    "nearest_unknown_access_pit_miles":                 "Nearest Unknown-Access Pit (miles)",
    "unknown_access_pits_within_25mi":                  "Unknown-Access Pits Within 25 mi",
    "has_unknown_access_pit_within_25mi":               "Has Unknown-Access Pit (25 mi)",
    "nearest_accessible_pit_miles":                     "Nearest Accessible Pit (miles)",
    "accessible_pits_lt_10mi":                          "Accessible Pits Within 10 mi",
    "accessible_pits_10_25mi":                          "Accessible Pits 10–25 mi",
    "accessible_pits_25_50mi":                          "Accessible Pits 25–50 mi",
    "best_accessible_pit_rating_within_25mi":           "Best Accessible Pit Rating (25 mi)",
    "avg_accessible_pit_rating_within_25mi":            "Avg Accessible Pit Rating (25 mi)",
    "nearest_owned_or_restricted_pit_miles":            "Nearest Owned/Restricted Pit (miles)",
    "owned_or_restricted_pits_within_25mi":             "Owned/Restricted Pits Within 25 mi",
    "best_owned_or_restricted_pit_rating_within_25mi":  "Best Owned/Restricted Pit Rating (25 mi)",
    "has_competitor_restricted_pit_within_25mi":        "Competitor Has Restricted Pit (25 mi)",
    "nearest_knife_river_pending_pit_miles":            "Nearest KR Pending Pit (miles)",
    "knife_river_pending_pits_within_25mi":             "KR Pending Pits Within 25 mi",
    "competitor_pit_distance_advantage_vs_open":        "Pit Distance Advantage vs Open",
    "competitor_pit_distance_advantage_vs_market_median": "Pit Distance Advantage vs Market Median",
    "has_clear_pit_advantage":                          "Has Clear Pit Advantage",
}

# Group and description overrides. All pit features are MN-only because the
# MN Pit List covers Minnesota only; non-MN rows are set to 9999/0.
_MN = " — MN projects only (set to 9999/0 for ND/SD/IA/etc.)"
FEATURE_META_OVERRIDES: dict[str, dict[str, str]] = {
    # Project type match (renamed features)
    "same_project_type_bid_count":  {"group": "project_type", "description": "Prior bids on the exact same project_type as this project (same state)"},
    "ever_bid_same_project_type":   {"group": "project_type", "description": "Binary: competitor has at least one prior bid on the same project_type (0/1)"},
    # MN applicability flag
    "pit_applicable":               {"group": "pit", "description": "1 if this project is in Minnesota (pit data available), 0 for other states (all pit features zeroed out)"},
    # Open pits — marginal bands
    "nearest_open_pit_miles":                {"group": "pit", "description": "Distance in miles to the nearest publicly open pit" + _MN},
    "open_pits_lt_10mi":                     {"group": "pit", "description": "Count of publicly open pits within 10 miles" + _MN},
    "open_pits_10_25mi":                     {"group": "pit", "description": "Count of publicly open pits between 10 and 25 miles" + _MN},
    "open_pits_25_50mi":                     {"group": "pit", "description": "Count of publicly open pits between 25 and 50 miles" + _MN},
    "best_open_pit_rating_within_25mi":      {"group": "pit", "description": "Highest quality rating among open pits within 25 miles" + _MN},
    "avg_open_pit_rating_within_25mi":       {"group": "pit", "description": "Average quality rating among open pits within 25 miles" + _MN},
    # Unknown-access pits
    "nearest_unknown_access_pit_miles":      {"group": "pit", "description": "Distance in miles to the nearest unknown-access pit" + _MN},
    "unknown_access_pits_within_25mi":       {"group": "pit", "description": "Count of unknown-access pits within 25 miles" + _MN},
    "has_unknown_access_pit_within_25mi":    {"group": "pit", "description": "Flag: at least one unknown-access pit exists within 25 miles (0/1)" + _MN},
    # Accessible pits — marginal bands
    "nearest_accessible_pit_miles":          {"group": "pit", "description": "Distance in miles to the nearest accessible pit (open + unknown + owned)" + _MN},
    "accessible_pits_lt_10mi":               {"group": "pit", "description": "Count of accessible pits (open + unknown + owned) within 10 miles" + _MN},
    "accessible_pits_10_25mi":               {"group": "pit", "description": "Count of accessible pits between 10 and 25 miles" + _MN},
    "accessible_pits_25_50mi":               {"group": "pit", "description": "Count of accessible pits between 25 and 50 miles" + _MN},
    "best_accessible_pit_rating_within_25mi":{"group": "pit", "description": "Highest quality rating among accessible pits within 25 miles" + _MN},
    "avg_accessible_pit_rating_within_25mi": {"group": "pit", "description": "Average quality rating among accessible pits within 25 miles" + _MN},
    # Owned/restricted pits
    "nearest_owned_or_restricted_pit_miles":           {"group": "pit", "description": "Distance in miles to this competitor's nearest owned/restricted pit" + _MN},
    "best_owned_or_restricted_pit_rating_within_25mi": {"group": "pit", "description": "Highest quality rating among this competitor's owned pits within 25 miles" + _MN},
    "has_competitor_restricted_pit_within_25mi":       {"group": "pit", "description": "Flag: this competitor has an owned/restricted pit within 25 miles (0/1)" + _MN},
    # Knife River pending
    "nearest_knife_river_pending_pit_miles": {"group": "pit", "description": "Distance in miles to the nearest Knife River pending pit" + _MN},
    "knife_river_pending_pits_within_25mi":  {"group": "pit", "description": "Count of Knife River pending pits within 25 miles" + _MN},
    # Competitive advantage
    "competitor_pit_distance_advantage_vs_open":          {"group": "pit", "description": "Nearest open pit distance minus competitor's nearest owned pit distance (positive = competitor closer than open market)" + _MN},
    "competitor_pit_distance_advantage_vs_market_median": {"group": "pit", "description": "Median distance to all pits minus competitor's nearest owned pit distance (positive = better than median)" + _MN},
    "has_clear_pit_advantage":                            {"group": "pit", "description": "Flag: competitor's nearest owned pit is ≤25 miles and ≥10 miles closer than nearest open pit (0/1)" + _MN},
}


def build_importance_table(model: dict, manifest: pd.DataFrame) -> pd.DataFrame:
    weights = model["feature_weights"]
    manifest_map = manifest.set_index("feature_name")

    rows = []
    for feat, coef in weights.items():
        abs_coef = abs(coef)
        if abs_coef == 0.0:
            direction = "inactive (zero weight)"
        elif coef > 0:
            direction = "increases bid probability"
        else:
            direction = "decreases bid probability"

        override = FEATURE_META_OVERRIDES.get(feat, {})
        group = (
            override.get("group")
            or (manifest_map.loc[feat, "group"] if feat in manifest_map.index else "—")
        )
        description = (
            override.get("description")
            or (manifest_map.loc[feat, "description"] if feat in manifest_map.index else "—")
        )

        rows.append({
            "feature_name":         feat,
            "display_label":        FEATURE_LABELS.get(feat, feat),
            "feature_group":        group,
            "standardized_coef":    round(coef, 6),
            "abs_standardized_coef": round(abs_coef, 6),
            "direction":            direction,
            "description":          description,
        })

    df = pd.DataFrame(rows)
    df = df.sort_values("abs_standardized_coef", ascending=False).reset_index(drop=True)
    df.insert(0, "rank", df.index + 1)
    return df


def format_table(df: pd.DataFrame) -> str:
    header = (
        "LOGISTIC BASELINE MODEL — Feature Importance Table\n"
        "Coefficients are for z-scored inputs: |coef| = impact of 1 SD shift on log-odds of bidding\n"
        f"Intercept (base log-odds): {df.attrs.get('intercept', 'see model JSON')}\n"
        + "=" * 110
    )

    active = df[df["direction"] != "inactive (zero weight)"]
    inactive = df[df["direction"] == "inactive (zero weight)"]

    col_w = {"rank": 4, "display_label": 32, "feature_group": 13,
             "standardized_coef": 12, "direction": 30}

    def row_str(r: pd.Series) -> str:
        return (
            f"  {r['rank']:<{col_w['rank']}}  "
            f"{r['display_label']:<{col_w['display_label']}}  "
            f"{r['feature_group']:<{col_w['feature_group']}}  "
            f"{r['standardized_coef']:>{col_w['standardized_coef']}.6f}  "
            f"{r['direction']}"
        )

    col_header = (
        f"  {'Rank':<{col_w['rank']}}  "
        f"{'Display Label':<{col_w['display_label']}}  "
        f"{'Group':<{col_w['feature_group']}}  "
        f"{'Std. Coeff':>{col_w['standardized_coef']}}  "
        f"Direction"
    )
    sep = "  " + "─" * 106

    lines = [header, col_header, sep]
    lines += [row_str(r) for _, r in active.iterrows()]

    if not inactive.empty:
        lines += ["", "  ── Inactive features (zero weight) ──"]
        for feat in inactive["feature_name"].tolist():
            lines.append(f"    {feat}")

    return "\n".join(lines) + "\n"


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    model = json.loads(MODEL_PATH.read_text())
    manifest = pd.read_csv(MANIFEST_PATH)

    table = build_importance_table(model, manifest)
    table.attrs["intercept"] = model.get("intercept", "N/A")

    csv_path = OUT_DIR / "logistic_feature_importance.csv"
    table.to_csv(csv_path, index=False)
    print(f"Saved → {csv_path}")

    # Chart-ready CSV with cleaner column names and abs_importance alias
    chart = table.rename(columns={"abs_standardized_coef": "abs_importance"})[
        ["rank", "feature_group", "feature_name", "display_label",
         "standardized_coef", "abs_importance", "direction", "description"]
    ]
    chart_path = OUT_DIR / "feature_importance_for_chart.csv"
    chart.to_csv(chart_path, index=False)
    print(f"Saved → {chart_path}")

    text = format_table(table)
    txt_path = OUT_DIR / "logistic_feature_importance.txt"
    txt_path.write_text(text)
    print(f"Saved → {txt_path}")
    print()
    print(text)


if __name__ == "__main__":
    main()
