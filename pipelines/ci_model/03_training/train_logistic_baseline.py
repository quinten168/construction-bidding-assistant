#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "shared"))

import argparse
import json

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

from config import RANKING_FEATURE_COLUMNS, TRAIN_END_DATE, VALIDATION_END_DATE
from io_utils import read_table


SOLVER   = "saga"
MAX_ITER = 1000
PENALTY  = "l2"
DEFAULT_C = 1.0   # sklearn default; use tune_logistic.py for hyperparameter search


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
    tmp = df[["job_id", "did_bid"]].copy()
    tmp["score"] = scores
    precisions = []
    for _, grp in tmp.groupby("job_id", sort=False):
        top = grp.nlargest(k, "score")
        precisions.append(int(top["did_bid"].sum()) / k)
    return float(np.mean(precisions)) if precisions else 0.0


def main() -> None:
    _STEP_OUT = Path(__file__).resolve().parent / "outputs"
    parser = argparse.ArgumentParser(description="Train Model 1 logistic ranking baseline (sklearn).")
    parser.add_argument("--features", default="data/processed/model1/ranking_features.parquet")
    parser.add_argument("--train-end-date", default=TRAIN_END_DATE)
    parser.add_argument("--validation-end-date", default=VALIDATION_END_DATE)
    parser.add_argument("--c", type=float, default=DEFAULT_C, dest="C",
                        help="Inverse regularization strength (sklearn C). Use tune_logistic.py for grid search.")
    parser.add_argument("--predictions-output", default=str(_STEP_OUT / "ranking_predictions.csv"))
    parser.add_argument("--model-output", default=str(_STEP_OUT / "logistic_baseline_model.json"))
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

    clf = LogisticRegression(
        penalty=PENALTY,
        C=args.C,
        class_weight="balanced",
        solver=SOLVER,
        max_iter=MAX_ITER,
        random_state=42,
        n_jobs=-1,
    )
    clf.fit(X_train, y_train)

    features["logistic_score"] = clf.predict_proba(X_all)[:, 1]
    features["rule_score"] = pd.to_numeric(features["rule_score"], errors="coerce").fillna(0)

    output_cols = [
        "candidate_rule_version",
        "time_split",
        "job_id",
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

    val_p10 = None
    if not val.empty:
        X_val   = scaler.transform(val[RANKING_FEATURE_COLUMNS].values.astype(float))
        val_scores = clf.predict_proba(X_val)[:, 1]
        val_p10 = round(_mean_precision_at_k(val, val_scores, 10), 4)

    model_meta = {
        "model":               "logistic_regression_sklearn",
        "penalty":             PENALTY,
        "C":                   float(args.C),
        "l1_ratio":            None,
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
        "split_projects":      features.groupby("time_split")["job_id"].nunique().to_dict(),
    }
    Path(args.model_output).write_text(json.dumps(model_meta, indent=2) + "\n")

    print("Logistic baseline training complete (sklearn)")
    print(f"  predictions: {args.predictions_output}")
    print(f"  model:       {args.model_output}")
    print(f"  rows:        {len(features):,}")
    print(f"  splits:      {model_meta['split_rows']}")
    if val_p10 is not None:
        print(f"  val P@10:    {val_p10:.4f}")


if __name__ == "__main__":
    main()
