#!/usr/bin/env python3
"""
Evaluate Model 1 ranking models and auto-log to experiments_log.csv.

Computes three metric families for each model × split:
  - Ranking metrics: Precision@K, NDCG (project-level, full candidate pool)
  - Tiered metrics:  Tier 1 (priority) Precision@K + NDCG; Tier 2 (discovery) Precision@K
  - Binary metrics:  ROC-AUC, PR-AUC (row-level, important for imbalanced data)

Tier 1 (priority competitors — always in candidate set): ranking quality is primary.
Tier 2 (rule-discovered competitors): surfacing relevant newcomers is primary.

Auto-logs results to experiment_tracker after each run.

Usage:
    python evaluate_ranking.py
    python evaluate_ranking.py --note "added xgboost" --candidate-rule county_state_type_plus_state_recent_12m
"""
from __future__ import annotations

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "shared"))

import argparse

import numpy as np
import pandas as pd
try:
    from sklearn.metrics import roc_auc_score, average_precision_score
except ImportError:
    def roc_auc_score(y_true: np.ndarray, y_score: np.ndarray) -> float:
        y_true = np.asarray(y_true).astype(int)
        y_score = np.asarray(y_score).astype(float)
        positives = y_true == 1
        n_pos = int(positives.sum())
        n_neg = int(len(y_true) - n_pos)
        if n_pos == 0 or n_neg == 0:
            raise ValueError("ROC-AUC is undefined with one class.")
        ranks = pd.Series(y_score).rank(method="average").to_numpy()
        return float((ranks[positives].sum() - n_pos * (n_pos + 1) / 2) / (n_pos * n_neg))

    def average_precision_score(y_true: np.ndarray, y_score: np.ndarray) -> float:
        y_true = np.asarray(y_true).astype(int)
        y_score = np.asarray(y_score).astype(float)
        order = np.argsort(-y_score, kind="mergesort")
        y_sorted = y_true[order]
        positives = int(y_sorted.sum())
        if positives == 0:
            return 0.0
        cumulative_hits = np.cumsum(y_sorted)
        ranks = np.arange(1, len(y_sorted) + 1)
        precision_at_hits = cumulative_hits[y_sorted == 1] / ranks[y_sorted == 1]
        return float(precision_at_hits.sum() / positives)

from config import COMPETITOR_REGISTRY_PATH, DISCOVERY_TIER, PRIORITY_TIER, TIER_COL, TOP_K_VALUES
from io_utils import read_table
import experiment_tracker

# ============================================================================
# Methods to evaluate: name → score column in ranking_predictions.csv
# Add new models here; missing score columns are silently skipped.
# ============================================================================

METHOD_SCORE_COLUMNS = {
    "xgboost":               "xgb_score",
    "logistic_regression":   "logistic_score",
    "shallow_decision_tree": "tree_score_tiebreak",
    "linear_svm":            "svm_score",
    "rule_based_score":      "rule_score",
    "simple_rule_based":     "simple_rule_score",
}


# ============================================================================
# Ranking metrics (project-level)
# ============================================================================

def _average_precision(relevance: list[int], actual_total: int) -> float:
    if actual_total == 0:
        return 0.0
    hits = 0
    precision_sum = 0.0
    for rank, rel in enumerate(relevance, start=1):
        if rel:
            hits += 1
            precision_sum += hits / rank
    return precision_sum / actual_total


def _ndcg(relevance: list[int], actual_total: int, k: int | None = None) -> float:
    if actual_total == 0:
        return 0.0
    evaluated = relevance[:k] if k is not None else relevance
    dcg = sum(rel / np.log2(rank + 1) for rank, rel in enumerate(evaluated, start=1))
    ideal_len = min(actual_total, len(evaluated))
    idcg = sum(1 / np.log2(rank + 1) for rank in range(1, ideal_len + 1))
    return float(dcg / idcg) if idcg else 0.0


def _graded_ndcg(graded_relevance: list[float]) -> float:
    """NDCG with continuous relevance scores from bid amounts.

    Relevance = max(0, 1 - gap_to_low) where gap_to_low = (bid - low_bid) / low_bid.
    Winner scores 1.0; each % above the low bid reduces relevance proportionally.
    Non-bidders score 0. Ideal DCG uses the same scores sorted descending.
    """
    if not any(r > 0 for r in graded_relevance):
        return 0.0
    dcg = sum(rel / np.log2(rank + 1) for rank, rel in enumerate(graded_relevance, start=1))
    ideal = sorted(graded_relevance, reverse=True)
    idcg = sum(rel / np.log2(rank + 1) for rank, rel in enumerate(ideal, start=1) if rel > 0)
    return float(dcg / idcg) if idcg else 0.0


def _harmonic_discount_mean(n: int) -> float:
    """E[1/log2(rank+1)] over a uniform random permutation of n positions.

    By symmetry every item has an equal chance at every rank, so this
    expected discount is the same for all items.
    """
    return sum(1.0 / np.log2(k + 1) for k in range(1, n + 1)) / n


def compute_random_baselines(
    predictions: pd.DataFrame,
    tier: int,
) -> dict[str, dict]:
    """Analytical random-ranking baseline per time split.

    For Tier 2 (discovery):
        E[P@K] = B_j / N_j  (K cancels via hypergeometric expectation)
        so discovery_p5 == discovery_p10 == discovery_p20 == mean(B_j / N_j)

    For Tier 1 (priority):
        E[graded_NDCG_j] = H_n × sum(r_i) / IDCG_graded_j
        E[binary_NDCG_j] = H_n × B_j / IDCG_binary_j
        where H_n = (1/n) × Σ_{k=1}^{n} 1/log2(k+1)

    Returns dict[split → dict of aggregated metric values].
    """
    tier_preds = predictions[predictions[TIER_COL] == tier].copy()
    has_amounts = (
        "bid_amount" in tier_preds.columns
        and "low_bid_amount" in tier_preds.columns
    )

    split_rows: dict[str, list[dict]] = {"train": [], "validation": [], "test": []}

    for _project_natural_key, group in tier_preds.groupby("project_natural_key", sort=False):
        split = str(group["time_split"].iloc[0])
        if split not in split_rows:
            continue
        n = len(group)
        actual_total = int((group["did_bid"] == 1).sum())
        if actual_total == 0:
            continue

        h_n = _harmonic_discount_mean(n)
        base_rate = actual_total / n

        winner_hit_rate_10 = min(10, n) / n if n > 0 else float("nan")

        if tier == DISCOVERY_TIER:
            split_rows[split].append({"p5": base_rate, "p10": base_rate, "p20": base_rate,
                                      "winner_hit_rate_10": winner_hit_rate_10})

        elif tier == PRIORITY_TIER:
            # Binary NDCG
            idcg_b = sum(1.0 / np.log2(k + 1) for k in range(1, actual_total + 1))
            binary_ndcg = (h_n * actual_total / idcg_b) if idcg_b > 0 else 0.0

            # Graded NDCG
            graded_ndcg = float("nan")
            if has_amounts:
                low_col = group["low_bid_amount"].dropna()
                low_bid = float(low_col.iloc[0]) if not low_col.empty else None
                if low_bid and low_bid > 0:
                    rels = []
                    for _, row in group.iterrows():
                        if row["did_bid"] == 0 or pd.isna(row.get("bid_amount")):
                            rels.append(0.0)
                        else:
                            gap = (row["bid_amount"] - low_bid) / low_bid
                            rels.append(max(0.0, 1.0 - gap))
                    sum_r = sum(rels)
                    sorted_r = sorted(rels, reverse=True)
                    idcg_g = sum(
                        v / np.log2(k + 1)
                        for k, v in enumerate(sorted_r, start=1) if v > 0
                    )
                    graded_ndcg = (h_n * sum_r / idcg_g) if idcg_g > 0 else 0.0

            split_rows[split].append({
                "p5": base_rate, "p10": base_rate, "p20": base_rate,
                "ndcg": binary_ndcg, "graded_ndcg": graded_ndcg,
                "winner_hit_rate_10": winner_hit_rate_10,
            })

    result: dict[str, dict] = {}
    for split, rows in split_rows.items():
        if not rows:
            continue
        df = pd.DataFrame(rows)
        result[split] = {col: round(float(df[col].mean(skipna=True)), 4) for col in df.columns}
    return result


def build_topk_precision(
    predictions: pd.DataFrame,
    actual_counts: pd.DataFrame,
    method_name: str,
    score_col: str,
) -> pd.DataFrame:
    rows = []
    merged = predictions.merge(actual_counts, on="project_natural_key", how="left")
    merged["actual_bidder_count"] = merged["actual_bidder_count"].fillna(0).astype(int)

    for project_natural_key, group in merged.groupby("project_natural_key", sort=False):
        actual_total = int(group["actual_bidder_count"].iloc[0])
        if actual_total == 0:
            continue
        ordered = group.sort_values(score_col, ascending=False).copy()
        relevance = ordered["did_bid"].astype(int).tolist()
        has_winner = "did_win" in ordered.columns and int(ordered["did_win"].sum()) > 0
        row = {
            "method": method_name,
            "time_split": ordered["time_split"].iloc[0],
            "project_natural_key": project_natural_key,
            "bid_date": ordered["bid_date"].iloc[0],
            "state": ordered.get("state", pd.Series([pd.NA])).iloc[0],
            "project_type": ordered.get("project_type", pd.Series([pd.NA])).iloc[0],
            "actual_bidder_count": actual_total,
            "actual_bidders_in_candidate_set": int(ordered["did_bid"].sum()),
            "candidate_count": int(len(ordered)),
            "average_precision": _average_precision(relevance, actual_total),
            "ndcg": _ndcg(relevance, actual_total),
        }
        row["candidate_recall"] = row["actual_bidders_in_candidate_set"] / actual_total
        for k in TOP_K_VALUES:
            captured = int(ordered.head(k)["did_bid"].sum())
            row[f"actual_bidders_captured_at_{k}"] = captured
            row[f"precision_at_{k}"] = captured / k
            row[f"ndcg_at_{k}"] = _ndcg(relevance, actual_total, k=k)
            row[f"all_actual_bidders_in_top_{k}"] = int(captured == actual_total)
            row[f"any_actual_bidder_in_top_{k}"] = int(captured > 0)
            if has_winner:
                winner_captured = int(ordered.head(k)["did_win"].sum())
                row[f"winner_in_top_{k}"] = int(winner_captured > 0)
            else:
                row[f"winner_in_top_{k}"] = float("nan")
        rows.append(row)

    return pd.DataFrame(rows)


def build_winner_hit_rate(
    predictions: pd.DataFrame,
    method_name: str,
    score_col: str,
) -> pd.DataFrame:
    """Winner hit rate @K: reuses build_topk_precision verbatim by swapping the
    `did_bid` relevance column for `did_win` and `actual_bidder_count` for a
    per-project winner-present flag (0 or 1). With actual_total in {0, 1},
    `any_actual_bidder_in_top_{k}` from build_topk_precision is exactly
    "the actual winner is ranked in the top k" -- projects where the winner
    is not in the candidate pool are excluded (actual_total == 0), not scored
    as misses.
    """
    swapped = predictions.copy()
    swapped["did_bid"] = swapped["did_win"]
    winner_present = (
        predictions.groupby("project_natural_key")["did_win"].max()
        .reset_index(name="actual_bidder_count")
    )
    return build_topk_precision(swapped, winner_present, method_name, score_col)


def summarize_metrics(topk: pd.DataFrame, group_cols: list[str] | None = None) -> pd.DataFrame:
    group_cols = group_cols or []
    metric_cols = [
        "candidate_recall",
        "candidate_count",
        "actual_bidder_count",
        "actual_bidders_in_candidate_set",
        "average_precision",
        "ndcg",
        "graded_ndcg",
        *[f"precision_at_{k}" for k in TOP_K_VALUES],
        *[f"ndcg_at_{k}" for k in TOP_K_VALUES],
        *[f"all_actual_bidders_in_top_{k}" for k in TOP_K_VALUES],
        *[f"any_actual_bidder_in_top_{k}" for k in TOP_K_VALUES],
        *[f"winner_in_top_{k}" for k in TOP_K_VALUES],
    ]
    grouped = topk.groupby(["method", "time_split", *group_cols], dropna=False)
    rows = []
    for keys, frame in grouped:
        if not isinstance(keys, tuple):
            keys = (keys,)
        row = dict(zip(["method", "time_split", *group_cols], keys))
        row["projects"] = int(frame["project_natural_key"].nunique())
        if "candidate_count" in frame.columns:
            row["median_candidates"] = float(frame["candidate_count"].median())
        if "actual_bidder_count" in frame.columns:
            row["mean_actual_bidders"] = float(frame["actual_bidder_count"].mean())
        for col in metric_cols:
            if col in {"candidate_count", "actual_bidder_count"}:
                continue
            if col in frame.columns:
                row[f"mean_{col}"] = float(frame[col].mean())
        rows.append(row)
    return pd.DataFrame(rows)


def build_tier_topk_precision(
    predictions: pd.DataFrame,
    method_name: str,
    score_col: str,
    tier: int,
) -> pd.DataFrame:
    """Compute Precision@K, binary NDCG, and graded NDCG for one tier per project.

    Graded NDCG uses bid_amount as relevance: winner = 1.0, each % above the low
    bid reduces relevance proportionally. Requires bid_amount and low_bid_amount
    columns merged into predictions beforehand; falls back to NaN if absent.
    """
    tier_preds = predictions[predictions[TIER_COL] == tier].copy()
    has_bid_amounts = "bid_amount" in tier_preds.columns and "low_bid_amount" in tier_preds.columns
    rows = []
    for project_natural_key, group in tier_preds.groupby("project_natural_key", sort=False):
        ordered = group.sort_values(score_col, ascending=False).copy()
        actual_total = int((ordered["did_bid"] == 1).sum())
        if actual_total == 0:
            continue
        relevance = ordered["did_bid"].astype(int).tolist()

        graded_relevance = []
        if has_bid_amounts:
            for _, r in ordered.iterrows():
                if r["did_bid"] == 0 or pd.isna(r.get("bid_amount")) or pd.isna(r.get("low_bid_amount")) or r["low_bid_amount"] <= 0:
                    graded_relevance.append(0.0)
                else:
                    gap = (r["bid_amount"] - r["low_bid_amount"]) / r["low_bid_amount"]
                    graded_relevance.append(max(0.0, 1.0 - gap))

        row = {
            "method": method_name,
            "time_split": ordered["time_split"].iloc[0],
            "project_natural_key": project_natural_key,
            "actual_bidder_count": actual_total,
            "candidate_count": len(ordered),
            "ndcg": _ndcg(relevance, actual_total),
            "graded_ndcg": _graded_ndcg(graded_relevance) if graded_relevance else float("nan"),
        }
        for k in TOP_K_VALUES:
            captured = int(ordered.head(k)["did_bid"].sum())
            row[f"precision_at_{k}"] = captured / k
            row[f"ndcg_at_{k}"] = _ndcg(relevance, actual_total, k=k)
        rows.append(row)
    return pd.DataFrame(rows)


# ============================================================================
# Binary metrics (row-level) — important for imbalanced data
# ============================================================================

def compute_binary_metrics(
    predictions: pd.DataFrame,
    score_col: str,
    split: str,
) -> dict:
    """
    Compute ROC-AUC and PR-AUC (area under precision-recall curve) for a
    given method × split. Both are row-level metrics across all candidates.

    PR-AUC is preferred over ROC-AUC for imbalanced data because ROC-AUC
    is insensitive to the ratio of negatives and can look deceptively high.
    PR-AUC reflects performance on the minority (positive) class directly.
    """
    subset = predictions[predictions["time_split"] == split].copy()
    if subset.empty or score_col not in subset.columns:
        return {"roc_auc": None, "pr_auc": None}

    y_true  = subset["did_bid"].astype(int).values
    y_score = pd.to_numeric(subset[score_col], errors="coerce").fillna(0).values

    if y_true.sum() == 0 or y_true.sum() == len(y_true):
        return {"roc_auc": None, "pr_auc": None}

    return {
        "roc_auc": round(float(roc_auc_score(y_true, y_score)), 4),
        "pr_auc":  round(float(average_precision_score(y_true, y_score)), 4),
    }


# ============================================================================
# Build experiment log entry
# ============================================================================

def _build_log_rows(
    predictions: pd.DataFrame,
    metrics_df: pd.DataFrame,
    tier1_metrics_df: pd.DataFrame,
    discovery_metrics_df: pd.DataFrame,
    note: str,
    candidate_rule: str,
    random_tier1: dict | None = None,
    random_discovery: dict | None = None,
) -> list[dict]:
    """
    Build one row per (model × split) for experiment_tracker.log_experiment().
    This long format makes it easy to see train vs. test gaps in Excel or the tracker.
    """
    import json as _json

    # Load model configs once
    xgb_cfg: dict = {}
    xgb_path = Path(__file__).parent.parent / "03_training" / "outputs" / "xgboost_model.json"
    if xgb_path.exists():
        bp = _json.loads(xgb_path.read_text()).get("best_params", {})
        xgb_cfg = {
            "xgb_n_estimators":     bp.get("actual_n_estimators"),
            "xgb_max_depth":        bp.get("max_depth"),
            "xgb_learning_rate":    bp.get("learning_rate"),
            "xgb_scale_pos_weight": bp.get("scale_pos_weight"),
        }

    tree_cfg: dict = {}
    tree_path = Path(__file__).parent.parent / "03_training" / "outputs" / "shallow_decision_tree.json"
    if tree_path.exists():
        tm = _json.loads(tree_path.read_text())
        tree_cfg = {
            "tree_best_depth":    tm.get("selected_max_depth"),
            "tree_best_min_leaf": tm.get("selected_min_samples_leaf"),
        }

    rows = []
    for method_key, score_col in METHOD_SCORE_COLUMNS.items():
        if score_col not in predictions.columns:
            continue

        for split in ("train", "validation", "test"):
            binary = compute_binary_metrics(predictions, score_col, split)

            rank_row = metrics_df[
                (metrics_df["method"] == method_key) &
                (metrics_df["time_split"] == split)
            ]

            row: dict = {
                "note":           note,
                "candidate_rule": candidate_rule,
                "model":          method_key,
                "split":          split,
                "roc_auc":        binary["roc_auc"],
                "pr_auc":         binary["pr_auc"],
            }

            if not rank_row.empty:
                r = rank_row.iloc[0]
                row["p5"]      = round(float(r.get("mean_precision_at_5",  0)), 4)
                row["p10"]     = round(float(r.get("mean_precision_at_10", 0)), 4)
                row["p20"]     = round(float(r.get("mean_precision_at_20", 0)), 4)
                row["ndcg"]    = round(float(r.get("mean_ndcg", 0)), 4)
                row["projects"] = int(r.get("projects", 0))

            # Tier 1 (priority) metrics
            t1_row = tier1_metrics_df[
                (tier1_metrics_df["method"] == method_key) &
                (tier1_metrics_df["time_split"] == split)
            ] if not tier1_metrics_df.empty else pd.DataFrame()
            if not t1_row.empty:
                t = t1_row.iloc[0]
                row["tier1_p5"]   = round(float(t.get("mean_precision_at_5",  0)), 4)
                row["tier1_p10"]  = round(float(t.get("mean_precision_at_10", 0)), 4)
                row["tier1_p20"]  = round(float(t.get("mean_precision_at_20", 0)), 4)
                row["tier1_ndcg"]        = round(float(t.get("mean_ndcg", 0)), 4)
                row["tier1_graded_ndcg"] = round(float(t.get("mean_graded_ndcg", 0)), 4) if not pd.isna(t.get("mean_graded_ndcg", float("nan"))) else None

            # Tier 2 (discovery) metrics
            d_row = discovery_metrics_df[
                (discovery_metrics_df["method"] == method_key) &
                (discovery_metrics_df["time_split"] == split)
            ] if not discovery_metrics_df.empty else pd.DataFrame()
            if not d_row.empty:
                d = d_row.iloc[0]
                row["discovery_p5"]  = round(float(d.get("mean_precision_at_5",  0)), 4)
                row["discovery_p10"] = round(float(d.get("mean_precision_at_10", 0)), 4)
                row["discovery_p20"] = round(float(d.get("mean_precision_at_20", 0)), 4)

            # Attach model-specific config to its own rows
            if method_key == "xgboost":
                row.update(xgb_cfg)
            elif method_key == "shallow_decision_tree":
                row.update(tree_cfg)

            rows.append(row)

    # ── Random baseline rows (one per split, no score column needed) ──────
    if random_tier1 or random_discovery:
        for split in ("train", "validation", "test"):
            row: dict = {
                "note":           note,
                "candidate_rule": candidate_rule,
                "model":          "random_baseline",
                "split":          split,
                "roc_auc":        None,
                "pr_auc":         None,
            }
            if random_tier1 and split in random_tier1:
                t = random_tier1[split]
                row["tier1_p5"]          = t.get("p5")
                row["tier1_p10"]         = t.get("p10")
                row["tier1_p20"]         = t.get("p20")
                row["tier1_ndcg"]        = t.get("ndcg")
                row["tier1_graded_ndcg"] = t.get("graded_ndcg")
            if random_discovery and split in random_discovery:
                d = random_discovery[split]
                row["discovery_p5"]  = d.get("p5")
                row["discovery_p10"] = d.get("p10")
                row["discovery_p20"] = d.get("p20")
            rows.append(row)

    return rows


# ============================================================================
# Main
# ============================================================================

def main() -> None:
    _STEP_OUT = Path(__file__).resolve().parent / "outputs"
    _PRED_INPUT = str(Path(__file__).resolve().parent.parent / "03_training" / "outputs" / "ranking_predictions.csv")
    parser = argparse.ArgumentParser(description="Evaluate Model 1 ranking models.")
    parser.add_argument("--predictions",  default=_PRED_INPUT)
    parser.add_argument("--bidder-results", default="data/processed/bidder_results.parquet")
    parser.add_argument("--registry", default=str(COMPETITOR_REGISTRY_PATH),
                        help="Path to competitor_name_registry - name_variants.csv")
    parser.add_argument("--metrics-output", default=str(_STEP_OUT / "ranking_metrics.csv"))
    parser.add_argument("--metrics-by-project-type-output", default=str(_STEP_OUT / "ranking_metrics_by_project_type.csv"))
    parser.add_argument("--metrics-by-state-output", default=str(_STEP_OUT / "ranking_metrics_by_state.csv"))
    parser.add_argument("--tier1-metrics-output", default=str(_STEP_OUT / "tier1_ranking_metrics.csv"))
    parser.add_argument("--discovery-metrics-output", default=str(_STEP_OUT / "discovery_ranking_metrics.csv"))
    parser.add_argument("--winner-hit-rate-output", default=str(_STEP_OUT / "winner_hit_rate_metrics.csv"))
    parser.add_argument("--topk-output",  default=str(_STEP_OUT / "top_k_precision.csv"))
    parser.add_argument("--note",         default="", help="Description for this experiment run")
    parser.add_argument("--candidate-rule", default="county_state_type_plus_state_recent_90d",
                        help="Candidate rule used in this run")
    args = parser.parse_args()

    predictions    = pd.read_csv(args.predictions)
    bidder_results = read_table(args.bidder_results)
    actual_counts  = (
        bidder_results.groupby("project_natural_key")["competitor_unit_id"]
        .nunique()
        .reset_index(name="actual_bidder_count")
    )

    # ── Derive tier column from name registry via raw_bidder_name mapping ──
    registry_path = Path(args.registry)
    if TIER_COL not in predictions.columns and registry_path.exists():
        registry = pd.read_csv(registry_path)
        top_raw_variants = set(
            registry[registry["Top Competitors Tag"].astype(str) == "1"]["raw_name_variant"]
            .dropna().str.upper()
        )
        priority_ids = set(
            bidder_results[
                bidder_results["raw_bidder_name"].str.upper().isin(top_raw_variants)
            ]["competitor_unit_id"].dropna().astype(str)
        ) if "raw_bidder_name" in bidder_results.columns else set()
        predictions[TIER_COL] = np.where(
            predictions["competitor_unit_id"].isin(priority_ids), PRIORITY_TIER, DISCOVERY_TIER
        )
        print(f"  Tier 1 priority competitors resolved: {len(priority_ids)} unique IDs")

    # ── Merge bid_amount for graded NDCG ─────────────────────────────────
    bid_info = bidder_results[["project_natural_key", "competitor_unit_id", "bid_amount"]].copy()
    bid_info["bid_amount"] = pd.to_numeric(bid_info["bid_amount"], errors="coerce")
    low_bid = (
        bid_info[bid_info["bid_amount"] > 0]
        .groupby("project_natural_key")["bid_amount"].min()
        .reset_index(name="low_bid_amount")
    )
    bid_info = bid_info.merge(low_bid, on="project_natural_key", how="left")
    predictions = predictions.merge(
        bid_info, on=["project_natural_key", "competitor_unit_id"], how="left", suffixes=("", "_br")
    )
    if "bid_amount_br" in predictions.columns:
        predictions["bid_amount"] = predictions["bid_amount"].fillna(predictions.pop("bid_amount_br"))

    # ── Ranking metrics (full pool) ───────────────────────────────────────
    frames = []
    for method_name, score_col in METHOD_SCORE_COLUMNS.items():
        if score_col in predictions.columns:
            frames.append(build_topk_precision(predictions, actual_counts, method_name, score_col))
    topk = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()

    metrics          = summarize_metrics(topk)
    metrics_by_type  = summarize_metrics(topk, ["project_type"])
    metrics_by_state = summarize_metrics(topk, ["state"])

    # ── Tiered metrics ────────────────────────────────────────────────────
    tier1_frames, discovery_frames = [], []
    if TIER_COL in predictions.columns:
        for method_name, score_col in METHOD_SCORE_COLUMNS.items():
            if score_col in predictions.columns:
                tier1_frames.append(
                    build_tier_topk_precision(predictions, method_name, score_col, PRIORITY_TIER)
                )
                discovery_frames.append(
                    build_tier_topk_precision(predictions, method_name, score_col, DISCOVERY_TIER)
                )
    tier1_topk      = pd.concat(tier1_frames,     ignore_index=True) if tier1_frames     else pd.DataFrame()
    discovery_topk  = pd.concat(discovery_frames,  ignore_index=True) if discovery_frames  else pd.DataFrame()
    tier1_metrics     = summarize_metrics(tier1_topk)     if not tier1_topk.empty     else pd.DataFrame()
    discovery_metrics = summarize_metrics(discovery_topk) if not discovery_topk.empty else pd.DataFrame()

    # ── Winner hit rate @K (reuses build_topk_precision with did_win as relevance) ──
    winner_frames = []
    for method_name, score_col in METHOD_SCORE_COLUMNS.items():
        if score_col in predictions.columns:
            winner_frames.append(build_winner_hit_rate(predictions, method_name, score_col))
    winner_topk = pd.concat(winner_frames, ignore_index=True) if winner_frames else pd.DataFrame()
    winner_hit_rate_metrics = summarize_metrics(winner_topk) if not winner_topk.empty else pd.DataFrame()

    # ── Random baseline (analytical, no model needed) ─────────────────────
    random_tier1     = compute_random_baselines(predictions, PRIORITY_TIER)  if TIER_COL in predictions.columns else {}
    random_discovery = compute_random_baselines(predictions, DISCOVERY_TIER) if TIER_COL in predictions.columns else {}

    Path(args.metrics_output).parent.mkdir(parents=True, exist_ok=True)
    metrics.to_csv(args.metrics_output, index=False)
    metrics_by_type.to_csv(args.metrics_by_project_type_output, index=False)
    metrics_by_state.to_csv(args.metrics_by_state_output, index=False)
    topk.to_csv(args.topk_output, index=False)
    if not tier1_metrics.empty:
        tier1_metrics.to_csv(args.tier1_metrics_output, index=False)
    if not discovery_metrics.empty:
        discovery_metrics.to_csv(args.discovery_metrics_output, index=False)
    if not winner_hit_rate_metrics.empty:
        winner_hit_rate_metrics.to_csv(args.winner_hit_rate_output, index=False)

    # ── Binary metrics summary (printed) ─────────────────────────────────
    print("=" * 80)
    print("BINARY METRICS — ROC-AUC and PR-AUC (test split)")
    print("  PR-AUC is preferred for imbalanced data")
    print("=" * 80)
    print(f"  {'Method':<25}  {'ROC-AUC':>8}  {'PR-AUC':>8}")
    print(f"  {'─'*25}  {'─'*8}  {'─'*8}")
    for method_name, score_col in METHOD_SCORE_COLUMNS.items():
        if score_col not in predictions.columns:
            continue
        bm = compute_binary_metrics(predictions, score_col, "test")
        roc = f"{bm['roc_auc']:.4f}" if bm["roc_auc"] is not None else "   —  "
        pr  = f"{bm['pr_auc']:.4f}"  if bm["pr_auc"]  is not None else "   —  "
        print(f"  {method_name:<25}  {roc:>8}  {pr:>8}")

    print("\n")
    print("RANKING METRICS — FULL POOL (test split)")
    print("=" * 80)
    test_metrics = metrics[metrics["time_split"] == "test"]
    if not test_metrics.empty:
        cols = ["method", "projects", "mean_precision_at_5", "mean_precision_at_10",
                "mean_precision_at_20", "mean_ndcg"]
        available = [c for c in cols if c in test_metrics.columns]
        print(test_metrics[available].to_string(index=False))

    if not tier1_metrics.empty:
        print("\n")
        print("TIER 1 (PRIORITY) METRICS — test split")
        print("=" * 80)
        t1_test = tier1_metrics[tier1_metrics["time_split"] == "test"]
        if not t1_test.empty:
            cols = ["method", "projects", "mean_precision_at_5", "mean_precision_at_10",
                    "mean_precision_at_20", "mean_ndcg", "mean_graded_ndcg"]
            available = [c for c in cols if c in t1_test.columns]
            print(t1_test[available].to_string(index=False))
            print("  (graded_ndcg uses bid_amount: winner=1.0, penalty proportional to gap from low bid)")

    if not discovery_metrics.empty:
        print("\n")
        print("TIER 2 (DISCOVERY) METRICS — test split")
        print("=" * 80)
        d_test = discovery_metrics[discovery_metrics["time_split"] == "test"]
        if not d_test.empty:
            cols = ["method", "projects", "mean_precision_at_5", "mean_precision_at_10",
                    "mean_precision_at_20"]
            available = [c for c in cols if c in d_test.columns]
            print(d_test[available].to_string(index=False))

    if not winner_hit_rate_metrics.empty:
        print("\n")
        print("WINNER HIT RATE @ K — test split")
        print("  fraction of projects where the actual auction WINNER, when present")
        print("  in the candidate pool, is ranked in the top K by score")
        print("=" * 80)
        w_test = winner_hit_rate_metrics[winner_hit_rate_metrics["time_split"] == "test"]
        if not w_test.empty:
            cols = ["method", "projects", "mean_any_actual_bidder_in_top_5",
                    "mean_any_actual_bidder_in_top_10", "mean_any_actual_bidder_in_top_20"]
            available = [c for c in cols if c in w_test.columns]
            rename = {
                "mean_any_actual_bidder_in_top_5": "winner_hit_rate_at_5",
                "mean_any_actual_bidder_in_top_10": "winner_hit_rate_at_10",
                "mean_any_actual_bidder_in_top_20": "winner_hit_rate_at_20",
            }
            print(w_test[available].rename(columns=rename).to_string(index=False))

    if random_tier1 or random_discovery:
        print("\n")
        print("RANDOM BASELINE (analytical) — test split")
        print("=" * 80)
        if "test" in random_tier1:
            t = random_tier1["test"]
            print(f"  Tier 1   binary NDCG:  {t.get('ndcg', float('nan')):.4f}")
            print(f"  Tier 1   graded NDCG:  {t.get('graded_ndcg', float('nan')):.4f}")
            print(f"  Tier 1   P@5/10/20:    {t.get('p5', float('nan')):.4f}  (= B_j/N_j, same for all K)")
        if "test" in random_discovery:
            d = random_discovery["test"]
            print(f"  Discovery P@5/10/20:   {d.get('p5', float('nan')):.4f}  (= B_j/N_j, same for all K)")

    print(f"\n  metrics:              {args.metrics_output}")
    print(f"  metrics by type:      {args.metrics_by_project_type_output}")
    print(f"  metrics by state:     {args.metrics_by_state_output}")
    print(f"  tier1 metrics:        {args.tier1_metrics_output}")
    print(f"  discovery metrics:    {args.discovery_metrics_output}")
    print(f"  top-k precision:      {args.topk_output}")
    print(f"  winner hit rate:      {args.winner_hit_rate_output}")

    # ── Auto-log to experiment tracker ───────────────────────────────────
    log_rows = _build_log_rows(
        predictions=predictions,
        metrics_df=metrics,
        tier1_metrics_df=tier1_metrics,
        discovery_metrics_df=discovery_metrics,
        note=args.note,
        candidate_rule=args.candidate_rule,
        random_tier1=random_tier1,
        random_discovery=random_discovery,
    )
    experiment_tracker.log_experiment(log_rows)


if __name__ == "__main__":
    main()
