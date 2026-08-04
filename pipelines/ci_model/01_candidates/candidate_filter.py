from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from config import (
    DEFAULT_CANDIDATE_RULE,
    V3_FALLBACK_LOOKBACK_DAYS,
    V3_FALLBACK_SCORE_THRESHOLD,
    V3_HISTORICAL_WINNER_WEIGHT,
    V3_PRIORITY_WEIGHT,
    V3_RECENT_WINDOW_DAYS,
    V3_RECURRING_REGIONAL_MIN_BIDS,
    V3_RECURRING_REGIONAL_WEIGHT,
    V3_WARMUP_HISTORY_DAYS,
    V3_WARMUP_RECENT_DAYS,
)


@dataclass(frozen=True)
class CandidateRule:
    name: str
    include_same_state: bool = False
    include_same_county: bool = False
    include_state_type: bool = False
    recent_window_days: int | None = None
    include_current_season: bool = False
    recent_same_state_only: bool = False


CANDIDATE_RULES = [
    CandidateRule("state_broad", include_same_state=True),
    CandidateRule("county_only", include_same_county=True),
    CandidateRule("state_type", include_state_type=True),
    CandidateRule(
        "county_or_state_type",
        include_same_county=True,
        include_state_type=True,
    ),
    CandidateRule(
        "county_state_type_plus_recent_90d",
        include_same_county=True,
        include_state_type=True,
        recent_window_days=90,
    ),
    CandidateRule(
        "county_state_type_plus_recent_180d",
        include_same_county=True,
        include_state_type=True,
        recent_window_days=180,
    ),
    CandidateRule(
        "county_state_type_plus_current_season",
        include_same_county=True,
        include_state_type=True,
        include_current_season=True,
    ),
    CandidateRule(
        "county_state_type_plus_12m",
        include_same_county=True,
        include_state_type=True,
        recent_window_days=365,
    ),
    CandidateRule(
        "county_state_type_plus_24m",
        include_same_county=True,
        include_state_type=True,
        recent_window_days=730,
    ),
    CandidateRule(
        "county_state_type_plus_state_recent_90d",
        include_same_county=True,
        include_state_type=True,
        recent_window_days=90,
        recent_same_state_only=True,
    ),
    CandidateRule(
        "county_state_type_plus_state_recent_180d",
        include_same_county=True,
        include_state_type=True,
        recent_window_days=180,
        recent_same_state_only=True,
    ),
    CandidateRule(
        "county_state_type_plus_state_current_season",
        include_same_county=True,
        include_state_type=True,
        include_current_season=True,
        recent_same_state_only=True,
    ),
    CandidateRule(
        "county_state_type_plus_state_recent_12m",
        include_same_county=True,
        include_state_type=True,
        recent_window_days=365,
        recent_same_state_only=True,
    ),
]

PROJECT_TYPE_FEATURE_COLUMNS = [
    "rule_based_primary_project_type_v1",
    "project_type_source",
    "project_type_rule",
]

# Bid-schedule quantities — a separate list from PROJECT_TYPE_FEATURE_COLUMNS (which is work-type
# flags, not quantities). Carried through the same per-project loop as those flags so
# rule_candidate_set (and therefore the training panel) actually has mix/grading/base/etc. tonnage
# on every candidate row, not just on missed_actual_bidder rows (build_training_panel.py's `actual`
# gets these via project_lookup, but rule_candidates never did until this list existed).
PROJECT_QUANTITY_COLUMNS = [
    "mix_tons",
    "grading_yards",
    "base_tons",
    "shldr_tons",
    "mill_sy",
    "crush_tons",
    "stock_tons",
]


def _priority_ids_for_date(
    priority_competitors: pd.DataFrame | None,
    bid_date: pd.Timestamp,
) -> set[str]:
    if priority_competitors is None or priority_competitors.empty:
        return set()
    if "competitor_unit_id" not in priority_competitors.columns:
        return set()

    table = priority_competitors.copy()
    if "effective_from" not in table.columns:
        table["effective_from"] = pd.NA
    effective_from = pd.to_datetime(table["effective_from"], errors="coerce")
    active = effective_from.isna() | (bid_date >= effective_from)
    return set(table.loc[active, "competitor_unit_id"].dropna().astype(str))


def _active_entity_ids_for_date(
    entities: pd.DataFrame | None,
    bid_date: pd.Timestamp,
) -> set[str] | None:
    if entities is None or entities.empty:
        return None
    if "competitor_unit_id" not in entities.columns:
        return None

    table = entities.copy()
    if "effective_from" not in table.columns:
        table["effective_from"] = pd.NA
    if "effective_to" not in table.columns:
        table["effective_to"] = pd.NA

    valid_from = pd.to_datetime(table["effective_from"], errors="coerce")
    valid_to = pd.to_datetime(table["effective_to"], errors="coerce")
    active = pd.Series(True, index=table.index)
    active &= valid_from.isna() | (bid_date >= valid_from)
    active &= valid_to.isna() | (bid_date <= valid_to)
    if "active_flag" in table.columns:
        active &= table["active_flag"].astype("string").fillna("1").isin(
            ["1", "TRUE", "True", "true"]
        )
    return set(table.loc[active, "competitor_unit_id"].dropna().astype(str))


def _current_season_start(bid_date: pd.Timestamp) -> pd.Timestamp:
    return pd.Timestamp(year=bid_date.year, month=1, day=1)


def _sources_to_string(row: dict[str, bool]) -> str:
    sources = []
    for col, source in [
        ("source_same_state", "same_state"),
        ("source_same_county", "same_county"),
        ("source_same_state_type", "same_state_type"),
        ("source_recent_activity", "recent_activity"),
        ("source_priority", "priority"),
        ("source_regional", "regional"),
    ]:
        if row.get(col, False):
            sources.append(source)
    return "|".join(sources)


def build_rule_candidate_set(
    projects: pd.DataFrame,
    bidder_results: pd.DataFrame,
    rule: CandidateRule,
    priority_competitors: pd.DataFrame | None = None,
    entities: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Build point-in-time rule candidates for a single candidate rule."""

    projects = projects.copy()
    bidder_results = bidder_results.copy()
    projects["bid_date"] = pd.to_datetime(projects["bid_date"], errors="coerce")

    bid_history = bidder_results.merge(
        projects[["project_natural_key", "bid_date", "state", "county", "project_type"]],
        on="project_natural_key",
        how="left",
        validate="many_to_one",
    )
    bid_history["bid_date"] = pd.to_datetime(bid_history["bid_date"], errors="coerce")
    bid_history["competitor_unit_id"] = bid_history["competitor_unit_id"].astype(str)

    rows: list[dict] = []

    for _, project in projects.sort_values("bid_date").iterrows():
        project_natural_key = project.get("project_natural_key")
        bid_date = project["bid_date"]
        state = project.get("state")
        county = project.get("county")
        project_type = project.get("project_type")

        prior = bid_history[bid_history["bid_date"] < bid_date]
        active_ids = _active_entity_ids_for_date(entities, bid_date)
        priority_ids = _priority_ids_for_date(priority_competitors, bid_date)

        source_map: dict[str, dict[str, bool]] = {}

        def add_candidates(ids: set[str], source_col: str) -> None:
            if active_ids is not None:
                ids = ids & active_ids
            for competitor_id in ids:
                if competitor_id == "nan":
                    continue
                source_map.setdefault(
                    competitor_id,
                    {
                        "source_same_state": False,
                        "source_same_county": False,
                        "source_same_state_type": False,
                        "source_recent_activity": False,
                        "source_priority": False,
                        "source_regional": False,
                    },
                )[source_col] = True

        if rule.include_same_state and pd.notna(state):
            ids = set(prior.loc[prior["state"] == state, "competitor_unit_id"])
            add_candidates(ids, "source_same_state")

        if rule.include_same_county and pd.notna(county):
            ids = set(
                prior.loc[
                    (prior["state"] == state) & (prior["county"] == county),
                    "competitor_unit_id",
                ]
            )
            add_candidates(ids, "source_same_county")

        if (
            rule.include_state_type
            and pd.notna(state)
            and pd.notna(project_type)
            and str(project_type).strip()
        ):
            ids = set(
                prior.loc[
                    (prior["state"] == state)
                    & (prior["project_type"] == project_type),
                    "competitor_unit_id",
                ]
            )
            add_candidates(ids, "source_same_state_type")

        if rule.recent_window_days is not None:
            start_date = bid_date - pd.Timedelta(days=rule.recent_window_days)
            recent_mask = (prior["bid_date"] >= start_date) & (prior["bid_date"] < bid_date)
            if rule.recent_same_state_only and pd.notna(state):
                recent_mask &= prior["state"] == state
            ids = set(
                prior.loc[recent_mask, "competitor_unit_id"]
            )
            add_candidates(ids, "source_recent_activity")

        if rule.include_current_season:
            start_date = _current_season_start(bid_date)
            season_mask = (prior["bid_date"] >= start_date) & (prior["bid_date"] < bid_date)
            if rule.recent_same_state_only and pd.notna(state):
                season_mask &= prior["state"] == state
            ids = set(
                prior.loc[season_mask, "competitor_unit_id"]
            )
            add_candidates(ids, "source_recent_activity")

        add_candidates(priority_ids, "source_priority")

        for competitor_unit_id, flags in source_map.items():
            row = {
                "candidate_rule_version": rule.name,
                "project_natural_key": project_natural_key,
                "bid_date": bid_date,
                "state": state,
                "county": county,
                "project_type": project_type,
                **{
                    col: project.get(col)
                    for col in (*PROJECT_TYPE_FEATURE_COLUMNS, *PROJECT_QUANTITY_COLUMNS)
                    if col in projects.columns
                },
                "competitor_unit_id": competitor_unit_id,
                "was_rule_candidate": 1,
                **flags,
            }
            row["candidate_source"] = _sources_to_string(row)
            rows.append(row)

    columns = [
        "candidate_rule_version",
        "project_natural_key",
        "bid_date",
        "state",
        "county",
        "project_type",
        *[col for col in (*PROJECT_TYPE_FEATURE_COLUMNS, *PROJECT_QUANTITY_COLUMNS)
          if col in projects.columns],
        "competitor_unit_id",
        "was_rule_candidate",
        "source_same_state",
        "source_same_county",
        "source_same_state_type",
        "source_recent_activity",
        "source_priority",
        "source_regional",
        "candidate_source",
    ]
    if not rows:
        return pd.DataFrame(columns=columns)
    return pd.DataFrame(rows)[columns].sort_values(
        ["candidate_rule_version", "project_natural_key", "competitor_unit_id"]
    )


def build_all_rule_candidate_sets(
    projects: pd.DataFrame,
    bidder_results: pd.DataFrame,
    priority_competitors: pd.DataFrame | None = None,
    entities: pd.DataFrame | None = None,
    rules: list[CandidateRule] | None = None,
) -> pd.DataFrame:
    selected_rules = rules or CANDIDATE_RULES
    frames = []
    for rule in selected_rules:
        frame = build_rule_candidate_set(
            projects=projects,
            bidder_results=bidder_results,
            rule=rule,
            priority_competitors=priority_competitors,
            entities=entities,
        )
        if not frame.empty:
            frames.append(frame)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


V3_SOURCE_COLUMNS = [
    "source_same_state",
    "source_same_county",
    "source_same_state_type",
    "source_recent_activity",
    "source_recent_90d_same_state",
    "source_warmup_12m_same_state",
    "source_priority",
    "source_historical_winner_24m",
    "source_recurring_regional_24m",
    "source_regional",
]


def build_v3_candidate_set(
    projects: pd.DataFrame,
    bidder_results: pd.DataFrame,
    priority_competitors: pd.DataFrame | None = None,
    entities: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Build the production V3 candidate pool without future-data leakage.

    V3 uses the 90-day same-state pool as its default, restores the 12-month
    window only while the dataset is left-censored, and adds active entities
    whose point-in-time fallback score is at least 1.5.
    """

    projects = projects.copy()
    bidder_results = bidder_results.copy()
    projects["bid_date"] = pd.to_datetime(projects["bid_date"], errors="coerce")
    projects = projects.dropna(subset=["project_natural_key", "bid_date"])
    history_start = projects["bid_date"].min()

    history_cols = [
        "project_natural_key", "bid_date", "state", "county", "project_type"
    ]
    available_history_cols = [col for col in history_cols if col in projects.columns]
    bid_history = bidder_results.merge(
        projects[available_history_cols],
        on="project_natural_key",
        how="left",
        validate="many_to_one",
    )
    bid_history["bid_date"] = pd.to_datetime(bid_history["bid_date"], errors="coerce")
    bid_history["competitor_unit_id"] = bid_history["competitor_unit_id"].astype(str)
    if "did_win" not in bid_history.columns:
        bid_history["did_win"] = 0
    bid_history["did_win"] = pd.to_numeric(
        bid_history["did_win"], errors="coerce"
    ).fillna(0)

    rows: list[dict] = []
    for _, project in projects.sort_values(["bid_date", "project_natural_key"]).iterrows():
        project_natural_key = project.get("project_natural_key")
        bid_date = project["bid_date"]
        state = project.get("state")
        county = project.get("county")
        project_type = project.get("project_type")
        history_days_available = int((bid_date - history_start).days)
        is_warmup = history_days_available < V3_WARMUP_HISTORY_DAYS

        prior = bid_history[bid_history["bid_date"] < bid_date].copy()
        prior["age_days"] = (bid_date - prior["bid_date"]).dt.days
        same_state = prior["state"].eq(state) if pd.notna(state) else pd.Series(False, index=prior.index)
        same_county = (
            same_state & prior["county"].eq(county)
            if pd.notna(county)
            else pd.Series(False, index=prior.index)
        )
        same_type = (
            same_state & prior["project_type"].eq(project_type)
            if pd.notna(project_type) and str(project_type).strip()
            else pd.Series(False, index=prior.index)
        )
        recent_90d = same_state & prior["age_days"].le(V3_RECENT_WINDOW_DAYS)
        warmup_12m = (
            same_state
            & prior["age_days"].le(V3_WARMUP_RECENT_DAYS)
            & is_warmup
        )
        lookback_24m = prior["age_days"].le(V3_FALLBACK_LOOKBACK_DAYS)

        def ids(mask: pd.Series) -> set[str]:
            return set(prior.loc[mask, "competitor_unit_id"].dropna().astype(str))

        same_state_ids = ids(same_state)
        same_county_ids = ids(same_county)
        same_type_ids = ids(same_type)
        recent_90d_ids = ids(recent_90d)
        warmup_ids = ids(warmup_12m)
        historical_winner_ids = (
            ids(lookback_24m & prior["did_win"].eq(1)) & same_state_ids
        )
        state_counts_24m = prior.loc[same_state & lookback_24m].groupby(
            "competitor_unit_id"
        ).size()
        recurring_regional_ids = set(
            state_counts_24m[
                state_counts_24m >= V3_RECURRING_REGIONAL_MIN_BIDS
            ].index.astype(str)
        )
        priority_ids = _priority_ids_for_date(priority_competitors, bid_date)

        signal_ids = (
            same_county_ids
            | same_type_ids
            | recent_90d_ids
            | warmup_ids
            | historical_winner_ids
            | recurring_regional_ids
            | priority_ids
        )
        active_ids = _active_entity_ids_for_date(entities, bid_date)
        if active_ids is not None:
            signal_ids &= active_ids

        for competitor_id in signal_ids:
            if competitor_id == "nan":
                continue
            is_priority = competitor_id in priority_ids
            is_historical_winner = competitor_id in historical_winner_ids
            is_recurring = competitor_id in recurring_regional_ids
            fallback_score = (
                V3_PRIORITY_WEIGHT * is_priority
                + V3_HISTORICAL_WINNER_WEIGHT * is_historical_winner
                + V3_RECURRING_REGIONAL_WEIGHT * is_recurring
            )
            in_default_90d = (
                competitor_id in same_county_ids
                or competitor_id in same_type_ids
                or competitor_id in recent_90d_ids
            )
            in_warmup = competitor_id in warmup_ids
            in_targeted_fallback = fallback_score >= V3_FALLBACK_SCORE_THRESHOLD
            if not (in_default_90d or in_warmup or in_targeted_fallback):
                continue

            flags = {
                "source_same_state": competitor_id in same_state_ids,
                "source_same_county": competitor_id in same_county_ids,
                "source_same_state_type": competitor_id in same_type_ids,
                "source_recent_activity": competitor_id in recent_90d_ids,
                "source_recent_90d_same_state": competitor_id in recent_90d_ids,
                "source_warmup_12m_same_state": in_warmup,
                "source_priority": is_priority,
                "source_historical_winner_24m": is_historical_winner,
                "source_recurring_regional_24m": is_recurring,
                "source_regional": is_recurring,
            }
            entry_reasons = []
            if in_default_90d:
                entry_reasons.append("90d_default")
            if in_warmup:
                entry_reasons.append("warmup_12m")
            if is_priority:
                entry_reasons.append("hard_priority")
            if in_targeted_fallback:
                entry_reasons.append("fallback_score_ge_1_5")

            row = {
                "candidate_rule_version": DEFAULT_CANDIDATE_RULE,
                "project_natural_key": project_natural_key,
                "bid_date": bid_date,
                "state": state,
                "county": county,
                "project_type": project_type,
                **{
                    col: project.get(col)
                    for col in (*PROJECT_TYPE_FEATURE_COLUMNS, *PROJECT_QUANTITY_COLUMNS)
                    if col in projects.columns
                },
                "competitor_unit_id": competitor_id,
                "was_rule_candidate": 1,
                **flags,
                "history_days_available": history_days_available,
                "history_left_censored_12m": int(is_warmup),
                "fallback_score": float(fallback_score),
                "v3_in_default_90d": int(in_default_90d),
                "v3_in_warmup_12m": int(in_warmup),
                "v3_in_targeted_fallback": int(in_targeted_fallback),
                "candidate_source": "|".join(entry_reasons),
            }
            rows.append(row)

    columns = [
        "candidate_rule_version", "project_natural_key", "bid_date", "state", "county",
        "project_type",
        *[col for col in (*PROJECT_TYPE_FEATURE_COLUMNS, *PROJECT_QUANTITY_COLUMNS)
          if col in projects.columns],
        "competitor_unit_id", "was_rule_candidate", *V3_SOURCE_COLUMNS,
        "history_days_available", "history_left_censored_12m", "fallback_score",
        "v3_in_default_90d", "v3_in_warmup_12m",
        "v3_in_targeted_fallback", "candidate_source",
    ]
    if not rows:
        return pd.DataFrame(columns=columns)
    return pd.DataFrame(rows)[columns].sort_values(
        ["candidate_rule_version", "project_natural_key", "competitor_unit_id"]
    ).reset_index(drop=True)
