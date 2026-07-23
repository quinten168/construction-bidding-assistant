"""
Tool 1 — predict_and_explain

Loads the logistic model JSON and computes per-feature log-odds contributions for one
competitor × project row. Handles both model formats:
  - sklearn format (train_logistic_baseline.py, incl. --tune): keys  scaler_mean / scaler_std / intercept / feature_weights
  - numpy  format (legacy): keys  feature_means / feature_stds / weights
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd


def load_model(model_path: str | Path) -> dict:
    return json.loads(Path(model_path).read_text())


def _sigmoid(z: float) -> float:
    return float(1 / (1 + np.exp(-np.clip(z, -30, 30))))


def _extract_scaling(model: dict, feature_cols: list[str]) -> tuple[np.ndarray, np.ndarray]:
    """Return (means, stds) as numpy arrays aligned to feature_cols."""
    if "scaler_mean" in model:
        # sklearn format — lists already ordered by feature_cols
        return np.array(model["scaler_mean"]), np.array(model["scaler_std"])
    else:
        # numpy format — dicts keyed by feature name
        means_d = model["feature_means"]
        stds_d  = model["feature_stds"]
        means = np.array([means_d.get(f, 0.0) for f in feature_cols])
        stds  = np.array([max(stds_d.get(f, 1.0), 1e-8) for f in feature_cols])
        return means, stds


def _extract_coefs(model: dict, feature_cols: list[str]) -> tuple[float, np.ndarray]:
    """Return (intercept, coefs) aligned to feature_cols."""
    intercept = float(model["intercept"])
    fw = model["feature_weights"]
    coefs = np.array([fw.get(f, 0.0) for f in feature_cols])
    return intercept, coefs


def predict_and_explain(
    row: pd.Series,
    model: dict,
) -> dict:
    """
    Compute bid probability and per-feature log-odds contributions for one row.

    Args:
        row:   a single row from ranking_predictions.csv (as a pandas Series)
        model: loaded model JSON dict

    Returns:
        {
            competitor_id, bid_probability,
            top_reasons_to_bid    (list of (feature, contribution) sorted desc),
            top_reasons_not_to_bid (list of (feature, contribution) sorted asc),
            raw_contributions (dict feature → contribution),
            feature_values    (dict feature → raw value),
        }
    """
    feature_cols = model["feature_columns"]
    means, stds  = _extract_scaling(model, feature_cols)
    intercept, coefs = _extract_coefs(model, feature_cols)

    x_raw    = np.array([float(row.get(f, 0.0)) for f in feature_cols])
    x_scaled = (x_raw - means) / np.where(stds == 0, 1.0, stds)

    log_odds = intercept + float(coefs @ x_scaled)
    prob     = _sigmoid(log_odds)

    raw_contributions: dict[str, float] = {
        feat: float(coefs[i]) * float(x_scaled[i])
        for i, feat in enumerate(feature_cols)
    }

    sorted_desc = sorted(raw_contributions.items(), key=lambda x: x[1], reverse=True)
    sorted_asc  = sorted(raw_contributions.items(), key=lambda x: x[1])

    # Exclude zero-contribution features from top reasons
    top_bid     = [(f, c) for f, c in sorted_desc if c > 0.0][:3]
    top_no_bid  = [(f, c) for f, c in sorted_asc  if c < 0.0][:3]

    return {
        "competitor_id":        str(row.get("competitor_unit_id", "")),
        "bid_probability":      round(prob, 4),
        "top_reasons_to_bid":   top_bid,
        "top_reasons_not_to_bid": top_no_bid,
        "raw_contributions":    raw_contributions,
        "feature_values":       {f: float(x_raw[i]) for i, f in enumerate(feature_cols)},
    }
