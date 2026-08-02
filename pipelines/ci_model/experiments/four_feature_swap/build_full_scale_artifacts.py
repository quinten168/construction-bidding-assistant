#!/usr/bin/env python3
"""
Same idea as build_experiment_artifacts.py, but fit on the FULL training corpus instead of the
20-project reviewable sample -- so the scaler/intercept/weights are the real thing, not an
approximation. Still writes only new files under experiments/four_feature_swap/outputs/; does not
touch any tracked file and does not re-run any pipeline script (the candidate panel it needs,
data/processed/model1/ranking_training_panel.parquet, already exists on disk).

Uses the exact same time_split cutoffs the production logistic_baseline_model.json was trained
with (train_end_date / validation_end_date), so split_rows should match production's
{train: 92671, validation: 87801, test: 49976} as a sanity check.
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
_REPO_ROOT = _EXP_DIR.parent.parent.parent.parent
_TRAINING_DIR = _REPO_ROOT / "pipelines" / "ci_model" / "03_training"
sys.path.insert(0, str(_TRAINING_DIR))

from train_simple_rule_baseline import MATERIALS, MIN_MATERIAL_BIDS  # noqa: E402
from build_experiment_artifacts import compute_primary_features  # noqa: E402

PANEL_PARQUET = _REPO_ROOT / "data" / "processed" / "model1" / "ranking_training_panel.parquet"
PROJECTS_CSV = _REPO_ROOT / "data" / "processed" / "projects.csv"
BIDDER_RESULTS_CSV = _REPO_ROOT / "data" / "processed" / "bidder_results.csv"
PROD_MODEL_JSON = _TRAINING_DIR / "outputs" / "logistic_baseline_model.json"
PROD_WEIGHTS_JSON = _TRAINING_DIR / "outputs" / "simple_rule_baseline_weights.json"

OUT_DIR = _EXP_DIR / "outputs"
OUT_PREDICTIONS = OUT_DIR / "full_scale_predictions.parquet"
OUT_MODEL = OUT_DIR / "full_scale_model.json"

FEATURE_COLUMNS = ["primary_county", "primary_type", "primary_state", "primary_size_fit"]


def build_history(projects_path: str, bidder_results_path: str):
    projects = pd.read_csv(projects_path)
    bidder_results = pd.read_csv(bidder_results_path)
    projects["bid_date"] = pd.to_datetime(projects["bid_date"], errors="coerce")
    for m in MATERIALS:
        projects[m] = pd.to_numeric(projects[m], errors="coerce").fillna(0)
    history = bidder_results.merge(
        projects[["project_natural_key", "bid_date", "state", "county", "project_type", *MATERIALS]],
        on="project_natural_key", how="left", validate="many_to_one",
    )
    history["competitor_unit_id"] = history["competitor_unit_id"].astype(str)
    history["did_win"] = pd.to_numeric(history["did_win"], errors="coerce").fillna(0)
    return history, projects.set_index("project_natural_key")


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    prod_model_meta = json.loads(PROD_MODEL_JSON.read_text())
    train_end = pd.Timestamp(prod_model_meta["train_end_date"])
    val_end = pd.Timestamp(prod_model_meta["validation_end_date"])

    panel = pd.read_parquet(PANEL_PARQUET)
    panel["bid_date"] = pd.to_datetime(panel["bid_date"], errors="coerce")
    panel["competitor_unit_id"] = panel["competitor_unit_id"].astype(str)
    panel["time_split"] = np.select(
        [panel["bid_date"] < train_end, panel["bid_date"] < val_end],
        ["train", "validation"],
        default="test",
    )
    print("time_split row counts:\n", panel["time_split"].value_counts())
    print("time_split project counts:\n",
          panel.groupby("time_split")["project_natural_key"].nunique())
    print("(production reference: rows train=92671 val=87801 test=49976; "
          "projects train=817 val=531 test=243)")

    history, projects_by_job = build_history(str(PROJECTS_CSV), str(BIDDER_RESULTS_CSV))
    enriched = compute_primary_features(panel, history, projects_by_job)

    # Cross-check against the already-fitted production weights (raw-space, from
    # simple_rule_baseline_weights.json) -- confirms our feature recomputation matches what
    # actually produced that artifact, on the full corpus this time (not just the 20-project sample).
    prod_weights = json.loads(PROD_WEIGHTS_JSON.read_text())["weights"]
    enriched["simple_rule_score_recomputed"] = (
        prod_weights["county"] * enriched["primary_county"]
        + prod_weights["type"] * enriched["primary_type"]
        + prod_weights["state"] * enriched["primary_state"]
        + prod_weights["size_fit"] * enriched["primary_size_fit"]
    )

    X = enriched[FEATURE_COLUMNS].to_numpy()
    y = enriched["did_bid"].to_numpy()
    train_mask = (enriched["time_split"] == "train").to_numpy()
    scaler = StandardScaler().fit(X[train_mask])
    clf = LogisticRegression(C=1.0, class_weight="balanced").fit(scaler.transform(X[train_mask]), y[train_mask])

    model = {
        "model": "simple_rule_4feature_FULL_SCALE",
        "feature_columns": FEATURE_COLUMNS,
        "intercept": float(clf.intercept_[0]),
        "feature_weights": dict(zip(FEATURE_COLUMNS, clf.coef_[0].tolist())),
        "scaler_mean": scaler.mean_.tolist(),
        "scaler_std": scaler.scale_.tolist(),
        "train_end_date": prod_model_meta["train_end_date"],
        "validation_end_date": prod_model_meta["validation_end_date"],
        "split_rows": {s: int((enriched["time_split"] == s).sum()) for s in ("train", "validation", "test")},
    }
    OUT_MODEL.write_text(json.dumps(model, indent=2))
    enriched.to_parquet(OUT_PREDICTIONS, index=False)
    enriched.to_csv(str(OUT_PREDICTIONS).replace(".parquet", ".csv"), index=False)

    print(f"\nwrote {OUT_MODEL}")
    print(f"wrote {OUT_PREDICTIONS}")
    print("fitted weights (standardized coef):", model["feature_weights"])


if __name__ == "__main__":
    main()
