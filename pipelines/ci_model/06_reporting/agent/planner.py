"""
Planner Agent

Given the full candidate pool for a project, decides which competitors to analyze
and in what order. Priority competitors (Tier 1) always go first; within each tier
competitors are sorted by simple_rule_score descending.

score_col default switched from logistic_score (36-feature model) to simple_rule_score
(4-feature: county/type/state/size_fit) -- see CI_MODEL_JSON in apps/api/backend/config.py
for why.
"""
from __future__ import annotations

import pandas as pd


def classify_threat(probability: float) -> str:
    if probability >= 0.70:
        return "HIGH"
    elif probability >= 0.40:
        return "MEDIUM"
    return "LOW"


def plan(
    project_rows: pd.DataFrame,
    top_n: int = 10,
    score_col: str = "simple_rule_score",
) -> list[str]:
    """
    Return an ordered list of competitor_unit_ids to analyze.

    Ordering: Tier 1 (priority) first, then Tier 2, both sorted by score desc.
    Capped at top_n total.
    """
    df = project_rows.copy()
    df[score_col] = pd.to_numeric(df[score_col], errors="coerce").fillna(0)

    ordered = (
        df.sort_values(score_col, ascending=False)
        ["competitor_unit_id"]
        .tolist()
    )

    return ordered[:top_n]
