#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "shared"))

import argparse
import json

import numpy as np
import pandas as pd

from io_utils import read_table, write_table


FEATURE_COLUMNS = [
    "same_county_history_count",
    "same_state_history_count",
    "same_type_history_count",
    "recent_12m_bid_count",
    "recent_24m_bid_count",
    "historical_bid_count",
    "historical_win_count",
    "historical_win_rate",
    "days_since_last_bid",
    "has_paving",
    "has_grading",
    "has_utility",
    "has_structure",
    "has_drainage",
    "has_reclamation",
    "has_trail",
    "is_reconstruction",
    "is_structure_replacement",
]


def build_asof_features(
    ranking_panel: pd.DataFrame,
    projects: pd.DataFrame,
    bidder_results: pd.DataFrame,
) -> pd.DataFrame:
    panel = ranking_panel.copy()
    projects = projects.copy()
    bidder_results = bidder_results.copy()

    panel["bid_date"] = pd.to_datetime(panel["bid_date"], errors="coerce")
    projects["bid_date"] = pd.to_datetime(projects["bid_date"], errors="coerce")
    history = bidder_results.merge(
        projects[
            [
                "job_id",
                "bid_date",
                "state",
                "county",
                "project_type",
            ]
        ],
        on="job_id",
        how="left",
        validate="many_to_one",
    )
    history["bid_date"] = pd.to_datetime(history["bid_date"], errors="coerce")
    history["did_win"] = pd.to_numeric(history["did_win"], errors="coerce").fillna(0)

    feature_frames = []
    for job_id, frame in panel.groupby("job_id", sort=False):
        project = frame.iloc[0]
        bid_date = project["bid_date"]
        state = project.get("state")
        county = project.get("county")
        project_type = project.get("project_type")
        candidate_ids = frame["competitor_unit_id"].astype(str)

        prior = history[history["bid_date"] < bid_date].copy()
        base = pd.DataFrame(
            {
                "job_id": job_id,
                "competitor_unit_id": candidate_ids,
            },
            index=frame.index,
        )

        if prior.empty:
            for col in FEATURE_COLUMNS:
                if col not in frame.columns:
                    base[col] = 0
            base["days_since_last_bid"] = 9999
            feature_frames.append(base)
            continue

        prior["competitor_unit_id"] = prior["competitor_unit_id"].astype(str)

        def count_map(mask: pd.Series) -> pd.Series:
            return prior.loc[mask].groupby("competitor_unit_id").size()

        same_state = prior["state"] == state
        same_county = same_state & (prior["county"] == county)
        same_type = same_state & (prior["project_type"] == project_type)
        recent_12m = prior["bid_date"] >= bid_date - pd.Timedelta(days=365)
        recent_24m = prior["bid_date"] >= bid_date - pd.Timedelta(days=730)

        maps = {
            "same_county_history_count": count_map(same_county),
            "same_state_history_count": count_map(same_state),
            "same_type_history_count": count_map(same_type),
            "recent_12m_bid_count": count_map(recent_12m),
            "recent_24m_bid_count": count_map(recent_24m),
            "historical_bid_count": prior.groupby("competitor_unit_id").size(),
            "historical_win_count": prior.groupby("competitor_unit_id")["did_win"].sum(),
        }

        for col, values in maps.items():
            base[col] = candidate_ids.map(values).fillna(0).to_numpy()

        base["historical_win_rate"] = np.where(
            base["historical_bid_count"] > 0,
            base["historical_win_count"] / base["historical_bid_count"],
            0,
        )
        last_bid = prior.groupby("competitor_unit_id")["bid_date"].max()
        last_dates = candidate_ids.map(last_bid)
        base["days_since_last_bid"] = (bid_date - last_dates).dt.days.fillna(9999).to_numpy()

        feature_frames.append(base)

    features = pd.concat(feature_frames).sort_index()
    new_feature_cols = features.drop(columns=["job_id", "competitor_unit_id"])
    new_feature_cols = new_feature_cols.drop(
        columns=[col for col in new_feature_cols.columns if col in panel.columns],
        errors="ignore",
    )
    result = panel.join(new_feature_cols)
    for col in FEATURE_COLUMNS:
        result[col] = pd.to_numeric(result[col], errors="coerce").fillna(0)
    return result


def _sigmoid(values: np.ndarray) -> np.ndarray:
    return 1 / (1 + np.exp(-np.clip(values, -30, 30)))


def fit_logistic_numpy(
    train: pd.DataFrame,
    feature_cols: list[str],
    iterations: int,
    learning_rate: float,
    l2: float,
) -> tuple[np.ndarray, pd.Series, pd.Series]:
    x_train = train[feature_cols].astype(float)
    y_train = train["did_bid"].astype(float).to_numpy()

    means = x_train.mean()
    stds = x_train.std().replace(0, 1)
    x = ((x_train - means) / stds).to_numpy()
    x = np.column_stack([np.ones(len(x)), x])

    weights = np.zeros(x.shape[1])
    positives = max(float(y_train.sum()), 1.0)
    negatives = max(float(len(y_train) - y_train.sum()), 1.0)
    sample_weights = np.where(y_train == 1, negatives / positives, 1.0)

    for _ in range(iterations):
        pred = _sigmoid(x @ weights)
        error = (pred - y_train) * sample_weights
        grad = (x.T @ error) / len(x)
        grad[1:] += l2 * weights[1:]
        weights -= learning_rate * grad

    return weights, means, stds


def predict_logistic(
    frame: pd.DataFrame,
    feature_cols: list[str],
    weights: np.ndarray,
    means: pd.Series,
    stds: pd.Series,
) -> np.ndarray:
    x = ((frame[feature_cols].astype(float) - means) / stds).to_numpy()
    x = np.column_stack([np.ones(len(x)), x])
    return _sigmoid(x @ weights)


def topk_metrics(frame: pd.DataFrame, score_col: str = "predicted_bid_probability") -> pd.DataFrame:
    rows = []
    for job_id, group in frame.groupby("job_id"):
        actual_count = int(group["did_bid"].sum())
        if actual_count == 0:
            continue
        ordered = group.sort_values(score_col, ascending=False)
        row = {
            "job_id": job_id,
            "actual_bidders": actual_count,
            "candidate_count": int(len(group)),
        }
        for k in [5, 10]:
            captured = int(ordered.head(k)["did_bid"].sum())
            row[f"top{k}_actual_bidders_captured"] = captured
            row[f"top{k}_precision"] = captured / k
            row[f"has_any_actual_in_top{k}"] = int(captured > 0)
        rows.append(row)
    return pd.DataFrame(rows)


def summarize_topk(topk: pd.DataFrame) -> dict:
    if topk.empty:
        return {}
    return {
        "projects": int(len(topk)),
        "mean_top5_precision": float(topk["top5_precision"].mean()),
        "mean_top10_precision": float(topk["top10_precision"].mean()),
        "projects_with_any_actual_in_top5": float(topk["has_any_actual_in_top5"].mean()),
        "projects_with_any_actual_in_top10": float(topk["has_any_actual_in_top10"].mean()),
        "median_candidate_count": float(topk["candidate_count"].median()),
    }


def main() -> None:
    _STEP_OUT = Path(__file__).resolve().parent / "outputs"
    parser = argparse.ArgumentParser(
        description="Build leakage-safe Model 1 ranking baseline features and metrics."
    )
    parser.add_argument("--ranking-panel", default="data/processed/model1/ranking_training_panel.parquet")
    parser.add_argument("--projects", default="data/processed/projects.csv")
    parser.add_argument("--bidder-results", default="data/processed/bidder_results.csv")
    parser.add_argument("--candidate-rule", default="county_state_type_plus_state_recent_12m")
    parser.add_argument("--test-start-date", default="2025-01-01")
    parser.add_argument("--iterations", type=int, default=250)
    parser.add_argument("--learning-rate", type=float, default=0.08)
    parser.add_argument("--l2", type=float, default=0.001)
    parser.add_argument("--features-output", default="data/processed/model1/ranking_baseline_features.parquet")
    parser.add_argument("--predictions-output", default=str(_STEP_OUT / "ranking_baseline_predictions.csv"))
    parser.add_argument("--topk-output", default=str(_STEP_OUT / "ranking_baseline_topk_by_project.csv"))
    parser.add_argument("--metrics-output", default=str(_STEP_OUT / "ranking_baseline_metrics.json"))
    args = parser.parse_args()

    ranking_panel = read_table(args.ranking_panel)
    ranking_panel = ranking_panel[
        ranking_panel["candidate_rule_version"] == args.candidate_rule
    ].copy()
    projects = pd.read_csv(args.projects)
    bidder_results = pd.read_csv(args.bidder_results)

    features = build_asof_features(ranking_panel, projects, bidder_results)
    features["bid_date"] = pd.to_datetime(features["bid_date"], errors="coerce")
    test_start = pd.Timestamp(args.test_start_date)
    train = features[features["bid_date"] < test_start].copy()
    test = features[features["bid_date"] >= test_start].copy()

    weights, means, stds = fit_logistic_numpy(
        train=train,
        feature_cols=FEATURE_COLUMNS,
        iterations=args.iterations,
        learning_rate=args.learning_rate,
        l2=args.l2,
    )
    features["predicted_bid_probability"] = predict_logistic(
        features,
        FEATURE_COLUMNS,
        weights,
        means,
        stds,
    )
    test_predictions = features[features["bid_date"] >= test_start].copy()
    topk = topk_metrics(test_predictions)
    metrics = {
        "candidate_rule_version": args.candidate_rule,
        "test_start_date": args.test_start_date,
        "train_rows": int(len(train)),
        "test_rows": int(len(test)),
        "train_projects": int(train["job_id"].nunique()),
        "test_projects": int(test["job_id"].nunique()),
        "train_positive_rate": float(train["did_bid"].mean()) if len(train) else 0.0,
        "test_positive_rate": float(test["did_bid"].mean()) if len(test) else 0.0,
        "topk": summarize_topk(topk),
        "feature_columns": FEATURE_COLUMNS,
    }

    write_table(features, args.features_output)
    Path(args.predictions_output).parent.mkdir(parents=True, exist_ok=True)
    test_predictions[
        [
            "job_id",
            "bid_date",
            "competitor_unit_id",
            "did_bid",
            "did_win",
            "predicted_bid_probability",
            *FEATURE_COLUMNS,
        ]
    ].to_csv(args.predictions_output, index=False)
    topk.to_csv(args.topk_output, index=False)
    Path(args.metrics_output).write_text(json.dumps(metrics, indent=2) + "\n")

    print("Ranking baseline complete")
    print(f"  candidate rule: {args.candidate_rule}")
    print(f"  train rows:     {metrics['train_rows']:,}")
    print(f"  test rows:      {metrics['test_rows']:,}")
    print(f"  metrics:        {args.metrics_output}")
    print(json.dumps(metrics["topk"], indent=2))


if __name__ == "__main__":
    main()
