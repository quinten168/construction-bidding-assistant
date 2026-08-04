#!/usr/bin/env python3
"""
Full-corpus apples-to-apples comparison: apply BOTH the production 36-feature logistic model and
our full-scale-refit 4-feature model to every row of data/processed/model1/ranking_features.parquet
(230k rows, real train/val/test split), and compare winner-hit-rate@10 on the test split.

Read-only against tracked files; writes only to experiments/four_feature_swap/outputs/.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

_EXP_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _EXP_DIR.parent.parent.parent.parent
_TRAINING_DIR = _REPO_ROOT / "pipelines" / "ci_model" / "03_training"

FEATURES_PARQUET = _REPO_ROOT / "data" / "processed" / "model1" / "ranking_features.parquet"
PROD_MODEL_JSON = _TRAINING_DIR / "outputs" / "logistic_baseline_model.json"
FULL_SCALE_MODEL_JSON = _EXP_DIR / "outputs" / "full_scale_model.json"
FULL_SCALE_PREDICTIONS = _EXP_DIR / "outputs" / "full_scale_predictions.parquet"


def sigmoid(z):
    return 1.0 / (1.0 + np.exp(-np.clip(z, -30, 30)))


def score_with_model(df: pd.DataFrame, model: dict, feature_source: pd.DataFrame | None = None) -> np.ndarray:
    cols = model["feature_columns"]
    src = feature_source if feature_source is not None else df
    X = src[cols].apply(pd.to_numeric, errors="coerce").fillna(0.0).to_numpy()
    mean = np.array(model["scaler_mean"])
    std = np.array(model["scaler_std"])
    Xs = (X - mean) / np.where(std == 0, 1.0, std)
    fw = model["feature_weights"]
    coefs = np.array([fw[c] for c in cols])
    z = model["intercept"] + Xs @ coefs
    return sigmoid(z)


def winner_hit_rate_at_10(df: pd.DataFrame, score_col: str, split: str) -> tuple[float, int]:
    sub = df[df["time_split"] == split]
    hits, n = 0, 0
    for project_natural_key, g in sub.groupby("project_natural_key"):
        if g["did_win"].sum() == 0:
            continue  # winner not in candidate pool at all -- excluded, not scored as a miss
        n += 1
        top10 = g.sort_values(score_col, ascending=False).head(10)
        hits += int(top10["did_win"].sum() > 0)
    return (hits / n if n else float("nan")), n


def main() -> None:
    features = pd.read_parquet(FEATURES_PARQUET)
    features["bid_date"] = pd.to_datetime(features["bid_date"], errors="coerce")

    prod_model = json.loads(PROD_MODEL_JSON.read_text())
    train_end = pd.Timestamp(prod_model["train_end_date"])
    val_end = pd.Timestamp(prod_model["validation_end_date"])
    features["time_split"] = np.select(
        [features["bid_date"] < train_end, features["bid_date"] < val_end],
        ["train", "validation"], default="test",
    )

    features["logistic_score_36feat"] = score_with_model(features, prod_model)

    full_scale_model = json.loads(FULL_SCALE_MODEL_JSON.read_text())
    four_feat_preds = pd.read_parquet(FULL_SCALE_PREDICTIONS)[
        ["project_natural_key", "competitor_unit_id", *full_scale_model["feature_columns"]]
    ]
    features["competitor_unit_id"] = features["competitor_unit_id"].astype(str)
    four_feat_preds["competitor_unit_id"] = four_feat_preds["competitor_unit_id"].astype(str)
    merged = features.merge(four_feat_preds, on=["project_natural_key", "competitor_unit_id"], how="left")
    merged["logistic_score_4feat"] = score_with_model(merged, full_scale_model)

    for split in ("train", "validation", "test"):
        r36, n36 = winner_hit_rate_at_10(merged, "logistic_score_36feat", split)
        r4, n4 = winner_hit_rate_at_10(merged, "logistic_score_4feat", split)
        print(f"{split:>10}  36-feature: {r36:.4f} (n={n36})   4-feature: {r4:.4f} (n={n4})")


if __name__ == "__main__":
    main()
