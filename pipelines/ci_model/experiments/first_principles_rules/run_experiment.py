#!/usr/bin/env python3
"""
Reverse-baseline experiment requested by Mochen: instead of making the ML model
more complex, hand-write first-principles single-factor rules and see whether
any of them alone can reproduce the client's "3-5 known real competitors, 90%
of the time the winner is one of them" intuition -- WITHOUT any candidate
pre-filtering (i.e. ranking directly over the full ~700+ competitor universe,
same setup the teammate already used for the composite "Simple Rule-Based"
baseline).

Rules implemented (see rules.py for the exact math):
  1. distance        - nearest self-owned MN pit to the project site, nothing else
  2. capacity_size_fit - project-material-scale fit (variant A of "capacity")
  3. capacity_volume    - raw historical dollar volume, no project-fit (variant B)
  4. historical_winrate_state - win rate for the project type, candidate pool
                                 restricted to same-state history only

This script is fully independent of the existing 01-06 pipeline: it reads the
same processed data files but does not modify or depend on any pipeline step.

Usage:
    python run_experiment.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from rules import (
    MATERIAL_COLUMNS,
    build_company_pit_locations,
    restrict_and_score_historical_winrate,
    score_capacity_size_fit,
    score_capacity_volume,
    score_distance_rule,
)

REPO_ROOT = Path(__file__).resolve().parents[4]
DATA_DIR = REPO_ROOT / "data" / "processed"
OUT_DIR = Path(__file__).resolve().parent / "outputs"

# Match the existing pipeline's train/validation/test split (shared/config.py)
# so results are comparable to the XGBoost / Logistic / Existing-Rule numbers.
VALIDATION_END_DATE = "2025-05-01"
TOP_K_VALUES = [5, 10, 20]


def load_data() -> dict[str, pd.DataFrame]:
    projects = pd.read_csv(DATA_DIR / "projects.csv")
    projects["bid_date"] = pd.to_datetime(projects["bid_date"], errors="coerce")

    bidder_results = pd.read_csv(DATA_DIR / "bidder_results.csv")
    bidder_results["did_win"] = pd.to_numeric(bidder_results["did_win"], errors="coerce").fillna(0)

    pit_list = pd.read_csv(DATA_DIR / "MN_pit_list_cleaned.csv")

    history = bidder_results.merge(
        projects[["project_natural_key", "bid_date", "state", "county", "project_type"] + MATERIAL_COLUMNS],
        on="project_natural_key",
        how="left",
        validate="many_to_one",
    )
    return {
        "projects": projects,
        "bidder_results": bidder_results,
        "pit_list": pit_list,
        "history": history,
    }


def build_full_universe_panel(projects: pd.DataFrame, history: pd.DataFrame) -> pd.DataFrame:
    """One row per (test project, every competitor with prior history before its bid_date).

    This is the "no pre-filtering, all 700+ companies" candidate pool -- the same
    setup used for the existing composite Simple Rule-Based baseline.
    """
    test_projects = projects[projects["bid_date"] >= pd.Timestamp(VALIDATION_END_DATE)].copy()

    rows = []
    for _, project in test_projects.iterrows():
        bid_date = project["bid_date"]
        prior = history[history["bid_date"] < bid_date]
        universe = prior["competitor_unit_id"].dropna().astype(str).unique()
        if len(universe) == 0:
            continue
        actual = history[(history["project_natural_key"] == project["project_natural_key"])]
        did_bid_ids = set(actual["competitor_unit_id"].astype(str))
        did_win_ids = set(actual.loc[actual["did_win"] == 1, "competitor_unit_id"].astype(str))

        frame = pd.DataFrame({"competitor_unit_id": universe})
        frame["project_natural_key"] = project["project_natural_key"]
        frame["did_bid"] = frame["competitor_unit_id"].isin(did_bid_ids).astype(int)
        frame["did_win"] = frame["competitor_unit_id"].isin(did_win_ids).astype(int)
        rows.append(frame)

    panel = pd.concat(rows, ignore_index=True)
    return panel.merge(test_projects, on="project_natural_key", how="left")


def compute_hit_rates(scored: pd.DataFrame, score_col: str) -> dict:
    """Winner Hit Rate@K and any-bidder Precision@K, restricted to projects with
    a resolvable winner inside the (possibly rule-restricted) candidate pool."""
    rows = []
    for project_natural_key, group in scored.groupby("project_natural_key", sort=False):
        has_winner = int(group["did_win"].sum()) > 0
        ordered = group.sort_values(score_col, ascending=False)
        row = {"project_natural_key": project_natural_key, "has_winner_in_pool": has_winner, "candidate_count": len(group)}
        for k in TOP_K_VALUES:
            top = ordered.head(k)
            row[f"winner_in_top_{k}"] = int(top["did_win"].sum() > 0) if has_winner else np.nan
            row[f"precision_at_{k}"] = int(top["did_bid"].sum()) / k
        rows.append(row)
    per_project = pd.DataFrame(rows)

    summary = {"projects_evaluated": int(len(per_project))}
    with_winner = per_project[per_project["has_winner_in_pool"]]
    summary["projects_with_winner_in_pool"] = int(len(with_winner))
    for k in TOP_K_VALUES:
        summary[f"winner_hit_rate_at_{k}"] = (
            round(float(with_winner[f"winner_in_top_{k}"].mean()), 4) if len(with_winner) else float("nan")
        )
        summary[f"precision_at_{k}"] = round(float(per_project[f"precision_at_{k}"].mean()), 4)
    return summary, per_project


def run_rule(name: str, scored: pd.DataFrame, score_col: str, notes: str) -> dict:
    summary, per_project = compute_hit_rates(scored, score_col)
    summary["rule"] = name
    summary["notes"] = notes
    per_project.to_csv(OUT_DIR / f"per_project_{name}.csv", index=False)
    return summary


def add_existing_model_reference_rows(results: list[dict]) -> None:
    """Pull Winner Hit Rate@K for the existing (filtered-candidate-pool) models
    from 03_training/outputs/ranking_predictions.csv, for side-by-side comparison.
    These run on the pre-filtered candidate panel, not the full universe -- noted
    explicitly since the pool sizes are not apples-to-apples."""
    pred_path = REPO_ROOT / "ci_model" / "competitor_prediction_model" / "03_training" / "outputs" / "ranking_predictions.csv"
    if not pred_path.exists():
        return
    predictions = pd.read_csv(pred_path)
    if "time_split" not in predictions.columns:
        return
    test = predictions[predictions["time_split"] == "test"].copy()
    if "did_win" not in test.columns:
        return
    test["did_win"] = pd.to_numeric(test["did_win"], errors="coerce").fillna(0)
    test["did_bid"] = pd.to_numeric(test["did_bid"], errors="coerce").fillna(0)

    reference_cols = {
        "existing_rule_heuristic (filtered pool)": "rule_score",
        "logistic_regression (filtered pool)": "logistic_score",
    }
    for name, col in reference_cols.items():
        if col not in test.columns:
            continue
        summary, _ = compute_hit_rates(test, col)
        summary["rule"] = name
        summary["notes"] = "reference only -- runs on pre-filtered candidate pool, not full universe"
        results.append(summary)


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    data = load_data()
    projects, history, pit_list = data["projects"], data["history"], data["pit_list"]

    print("Building full-universe (no pre-filtering) candidate panel for test-split projects...")
    panel = build_full_universe_panel(projects, history)
    print(f"  test projects: {panel['project_natural_key'].nunique():,}")
    print(f"  candidate rows: {len(panel):,}  (median candidates/project: {panel.groupby('project_natural_key').size().median():.0f})")

    company_pit_locations = build_company_pit_locations(pit_list, data["bidder_results"])
    print(f"  companies with an owned MN pit (distance rule coverage): {len(company_pit_locations)}")

    results: list[dict] = []
    distance_frames, size_fit_frames, volume_frames, winrate_frames = [], [], [], []

    for project_natural_key, candidates in panel.groupby("project_natural_key", sort=False):
        project_row = candidates.iloc[0]
        bid_date = project_row["bid_date"]
        prior_bids = history[history["bid_date"] < bid_date]

        c = candidates.copy()
        c["score"] = score_distance_rule(
            c, project_row.get("project_latitude"), project_row.get("project_longitude"),
            project_row.get("state"), company_pit_locations,
        )
        distance_frames.append(c)

        c = candidates.copy()
        c["score"] = score_capacity_size_fit(c, project_row, prior_bids)
        size_fit_frames.append(c)

        c = candidates.copy()
        c["score"] = score_capacity_volume(c, prior_bids)
        volume_frames.append(c)

        restricted, scores = restrict_and_score_historical_winrate(candidates, project_row, prior_bids)
        if not restricted.empty:
            restricted = restricted.copy()
            restricted["score"] = scores
            winrate_frames.append(restricted)

    results.append(run_rule(
        "distance", pd.concat(distance_frames, ignore_index=True), "score",
        "nearest self-owned MN pit to project site; MN projects only, "
        f"{len(company_pit_locations)}/{panel['competitor_unit_id'].nunique()} companies have a computable distance",
    ))
    results.append(run_rule(
        "capacity_size_fit", pd.concat(size_fit_frames, ignore_index=True), "score",
        "project-material-scale fit vs company's historical avg qty per material (>=3 prior bids required per material)",
    ))
    results.append(run_rule(
        "capacity_volume", pd.concat(volume_frames, ignore_index=True), "score",
        "log(total historical bid dollar volume), no project-fit involved",
    ))
    if winrate_frames:
        results.append(run_rule(
            "historical_winrate_state", pd.concat(winrate_frames, ignore_index=True), "score",
            "candidate pool restricted to same-state history only; score = win rate for this project_type in-state (falls back to overall in-state win rate)",
        ))

    add_existing_model_reference_rows(results)

    summary_df = pd.DataFrame(results)
    ordered_cols = [
        "rule", "projects_evaluated", "projects_with_winner_in_pool",
        "winner_hit_rate_at_5", "winner_hit_rate_at_10", "winner_hit_rate_at_20",
        "precision_at_5", "precision_at_10", "precision_at_20", "notes",
    ]
    summary_df = summary_df[[c for c in ordered_cols if c in summary_df.columns]]
    summary_df.to_csv(OUT_DIR / "summary.csv", index=False)

    print("\n" + "=" * 100)
    print("WINNER HIT RATE @5/@10/@20 -- first-principles single-factor rules vs. existing models")
    print("=" * 100)
    print(summary_df.drop(columns=["notes"]).to_string(index=False))
    print("\nFull notes + per-project breakdowns written to:", OUT_DIR)


if __name__ == "__main__":
    main()
