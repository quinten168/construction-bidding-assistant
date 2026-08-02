#!/usr/bin/env python3
"""
Train a Linear SVM and kernel-approximated SVM (Nystroem RBF) ranking model.

Why not vanilla SVC(kernel='rbf')?  ~95K training rows makes it prohibitively
slow (O(n²–n³) time).  Instead, Nystroem maps the data to an explicit RBF
feature space (n_components random features), then LinearSVC runs on that
expanded matrix — O(n) in training rows, close to true-RBF quality.

Imbalance handling:
  - class_weight='balanced' in LinearSVC (up-weights the rare positive class)
  - CalibratedClassifierCV(cv=5) does cross-validated sigmoid (Platt) scaling
    on training data — no separate calibration split needed.

Tuning is scored by validation PR-AUC (same criterion as XGBoost tuner).

Input:  data/processed/model1/ranking_features.parquet
        outputs/model1/ranking_predictions.csv  (existing scores already present)
Output: outputs/model1/ranking_predictions.csv  (adds svm_score column)
        outputs/model1/svm_model.json            (best params + coefficients)
        outputs/model1/svm_tuning.csv            (all tuning configs + val metrics)

Run after train_xgboost.py, before evaluate_ranking.py.
"""
from __future__ import annotations

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "shared"))

import argparse
import json

import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.kernel_approximation import Nystroem
from sklearn.metrics import average_precision_score, roc_auc_score
from sklearn.preprocessing import StandardScaler
from sklearn.svm import LinearSVC

from config import RANKING_FEATURE_COLUMNS, TRAIN_END_DATE, VALIDATION_END_DATE
from io_utils import read_table

TUNING_K = 10   # Precision@K used as the primary tuning criterion


def _mean_precision_at_k(val_df: pd.DataFrame, scores: np.ndarray, k: int) -> float:
    """Mean Precision@K across all validation projects."""
    tmp = val_df[["project_natural_key", "did_bid"]].copy()
    tmp["score"] = scores
    precisions = []
    for _, grp in tmp.groupby("project_natural_key", sort=False):
        top = grp.nlargest(k, "score")
        precisions.append(int(top["did_bid"].sum()) / k)
    return float(np.mean(precisions)) if precisions else 0.0

# ============================================================================
# Hyperparameter grid
# kernel "linear" → LinearSVC only
# kernel "rbf"    → Nystroem(n_components) + LinearSVC
# ============================================================================

PARAM_GRID = [
    {"kernel": "linear", "C": 0.01},
    {"kernel": "linear", "C": 0.1},
    {"kernel": "linear", "C": 1.0},
    {"kernel": "linear", "C": 10.0},
    {"kernel": "rbf",    "C": 0.1,  "n_components": 500},
    {"kernel": "rbf",    "C": 1.0,  "n_components": 500},
    {"kernel": "rbf",    "C": 10.0, "n_components": 500},
    {"kernel": "rbf",    "C": 1.0,  "n_components": 1000},
]

MAX_ITER = 5000
CALIB_CV = 5   # folds for cross-validated sigmoid calibration


def _assign_time_split(frame: pd.DataFrame) -> pd.Series:
    bid_date  = pd.to_datetime(frame["bid_date"], errors="coerce")
    train_end = pd.Timestamp(TRAIN_END_DATE)
    val_end   = pd.Timestamp(VALIDATION_END_DATE)
    split = pd.Series("test", index=frame.index)
    split.loc[bid_date < train_end] = "train"
    split.loc[(bid_date >= train_end) & (bid_date < val_end)] = "validation"
    return split


def _fit_one(
    params: dict,
    X_train: np.ndarray,
    y_train: np.ndarray,
    X_val: np.ndarray,
) -> tuple:
    """
    Train one SVM config. Returns (calibrated_model, val_probas, nystroem_or_None).
    CalibratedClassifierCV(cv=CALIB_CV) does cross-validated Platt sigmoid
    calibration on the training data — no separate calibration split needed.
    """
    kernel = params["kernel"]
    C      = params["C"]

    if kernel == "linear":
        svc = LinearSVC(C=C, class_weight="balanced", max_iter=MAX_ITER, random_state=42)
        calibrated = CalibratedClassifierCV(svc, cv=CALIB_CV, method="sigmoid")
        calibrated.fit(X_train, y_train)
        val_proba = calibrated.predict_proba(X_val)[:, 1]
        return calibrated, val_proba, None

    else:  # rbf via Nystroem
        n_comp    = params["n_components"]
        nys       = Nystroem(kernel="rbf", n_components=n_comp, random_state=42)
        X_tr_nys  = nys.fit_transform(X_train)
        X_val_nys = nys.transform(X_val)

        svc = LinearSVC(C=C, class_weight="balanced", max_iter=MAX_ITER, random_state=42)
        calibrated = CalibratedClassifierCV(svc, cv=CALIB_CV, method="sigmoid")
        calibrated.fit(X_tr_nys, y_train)
        val_proba = calibrated.predict_proba(X_val_nys)[:, 1]
        return calibrated, val_proba, nys


def train_svm(
    features_path: str,
    predictions_path: str,
    model_output: str,
    tuning_output: str,
) -> dict:
    print("=" * 80)
    print("Training SVM Ranking Model  (Linear + Nystroem-RBF)")
    print("=" * 80)

    print("\nLoading ranking features...")
    df = read_table(features_path)
    df["bid_date"] = pd.to_datetime(df["bid_date"], errors="coerce")
    df["time_split"] = _assign_time_split(df)
    for col in RANKING_FEATURE_COLUMNS:
        if col not in df.columns:
            df[col] = 0.0
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    train_df = df[df["time_split"] == "train"].copy()
    val_df   = df[df["time_split"] == "validation"].copy()

    if train_df.empty:
        raise ValueError("Training split is empty; check TRAIN_END_DATE in config.py")
    if val_df.empty:
        raise ValueError("Validation split is empty; check VALIDATION_END_DATE in config.py")

    # Scale features — required for SVM convergence
    scaler  = StandardScaler()
    X_train = scaler.fit_transform(train_df[RANKING_FEATURE_COLUMNS].values.astype(float))
    y_train = train_df["did_bid"].astype(int).values
    X_val   = scaler.transform(val_df[RANKING_FEATURE_COLUMNS].values.astype(float))
    y_val   = val_df["did_bid"].astype(int).values

    pos_rate      = y_train.mean()
    neg_pos_ratio = round((1 - pos_rate) / pos_rate, 1)
    print(f"  Train rows:    {len(X_train):,}")
    print(f"  Val rows:      {len(X_val):,}")
    print(f"  Positive rate: {pos_rate:.1%}  (neg/pos ratio = {neg_pos_ratio}x)")
    print(f"  Features:      {len(RANKING_FEATURE_COLUMNS)}")
    print(f"  Imbalance:     class_weight='balanced' + {CALIB_CV}-fold sigmoid calibration")

    print(f"\nGrid search over {len(PARAM_GRID)} configs (scored by val Precision@{TUNING_K})...\n")
    print(f"  {'#':>3}  {'kernel':<8}  {'C':>6}  {'n_comp':>7}  {'val P@10':>8}  {'val PR-AUC':>10}  {'val ROC-AUC':>11}")
    print(f"  {'─'*3}  {'─'*8}  {'─'*6}  {'─'*7}  {'─'*8}  {'─'*10}  {'─'*11}")

    tuning_rows = []
    best_model  = None
    best_nys    = None
    best_params = None
    best_prec_k = -np.inf

    for i, params in enumerate(PARAM_GRID, start=1):
        calibrated, val_proba, nys = _fit_one(params, X_train, y_train, X_val)
        val_precision_k = _mean_precision_at_k(val_df, val_proba, TUNING_K)
        val_pr_auc      = average_precision_score(y_val, val_proba)
        val_roc_auc     = roc_auc_score(y_val, val_proba)
        n_comp_str      = str(params.get("n_components", "—"))

        print(f"  {i:>3}  {params['kernel']:<8}  {params['C']:>6}  {n_comp_str:>7}  "
              f"{val_precision_k:>8.4f}  {val_pr_auc:>10.4f}  {val_roc_auc:>11.4f}")

        tuning_rows.append({
            "config":                      i,
            "kernel":                      params["kernel"],
            "C":                           params["C"],
            "n_components":                params.get("n_components"),
            f"val_precision_at_{TUNING_K}": round(val_precision_k, 4),
            "val_pr_auc":                  round(val_pr_auc,  4),
            "val_roc_auc":                 round(val_roc_auc, 4),
        })

        if val_precision_k > best_prec_k:
            best_prec_k = val_precision_k
            best_model  = calibrated
            best_nys    = nys
            best_params = dict(params)

    print(f"\n  ✓ Best config: {best_params}  (val Precision@{TUNING_K}={best_prec_k:.4f})")

    # Score all rows
    print("\nScoring all rows with best model...")
    X_all = scaler.transform(df[RANKING_FEATURE_COLUMNS].values.astype(float))
    if best_nys is not None:
        X_all = best_nys.transform(X_all)
    df["svm_score"] = best_model.predict_proba(X_all)[:, 1]

    # Feature coefficients (averaged over calibrated classifiers)
    coef_list = []
    for est in best_model.calibrated_classifiers_:
        coef_list.append(est.estimator.coef_[0])
    mean_coef = np.mean(coef_list, axis=0)

    # For Nystroem models the coef is in the expanded feature space — report top components
    if best_nys is None:
        feat_names = RANKING_FEATURE_COLUMNS
    else:
        n = len(mean_coef)
        feat_names = [f"nystroem_component_{j}" for j in range(n)]

    feat_imp = sorted(
        zip(feat_names, mean_coef.tolist()),
        key=lambda x: abs(x[1]),
        reverse=True,
    )
    print(f"\nTop 10 features by |coefficient| ({best_params['kernel']} kernel):")
    for feat, coef in feat_imp[:10]:
        bar = "█" * int(abs(coef) * 20)
        print(f"  {feat:<40} {coef:+.4f}  {bar}")

    # Merge svm_score into ranking_predictions.csv
    print(f"\nMerging svm_score into {predictions_path}...")
    if Path(predictions_path).exists():
        preds = pd.read_csv(predictions_path)
        score_map = df.set_index(["project_natural_key", "competitor_unit_id"])["svm_score"]
        preds["svm_score"] = (
            preds.set_index(["project_natural_key", "competitor_unit_id"]).index.map(score_map)
        )
        preds["svm_score"] = preds["svm_score"].fillna(df["svm_score"].mean())
    else:
        preds = df[["project_natural_key", "competitor_unit_id", "bid_date", "time_split",
                    "did_bid", "svm_score", *RANKING_FEATURE_COLUMNS]].copy()

    Path(predictions_path).parent.mkdir(parents=True, exist_ok=True)
    preds.to_csv(predictions_path, index=False)
    print(f"  ✓ Saved {predictions_path}")

    pd.DataFrame(tuning_rows).to_csv(tuning_output, index=False)
    print(f"  ✓ Tuning log: {tuning_output}")

    model_meta = {
        "model":               "svm",
        "best_params":         best_params,
        "imbalance_handling":  "class_weight=balanced",
        "calibration":         f"sigmoid ({CALIB_CV}-fold cross-validated on train)",
        "feature_columns":     RANKING_FEATURE_COLUMNS if best_nys is None else None,
        "scaler_mean":         scaler.mean_.tolist(),
        "scaler_std":          scaler.scale_.tolist(),
        "train_end_date":      TRAIN_END_DATE,
        "validation_end_date": VALIDATION_END_DATE,
        "train_rows":          int(len(X_train)),
        "val_rows":            int(len(X_val)),
        "positive_rate":       float(pos_rate),
        f"val_precision_at_{TUNING_K}": float(best_prec_k),
    }
    Path(model_output).parent.mkdir(parents=True, exist_ok=True)
    Path(model_output).write_text(json.dumps(model_meta, indent=2) + "\n")
    print(f"  ✓ Model metadata: {model_output}")

    print("\n" + "=" * 80)
    print("✓ SVM training complete")
    print("=" * 80)
    print(f"\n  Best val Precision@{TUNING_K}: {best_prec_k:.4f}")
    print(f"  Best config:                 {best_params}")
    print(f"\nNext: python evaluate_ranking.py --note 'svm with kernel tuning'")

    return best_params


def main() -> None:
    _STEP_OUT = Path(__file__).resolve().parent / "outputs"
    parser = argparse.ArgumentParser(description="Train SVM ranking model (linear + Nystroem RBF).")
    parser.add_argument("--features",      default="data/processed/model1/ranking_features.parquet")
    parser.add_argument("--predictions",   default=str(_STEP_OUT / "ranking_predictions.csv"))
    parser.add_argument("--model-output",  default=str(_STEP_OUT / "svm_model.json"))
    parser.add_argument("--tuning-output", default=str(_STEP_OUT / "svm_tuning.csv"))
    args = parser.parse_args()

    train_svm(
        features_path=args.features,
        predictions_path=args.predictions,
        model_output=args.model_output,
        tuning_output=args.tuning_output,
    )


if __name__ == "__main__":
    main()
