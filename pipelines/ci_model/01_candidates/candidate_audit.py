from __future__ import annotations

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "shared"))

import pandas as pd

from config import PRIORITY_TIER, TIER_COL


def audit_candidate_rules(training_audit_panel: pd.DataFrame) -> pd.DataFrame:
    rows = []
    grouped = training_audit_panel.groupby("candidate_rule_version", dropna=False)
    for rule_name, frame in grouped:
        actual = frame[frame["did_bid"] == 1]
        near_low = frame[frame["is_near_low"] == 1]
        winners = frame[frame["did_win"] == 1]
        rule_candidates = frame[frame["was_rule_candidate"] == 1]

        project_group = frame.groupby("project_natural_key")
        candidate_counts = rule_candidates.groupby("project_natural_key")["competitor_unit_id"].nunique()

        actual_by_project = actual.groupby("project_natural_key")["competitor_unit_id"].nunique()
        captured_actual_by_project = actual[actual["was_rule_candidate"] == 1].groupby("project_natural_key")[
            "competitor_unit_id"
        ].nunique()
        candidate_counts_all_projects = (
            frame[["project_natural_key"]]
            .drop_duplicates()
            .merge(
                candidate_counts.rename("candidate_count"),
                on="project_natural_key",
                how="left",
            )["candidate_count"]
            .fillna(0)
        )
        recall_check = (
            pd.concat(
                [
                    actual_by_project.rename("actual_bidders"),
                    captured_actual_by_project.rename("captured_bidders"),
                    candidate_counts.rename("candidate_count"),
                ],
                axis=1,
            )
            .fillna(0)
        )
        recall_check["candidate_multiplier"] = recall_check.apply(
            lambda row: row["candidate_count"] / row["actual_bidders"]
            if row["actual_bidders"] > 0
            else 0,
            axis=1,
        )

        # Tier breakdown (available when rule_candidate_set was built with tier column)
        tier_stats: dict = {}
        if TIER_COL in rule_candidates.columns:
            priority_cands = rule_candidates[rule_candidates[TIER_COL] == PRIORITY_TIER]
            discovery_cands = rule_candidates[rule_candidates[TIER_COL] != PRIORITY_TIER]
            tier_stats = {
                "priority_candidates": int(len(priority_cands)),
                "discovery_candidates": int(len(discovery_cands)),
                "priority_actual_bidder_recall": _safe_rate(
                    int((priority_cands["did_bid"] == 1).sum()),
                    int((actual["source_priority"] == True).sum()) if "source_priority" in actual.columns else 0,
                ),
                "discovery_actual_bidder_recall": _safe_rate(
                    int((discovery_cands["did_bid"] == 1).sum()),
                    int((actual.get("source_priority", pd.Series(False, index=actual.index)) == False).sum()),
                ),
            }

        rows.append(
            {
                "candidate_rule_version": rule_name,
                "projects": int(frame["project_natural_key"].nunique()),
                "rule_candidate_rows": int(len(rule_candidates)),
                "training_audit_rows": int(len(frame)),
                "actual_bidder_rows": int(len(actual)),
                "actual_bidders_per_project": float(actual_by_project.mean())
                if len(actual_by_project)
                else 0.0,
                "missed_actual_bidders": int(
                    ((frame["did_bid"] == 1) & (frame["was_rule_candidate"] == 0)).sum()
                ),
                "candidate_recall": _safe_rate(
                    int(((actual["was_rule_candidate"] == 1)).sum()),
                    int(len(actual)),
                ),
                "precision": _safe_rate(
                    int((rule_candidates["did_bid"] == 1).sum()),
                    int(len(rule_candidates)),
                ),
                "winner_recall": _safe_rate(
                    int((winners["was_rule_candidate"] == 1).sum()),
                    int(len(winners)),
                ),
                "near_low_bidder_recall": _safe_rate(
                    int((near_low["was_rule_candidate"] == 1).sum()),
                    int(len(near_low)),
                ),
                "projects_with_full_bidder_recall": _safe_rate(
                    int(
                        (
                            recall_check["actual_bidders"]
                            == recall_check["captured_bidders"]
                        ).sum()
                    ),
                    int(len(recall_check)),
                ),
                "full_project_recall": _safe_rate(
                    int(
                        (
                            recall_check["actual_bidders"]
                            == recall_check["captured_bidders"]
                        ).sum()
                    ),
                    int(len(recall_check)),
                ),
                "projects_with_winner_captured": _project_capture_rate(winners),
                "projects_with_zero_candidates": int((candidate_counts_all_projects == 0).sum()),
                "avg_candidates_per_project": float(candidate_counts.mean())
                if len(candidate_counts)
                else 0.0,
                "median_candidates_per_project": float(candidate_counts.median())
                if len(candidate_counts)
                else 0.0,
                "p75_candidates_per_project": float(candidate_counts.quantile(0.75))
                if len(candidate_counts)
                else 0.0,
                "p90_candidates_per_project": float(candidate_counts.quantile(0.9))
                if len(candidate_counts)
                else 0.0,
                "p95_candidates_per_project": float(candidate_counts.quantile(0.95))
                if len(candidate_counts)
                else 0.0,
                "max_candidates_per_project": int(candidate_counts.max())
                if len(candidate_counts)
                else 0,
                "avg_candidate_multiplier": float(recall_check["candidate_multiplier"].mean())
                if len(recall_check)
                else 0.0,
                "median_candidate_multiplier": float(recall_check["candidate_multiplier"].median())
                if len(recall_check)
                else 0.0,
                "positive_rate_in_ranking_panel": _safe_rate(
                    int(((rule_candidates["did_bid"] == 1)).sum()),
                    int(len(rule_candidates)),
                ),
                **tier_stats,
            }
        )

    return pd.DataFrame(rows).sort_values("candidate_rule_version").reset_index(drop=True)


def audit_candidate_rules_by_project_type(training_audit_panel: pd.DataFrame) -> pd.DataFrame:
    rows = []
    grouped = training_audit_panel.groupby(
        ["candidate_rule_version", "project_type"],
        dropna=False,
    )
    for (rule_name, project_type), frame in grouped:
        actual = frame[frame["did_bid"] == 1]
        rule_candidates = frame[frame["was_rule_candidate"] == 1]
        winners = frame[frame["did_win"] == 1]
        candidate_counts = rule_candidates.groupby("project_natural_key")["competitor_unit_id"].nunique()

        actual_by_project = actual.groupby("project_natural_key")["competitor_unit_id"].nunique()
        captured_actual_by_project = actual[actual["was_rule_candidate"] == 1].groupby("project_natural_key")[
            "competitor_unit_id"
        ].nunique()
        recall_check = (
            pd.concat(
                [
                    actual_by_project.rename("actual_bidders"),
                    captured_actual_by_project.rename("captured_bidders"),
                    candidate_counts.rename("candidate_count"),
                ],
                axis=1,
            )
            .fillna(0)
        )

        rows.append(
            {
                "candidate_rule_version": rule_name,
                "project_type": project_type,
                "projects": int(frame["project_natural_key"].nunique()),
                "actual_bidder_rows": int(len(actual)),
                "missed_actual_bidders": int(
                    ((frame["did_bid"] == 1) & (frame["was_rule_candidate"] == 0)).sum()
                ),
                "candidate_recall": _safe_rate(
                    int((actual["was_rule_candidate"] == 1).sum()),
                    int(len(actual)),
                ),
                "winner_recall": _safe_rate(
                    int((winners["was_rule_candidate"] == 1).sum()),
                    int(len(winners)),
                ),
                "full_project_recall": _safe_rate(
                    int((recall_check["actual_bidders"] == recall_check["captured_bidders"]).sum()),
                    int(len(recall_check)),
                ),
                "precision": _safe_rate(
                    int((rule_candidates["did_bid"] == 1).sum()),
                    int(len(rule_candidates)),
                ),
                "median_candidates_per_project": float(candidate_counts.median())
                if len(candidate_counts)
                else 0.0,
                "p90_candidates_per_project": float(candidate_counts.quantile(0.9))
                if len(candidate_counts)
                else 0.0,
            }
        )

    return (
        pd.DataFrame(rows)
        .sort_values(["candidate_rule_version", "project_type"])
        .reset_index(drop=True)
    )


def _safe_rate(numerator: int, denominator: int) -> float:
    if denominator == 0:
        return 0.0
    return numerator / denominator


def _project_capture_rate(winners: pd.DataFrame) -> float:
    if winners.empty:
        return 0.0
    by_project = winners.groupby("project_natural_key")["was_rule_candidate"].max()
    return float((by_project == 1).mean())


def classify_missed_reasons(
    missed: pd.DataFrame,
    projects: pd.DataFrame,
    bidder_results: pd.DataFrame,
) -> pd.DataFrame:
    if missed.empty:
        missed["miss_reason"] = pd.Series(dtype="string")
        return missed

    projects = projects.copy()
    bidder_results = bidder_results.copy()
    projects["bid_date"] = pd.to_datetime(projects["bid_date"], errors="coerce")
    history = bidder_results.merge(
        projects[["project_natural_key", "bid_date", "state", "county", "project_type"]],
        on="project_natural_key",
        how="left",
        validate="many_to_one",
    )
    history["bid_date"] = pd.to_datetime(history["bid_date"], errors="coerce")

    detail_rows = []
    for _, row in missed.iterrows():
        bid_date = pd.to_datetime(row.get("bid_date"), errors="coerce")
        competitor = row.get("competitor_unit_id")
        state = row.get("state")
        county = row.get("county")
        project_type = row.get("project_type")

        details = {
            "was_same_state": 0,
            "was_same_county": 0,
            "had_same_type_history": 0,
            "had_recent_12m_activity": 0,
            "had_recent_24m_activity": 0,
            "closest_matching_historical_type": pd.NA,
            "days_since_last_bid": pd.NA,
        }

        if pd.isna(state) or not str(state).strip():
            reason = "missing_or_unstandardized_state"
        elif pd.isna(county) or not str(county).strip():
            reason = "missing_project_location"
        else:
            prior = history[
                (history["competitor_unit_id"] == competitor)
                & (history["bid_date"] < bid_date)
            ]
            if prior.empty:
                reason = "first_appearance_in_data"
            else:
                last_bid_date = prior["bid_date"].max()
                details["days_since_last_bid"] = (bid_date - last_bid_date).days
                details["had_recent_12m_activity"] = int(
                    (prior["bid_date"] >= bid_date - pd.Timedelta(days=365)).any()
                )
                details["had_recent_24m_activity"] = int(
                    (prior["bid_date"] >= bid_date - pd.Timedelta(days=730)).any()
                )
                prior_same_state = prior[prior["state"] == state]
                details["was_same_state"] = int(not prior_same_state.empty)
                if prior_same_state.empty:
                    reason = "cross_state_bidder"
                else:
                    prior_same_county = prior_same_state[prior_same_state["county"] == county]
                    details["was_same_county"] = int(not prior_same_county.empty)
                    prior_same_type = pd.DataFrame()
                    if pd.notna(project_type) and str(project_type).strip():
                        prior_same_type = prior_same_state[
                            prior_same_state["project_type"] == project_type
                        ]
                        details["had_same_type_history"] = int(not prior_same_type.empty)
                    prior_types = (
                        prior_same_state["project_type"]
                        .dropna()
                        .astype(str)
                        .value_counts()
                    )
                    if not prior_types.empty:
                        details["closest_matching_historical_type"] = prior_types.index[0]

                    if details["days_since_last_bid"] > 730:
                        reason = "inactive_more_than_24m"
                    elif not details["had_recent_12m_activity"]:
                        reason = "older_than_12m"
                    elif pd.notna(project_type) and str(project_type).strip():
                        if details["had_same_type_history"]:
                            reason = "other"
                        else:
                            reason = "no_prior_same_type"
                    else:
                        reason = "missing_project_type"
        details["miss_reason"] = reason
        detail_rows.append(details)

    result = missed.copy()
    result = pd.concat([result.reset_index(drop=True), pd.DataFrame(detail_rows)], axis=1)
    return result


def missed_reason_by_project_type(missed: pd.DataFrame) -> pd.DataFrame:
    if missed.empty:
        return pd.DataFrame(
            columns=[
                "candidate_rule_version",
                "project_type",
                "miss_reason",
                "missed_actual_bidders",
            ]
        )

    group_cols = [
        "candidate_rule_version",
        "project_type",
        "miss_reason",
    ]
    available = [col for col in group_cols if col in missed.columns]
    return (
        missed.groupby(available, dropna=False)
        .size()
        .reset_index(name="missed_actual_bidders")
        .sort_values(
            ["candidate_rule_version", "project_type", "missed_actual_bidders"],
            ascending=[True, True, False],
        )
    )


def missed_actual_bidders(
    training_audit_panel: pd.DataFrame,
    projects: pd.DataFrame | None = None,
    bidder_results: pd.DataFrame | None = None,
) -> pd.DataFrame:
    missed = training_audit_panel[
        (training_audit_panel["did_bid"] == 1)
        & (training_audit_panel["was_rule_candidate"] == 0)
    ].copy()
    if projects is not None and bidder_results is not None:
        missed = classify_missed_reasons(missed, projects, bidder_results)
    elif not missed.empty:
        missed["miss_reason"] = "not_classified"

    cols = [
        "candidate_rule_version",
        "project_natural_key",
        "bid_date",
        "state",
        "county",
        "project_type",
        "competitor_unit_id",
        "bid_amount",
        "bid_rank",
        "did_win",
        "gap_to_low",
        "is_near_low",
        "miss_reason",
        "was_same_state",
        "was_same_county",
        "had_same_type_history",
        "had_recent_12m_activity",
        "had_recent_24m_activity",
        "closest_matching_historical_type",
        "days_since_last_bid",
    ]
    return missed[[col for col in cols if col in missed.columns]].sort_values(
        ["candidate_rule_version", "project_natural_key", "bid_rank", "competitor_unit_id"]
    )
