#!/usr/bin/env python3
"""Build the project x competitor operating-unit panel.

This script creates the label panel for Stage 1. It does not train a model and
does not compute point-in-time historical features beyond candidate eligibility.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import pandas as pd

from entity_resolution import apply_competitor_mapping


STATE_NAME_TO_ABBR = {
    "IOWA": "IA",
    "MINNESOTA": "MN",
    "MONTANA": "MT",
    "NEBRASKA": "NE",
    "NORTH DAKOTA": "ND",
    "SOUTH DAKOTA": "SD",
}


def _state_key(row: pd.Series) -> str | pd.NA:
    state = row.get("State")
    if pd.notna(state) and str(state).strip():
        value = str(state).strip().upper()
        return STATE_NAME_TO_ABBR.get(value, value[:2])

    for col in ["County", "LOCATION"]:
        value = row.get(col)
        if pd.isna(value):
            continue
        match = re.search(r"\b(MN|ND|SD|IA|NE|MT)\b", str(value).upper())
        if match:
            return match.group(1)

    return pd.NA


def _county_key(value: object) -> str | pd.NA:
    if pd.isna(value):
        return pd.NA
    text = str(value).upper().strip()
    text = re.sub(r"\b(MN|ND|SD|IA|NE|MT)\b", "", text)
    text = re.sub(r"\s+", " ", text).strip(" ,-")
    return text or pd.NA


def _project_identity(df: pd.DataFrame) -> pd.Series:
    if "strict_key" in df.columns:
        return df["strict_key"].astype("string")
    return (
        df["DATE"].astype("string").fillna("")
        + "|"
        + df["LOCATION"].astype("string").fillna("")
        + "|"
        + df["PROJECT"].astype("string").fillna("")
    )


def build_projects(long_bids: pd.DataFrame) -> pd.DataFrame:
    bids = long_bids.copy()
    bids["_project_identity"] = _project_identity(bids)
    bids["bid_date"] = pd.to_datetime(bids["DATE"], errors="coerce")
    bids["state"] = bids.apply(_state_key, axis=1)
    bids["county"] = bids["County"].apply(_county_key)

    project_cols = [
        "_project_identity",
        "bid_date",
        "state",
        "county",
        "LOCATION",
        "PROJECT",
        "primary_project_id",
        "MIX TN",
        "GRADE CY",
        "BID_AMOUNT",
    ]
    available_cols = [col for col in project_cols if col in bids.columns]

    projects = (
        bids[available_cols]
        .sort_values(["bid_date", "_project_identity"])
        .groupby("_project_identity", dropna=False)
        .agg(
            bid_date=("bid_date", "first"),
            state=("state", "first"),
            county=("county", "first"),
            project_location=("LOCATION", "first"),
            project_name=("PROJECT", "first"),
            source_project_id=("primary_project_id", "first"),
            mix_tons=("MIX TN", "first"),
            grading_yards=("GRADE CY", "first"),
            estimated_value=("BID_AMOUNT", "min"),
        )
        .reset_index()
        .sort_values(["bid_date", "_project_identity"])
        .reset_index(drop=True)
    )
    projects.insert(0, "job_id", [f"P{i:06d}" for i in range(1, len(projects) + 1)])
    projects["project_type"] = pd.NA
    return projects


def build_bidder_results(
    long_bids: pd.DataFrame,
    aliases: pd.DataFrame,
    projects: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    mapped = apply_competitor_mapping(
        bids=long_bids,
        aliases=aliases,
        bidder_col="BIDDER_NAME",
    )
    mapped["_project_identity"] = _project_identity(mapped)
    mapped = mapped.merge(
        projects[["_project_identity", "job_id"]],
        on="_project_identity",
        how="left",
        validate="many_to_one",
    )
    mapped["bid_amount"] = pd.to_numeric(mapped["BID_AMOUNT"], errors="coerce")
    mapped["bid_rank"] = pd.to_numeric(mapped["bidder_sequence"], errors="coerce")

    duplicate_actual_units = (
        mapped.groupby(["job_id", "competitor_unit_id"], dropna=False)
        .size()
        .reset_index(name="actual_rows")
        .query("actual_rows > 1")
        .sort_values(["actual_rows", "job_id"], ascending=[False, True])
    )

    low_bid = mapped.groupby("job_id")["bid_amount"].min().rename("low_bid_amount")
    mapped = mapped.merge(low_bid, on="job_id", how="left")
    mapped["did_win_row"] = (
        mapped["bid_amount"].notna()
        & mapped["low_bid_amount"].notna()
        & (mapped["bid_amount"] == mapped["low_bid_amount"])
    ).astype(int)

    bidder_results = (
        mapped.groupby(["job_id", "competitor_unit_id"], dropna=False)
        .agg(
            bid_amount=("bid_amount", "min"),
            bid_rank=("bid_rank", "min"),
            did_win=("did_win_row", "max"),
            raw_bidder_name=("BIDDER_NAME", lambda s: "; ".join(sorted(set(s.dropna().astype(str))))),
            mapping_status=("mapping_status", lambda s: "; ".join(sorted(set(s.dropna().astype(str))))),
        )
        .reset_index()
    )

    return bidder_results, duplicate_actual_units


def _active_entity_ids_for_date(
    entities: pd.DataFrame,
    bid_date: pd.Timestamp,
) -> set[str]:
    if entities.empty:
        return set()

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
        active &= table["active_flag"].astype("string").fillna("1").isin(["1", "TRUE", "True", "true"])

    return set(table.loc[active, "competitor_unit_id"].dropna().astype(str))


def build_project_competitor_panel(
    projects: pd.DataFrame,
    bidder_results: pd.DataFrame,
    priority_competitors: pd.DataFrame | None = None,
    entities: pd.DataFrame | None = None,
) -> pd.DataFrame:
    projects = projects.copy()
    bidder_results = bidder_results.copy()
    projects["bid_date"] = pd.to_datetime(projects["bid_date"], errors="coerce")

    if priority_competitors is not None and "competitor_unit_id" in priority_competitors.columns:
        priority_ids = set(priority_competitors["competitor_unit_id"].dropna().astype(str))
    else:
        priority_ids = set()

    rows: list[dict] = []

    for _, project in projects.sort_values("bid_date").iterrows():
        job_id = project["job_id"]
        bid_date = project["bid_date"]

        actual_bids = bidder_results[bidder_results["job_id"] == job_id].copy()
        actual_competitors = set(actual_bids["competitor_unit_id"].dropna().astype(str))

        prior_job_ids = projects.loc[
            (projects["bid_date"] < bid_date)
            & (projects["state"] == project["state"]),
            "job_id",
        ]

        historical_competitors = set(
            bidder_results.loc[
                bidder_results["job_id"].isin(prior_job_ids),
                "competitor_unit_id",
            ]
            .dropna()
            .astype(str)
        )

        candidate_competitors = historical_competitors | actual_competitors | priority_ids

        if entities is not None:
            active_ids = _active_entity_ids_for_date(entities, bid_date)
            candidate_competitors = (candidate_competitors & active_ids) | actual_competitors

        bid_lookup = (
            actual_bids.dropna(subset=["competitor_unit_id"])
            .set_index("competitor_unit_id")
            .to_dict("index")
        )

        for competitor_unit_id in sorted(candidate_competitors):
            bid_record = bid_lookup.get(competitor_unit_id)
            rows.append(
                {
                    "job_id": job_id,
                    "bid_date": bid_date,
                    "state": project.get("state"),
                    "county": project.get("county"),
                    "project_type": project.get("project_type"),
                    "mix_tons": project.get("mix_tons"),
                    "grading_yards": project.get("grading_yards"),
                    "estimated_value": project.get("estimated_value"),
                    "competitor_unit_id": competitor_unit_id,
                    "did_bid": int(bid_record is not None),
                    "did_win": int(bid_record.get("did_win", 0)) if bid_record is not None else 0,
                    "bid_amount": bid_record.get("bid_amount") if bid_record is not None else pd.NA,
                    "bid_rank": bid_record.get("bid_rank") if bid_record is not None else pd.NA,
                    "candidate_source": _candidate_source(
                        competitor_unit_id,
                        historical_competitors,
                        actual_competitors,
                        priority_ids,
                    ),
                }
            )

    return pd.DataFrame(rows)


def _candidate_source(
    competitor_unit_id: str,
    historical_competitors: set[str],
    actual_competitors: set[str],
    priority_ids: set[str],
) -> str:
    sources = []
    if competitor_unit_id in historical_competitors:
        sources.append("historical_state")
    if competitor_unit_id in actual_competitors:
        sources.append("actual_bidder")
    if competitor_unit_id in priority_ids:
        sources.append("priority")
    return "+".join(sources)


def add_gap_to_low(panel: pd.DataFrame) -> pd.DataFrame:
    result = panel.copy()
    result["bid_amount"] = pd.to_numeric(result["bid_amount"], errors="coerce")

    low_bid = (
        result.loc[result["did_bid"] == 1]
        .groupby("job_id")["bid_amount"]
        .min()
        .rename("low_bid_amount")
    )

    result = result.merge(low_bid, on="job_id", how="left")
    result["gap_to_low"] = (
        result["bid_amount"] - result["low_bid_amount"]
    ) / result["low_bid_amount"]
    return result


def audit_panel(panel: pd.DataFrame, bidder_results: pd.DataFrame) -> dict:
    positive_rate = float(panel["did_bid"].mean())
    actual_counts = bidder_results.groupby("job_id")["competitor_unit_id"].nunique()
    positive_counts = panel.groupby("job_id")["did_bid"].sum()
    count_check = (
        pd.concat(
            [
                actual_counts.rename("actual_bidder_count"),
                positive_counts.rename("positive_rows_count"),
            ],
            axis=1,
        )
        .fillna(0)
        .astype(int)
    )
    count_mismatches = int(
        (count_check["actual_bidder_count"] != count_check["positive_rows_count"]).sum()
    )

    winner_counts = panel.groupby("job_id")["did_win"].sum()
    winner_without_bid_errors = panel[(panel["did_win"] == 1) & (panel["did_bid"] != 1)]

    return {
        "rows": int(len(panel)),
        "projects": int(panel["job_id"].nunique()),
        "competitors": int(panel["competitor_unit_id"].nunique()),
        "positive_rate": positive_rate,
        "average_candidates_per_project": float(panel.groupby("job_id").size().mean()),
        "missing_competitor_ids": int(panel["competitor_unit_id"].isna().sum()),
        "winner_without_bid_errors": int(len(winner_without_bid_errors)),
        "projects_with_multiple_winners": int((winner_counts > 1).sum()),
        "bidder_count_mismatched_projects": count_mismatches,
        "bidder_count_summary": panel.groupby("job_id")["did_bid"].sum().describe().to_dict(),
    }


def write_panel(panel: pd.DataFrame, output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        panel.to_parquet(output_path, index=False)
        return output_path
    except ImportError:
        fallback = output_path.with_suffix(".csv")
        panel.to_csv(fallback, index=False)
        print(
            "Parquet engine is not installed; wrote CSV fallback instead: "
            f"{fallback}"
        )
        return fallback


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build project x competitor operating-unit label panel."
    )
    parser.add_argument("--bids", default="data/processed/CSI_data_long_format.csv")
    parser.add_argument("--aliases", default="reference/competitor_aliases.csv")
    parser.add_argument("--entities", default="reference/competitor_entities.csv")
    parser.add_argument("--priority", default="reference/competitor_priority.csv")
    parser.add_argument("--panel-output", default="data/processed/project_competitor_panel.parquet")
    parser.add_argument("--projects-output", default="data/processed/projects.csv")
    parser.add_argument("--bidder-results-output", default="data/processed/bidder_results.csv")
    parser.add_argument("--audit-output", default="outputs/project_competitor_panel/panel_audit.json")
    parser.add_argument("--bidder-count-output", default="outputs/project_competitor_panel/bidder_count_check.csv")
    parser.add_argument("--duplicate-actual-output", default="outputs/project_competitor_panel/duplicate_actual_units.csv")
    args = parser.parse_args()

    long_bids = pd.read_csv(args.bids)
    aliases = pd.read_csv(args.aliases)
    entities = pd.read_csv(args.entities)
    priority = pd.read_csv(args.priority)

    projects = build_projects(long_bids)
    bidder_results, duplicate_actual_units = build_bidder_results(long_bids, aliases, projects)
    panel = build_project_competitor_panel(projects, bidder_results, priority, entities)
    panel = add_gap_to_low(panel)
    audit = audit_panel(panel, bidder_results)

    panel_written = write_panel(panel, Path(args.panel_output))

    Path(args.projects_output).parent.mkdir(parents=True, exist_ok=True)
    projects.to_csv(args.projects_output, index=False)
    bidder_results.to_csv(args.bidder_results_output, index=False)

    audit_path = Path(args.audit_output)
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    audit_path.write_text(json.dumps(audit, indent=2, default=str) + "\n")

    actual_counts = bidder_results.groupby("job_id")["competitor_unit_id"].nunique()
    positive_counts = panel.groupby("job_id")["did_bid"].sum()
    count_check = (
        pd.concat(
            [
                actual_counts.rename("actual_bidder_count"),
                positive_counts.rename("positive_rows_count"),
            ],
            axis=1,
        )
        .fillna(0)
        .astype(int)
        .reset_index()
    )
    count_check["counts_match"] = (
        count_check["actual_bidder_count"] == count_check["positive_rows_count"]
    )
    Path(args.bidder_count_output).parent.mkdir(parents=True, exist_ok=True)
    count_check.to_csv(args.bidder_count_output, index=False)
    duplicate_actual_units.to_csv(args.duplicate_actual_output, index=False)

    print("Project x competitor panel build complete")
    print(f"  panel output:          {panel_written}")
    print(f"  projects output:       {args.projects_output}")
    print(f"  bidder results output: {args.bidder_results_output}")
    print(f"  audit output:          {audit_path}")
    print(f"  rows:                  {audit['rows']}")
    print(f"  projects:              {audit['projects']}")
    print(f"  competitors:           {audit['competitors']}")
    print(f"  positive rate:         {audit['positive_rate']:.4f}")
    print(f"  avg candidates/project:{audit['average_candidates_per_project']:.2f}")
    print(f"  winner errors:         {audit['winner_without_bid_errors']}")
    print(f"  bidder count mismatches:{audit['bidder_count_mismatched_projects']}")


if __name__ == "__main__":
    main()
