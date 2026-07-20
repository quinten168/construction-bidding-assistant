#!/usr/bin/env python3
"""
Simple rule-based competitor score, built from segment-level win rates
(project type, county, state) rather than the existing rule_score's
bid-activity heuristic in build_ranking_features.py.

Segments are independent (not nested): "win rate on mill_overlay jobs"
counts wins in any state/county, etc. County matching is scoped to
(state, county) together since county names are not globally unique
(e.g. "CASS CO" collides across ND/MN/SD in this dataset).

State-level win rate has the most volume of the three, so it is used
as the shrinkage anchor for the sparser county/type rates:

    rate_state        = w_state / n_state, falling back to the
                         competitor's all-time global win rate if they
                         have never bid in this state, else 0
    rate_<seg>_shrunk  = (w_segment + k * rate_state) / (n_segment + k)

k = 5 pseudo-observations: with 5+ real bids in a segment the shrunk
rate is dominated by the segment's own history; with 0 it collapses
exactly to rate_state.

Win counts lead the score; shrunk rates only break exact ties. An
AUC decomposition on the test split showed the rate terms carry very
little signal on their own (AUC ~0.53-0.56) while raw win counts are
strong (AUC 0.71-0.80) -- in this market, established volume/experience
predicts winning far better than any win rate does. Tie-break weighting
follows the same tiny-epsilon convention already used for
tree_score_tiebreak in train_decision_tree_baseline.py, so the rate
terms can never overturn a count-based ordering.

Project size is added as one combined, competitor-specific "size fit"
term -- NOT the plain project-level log_mix_tons/log_grading_yards/etc.
columns already in build_ranking_features.py, which are identical for
every candidate in a project and therefore mathematically cannot change
a within-project ranking (that's also why they show exactly 0.0
importance in the logistic model). Size fit instead compares each
project's active materials (mix_tons, grading_yards, base_tons,
shldr_tons, mill_sy, crush_tons, stock_tons -- whichever are > 0 for
this project) against this competitor's own historical average handled
quantity for that material:

    size_fit_m   = -abs(log1p(project_qty_m) - competitor_avg_log1p_qty_m)
                   (0 = perfect scale match, more negative = bigger
                   mismatch; only computed once a competitor has >= 3
                   qualifying prior bids with material m present)
    size_fit_raw = mean(size_fit_m for active materials with enough data)

A competitor with no qualifying material history falls back to the
population mean of size_fit_raw over the TRAIN split (leakage-safe) --
NOT 0, since 0 is the best possible value in this metric's range and
would otherwise silently reward missing data. An AUC check on the test
split found size_fit_score alone at ~0.63 with this fallback (vs. 0.38
if defaulted to 0) -- real but moderate signal, weaker than the win
count terms, so it gets a matching moderate weight in primary:

    primary  = 3.0 * log1p(win_count_county)
             + 2.0 * log1p(win_count_type)
             + 1.0 * log1p(win_count_state)
             + 1.0 * size_fit_score
    tiebreak = rate_county_shrunk + rate_type_shrunk + rate_state
    simple_rule_score = primary + 1e-6 * tiebreak

All history is strictly before each project's bid_date (no leakage).

Input:  outputs/model1/ranking_predictions.csv  (for job_id/competitor_unit_id/
                                                  bid_date/state/county/project_type keys)
        data/processed/projects.csv, data/processed/bidder_results.csv (history)
Output: outputs/model1/ranking_predictions.csv  (adds simple_rule_score column)

Run alongside train_logistic_baseline.py / train_xgboost.py, before evaluate_ranking.py.
"""
from __future__ import annotations

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "shared"))

import argparse

import numpy as np
import pandas as pd

SHRINKAGE_K = 5.0
MATERIALS = ["mix_tons", "grading_yards", "base_tons", "shldr_tons", "mill_sy", "crush_tons", "stock_tons"]
MIN_MATERIAL_BIDS = 3


def build_history(projects_path: str, bidder_results_path: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    projects = pd.read_csv(projects_path)
    bidder_results = pd.read_csv(bidder_results_path)
    projects["bid_date"] = pd.to_datetime(projects["bid_date"], errors="coerce")
    for m in MATERIALS:
        projects[m] = pd.to_numeric(projects[m], errors="coerce").fillna(0)

    history = bidder_results.merge(
        projects[["job_id", "bid_date", "state", "county", "project_type", *MATERIALS]],
        on="job_id",
        how="left",
        validate="many_to_one",
    )
    history["competitor_unit_id"] = history["competitor_unit_id"].astype(str)
    history["did_win"] = pd.to_numeric(history["did_win"], errors="coerce").fillna(0)
    return history, projects.set_index("job_id")


def build_simple_rule_score(
    predictions: pd.DataFrame,
    history: pd.DataFrame,
    projects_by_job: pd.DataFrame,
) -> pd.DataFrame:
    predictions = predictions.copy()
    predictions["bid_date"] = pd.to_datetime(predictions["bid_date"], errors="coerce")

    raw_frames = []
    for job_id, frame in predictions.groupby("job_id", sort=False):
        project = frame.iloc[0]
        bid_date = project["bid_date"]
        state = project.get("state")
        county = project.get("county")
        project_type = project.get("project_type")
        candidate_ids = frame["competitor_unit_id"].astype(str)

        cols = ["n_type", "w_type", "n_county", "w_county", "n_state", "w_state", "n_global", "w_global"]
        base = pd.DataFrame(index=frame.index)
        prior = history[history["bid_date"] < bid_date]

        if prior.empty:
            for col in cols:
                base[col] = 0.0
            base["size_fit_raw"] = np.nan
            raw_frames.append(base)
            continue

        same_type = prior["project_type"] == project_type
        same_county = (prior["county"] == county) & (prior["state"] == state)
        same_state = prior["state"] == state

        def counts_and_wins(mask: pd.Series) -> tuple[pd.Series, pd.Series]:
            subset = prior.loc[mask]
            return subset.groupby("competitor_unit_id").size(), subset.groupby("competitor_unit_id")["did_win"].sum()

        n_type, w_type = counts_and_wins(same_type)
        n_county, w_county = counts_and_wins(same_county)
        n_state, w_state = counts_and_wins(same_state)
        n_global = prior.groupby("competitor_unit_id").size()
        w_global = prior.groupby("competitor_unit_id")["did_win"].sum()

        for col, values in [
            ("n_type", n_type), ("w_type", w_type),
            ("n_county", n_county), ("w_county", w_county),
            ("n_state", n_state), ("w_state", w_state),
            ("n_global", n_global), ("w_global", w_global),
        ]:
            base[col] = candidate_ids.map(values).fillna(0).to_numpy()

        # ── Size fit: competitor's typical scale vs. this project's active materials ──
        project_row = projects_by_job.loc[job_id]
        active_materials = [m for m in MATERIALS if project_row[m] > 0]
        fit_sums = pd.Series(0.0, index=candidate_ids.unique())
        fit_counts = pd.Series(0, index=candidate_ids.unique())
        for m in active_materials:
            proj_log = np.log1p(project_row[m])
            m_prior = prior[prior[m] > 0].copy()
            if m_prior.empty:
                continue
            m_prior["_log_qty"] = np.log1p(m_prior[m])
            grp = m_prior.groupby("competitor_unit_id")["_log_qty"]
            n_m = grp.size()
            avg_log_m = grp.mean()
            qualifying = n_m[n_m >= MIN_MATERIAL_BIDS].index
            for cid in qualifying:
                if cid in fit_sums.index:
                    fit_sums[cid] += -abs(proj_log - avg_log_m[cid])
                    fit_counts[cid] += 1
        with np.errstate(invalid="ignore"):
            size_fit_by_cid = (fit_sums / fit_counts.replace(0, np.nan))
        base["size_fit_raw"] = candidate_ids.map(size_fit_by_cid).to_numpy()

        raw_frames.append(base)

    raw = pd.concat(raw_frames).sort_index()

    global_rate = np.where(raw["n_global"] > 0, raw["w_global"] / raw["n_global"], 0.0)
    rate_state = np.where(raw["n_state"] > 0, raw["w_state"] / raw["n_state"], global_rate)

    k = SHRINKAGE_K
    rate_type_shrunk = (raw["w_type"] + k * rate_state) / (raw["n_type"] + k)
    rate_county_shrunk = (raw["w_county"] + k * rate_state) / (raw["n_county"] + k)

    # Leakage-safe neutral fallback: population mean of real (non-NaN) size_fit_raw
    # values on the TRAIN split only. 0 would be wrong here -- it's the ceiling of
    # this metric's range (perfect fit), so defaulting missing data to 0 would
    # silently reward competitors with no size history over ones with a real,
    # imperfect fit.
    train_mask = (predictions["time_split"] == "train").to_numpy()
    train_fit_values = raw["size_fit_raw"].to_numpy()[train_mask]
    neutral_fallback = np.nanmean(train_fit_values) if np.isfinite(np.nanmean(train_fit_values)) else 0.0
    size_fit_score = raw["size_fit_raw"].fillna(neutral_fallback).to_numpy()

    primary = (
        3.0 * np.log1p(raw["w_county"]).to_numpy()
        + 2.0 * np.log1p(raw["w_type"]).to_numpy()
        + 1.0 * np.log1p(raw["w_state"]).to_numpy()
        + 1.0 * size_fit_score
    )
    tiebreak = rate_county_shrunk.to_numpy() + rate_type_shrunk.to_numpy() + rate_state

    predictions["simple_rule_score"] = primary + 1e-6 * tiebreak
    return predictions


def main() -> None:
    _STEP_OUT = Path(__file__).resolve().parent / "outputs"
    parser = argparse.ArgumentParser(description="Compute simple rule-based competitor score (segment win rates).")
    parser.add_argument("--predictions", default=str(_STEP_OUT / "ranking_predictions.csv"))
    parser.add_argument("--projects", default="data/processed/projects.csv")
    parser.add_argument("--bidder-results", default="data/processed/bidder_results.csv")
    parser.add_argument("--predictions-output", default=str(_STEP_OUT / "ranking_predictions.csv"))
    args = parser.parse_args()

    predictions = pd.read_csv(args.predictions)
    history, projects_by_job = build_history(args.projects, args.bidder_results)
    predictions = build_simple_rule_score(predictions, history, projects_by_job)

    Path(args.predictions_output).parent.mkdir(parents=True, exist_ok=True)
    predictions.to_csv(args.predictions_output, index=False)
    print(f"Simple rule-based score complete")
    print(f"  rows:   {len(predictions):,}")
    print(f"  output: {args.predictions_output}")


if __name__ == "__main__":
    main()
