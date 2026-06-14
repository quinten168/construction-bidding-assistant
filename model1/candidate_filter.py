from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class CandidateRule:
    name: str
    include_same_state: bool = False
    include_same_county: bool = False
    include_state_type: bool = False
    recent_window_days: int | None = None
    include_current_season: bool = False


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
    project_lookup = projects.set_index("job_id")

    bid_history = bidder_results.merge(
        projects[["job_id", "bid_date", "state", "county", "project_type"]],
        on="job_id",
        how="left",
        validate="many_to_one",
    )
    bid_history["bid_date"] = pd.to_datetime(bid_history["bid_date"], errors="coerce")
    bid_history["competitor_unit_id"] = bid_history["competitor_unit_id"].astype(str)

    rows: list[dict] = []

    for _, project in projects.sort_values("bid_date").iterrows():
        job_id = project["job_id"]
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
            ids = set(
                prior.loc[
                    (prior["bid_date"] >= start_date)
                    & (prior["bid_date"] < bid_date),
                    "competitor_unit_id",
                ]
            )
            add_candidates(ids, "source_recent_activity")

        if rule.include_current_season:
            start_date = _current_season_start(bid_date)
            ids = set(
                prior.loc[
                    (prior["bid_date"] >= start_date)
                    & (prior["bid_date"] < bid_date),
                    "competitor_unit_id",
                ]
            )
            add_candidates(ids, "source_recent_activity")

        add_candidates(priority_ids, "source_priority")

        for competitor_unit_id, flags in source_map.items():
            row = {
                "candidate_rule_version": rule.name,
                "job_id": job_id,
                "bid_date": bid_date,
                "state": state,
                "county": county,
                "project_type": project_type,
                "competitor_unit_id": competitor_unit_id,
                "was_rule_candidate": 1,
                **flags,
            }
            row["candidate_source"] = _sources_to_string(row)
            rows.append(row)

    columns = [
        "candidate_rule_version",
        "job_id",
        "bid_date",
        "state",
        "county",
        "project_type",
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
        ["candidate_rule_version", "job_id", "competitor_unit_id"]
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
