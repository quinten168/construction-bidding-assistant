#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "shared"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "04_evaluation"))

import argparse
import json
from dataclasses import dataclass

import numpy as np
import pandas as pd

from config import RANKING_FEATURE_COLUMNS
from evaluate_ranking import build_topk_precision, summarize_metrics


@dataclass
class TreeNode:
    probability: float
    samples: int
    positives: int
    feature: str | None = None
    threshold: float | None = None
    left: "TreeNode | None" = None
    right: "TreeNode | None" = None


def _weighted_probability(y: np.ndarray, sample_weight: np.ndarray) -> float:
    total = sample_weight.sum()
    if total <= 0:
        return 0.0
    return float((y * sample_weight).sum() / total)


def _weighted_gini(y: np.ndarray, sample_weight: np.ndarray) -> float:
    p = _weighted_probability(y, sample_weight)
    return 1.0 - p**2 - (1.0 - p) ** 2


def _candidate_thresholds(values: np.ndarray, max_thresholds: int = 24) -> np.ndarray:
    unique = np.unique(values[~np.isnan(values)])
    if len(unique) <= 1:
        return np.array([])
    if len(unique) <= max_thresholds:
        return (unique[:-1] + unique[1:]) / 2
    quantiles = np.linspace(0.05, 0.95, max_thresholds)
    return np.unique(np.quantile(unique, quantiles))


def _best_split(
    x: pd.DataFrame,
    y: np.ndarray,
    sample_weight: np.ndarray,
    feature_cols: list[str],
    min_samples_leaf: int,
) -> tuple[str | None, float | None, float]:
    parent_weight = sample_weight.sum()
    parent_impurity = _weighted_gini(y, sample_weight)
    best_feature = None
    best_threshold = None
    best_gain = 0.0

    for feature in feature_cols:
        values = x[feature].to_numpy(dtype=float)
        for threshold in _candidate_thresholds(values):
            left_mask = values <= threshold
            right_mask = ~left_mask
            if left_mask.sum() < min_samples_leaf or right_mask.sum() < min_samples_leaf:
                continue
            left_weight = sample_weight[left_mask].sum()
            right_weight = sample_weight[right_mask].sum()
            if left_weight <= 0 or right_weight <= 0:
                continue
            weighted_child_impurity = (
                left_weight / parent_weight * _weighted_gini(y[left_mask], sample_weight[left_mask])
                + right_weight / parent_weight * _weighted_gini(y[right_mask], sample_weight[right_mask])
            )
            gain = parent_impurity - weighted_child_impurity
            if gain > best_gain:
                best_feature = feature
                best_threshold = float(threshold)
                best_gain = float(gain)

    return best_feature, best_threshold, best_gain


def fit_tree(
    x: pd.DataFrame,
    y: np.ndarray,
    sample_weight: np.ndarray,
    feature_cols: list[str],
    max_depth: int,
    min_samples_leaf: int,
    depth: int = 0,
) -> TreeNode:
    node = TreeNode(
        probability=_weighted_probability(y, sample_weight),
        samples=int(len(y)),
        positives=int(y.sum()),
    )
    if depth >= max_depth or len(y) < 2 * min_samples_leaf or y.sum() == 0 or y.sum() == len(y):
        return node

    feature, threshold, gain = _best_split(
        x=x,
        y=y,
        sample_weight=sample_weight,
        feature_cols=feature_cols,
        min_samples_leaf=min_samples_leaf,
    )
    if feature is None or threshold is None or gain <= 0:
        return node

    values = x[feature].to_numpy(dtype=float)
    left_mask = values <= threshold
    right_mask = ~left_mask
    node.feature = feature
    node.threshold = threshold
    node.left = fit_tree(
        x.loc[left_mask],
        y[left_mask],
        sample_weight[left_mask],
        feature_cols,
        max_depth,
        min_samples_leaf,
        depth + 1,
    )
    node.right = fit_tree(
        x.loc[right_mask],
        y[right_mask],
        sample_weight[right_mask],
        feature_cols,
        max_depth,
        min_samples_leaf,
        depth + 1,
    )
    return node


def predict_tree_row(row: pd.Series, node: TreeNode) -> float:
    current = node
    while current.feature is not None and current.threshold is not None:
        value = float(row[current.feature])
        if value <= current.threshold:
            current = current.left or current
        else:
            current = current.right or current
    return current.probability


def predict_tree(frame: pd.DataFrame, node: TreeNode) -> np.ndarray:
    return np.array([predict_tree_row(row, node) for _, row in frame.iterrows()])


def export_tree_text(node: TreeNode, depth: int = 0) -> str:
    indent = "  " * depth
    leaf = f"prob={node.probability:.4f}, samples={node.samples}, positives={node.positives}"
    if node.feature is None or node.threshold is None:
        return f"{indent}return {leaf}\n"
    text = f"{indent}if {node.feature} <= {node.threshold:.4f}:\n"
    text += export_tree_text(node.left or node, depth + 1)
    text += f"{indent}else:\n"
    text += export_tree_text(node.right or node, depth + 1)
    return text


def tree_to_dict(node: TreeNode) -> dict:
    return {
        "probability": node.probability,
        "samples": node.samples,
        "positives": node.positives,
        "feature": node.feature,
        "threshold": node.threshold,
        "left": tree_to_dict(node.left) if node.left else None,
        "right": tree_to_dict(node.right) if node.right else None,
    }


def _sample_weights(y: np.ndarray) -> np.ndarray:
    positives = max(float(y.sum()), 1.0)
    negatives = max(float(len(y) - y.sum()), 1.0)
    return np.where(y == 1, negatives / positives, 1.0)


def _validation_score(predictions: pd.DataFrame, bidder_results: pd.DataFrame) -> dict:
    actual_counts = (
        bidder_results.groupby("project_natural_key")["competitor_unit_id"]
        .nunique()
        .reset_index(name="actual_bidder_count")
    )
    topk = build_topk_precision(
        predictions,
        actual_counts,
        method_name="shallow_decision_tree",
        score_col="tree_score_tiebreak",
    )
    summary = summarize_metrics(topk)
    if summary.empty:
        return {}
    row = summary.iloc[0].to_dict()
    row["selection_score"] = (
        row.get("mean_precision_at_10", 0)
        + 0.5 * row.get("mean_precision_at_20", 0)
        + 0.25 * row.get("mean_average_precision", 0)
        + 0.25 * row.get("mean_ndcg", 0)
    )
    return row


def main() -> None:
    _STEP_OUT = Path(__file__).resolve().parent / "outputs"
    _PRED_INPUT = str(Path(__file__).resolve().parent / "outputs" / "ranking_predictions.csv")
    parser = argparse.ArgumentParser(description="Train shallow decision-tree ranking baseline.")
    parser.add_argument("--predictions", default=_PRED_INPUT)
    parser.add_argument("--bidder-results", default="data/processed/bidder_results.csv")
    parser.add_argument("--max-depths", default="2,3,4,5")
    parser.add_argument("--min-samples-leaf", default="50,100,200,500")
    parser.add_argument("--output-predictions", default=str(_STEP_OUT / "ranking_predictions.csv"))
    parser.add_argument("--tree-output", default=str(_STEP_OUT / "shallow_decision_tree.json"))
    parser.add_argument("--tree-text-output", default=str(_STEP_OUT / "shallow_decision_tree.txt"))
    parser.add_argument("--tuning-output", default=str(_STEP_OUT / "shallow_decision_tree_tuning.csv"))
    args = parser.parse_args()

    predictions = pd.read_csv(args.predictions)
    bidder_results = pd.read_csv(args.bidder_results)
    for col in RANKING_FEATURE_COLUMNS:
        if col not in predictions.columns:
            predictions[col] = 0.0
        predictions[col] = pd.to_numeric(predictions[col], errors="coerce").fillna(0)

    train = predictions[predictions["time_split"] == "train"].copy()
    validation = predictions[predictions["time_split"] == "validation"].copy()
    if train.empty or validation.empty:
        raise ValueError("Train and validation splits are required for tree tuning.")

    x_train = train[RANKING_FEATURE_COLUMNS]
    y_train = train["did_bid"].astype(int).to_numpy()
    sample_weight = _sample_weights(y_train)

    tuning_rows = []
    best = None
    best_score = -np.inf
    depths = [int(value) for value in args.max_depths.split(",")]
    leaves = [int(value) for value in args.min_samples_leaf.split(",")]

    for max_depth in depths:
        for min_leaf in leaves:
            tree = fit_tree(
                x=x_train,
                y=y_train,
                sample_weight=sample_weight,
                feature_cols=RANKING_FEATURE_COLUMNS,
                max_depth=max_depth,
                min_samples_leaf=min_leaf,
            )
            validation_scores = validation.copy()
            validation_scores["tree_score"] = predict_tree(validation_scores[RANKING_FEATURE_COLUMNS], tree)
            validation_scores["tree_score_tiebreak"] = (
                validation_scores["tree_score"]
                + 1e-6 * pd.to_numeric(validation_scores["logistic_score"], errors="coerce").fillna(0)
                + 1e-9 * pd.to_numeric(validation_scores["rule_score"], errors="coerce").fillna(0)
            )
            metrics = _validation_score(validation_scores, bidder_results)
            row = {
                "max_depth": max_depth,
                "min_samples_leaf": min_leaf,
                **metrics,
            }
            tuning_rows.append(row)
            score = metrics.get("selection_score", -np.inf)
            if score > best_score:
                best_score = score
                best = (max_depth, min_leaf, tree)

    if best is None:
        raise ValueError("No decision-tree configuration was fitted.")

    best_depth, best_leaf, best_tree = best
    predictions["tree_score"] = predict_tree(predictions[RANKING_FEATURE_COLUMNS], best_tree)
    predictions["tree_score_tiebreak"] = (
        predictions["tree_score"]
        + 1e-6 * pd.to_numeric(predictions["logistic_score"], errors="coerce").fillna(0)
        + 1e-9 * pd.to_numeric(predictions["rule_score"], errors="coerce").fillna(0)
    )

    Path(args.output_predictions).parent.mkdir(parents=True, exist_ok=True)
    predictions.to_csv(args.output_predictions, index=False)
    pd.DataFrame(tuning_rows).to_csv(args.tuning_output, index=False)
    tree_payload = {
        "model": "manual_weighted_gini_decision_tree",
        "selected_max_depth": best_depth,
        "selected_min_samples_leaf": best_leaf,
        "feature_columns": RANKING_FEATURE_COLUMNS,
        "tree": tree_to_dict(best_tree),
    }
    Path(args.tree_output).write_text(json.dumps(tree_payload, indent=2) + "\n")
    Path(args.tree_text_output).write_text(export_tree_text(best_tree))

    print("Shallow decision tree baseline complete")
    print(f"  selected max_depth:        {best_depth}")
    print(f"  selected min_samples_leaf: {best_leaf}")
    print(f"  predictions:               {args.output_predictions}")
    print(f"  tree text:                 {args.tree_text_output}")
    print()
    print(export_tree_text(best_tree))


if __name__ == "__main__":
    main()

