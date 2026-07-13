#!/usr/bin/env python3
"""
Experiment tracker for ranking models.

Log format: one row per (experiment × model × split), making it easy to:
  - Filter by model in Excel
  - See train vs. test gap to diagnose overfitting
  - Compare models across experiments

Auto-called by evaluate_ranking.py — no manual step needed.

Usage:
    python experiment_tracker.py                    # show all (test split)
    python experiment_tracker.py --top 3
    python experiment_tracker.py --sort pr_auc
    python experiment_tracker.py --split validation
    python experiment_tracker.py --delete 2
"""
from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path

import pandas as pd

# ============================================================================
# Paths
# ============================================================================

OUTPUTS_DIR = Path(__file__).parent / "outputs"
LOG_PATH    = OUTPUTS_DIR / "experiments_log.csv"

# ============================================================================
# Constants
# ============================================================================

# Internal method key → display label
METHOD_LABELS = {
    "xgboost":               "XGBoost",
    "logistic_regression":   "Logistic",
    "shallow_decision_tree": "Tree",
    "linear_svm":            "SVM",
    "rule_based_score":      "Rule",
    "random_baseline":       "Random",
}

SPLIT_ORDER  = ["train", "validation", "test"]
SORT_CHOICES = ["pr_auc", "roc_auc", "precision10", "precision20", "ndcg", "tier1_ndcg", "id"]

# Overfitting threshold: flag if train PR-AUC exceeds test by more than this
OVERFIT_THRESHOLD = 0.08


# ============================================================================
# Public: called by evaluate_ranking.py to auto-log each run
# ============================================================================

def log_experiment(rows: list[dict]) -> None:
    """
    Append a run to the experiment log. Each call writes N rows
    (one per model × split) all sharing the same experiment_id.

    Expected keys in each row dict:
        note, candidate_rule, model, split,
        roc_auc, pr_auc, p5, p10, p20, ndcg, projects,
        (optional) tier1_p5, tier1_p10, tier1_p20, tier1_ndcg,
                   discovery_p5, discovery_p10, discovery_p20,
                   xgb_n_estimators, xgb_max_depth, xgb_learning_rate,
                   xgb_scale_pos_weight, tree_best_depth, tree_best_min_leaf
    """
    log_df = pd.read_csv(LOG_PATH) if LOG_PATH.exists() else pd.DataFrame()

    next_id   = 1 if log_df.empty or "experiment_id" not in log_df.columns \
                else int(log_df["experiment_id"].max()) + 1
    timestamp = datetime.now().isoformat(timespec="seconds")

    stamped = []
    for row in rows:
        stamped.append({"experiment_id": next_id, "timestamp": timestamp, **row})

    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    log_df = pd.concat([log_df, pd.DataFrame(stamped)], ignore_index=True)
    log_df.to_csv(LOG_PATH, index=False)

    print(f"\n  ✓ Logged experiment #{next_id} ({len(stamped)} rows) → {LOG_PATH}")
    print(f"    Run `python experiment_tracker.py` to compare all runs.")


# ============================================================================
# Display helpers
# ============================================================================

def _f(val, decimals: int = 4) -> str:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return "  —   "
    return f"{float(val):.{decimals}f}"


def _overfit_flag(train_pr: float | None, test_pr: float | None) -> str:
    if train_pr is None or test_pr is None:
        return ""
    if pd.isna(train_pr) or pd.isna(test_pr):
        return ""
    gap = float(train_pr) - float(test_pr)
    if gap > OVERFIT_THRESHOLD:
        return f"  ⚠ overfit (train−test PR gap: +{gap:.3f})"
    return ""


def show(df: pd.DataFrame, top: int | None, sort_by: str, split: str) -> None:
    # Sort experiments by their test-split XGBoost metric (best first)
    sort_metric_map = {
        "pr_auc":       "pr_auc",
        "roc_auc":      "roc_auc",
        "precision10":  "p10",
        "precision20":  "p20",
        "ndcg":         "ndcg",
        "tier1_ndcg":   "tier1_ndcg",
    }
    sort_col = sort_metric_map.get(sort_by)

    # Get experiment order by best XGBoost test metric
    test_xgb = df[
        (df["model"] == "xgboost") & (df["split"] == "test")
    ].copy()

    if sort_by == "id":
        exp_order = sorted(df["experiment_id"].unique())
    elif sort_col and sort_col in test_xgb.columns and not test_xgb.empty:
        test_xgb = test_xgb.sort_values(sort_col, ascending=False)
        exp_order = test_xgb["experiment_id"].tolist()
        # Add any experiments not in XGBoost test (e.g. only baseline models)
        for eid in df["experiment_id"].unique():
            if eid not in exp_order:
                exp_order.append(eid)
    else:
        exp_order = sorted(df["experiment_id"].unique())

    if top:
        exp_order = exp_order[:top]

    bar = "═" * 98
    sep = "─" * 98

    print(f"\n{bar}")
    print("EXPERIMENT TRACKER")
    print(f"  Sorted by: XGBoost {sort_by} (test)  |  Overfitting threshold: train−test PR > {OVERFIT_THRESHOLD}")
    print(bar)

    for exp_id in exp_order:
        exp_df = df[df["experiment_id"] == exp_id]
        if exp_df.empty:
            continue

        meta_row  = exp_df.iloc[0]
        ts        = str(meta_row.get("timestamp", ""))[:16]
        note      = str(meta_row.get("note", ""))[:40]
        rule      = str(meta_row.get("candidate_rule", ""))[:50]

        print(f"\n  #{int(exp_id)}  {ts}  {note}")
        print(f"     Candidate rule: {rule}")
        print()
        print(f"     {'Model':<10}  {'Split':<12}  {'ROC-AUC':>8}  {'PR-AUC':>8}  "
              f"{'P@5':>6}  {'P@10':>6}  {'P@20':>6}  {'NDCG':>6}  "
              f"{'T1-P10':>7}  {'T1-NDG':>7}  {'T1-GND':>7}  "
              f"{'D-P5':>6}  {'D-P10':>6}  {'D-P20':>6}")
        print(f"     {'─'*10}  {'─'*12}  {'─'*8}  {'─'*8}  "
              f"{'─'*6}  {'─'*6}  {'─'*6}  {'─'*6}  "
              f"{'─'*7}  {'─'*7}  {'─'*7}  "
              f"{'─'*6}  {'─'*6}  {'─'*6}")

        for method_key, label in METHOD_LABELS.items():
            method_rows = exp_df[exp_df["model"] == method_key]
            if method_rows.empty:
                continue

            # Get train and test PR-AUC for overfitting check
            train_pr = method_rows.loc[method_rows["split"] == "train", "pr_auc"].values
            test_pr  = method_rows.loc[method_rows["split"] == "test",  "pr_auc"].values
            overfit  = _overfit_flag(
                train_pr[0] if len(train_pr) else None,
                test_pr[0]  if len(test_pr)  else None,
            )

            first = True
            for s in SPLIT_ORDER:
                split_row = method_rows[method_rows["split"] == s]
                if split_row.empty:
                    continue
                r = split_row.iloc[0]
                label_col = label if first else ""
                first = False

                roc   = _f(r.get("roc_auc"))
                pr    = _f(r.get("pr_auc"))
                r5    = _f(r.get("p5"))
                r10   = _f(r.get("p10"))
                r20   = _f(r.get("p20"))
                ndcg  = _f(r.get("ndcg"))
                t1p10 = _f(r.get("tier1_p10"))
                t1ndg = _f(r.get("tier1_ndcg"))
                t1gnd = _f(r.get("tier1_graded_ndcg"))
                dp5   = _f(r.get("discovery_p5"))
                dp10  = _f(r.get("discovery_p10"))
                dp20  = _f(r.get("discovery_p20"))

                flag = overfit if s == "train" and overfit else ""
                print(f"     {label_col:<10}  {s:<12}  {roc:>8}  {pr:>8}  "
                      f"{r5:>6}  {r10:>6}  {r20:>6}  {ndcg:>6}  "
                      f"{t1p10:>7}  {t1ndg:>7}  {t1gnd:>7}  "
                      f"{dp5:>6}  {dp10:>6}  {dp20:>6}{flag}")

            # Print XGBoost config under the XGBoost block
            if method_key == "xgboost":
                cfg = {}
                for k in ("xgb_n_estimators", "xgb_max_depth", "xgb_learning_rate", "xgb_scale_pos_weight"):
                    v = method_rows.iloc[0].get(k)
                    if v is not None and (not isinstance(v, float) or not pd.isna(v)):
                        cfg[k.replace("xgb_", "")] = v
                if cfg:
                    cfg_str = "  ".join(f"{k}={v}" for k, v in cfg.items())
                    print(f"     {'':10}  config: {cfg_str}")

            elif method_key == "shallow_decision_tree":
                d = method_rows.iloc[0].get("tree_best_depth")
                l = method_rows.iloc[0].get("tree_best_min_leaf")
                if d is not None and not (isinstance(d, float) and pd.isna(d)):
                    print(f"     {'':10}  config: max_depth={int(d)}  min_samples_leaf={int(l)}")

            print()

    print(sep)
    print(f"Total experiments: {len(exp_order)}  |  log: {LOG_PATH}")


# ============================================================================
# Delete
# ============================================================================

def delete_experiment(exp_id: int) -> None:
    if not LOG_PATH.exists():
        print("No experiments logged yet.")
        return
    df = pd.read_csv(LOG_PATH)
    if exp_id not in df["experiment_id"].values:
        print(f"Experiment #{exp_id} not found.")
        return
    df = df[df["experiment_id"] != exp_id]
    df.to_csv(LOG_PATH, index=False)
    print(f"Deleted experiment #{exp_id}.")


# ============================================================================
# CLI
# ============================================================================

def main() -> None:
    parser = argparse.ArgumentParser(description="Experiment tracker for ranking models.")
    parser.add_argument("--top",    type=int, default=None, help="Show top N experiments")
    parser.add_argument("--sort",   choices=SORT_CHOICES, default="pr_auc",
                        help="Sort metric (default: pr_auc)")
    parser.add_argument("--split",  choices=SPLIT_ORDER, default="test",
                        help="Primary split to display (default: test) — all splits always shown")
    parser.add_argument("--delete", type=int, default=None, help="Delete experiment by ID")
    args = parser.parse_args()

    if args.delete:
        delete_experiment(args.delete)
        return

    if not LOG_PATH.exists():
        print("No experiments logged yet.")
        print("Run the pipeline ending with: python evaluate_ranking.py --note 'your note'")
        return

    df = pd.read_csv(LOG_PATH)
    if df.empty:
        print("Experiment log is empty.")
        return

    show(df, top=args.top, sort_by=args.sort, split=args.split)


if __name__ == "__main__":
    main()
