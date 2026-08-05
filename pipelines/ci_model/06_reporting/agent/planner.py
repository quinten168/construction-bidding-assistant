"""
Planner Agent

Given the full candidate pool for a project, decides which competitors to analyze
and in what order: a single flat ranking by simple_rule_score descending, capped
at top_n. No priority/discovery tiering -- a candidate's presence on CSI's tracked
list never affected this ordering (that field only drove a separate display
grouping downstream, in reporter.py/apps/api's competitor_report.py), so dropping
that grouping is a display-only simplification, not a ranking change.

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
    top_n: int = 5,
    score_col: str = "simple_rule_score",
) -> list[str]:
    """
    Return an ordered list of competitor_unit_ids to analyze: sorted by score desc,
    capped at top_n total.
    """
    df = project_rows.copy()
    df[score_col] = pd.to_numeric(df[score_col], errors="coerce").fillna(0)

    ordered = (
        df.sort_values(score_col, ascending=False)
        ["competitor_unit_id"]
        .tolist()
    )

    return ordered[:top_n]
