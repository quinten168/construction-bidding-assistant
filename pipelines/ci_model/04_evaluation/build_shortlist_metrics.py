#!/usr/bin/env python3
"""Build shortlist capture and ranking metrics for selected score columns.

Priority/discovery metrics are evaluated inside the same global Top-K shortlist.
This keeps the segmented metrics aligned with the planner-facing recommendation.
"""
from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd


METHODS = {
    "rule_based_score": "rule_score",
    "logistic_regression": "logistic_score",
}
KS = (5, 10)


def ndcg_at_k(relevance: list[int], actual_total: int, k: int) -> float:
    if actual_total <= 0:
        return 0.0
    rel = relevance[:k]
    dcg = sum(value / np.log2(rank + 1) for rank, value in enumerate(rel, start=1))
    ideal_len = min(actual_total, k)
    idcg = sum(1 / np.log2(rank + 1) for rank in range(1, ideal_len + 1))
    return float(dcg / idcg) if idcg else 0.0


def safe_ratio(numerator: int, denominator: int) -> float:
    return float(numerator / denominator) if denominator else float("nan")


def evaluate_method(
    predictions: pd.DataFrame,
    actual_count_by_job: dict[str, int],
    priority_ids: set[str],
    method: str,
    score_col: str,
) -> list[dict]:
    rows: list[dict] = []
    for project_natural_key, group in predictions.groupby("project_natural_key", sort=False):
        actual_total = actual_count_by_job.get(str(project_natural_key), 0)
        if actual_total <= 0:
            continue
        ordered = group.sort_values(score_col, ascending=False).copy()
        ranked_ids = ordered["competitor_unit_id"].astype(str).tolist()
        relevance = ordered["did_bid"].astype(int).tolist()
        priority_mask = ordered["competitor_unit_id"].astype(str).isin(priority_ids)
        actual_priority = int((priority_mask & ordered["did_bid"].eq(1)).sum())
        # Priority competitors are always in the pool. Any actual bidder missing
        # from the pool is therefore treated as discovery for recall accounting.
        actual_discovery = max(actual_total - actual_priority, 0)
        row = {
            "method": method,
            "split": "test",
            "project_natural_key": str(project_natural_key),
            "actual_bidder_count": actual_total,
            "actual_priority_count": actual_priority,
            "actual_discovery_count": actual_discovery,
        }
        for k in KS:
            top = ordered.head(k)
            top_ids = top["competitor_unit_id"].astype(str).tolist()
            top_priority_mask = top["competitor_unit_id"].astype(str).isin(priority_ids)
            captured = int(top["did_bid"].sum())
            priority_recommended = int(top_priority_mask.sum())
            discovery_recommended = len(top_ids) - priority_recommended
            priority_captured = int((top_priority_mask & top["did_bid"].eq(1)).sum())
            discovery_captured = captured - priority_captured
            row.update({
                f"precision_at_{k}": safe_ratio(captured, k),
                f"recall_at_{k}": safe_ratio(captured, actual_total),
                f"priority_precision_at_{k}": safe_ratio(priority_captured, priority_recommended),
                f"priority_recall_at_{k}": safe_ratio(priority_captured, actual_priority),
                f"discovery_precision_at_{k}": safe_ratio(discovery_captured, discovery_recommended),
                f"discovery_recall_at_{k}": safe_ratio(discovery_captured, actual_discovery),
                f"ndcg_at_{k}": ndcg_at_k(relevance, actual_total, k),
            })
        rows.append(row)
    return rows


def summarize(per_project: pd.DataFrame, candidate_rule: str, note: str) -> pd.DataFrame:
    metric_cols = [
        f"{prefix}_at_{k}"
        for k in KS
        for prefix in (
            "precision", "recall", "priority_precision", "priority_recall",
            "discovery_precision", "discovery_recall", "ndcg",
        )
    ]
    rows = []
    timestamp = datetime.now().isoformat(timespec="seconds")
    for method, frame in per_project.groupby("method", sort=False):
        row = {
            "experiment_id": 1,
            "timestamp": timestamp,
            "note": note,
            "candidate_rule": candidate_rule,
            "model": method,
            "split": "test",
            "projects": int(frame["project_natural_key"].nunique()),
        }
        for col in metric_cols:
            row[col] = float(frame[col].mean(skipna=True))
        rows.append(row)
    return pd.DataFrame(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--predictions", required=True)
    parser.add_argument("--bidder-results", required=True)
    parser.add_argument("--priority-registry", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--project-output", required=True)
    parser.add_argument("--note", default="shortlist capture + ranking metrics")
    args = parser.parse_args()

    predictions = pd.read_csv(args.predictions, low_memory=False)
    predictions = predictions[predictions["time_split"] == "test"].copy()
    bidder_results = pd.read_csv(args.bidder_results, low_memory=False)
    priority = pd.read_csv(args.priority_registry, low_memory=False)

    predictions["project_natural_key"] = predictions["project_natural_key"].astype(str)
    predictions["competitor_unit_id"] = predictions["competitor_unit_id"].astype(str)
    bidder_results["project_natural_key"] = bidder_results["project_natural_key"].astype(str)
    bidder_results["competitor_unit_id"] = bidder_results["competitor_unit_id"].astype(str)
    priority_ids = set(priority["competitor_unit_id"].dropna().astype(str))
    actual_count_by_job = (
        bidder_results.groupby("project_natural_key")["competitor_unit_id"].nunique().to_dict()
    )

    frames = []
    for method, score_col in METHODS.items():
        if score_col not in predictions.columns:
            raise ValueError(f"Missing required score column: {score_col}")
        frames.extend(evaluate_method(
            predictions, actual_count_by_job, priority_ids, method, score_col
        ))
    per_project = pd.DataFrame(frames)
    candidate_rule = str(predictions["candidate_rule_version"].dropna().iloc[0])
    summary = summarize(per_project, candidate_rule, args.note)

    output = Path(args.output)
    project_output = Path(args.project_output)
    output.parent.mkdir(parents=True, exist_ok=True)
    project_output.parent.mkdir(parents=True, exist_ok=True)
    summary.to_csv(output, index=False)
    per_project.to_csv(project_output, index=False)
    print(summary.to_string(index=False))
    print(f"\nsummary: {output}")
    print(f"detail:  {project_output}")


if __name__ == "__main__":
    main()
