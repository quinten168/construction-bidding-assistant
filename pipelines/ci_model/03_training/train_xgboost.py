#!/usr/bin/env python3
"""
Train XGBoost ranking model.

Uses RandomizedSearchCV over PARAM_DISTRIBUTIONS with a temporal PredefinedSplit
(train before TRAIN_END_DATE, val between TRAIN_END_DATE and VALIDATION_END_DATE).
Scored by validation average_precision (PR-AUC). Handles class imbalance via
scale_pos_weight, which is included in the search space.

Input:  data/processed/model1/ranking_features.parquet
Output: outputs/model1/ranking_predictions.csv  (adds xgb_score column)
        outputs/model1/xgboost_model.json        (best params + feature importance)
        outputs/model1/xgboost_tuning.csv        (all tuning configs + val metrics)

Run after train_decision_tree_baseline.py, before evaluate_ranking.py.
"""
from __future__ import annotations

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "shared"))

import argparse
import json

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score, average_precision_score
from sklearn.model_selection import RandomizedSearchCV, PredefinedSplit
from sklearn.pipeline import Pipeline

try:
    import xgboost as xgb
except ImportError:
    raise ImportError("xgboost is required: pip install xgboost")

from config import RANKING_FEATURE_COLUMNS, TOP_K_VALUES, TRAIN_END_DATE, VALIDATION_END_DATE
from io_utils import read_table

TUNING_K     = 10
N_ITER       = 50
CV_SCORING   = "average_precision"
RANDOM_STATE = 42

# ============================================================================
# Hyperparameter search space
# Scored by validation PR-AUC via a single temporal PredefinedSplit.
# scale_pos_weight range matched to wenyu positive rate (~2.3%, ratio ~34–44).
# ============================================================================

PARAM_DISTRIBUTIONS = {
    # Tree structure
    "model__max_depth":          [3, 4, 5, 6, 7],
    "model__min_child_weight":   [1, 3, 5, 10, 20],
    "model__gamma":              [0, 0.1, 0.2, 0.5, 1.0],

    # Learning
    "model__n_estimators":       [100, 200, 300, 500, 750],
    "model__learning_rate":      [0.01, 0.02, 0.05, 0.10, 0.20],

    # Sampling / regularization
    "model__subsample":          [0.6, 0.7, 0.8, 0.9, 1.0],
    "model__colsample_bytree":   [0.6, 0.7, 0.8, 0.9, 1.0],
    "model__reg_alpha":          [0, 0.1, 0.5, 1.0, 2.0],
    "model__reg_lambda":         [0.5, 1.0, 1.5, 2.0, 3.0],

    # Class imbalance — positive rate ~2.3%, ratio ~34–44
    "model__scale_pos_weight":   [5, 10, 15, 20, 25, 30, 40],
}


def _mean_precision_at_k(val_df: pd.DataFrame, scores: np.ndarray, k: int) -> float:
    tmp = val_df[["project_natural_key", "did_bid"]].copy()
    tmp["score"] = scores
    precisions = []
    for _, grp in tmp.groupby("project_natural_key", sort=False):
        top = grp.nlargest(k, "score")
        precisions.append(int(top["did_bid"].sum()) / k)
    return float(np.mean(precisions)) if precisions else 0.0


def _assign_time_split(frame: pd.DataFrame) -> pd.Series:
    bid_date  = pd.to_datetime(frame["bid_date"], errors="coerce")
    train_end = pd.Timestamp(TRAIN_END_DATE)
    val_end   = pd.Timestamp(VALIDATION_END_DATE)
    split = pd.Series("test", index=frame.index)
    split.loc[bid_date < train_end] = "train"
    split.loc[(bid_date >= train_end) & (bid_date < val_end)] = "validation"
    return split


def train_xgboost(
    features_path: str,
    predictions_path: str,
    model_output: str,
    tuning_output: str,
) -> tuple[Pipeline, dict]:
    print("=" * 80)
    print("Training XGBoost Ranking Model")
    print("=" * 80)

    # Load features
    print("\nLoading ranking features...")
    df = read_table(features_path)
    df["bid_date"]   = pd.to_datetime(df["bid_date"], errors="coerce")
    df["time_split"] = _assign_time_split(df)
    for col in RANKING_FEATURE_COLUMNS:
        if col not in df.columns:
            df[col] = 0.0
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    train = df[df["time_split"] == "train"].copy()
    val   = df[df["time_split"] == "validation"].copy()

    if train.empty:
        raise ValueError("Training split is empty; check TRAIN_END_DATE in config.py")
    if val.empty:
        raise ValueError("Validation split is empty; check VALIDATION_END_DATE in config.py")

    X_train = train[RANKING_FEATURE_COLUMNS].values
    y_train = train["did_bid"].astype(int).values
    X_val   = val[RANKING_FEATURE_COLUMNS].values
    y_val   = val["did_bid"].astype(int).values

    pos_rate = y_train.mean()
    print(f"  Train rows: {len(X_train):,}  |  positive rate: {pos_rate:.1%}")
    print(f"  Val rows:   {len(X_val):,}")
    print(f"  Features:   {len(RANKING_FEATURE_COLUMNS)}")

    # Combine train+val; PredefinedSplit uses -1 for train rows, 0 for val rows
    X_tv = np.vstack([X_train, X_val])
    y_tv = np.concatenate([y_train, y_val])
    split_idx = np.concatenate([
        np.full(len(X_train), -1, dtype=int),
        np.zeros(len(X_val),  dtype=int),
    ])
    ps = PredefinedSplit(split_idx)

    pipeline = Pipeline([
        ("model", xgb.XGBClassifier(
            random_state=RANDOM_STATE,
            n_jobs=-1,
            eval_metric="aucpr",
            verbosity=0,
        )),
    ])

    print(f"\nRandomizedSearchCV  —  {N_ITER} iterations  |  scoring: {CV_SCORING}")
    print(f"  Temporal split: train < {TRAIN_END_DATE}  |  val {TRAIN_END_DATE} – {VALIDATION_END_DATE}\n")

    search = RandomizedSearchCV(
        estimator=pipeline,
        param_distributions=PARAM_DISTRIBUTIONS,
        n_iter=N_ITER,
        scoring=CV_SCORING,
        cv=ps,
        verbose=1,
        random_state=RANDOM_STATE,
        n_jobs=-1,
        refit=True,
        return_train_score=True,
    )
    search.fit(X_tv, y_tv)

    best_model  = search.best_estimator_
    best_params = search.best_params_
    best_val_ap = search.best_score_

    print("\n" + "=" * 80)
    print("RANDOMIZED SEARCH RESULTS")
    print("=" * 80)
    print(f"\n  Best val {CV_SCORING}: {best_val_ap:.4f}")
    print(f"\n  Best parameters:")
    for k, v in sorted(best_params.items()):
        print(f"    {k:<40s}: {v}")

    # Top 5 configs
    cv_df = (
        pd.DataFrame(search.cv_results_)
        .sort_values("mean_test_score", ascending=False)
    )
    top5_cols = [
        "mean_test_score", "std_test_score",
        "param_model__max_depth", "param_model__learning_rate",
        "param_model__n_estimators", "param_model__scale_pos_weight",
        "param_model__min_child_weight",
    ]
    print(f"\n  Top 5 configurations:")
    print(cv_df[top5_cols].head(5).to_string(index=False))

    # Val P@K using best model (refit on train+val, so val is in-sample — reported for tracking)
    val_proba       = best_model.predict_proba(X_val)[:, 1]
    val_precision_k = _mean_precision_at_k(val, val_proba, TUNING_K)
    val_roc_auc     = roc_auc_score(y_val, val_proba)
    print(f"\n  Val Precision@{TUNING_K}: {val_precision_k:.4f}")
    print(f"  Val ROC-AUC:          {val_roc_auc:.4f}")

    # Score all rows
    print("\nScoring all rows with best model...")
    X_all = df[RANKING_FEATURE_COLUMNS].values
    df["xgb_score"] = best_model.predict_proba(X_all)[:, 1]

    # Feature importance
    xgb_step = best_model.named_steps["model"]
    importances = xgb_step.feature_importances_
    feat_imp = sorted(zip(RANKING_FEATURE_COLUMNS, importances), key=lambda x: x[1], reverse=True)
    print("\nFeature importance (top 10):")
    for feat, imp in feat_imp[:10]:
        bar = "█" * int(imp * 60)
        print(f"  {feat:<35} {imp:.4f}  {bar}")

    # Merge xgb_score into ranking_predictions.csv
    print(f"\nMerging xgb_score into {predictions_path}...")
    if Path(predictions_path).exists():
        preds = pd.read_csv(predictions_path)
        score_map = df.set_index(["project_natural_key", "competitor_unit_id"])["xgb_score"]
        preds["xgb_score"] = preds.set_index(["project_natural_key", "competitor_unit_id"]).index.map(score_map)
        global_mean = df["xgb_score"].mean()
        preds["xgb_score"] = preds["xgb_score"].fillna(global_mean)
    else:
        preds = df[["project_natural_key", "competitor_unit_id", "bid_date", "time_split",
                    "did_bid", "xgb_score", *RANKING_FEATURE_COLUMNS]].copy()

    Path(predictions_path).parent.mkdir(parents=True, exist_ok=True)
    preds.to_csv(predictions_path, index=False)
    print(f"  ✓ Saved {predictions_path}")

    # Save tuning results
    cv_df.to_csv(tuning_output, index=False)
    print(f"  ✓ Tuning log: {tuning_output}")

    # Save model metadata
    model_meta = {
        "model": "xgboost",
        "search": "RandomizedSearchCV",
        "n_iter": N_ITER,
        "scoring": CV_SCORING,
        "best_val_avg_precision": float(best_val_ap),
        "best_params": {k: (float(v) if hasattr(v, "item") else v) for k, v in best_params.items()},
        "feature_columns": RANKING_FEATURE_COLUMNS,
        "feature_importance": {k: float(v) for k, v in feat_imp},
        "train_end_date": TRAIN_END_DATE,
        "validation_end_date": VALIDATION_END_DATE,
        "train_rows": int(len(X_train)),
        "val_rows": int(len(X_val)),
        "positive_rate": float(pos_rate),
        f"val_precision_at_{TUNING_K}": float(val_precision_k),
    }
    Path(model_output).parent.mkdir(parents=True, exist_ok=True)
    Path(model_output).write_text(json.dumps(model_meta, indent=2) + "\n")
    print(f"  ✓ Model metadata: {model_output}")

    print("\n" + "=" * 80)
    print("✓ XGBoost training complete")
    print("=" * 80)
    print(f"\n  Best val PR-AUC:       {best_val_ap:.4f}")
    print(f"  Val Precision@{TUNING_K}:    {val_precision_k:.4f}")
    print(f"  Val ROC-AUC:           {val_roc_auc:.4f}")
    print(f"\nNext: python evaluate_ranking.py --note 'xgboost expanded grid'")

    return best_model, best_params


def main() -> None:
    _STEP_OUT = Path(__file__).resolve().parent / "outputs"
    parser = argparse.ArgumentParser(description="Train XGBoost ranking model.")
    parser.add_argument("--features",      default="data/processed/model1/ranking_features.parquet")
    parser.add_argument("--predictions",   default=str(_STEP_OUT / "ranking_predictions.csv"))
    parser.add_argument("--model-output",  default=str(_STEP_OUT / "xgboost_model.json"))
    parser.add_argument("--tuning-output", default=str(_STEP_OUT / "xgboost_tuning.csv"))
    args = parser.parse_args()

    train_xgboost(
        features_path=args.features,
        predictions_path=args.predictions,
        model_output=args.model_output,
        tuning_output=args.tuning_output,
    )


if __name__ == "__main__":
    main()
