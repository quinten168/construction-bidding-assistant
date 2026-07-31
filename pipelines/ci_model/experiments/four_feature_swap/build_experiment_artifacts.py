#!/usr/bin/env python3
"""
Build a self-contained (predictions.csv, model.json) pair for the 4-feature simple-rule model,
in the same on-disk shape `06_reporting/agent/orchestrator.py` already expects -- so orchestrator.py
itself needs zero changes to run against it via --predictions/--model.

Does not touch any tracked file. See README.md for the scaler/intercept approximation this makes.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

_EXP_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _EXP_DIR.parent.parent.parent.parent  # .../csi-bid-intelligence/
_TRAINING_DIR = _REPO_ROOT / "pipelines" / "ci_model" / "03_training"
sys.path.insert(0, str(_TRAINING_DIR))

from train_simple_rule_baseline import (  # noqa: E402  (production logic, reused not duplicated)
    MATERIALS, MIN_MATERIAL_BIDS, PRIMARY_FEATURES, SHRINKAGE_K, build_history,
)

SAMPLE_PREDICTIONS = _TRAINING_DIR / "outputs" / "ranking_predictions_sample.csv"
PROJECTS_CSV = _REPO_ROOT / "data" / "processed" / "projects.csv"
BIDDER_RESULTS_CSV = _REPO_ROOT / "data" / "processed" / "bidder_results.csv"
PRODUCTION_WEIGHTS_JSON = _TRAINING_DIR / "outputs" / "simple_rule_baseline_weights.json"

OUT_DIR = _EXP_DIR / "outputs"
OUT_PREDICTIONS = OUT_DIR / "experiment_predictions.csv"
OUT_MODEL = OUT_DIR / "experiment_model.json"

FEATURE_COLUMNS = ["primary_county", "primary_type", "primary_state", "primary_size_fit"]


def compute_primary_features(
    predictions: pd.DataFrame,
    history: pd.DataFrame,
    projects_by_job: pd.DataFrame,
) -> pd.DataFrame:
    """Same feature definitions as train_simple_rule_baseline.build_simple_rule_score, just
    stopped short of the final weighted sum so the 4 raw inputs survive as columns."""
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
            size_fit_by_cid = fit_sums / fit_counts.replace(0, np.nan)
        base["size_fit_raw"] = candidate_ids.map(size_fit_by_cid).to_numpy()

        raw_frames.append(base)

    raw = pd.concat(raw_frames).sort_index()

    train_mask = (predictions["time_split"] == "train").to_numpy()
    train_fit_values = raw["size_fit_raw"].to_numpy()[train_mask]
    neutral_fallback = np.nanmean(train_fit_values) if np.isfinite(np.nanmean(train_fit_values)) else 0.0
    size_fit_score = raw["size_fit_raw"].fillna(neutral_fallback).to_numpy()

    result = predictions.copy()
    result["primary_county"] = np.log1p(raw["w_county"]).to_numpy()
    result["primary_type"] = np.log1p(raw["w_type"]).to_numpy()
    result["primary_state"] = np.log1p(raw["w_state"]).to_numpy()
    result["primary_size_fit"] = size_fit_score
    return result


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    sample = pd.read_csv(SAMPLE_PREDICTIONS)
    projects = pd.read_csv(PROJECTS_CSV)
    sample = sample.merge(
        projects[["job_id", "project_natural_key", "project_latitude", "project_longitude"]],
        on="job_id", how="left",
    )

    history, projects_by_job = build_history(str(PROJECTS_CSV), str(BIDDER_RESULTS_CSV))
    enriched = compute_primary_features(sample, history, projects_by_job)

    # Cross-check: production weights (already fit on the full 92k-row train split) applied to our
    # 4 raw features, so the RANKING at least matches the real simple_rule_score column already
    # present in the sample (they should correlate near-perfectly within each project).
    prod_meta = json.loads(PRODUCTION_WEIGHTS_JSON.read_text())
    prod_weights = prod_meta["weights"]
    enriched["simple_rule_score_recomputed"] = (
        prod_weights["county"] * enriched["primary_county"]
        + prod_weights["type"] * enriched["primary_type"]
        + prod_weights["state"] * enriched["primary_state"]
        + prod_weights["size_fit"] * enriched["primary_size_fit"]
    )
    corr = enriched[["simple_rule_score", "simple_rule_score_recomputed"]].corr().iloc[0, 1]
    print(f"[check] corr(recomputed, original simple_rule_score) = {corr:.4f} (expect ~1.0)")

    # Fit our own scaler + intercept on this sample (APPROXIMATION -- see README) so
    # predict_and_explain.py's sklearn-format path (scaler_mean/std/intercept/feature_weights)
    # works unmodified and produces a real 0-1 probability + per-feature contributions.
    X = enriched[FEATURE_COLUMNS].to_numpy()
    y = enriched["did_bid"].to_numpy()
    train_mask = (enriched["time_split"] == "train").to_numpy()
    scaler = StandardScaler().fit(X[train_mask])
    clf = LogisticRegression(C=1.0, class_weight="balanced").fit(scaler.transform(X[train_mask]), y[train_mask])

    model = {
        "model": "simple_rule_4feature_EXPERIMENT",
        "feature_columns": FEATURE_COLUMNS,
        "intercept": float(clf.intercept_[0]),
        "feature_weights": dict(zip(FEATURE_COLUMNS, clf.coef_[0].tolist())),
        "scaler_mean": scaler.mean_.tolist(),
        "scaler_std": scaler.scale_.tolist(),
        "note": "EXPERIMENT ONLY -- scaler/intercept refit on the 20-project reviewable sample, "
                "not the full training corpus. See ../README.md.",
    }
    OUT_MODEL.write_text(json.dumps(model, indent=2))

    enriched.to_csv(OUT_PREDICTIONS, index=False)
    print(f"wrote {OUT_PREDICTIONS} ({len(enriched)} rows, {enriched['job_id'].nunique()} projects)")
    print(f"wrote {OUT_MODEL}")
    print("\nsample project_natural_keys to try:")
    for key in enriched["project_natural_key"].dropna().unique()[:8]:
        print(f"  {key}")


if __name__ == "__main__":
    main()
