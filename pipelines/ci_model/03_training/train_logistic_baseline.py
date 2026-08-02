#!/usr/bin/env python3
"""
Train Model 1's logistic ranking baseline (sklearn).

By default fits one L2 logistic regression at C=1.0. Pass --tune to instead
sweep a grid of regularization configs (L2/L1/elastic-net strengths/ratios),
score each on validation Precision@K, and keep the best one -- this was
previously a separate script (tune_logistic.py); merged in here since it's
the same model, just tried at more configs. --tune also writes the full
sweep log to --tuning-output.
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


SOLVER   = "saga"
MAX_ITER = 1000
PENALTY  = "l2"
DEFAULT_C = 1.0   # sklearn default; --tune sweeps a grid instead

# ── Tuning grid (only used with --tune) — edit these lists to change what gets tested ──
L2_STRENGTHS      = [0.0001, 0.001, 0.01, 0.1, 1.0]
L1_STRENGTHS      = [0.0001, 0.001, 0.01, 0.1]
ELASTIC_STRENGTHS = [0.01, 0.1]
ELASTIC_ALPHAS    = [0.30, 0.50, 0.70, 0.90]   # L1 ratio: 0=pure L2, 1=pure L1


def assign_time_split(
    frame: pd.DataFrame,
    train_end_date: str,
    validation_end_date: str,
) -> pd.Series:
    bid_date = pd.to_datetime(frame["bid_date"], errors="coerce")
    train_end = pd.Timestamp(train_end_date)
    validation_end = pd.Timestamp(validation_end_date)
    split = pd.Series("test", index=frame.index)
    split.loc[bid_date < train_end] = "train"
    split.loc[(bid_date >= train_end) & (bid_date < validation_end)] = "validation"
    return split


def _mean_precision_at_k(df: pd.DataFrame, scores: np.ndarray, k: int) -> float:
    tmp = df[["project_natural_key", "did_bid"]].copy()
    tmp["score"] = scores
    precisions = []
    for _, grp in tmp.groupby("project_natural_key", sort=False):
        top = grp.nlargest(k, "score")
        precisions.append(int(top["did_bid"].sum()) / k)
    return float(np.mean(precisions)) if precisions else 0.0


def _param_grid() -> list[dict]:
    return (
        [{"penalty": "l2", "strength": s, "l1_ratio": None} for s in L2_STRENGTHS]
        + [{"penalty": "l1", "strength": s, "l1_ratio": None} for s in L1_STRENGTHS]
        + [
            {"penalty": "elasticnet", "strength": s, "l1_ratio": a}
            for s in ELASTIC_STRENGTHS
            for a in ELASTIC_ALPHAS
        ]
    )


def _fit(
    X_train: np.ndarray,
    y_train: np.ndarray,
    penalty: str,
    C: float,
    l1_ratio: float | None,
) -> LogisticRegression:
    kwargs = dict(
        penalty=penalty,
        C=C,
        class_weight="balanced",
        solver=SOLVER,
        max_iter=MAX_ITER,
        random_state=42,
        n_jobs=-1,
    )
    if penalty == "elasticnet":
        kwargs["l1_ratio"] = l1_ratio
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")   # suppress saga convergence warnings mid-grid
        model = LogisticRegression(**kwargs)
        model.fit(X_train, y_train)
    return model


def _run_tune(
    X_train: np.ndarray,
    y_train: np.ndarray,
    X_val: np.ndarray,
    val: pd.DataFrame,
    tuning_k: int,
    tuning_output: str,
) -> tuple[LogisticRegression, dict, float]:
    print(f"  {'#':>3}  {'penalty':<12}  {'strength':>9}  {'l1_ratio':>9}  "
          f"{'val P@'+str(tuning_k):>10}  {'non-zero w':>10}")

    tuning_rows = []
    best_model, best_params, best_prec_k = None, None, -np.inf
    for i, params in enumerate(_param_grid(), start=1):
        C = 1.0 / params["strength"]
        model = _fit(X_train, y_train, params["penalty"], C, params["l1_ratio"])
        val_scores = model.predict_proba(X_val)[:, 1]
        prec_k = _mean_precision_at_k(val, val_scores, tuning_k)
        nonzero_w = int(np.sum(np.abs(model.coef_[0]) > 1e-6))
        ratio_str = f"{params['l1_ratio']:.2f}" if params["l1_ratio"] is not None else "    —  "

        print(f"  {i:>3}  {params['penalty']:<12}  {params['strength']:>9}  {ratio_str:>9}  "
              f"{prec_k:>10.4f}  {nonzero_w:>10}/{len(RANKING_FEATURE_COLUMNS)}")

        tuning_rows.append({
            "config":                     i,
            "penalty":                    params["penalty"],
            "strength":                   params["strength"],
            "C":                          round(C, 6),
            "l1_ratio":                   params["l1_ratio"],
            f"val_precision_at_{tuning_k}": round(prec_k, 4),
            "nonzero_weights":            nonzero_w,
        })

        if prec_k > best_prec_k:
            best_prec_k, best_model, best_params = prec_k, model, dict(params)

    Path(tuning_output).parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(tuning_rows).to_csv(tuning_output, index=False)
    print(f"\n  Best config: penalty={best_params['penalty']}  strength={best_params['strength']}  "
          f"l1_ratio={best_params['l1_ratio']}  (val P@{tuning_k}={best_prec_k:.4f})")
    print(f"  Tuning log: {tuning_output}")

    return best_model, best_params, best_prec_k


def main() -> None:
    _STEP_OUT = Path(__file__).resolve().parent / "outputs"
    parser = argparse.ArgumentParser(description="Train Model 1 logistic ranking baseline (sklearn).")
    parser.add_argument("--features", default="data/processed/model1/ranking_features.parquet")
    parser.add_argument("--train-end-date", default=TRAIN_END_DATE)
    parser.add_argument("--validation-end-date", default=VALIDATION_END_DATE)
    parser.add_argument("--c", type=float, default=DEFAULT_C, dest="C",
                        help="Inverse regularization strength (sklearn C). Ignored with --tune.")
    parser.add_argument("--tune", action="store_true",
                        help="Sweep the regularization grid instead of fitting one fixed config.")
    parser.add_argument("--tuning-k", type=int, default=10,
                        help="Precision@K used to score --tune configs on validation.")
    parser.add_argument("--predictions-output", default=str(_STEP_OUT / "ranking_predictions.csv"))
    parser.add_argument("--model-output", default=str(_STEP_OUT / "logistic_baseline_model.json"))
    parser.add_argument("--tuning-output", default=str(_STEP_OUT / "logistic_tuning.csv"))
    args = parser.parse_args()

    features = read_table(args.features)
    features["bid_date"] = pd.to_datetime(features["bid_date"], errors="coerce")
    features["time_split"] = assign_time_split(
        features,
        train_end_date=args.train_end_date,
        validation_end_date=args.validation_end_date,
    )
    for col in RANKING_FEATURE_COLUMNS:
        if col not in features.columns:
            features[col] = 0.0
        features[col] = pd.to_numeric(features[col], errors="coerce").fillna(0)

    train = features[features["time_split"] == "train"].copy()
    val   = features[features["time_split"] == "validation"].copy()
    if train.empty:
        raise ValueError("Training split is empty; adjust train-end-date.")

    scaler  = StandardScaler()
    X_train = scaler.fit_transform(train[RANKING_FEATURE_COLUMNS].values.astype(float))
    y_train = train["did_bid"].astype(int).values
    X_all   = scaler.transform(features[RANKING_FEATURE_COLUMNS].values.astype(float))
    X_val   = scaler.transform(val[RANKING_FEATURE_COLUMNS].values.astype(float)) if not val.empty else None

    if args.tune:
        if val.empty:
            raise ValueError("--tune requires a non-empty validation split.")
        print("Sweeping regularization grid...")
        clf, best_params, val_p10 = _run_tune(
            X_train, y_train, X_val, val, args.tuning_k, args.tuning_output,
        )
        penalty_meta = best_params["penalty"]
        C_meta = 1.0 / best_params["strength"]
        l1_ratio_meta = best_params["l1_ratio"]
        val_p10 = round(val_p10, 4)
    else:
        clf = _fit(X_train, y_train, PENALTY, args.C, None)
        penalty_meta = PENALTY
        C_meta = args.C
        l1_ratio_meta = None
        val_p10 = None
        if not val.empty:
            val_scores = clf.predict_proba(X_val)[:, 1]
            val_p10 = round(_mean_precision_at_k(val, val_scores, args.tuning_k), 4)

    features["logistic_score"] = clf.predict_proba(X_all)[:, 1]
    features["rule_score"] = pd.to_numeric(features["rule_score"], errors="coerce").fillna(0)

    output_cols = [
        "candidate_rule_version",
        "time_split",
        "project_natural_key",
        "bid_date",
        "state",
        "county",
        "project_type",
        "competitor_unit_id",
        "did_bid",
        "did_win",
        "bid_rank",
        "rule_score",
        "logistic_score",
        *RANKING_FEATURE_COLUMNS,
    ]
    Path(args.predictions_output).parent.mkdir(parents=True, exist_ok=True)
    features[[col for col in output_cols if col in features.columns]].to_csv(
        args.predictions_output, index=False,
    )

    feat_weights = dict(zip(RANKING_FEATURE_COLUMNS, clf.coef_[0].tolist()))

    model_meta = {
        "model":               "logistic_regression_sklearn",
        "penalty":             penalty_meta,
        "C":                   float(C_meta),
        "l1_ratio":            l1_ratio_meta,
        "solver":              SOLVER,
        "max_iter":            MAX_ITER,
        "class_weight":        "balanced",
        "feature_columns":     RANKING_FEATURE_COLUMNS,
        "intercept":           float(clf.intercept_[0]),
        "feature_weights":     feat_weights,
        "scaler_mean":         scaler.mean_.tolist(),
        "scaler_std":          scaler.scale_.tolist(),
        "train_end_date":      args.train_end_date,
        "validation_end_date": args.validation_end_date,
        "val_precision_at_10": val_p10,
        "split_rows":          features["time_split"].value_counts().to_dict(),
        "split_projects":      features.groupby("time_split")["project_natural_key"].nunique().to_dict(),
    }
    Path(args.model_output).write_text(json.dumps(model_meta, indent=2) + "\n")

    print("\nLogistic baseline training complete (sklearn)")
    print(f"  predictions: {args.predictions_output}")
    print(f"  model:       {args.model_output}")
    print(f"  rows:        {len(features):,}")
    print(f"  splits:      {model_meta['split_rows']}")
    if val_p10 is not None:
        print(f"  val P@10:    {val_p10:.4f}")


if __name__ == "__main__":
    main()
