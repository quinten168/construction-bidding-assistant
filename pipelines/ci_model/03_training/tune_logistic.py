#!/usr/bin/env python3
"""
Regularisation sweep for the logistic ranking model using scikit-learn.

Uses sklearn LogisticRegression with solver='saga', which supports all three
penalty types in one consistent solver:
  L2       — penalty='l2',      C=1/strength
  L1       — penalty='l1',      C=1/strength
  Elastic  — penalty='elasticnet', C=1/strength, l1_ratio=alpha
             (alpha=0 → pure L2, alpha=1 → pure L1)

Class imbalance handled via class_weight='balanced' (sklearn computes the
neg/pos ratio automatically).
Features scaled with StandardScaler (fit on train, applied to val/test).
Tuning scored by validation Precision@10.

Grid is defined as four compact lists — edit them to change what gets tested:
  L2_STRENGTHS      — one L2 config per strength value
  L1_STRENGTHS      — one L1 config per strength value
  ELASTIC_STRENGTHS — paired with every alpha in ELASTIC_ALPHAS
  ELASTIC_ALPHAS    — L1 ratio values (0=pure L2, 1=pure L1)

Input:  data/processed/model1/ranking_features.parquet
        outputs/model1/ranking_predictions.csv  (other model scores already present)
Output: outputs/model1/ranking_predictions.csv  (updates logistic_score with best config)
        outputs/model1/logistic_baseline_model.json  (best config metadata)
        outputs/model1/logistic_tuning.csv           (full tuning log)

Run before evaluate_ranking.py.
"""
from __future__ import annotations

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "shared"))

import argparse
import json
import warnings

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

from config import RANKING_FEATURE_COLUMNS, TRAIN_END_DATE, VALIDATION_END_DATE
from io_utils import read_table

# ============================================================================
# Tuning settings
# ============================================================================

MAX_ITER = 1000
TUNING_K = 10

# ── Grid definition — edit these lists to change what gets tested ─────────────
L2_STRENGTHS      = [0.0001, 0.001, 0.01, 0.1, 1.0]
L1_STRENGTHS      = [0.0001, 0.001, 0.01, 0.1]
ELASTIC_STRENGTHS = [0.01, 0.1]
ELASTIC_ALPHAS    = [0.30, 0.50, 0.70, 0.90]   # L1 ratio: 0=pure L2, 1=pure L1

# ── Auto-generated grid (do not edit below) ───────────────────────────────────
PARAM_GRID = (
    [{"penalty": "l2",         "strength": s, "l1_ratio": None} for s in L2_STRENGTHS]
  + [{"penalty": "l1",         "strength": s, "l1_ratio": None} for s in L1_STRENGTHS]
  + [{"penalty": "elasticnet", "strength": s, "l1_ratio": a}
     for s in ELASTIC_STRENGTHS for a in ELASTIC_ALPHAS]
)


# ============================================================================
# Precision@K helper
# ============================================================================

def _mean_precision_at_k(df: pd.DataFrame, scores: np.ndarray, k: int) -> float:
    tmp = df[["job_id", "did_bid"]].copy()
    tmp["score"] = scores
    precisions = []
    for _, grp in tmp.groupby("job_id", sort=False):
        top = grp.nlargest(k, "score")
        precisions.append(int(top["did_bid"].sum()) / k)
    return float(np.mean(precisions)) if precisions else 0.0


# ============================================================================
# Main
# ============================================================================

def main() -> None:
    _STEP_OUT = Path(__file__).resolve().parent / "outputs"
    parser = argparse.ArgumentParser(description="Regularisation sweep for logistic ranking model.")
    parser.add_argument("--features",      default="data/processed/model1/ranking_features.parquet")
    parser.add_argument("--predictions",   default=str(_STEP_OUT / "ranking_predictions.csv"))
    parser.add_argument("--model-output",  default=str(_STEP_OUT / "logistic_baseline_model.json"))
    parser.add_argument("--tuning-output", default=str(_STEP_OUT / "logistic_tuning.csv"))
    args = parser.parse_args()

    # ── Load & split ──────────────────────────────────────────────────────────
    print("=" * 80)
    print("Logistic Regression — Regularisation Sweep  (sklearn)")
    print("=" * 80)

    df = read_table(args.features)
    df["bid_date"] = pd.to_datetime(df["bid_date"], errors="coerce")

    bid_date  = df["bid_date"]
    train_end = pd.Timestamp(TRAIN_END_DATE)
    val_end   = pd.Timestamp(VALIDATION_END_DATE)
    df["time_split"] = "test"
    df.loc[bid_date < train_end,                            "time_split"] = "train"
    df.loc[(bid_date >= train_end) & (bid_date < val_end), "time_split"] = "validation"

    for col in RANKING_FEATURE_COLUMNS:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    train_df = df[df["time_split"] == "train"].copy()
    val_df   = df[df["time_split"] == "validation"].copy()

    if train_df.empty or val_df.empty:
        raise ValueError("Train or validation split is empty.")

    # ── Scale features ────────────────────────────────────────────────────────
    scaler  = StandardScaler()
    X_train = scaler.fit_transform(train_df[RANKING_FEATURE_COLUMNS].values.astype(float))
    y_train = train_df["did_bid"].astype(int).values
    X_val   = scaler.transform(val_df[RANKING_FEATURE_COLUMNS].values.astype(float))

    pos_rate = y_train.mean()
    print(f"\n  Train rows:    {len(X_train):,}  |  positive rate: {pos_rate:.1%}")
    print(f"  Val rows:      {len(val_df):,}")
    print(f"  Features:      {len(RANKING_FEATURE_COLUMNS)}")
    print(f"  Solver:        saga   max_iter: {MAX_ITER}   class_weight: balanced")
    print(f"  Tuning metric: Precision@{TUNING_K} (validation)\n")

    print(f"  {'#':>3}  {'penalty':<12}  {'strength':>9}  {'l1_ratio':>9}  "
          f"{'val P@10':>8}  {'non-zero w':>10}")
    print(f"  {'─'*3}  {'─'*12}  {'─'*9}  {'─'*9}  {'─'*8}  {'─'*10}")

    tuning_rows  = []
    best_model   = None
    best_scaler  = scaler
    best_prec_k  = -np.inf
    best_params  = None

    for i, params in enumerate(PARAM_GRID, start=1):
        C = 1.0 / params["strength"]   # sklearn uses C = inverse regularisation strength

        kwargs = dict(
            penalty=params["penalty"],
            C=C,
            class_weight="balanced",
            solver="saga",
            max_iter=MAX_ITER,
            random_state=42,
            n_jobs=-1,
        )
        if params["penalty"] == "elasticnet":
            kwargs["l1_ratio"] = params["l1_ratio"]

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")   # suppress saga convergence warnings mid-grid
            model = LogisticRegression(**kwargs)
            model.fit(X_train, y_train)

        val_scores = model.predict_proba(X_val)[:, 1]
        prec_k     = _mean_precision_at_k(val_df, val_scores, TUNING_K)
        nonzero_w  = int(np.sum(np.abs(model.coef_[0]) > 1e-6))
        ratio_str  = f"{params['l1_ratio']:.2f}" if params["l1_ratio"] is not None else "    —  "

        print(f"  {i:>3}  {params['penalty']:<12}  {params['strength']:>9}  {ratio_str:>9}  "
              f"{prec_k:>8.4f}  {nonzero_w:>10}/{len(RANKING_FEATURE_COLUMNS)}")

        tuning_rows.append({
            "config":                        i,
            "penalty":                       params["penalty"],
            "strength":                      params["strength"],
            "C":                             round(C, 6),
            "l1_ratio":                      params["l1_ratio"],
            f"val_precision_at_{TUNING_K}":  round(prec_k, 4),
            "nonzero_weights":               nonzero_w,
        })

        if prec_k > best_prec_k:
            best_prec_k = prec_k
            best_model  = model
            best_params = dict(params)

    print(f"\n  ✓ Best config: penalty={best_params['penalty']}  "
          f"strength={best_params['strength']}  l1_ratio={best_params['l1_ratio']}  "
          f"(val Precision@{TUNING_K}={best_prec_k:.4f})")

    # ── Score all rows with best model ────────────────────────────────────────
    print("\nScoring all rows with best config and updating ranking_predictions.csv...")
    X_all      = scaler.transform(df[RANKING_FEATURE_COLUMNS].values.astype(float))
    all_scores = best_model.predict_proba(X_all)[:, 1]
    df["logistic_score"] = all_scores

    if Path(args.predictions).exists():
        preds     = pd.read_csv(args.predictions)
        score_map = df.set_index(["job_id", "competitor_unit_id"])["logistic_score"]
        preds["logistic_score"] = (
            preds.set_index(["job_id", "competitor_unit_id"]).index.map(score_map)
        )
        preds["logistic_score"] = preds["logistic_score"].fillna(all_scores.mean())
    else:
        preds = df

    Path(args.predictions).parent.mkdir(parents=True, exist_ok=True)
    preds.to_csv(args.predictions, index=False)
    print(f"  ✓ Saved {args.predictions}")

    # ── Save tuning log ───────────────────────────────────────────────────────
    pd.DataFrame(tuning_rows).to_csv(args.tuning_output, index=False)
    print(f"  ✓ Tuning log: {args.tuning_output}")

    # ── Save model metadata ───────────────────────────────────────────────────
    feat_weights = dict(zip(RANKING_FEATURE_COLUMNS, best_model.coef_[0].tolist()))
    model_meta = {
        "model":               "logistic_regression_sklearn",
        "penalty":             best_params["penalty"],
        "strength":            best_params["strength"],
        "C":                   float(1.0 / best_params["strength"]),
        "l1_ratio":            best_params["l1_ratio"],
        "solver":              "saga",
        "max_iter":            MAX_ITER,
        "class_weight":        "balanced",
        "feature_columns":     RANKING_FEATURE_COLUMNS,
        "intercept":           float(best_model.intercept_[0]),
        "feature_weights":     feat_weights,
        "scaler_mean":         scaler.mean_.tolist(),
        "scaler_std":          scaler.scale_.tolist(),
        "train_end_date":      TRAIN_END_DATE,
        "validation_end_date": VALIDATION_END_DATE,
        f"val_precision_at_{TUNING_K}": float(best_prec_k),
    }
    Path(args.model_output).write_text(json.dumps(model_meta, indent=2) + "\n")
    print(f"  ✓ Model metadata: {args.model_output}")

    # ── Feature weight summary ────────────────────────────────────────────────
    print(f"\nTop 10 features by |weight| (best config):")
    sorted_feats = sorted(feat_weights.items(), key=lambda x: abs(x[1]), reverse=True)
    for feat, w in sorted_feats[:10]:
        bar = "█" * int(abs(w) * 30)
        print(f"  {feat:<40} {w:+.4f}  {bar}")

    print(f"\n  Non-zero weights: "
          f"{int(np.sum(np.abs(best_model.coef_[0]) > 1e-6))}/{len(RANKING_FEATURE_COLUMNS)}")
    print(f"\nNext: python evaluate_ranking.py --note 'logistic sklearn tuning'")


if __name__ == "__main__":
    main()
