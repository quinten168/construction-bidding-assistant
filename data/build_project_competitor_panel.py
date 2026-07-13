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

PROJECT_TYPE_FEATURE_COLUMNS = [
    "rule_based_primary_project_type_v1",
    "project_type_source",
    "project_type_rule",
    "matched_keywords",
    "has_paving",
    "has_grading",
    "has_base",
    "has_utility",
    "has_structure",
    "has_drainage",
    "has_reclamation",
    "has_trail",
    "is_reconstruction",
    "is_structure_replacement",
    "has_mix",
    "has_grade_quantity",
]


def _has_any(text: str, patterns: list[str]) -> bool:
    return any(re.search(pattern, text) for pattern in patterns)


def _matched_terms(text: str, patterns: list[tuple[str, str]]) -> list[str]:
    return [label for label, pattern in patterns if re.search(pattern, text)]


def _project_type_from_name(
    project_name: object,
    mix_tons: object,
    grading_yards: object,
    base_tons: object = 0,
    shldr_tons: object = 0,
    mill_sy: object = 0,
    crush_tons: object = 0,
    stock_tons: object = 0,
) -> dict[str, object]:
    """Assign CSI archetype project-type features — quantity-driven primary type plus keyword flags."""

    text = "" if pd.isna(project_name) else str(project_name).upper()
    text = re.sub(r"\s+", " ", text)

    def _qty(v: object) -> float:
        val = pd.to_numeric(pd.Series([v]), errors="coerce").iloc[0]
        return float(val) if pd.notna(val) else 0.0

    mix_value     = _qty(mix_tons)
    grading_value = _qty(grading_yards)
    base_value    = _qty(base_tons)
    shldr_value   = _qty(shldr_tons)
    mill_value    = _qty(mill_sy)
    crush_value   = _qty(crush_tons)
    stock_value   = _qty(stock_tons)

    # Quantity signals — primary drivers of archetype classification
    has_mix      = mix_value > 0
    has_grade_qty = grading_value > 0
    has_mill_qty  = mill_value > 0
    has_agg_qty   = base_value > 0 or shldr_value > 0 or crush_value > 0 or stock_value > 0

    # Keyword signals — fallback when quantities are missing
    has_mill_kw = bool(re.search(r"\bMILL(?:ING)?\b", text))
    has_agg_kw  = bool(re.search(
        r"\bBASE COURSE\b|\bSHLDR\b|\bSHOULDER\b|\bAGGREGATE\b|\bAGG\b|\bGRAVEL\b|\bCRUSH\b|\bSTOCKPILE\b",
        text,
    ))

    has_mill      = has_mill_qty or has_mill_kw
    has_base_shldr = has_agg_qty or has_agg_kw

    # Boolean scope flags — independent model features; use keyword OR quantity for maximum recall
    has_paving = has_mix or bool(re.search(
        r"\bASPHALT\b|\bBITUMINOUS\b|\bHMA\b|\bPAV(?:E|ING|EMENT)\b|\bSURFAC(?:E|ING)\b|\bOVERLAY\b|\bRESURFAC(?:E|ING)\b",
        text,
    ))
    has_grading = has_grade_qty or bool(re.search(r"\bGRADING\b|\bGRADE\b|\bEARTHWORK\b|\bEXCAVATION\b", text))
    # BASE is present as a component across all 5 archetypes in varying amounts;
    # quantity-driven (BASE TN / SHLDR TN) with keyword fallback
    has_base = (base_value > 0 or shldr_value > 0) or bool(re.search(
        r"\bBASE COURSE\b|\bSHLDR\b|\bSHOULDER\b|\bBASE\b", text,
    ))
    has_utility = bool(re.search(r"\bUTILITY\b|\bUTILITIES\b|\bUTIL\b|\bWATER\b|\bSEWER\b|\bSANITARY\b", text))
    has_structure = bool(re.search(r"\bSTRUCTURE\b|\bAPPROACH SLAB\b|\bSTRUCTURAL\b|\bBRIDGE\b|\bBOX CULVERT\b|\bRCBC\b", text))
    has_drainage = bool(re.search(r"\bPIPE\b|\bDRAINAGE\b|\bDRAINTILE\b|\bSTORMWATER\b|\bSTORM SEWER\b|\bCULVERT\b", text))
    has_trail = bool(re.search(r"\bTRAIL\b|\bSIDEWALK\b|\bSHARED USE\b|\bSHARED USED\b|\bPATH\b|\bBIKE\b|\bPEDESTRIAN\b", text))
    has_reclamation = bool(re.search(r"\bRECLAIM|\bRECLAMATION\b|\bFDR\b|\bCIR\b|COLD IN-PLACE", text))
    is_reconstruction = bool(re.search(r"\bRECONSTRUCT|\bRECONSTRUCTION\b|\bRECONST\b", text))
    is_structure_replacement = has_structure and bool(re.search(r"\bREPLACE\b|\bREPLACEMENT\b|REMOVE AND REPLACE|\bNEW BRIDGE\b", text))

    # CSI archetype primary type — mix-share-driven paving gate, then quantity waterfall
    MIX_SHARE_MIN = 0.15   # mix >= 15% of total tonnage -> paving job
    MIX_ABS_MIN = 1000.0   # or >= 1,000 tons of mix -> paving even if its share is low
    GRADE_CY_MIN = 500.0
    MILL_SY_MIN = 1000.0

    total_tons = mix_value + base_value + shldr_value + crush_value + stock_value
    mix_share = (mix_value / total_tons) if total_tons > 0 else 0.0
    is_paving = (mix_share >= MIX_SHARE_MIN) or (mix_value >= MIX_ABS_MIN)

    if is_paving:
        if grading_value >= GRADE_CY_MIN:
            primary_type = "reconstruct_rebuild"     # paving + regrade >= 500 CY: full roadway rebuild
            rule = "paving_grade_cy_ge_500"
        elif mill_value >= MILL_SY_MIN:
            primary_type = "mill_overlay"            # paving, grade < 500 CY, mill >= 1,000 SY
            rule = "paving_grade_cy_lt_500_mill_sy_ge_1000"
        else:
            primary_type = "hma_resurface"           # paving, grade < 500 CY, mill < 1,000 SY
            rule = "paving_grade_cy_lt_500_mill_sy_lt_1000"
    else:
        if grading_value >= GRADE_CY_MIN:
            primary_type = "grading_earthwork"       # no paving, grade >= 500 CY
            rule = "not_paving_grade_cy_ge_500"
        elif base_value > 0 or shldr_value > 0:
            primary_type = "aggregate_base_gravel"   # no paving, base or shoulder tonnage present
            rule = "not_paving_base_or_shldr_gt_0"
        else:
            primary_type = "other"                   # utility, structure, trail, etc.
            rule = "not_paving_no_grade_no_base"

    matched = []
    if has_mill: matched.append("mill")
    if has_base_shldr: matched.append("base_shldr")
    if has_paving: matched.append("paving")
    if has_grading: matched.append("grading")
    if has_utility: matched.append("utility")
    if has_structure: matched.append("structure")
    if has_drainage: matched.append("drainage")
    if has_trail: matched.append("trail")
    if has_reclamation: matched.append("reclamation")
    if is_reconstruction: matched.append("reconstruction")

    return {
        "rule_based_primary_project_type_v1": primary_type,
        "project_type": primary_type,
        "project_type_source": "csi_archetype_v3_mix_share_driven",
        "project_type_rule": rule,
        "matched_keywords": "|".join(matched),
        "has_paving": int(has_paving),
        "has_grading": int(has_grading),
        "has_base": int(has_base),
        "has_utility": int(has_utility),
        "has_structure": int(has_structure),
        "has_drainage": int(has_drainage),
        "has_reclamation": int(has_reclamation),
        "has_trail": int(has_trail),
        "is_reconstruction": int(is_reconstruction),
        "is_structure_replacement": int(is_structure_replacement),
        "has_mix": int(has_mix),
        "has_grade_quantity": int(has_grade_qty),
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
        "Latitude",
        "Longitude",
        "MIX TN",
        "GRADE CY",
        "BASE TN",
        "SHLDR TN",
        "MILL SY",
        "CRUSH TN",
        "STOCK TN",
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
            project_latitude=("Latitude", "first"),
            project_longitude=("Longitude", "first"),
            mix_tons=("MIX TN", "first"),
            grading_yards=("GRADE CY", "first"),
            base_tons=("BASE TN", "first"),
            shldr_tons=("SHLDR TN", "first"),
            mill_sy=("MILL SY", "first"),
            crush_tons=("CRUSH TN", "first"),
            stock_tons=("STOCK TN", "first"),
            estimated_value=("BID_AMOUNT", "min"),
        )
        .reset_index()
        .sort_values(["bid_date", "_project_identity"])
        .reset_index(drop=True)
    )
    projects.insert(0, "job_id", [f"P{i:06d}" for i in range(1, len(projects) + 1)])
    type_features = pd.DataFrame(
        [
            _project_type_from_name(
                row.get("project_name"),
                row.get("mix_tons"),
                row.get("grading_yards"),
                row.get("base_tons", 0),
                row.get("shldr_tons", 0),
                row.get("mill_sy", 0),
                row.get("crush_tons", 0),
                row.get("stock_tons", 0),
            )
            for _, row in projects.iterrows()
        ],
        index=projects.index,
    )
    projects = pd.concat([projects, type_features], axis=1)
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
                    **{
                        col: project.get(col)
                        for col in PROJECT_TYPE_FEATURE_COLUMNS
                        if col in projects.columns
                    },
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


def build_project_type_audit(projects: pd.DataFrame) -> pd.DataFrame:
    cols = [
        "job_id",
        "bid_date",
        "state",
        "county",
        "project_name",
        "project_type",
        "rule_based_primary_project_type_v1",
        "mix_tons",
        "grading_yards",
        "has_mix",
        "has_grade_quantity",
        "has_paving",
        "has_grading",
        "has_utility",
        "has_structure",
        "has_drainage",
        "has_reclamation",
        "has_trail",
        "is_reconstruction",
        "is_structure_replacement",
        "matched_keywords",
        "project_type_rule",
    ]
    available = [col for col in cols if col in projects.columns]
    return projects[available].sort_values(["project_type", "bid_date", "job_id"])


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
    parser.add_argument("--project-type-audit-output", default="outputs/project_competitor_panel/project_type_audit.csv")
    parser.add_argument("--bidder-count-output", default="outputs/project_competitor_panel/bidder_count_check.csv")
    parser.add_argument("--duplicate-actual-output", default="outputs/project_competitor_panel/duplicate_actual_units.csv")
    args = parser.parse_args()

    long_bids = pd.read_csv(args.bids)
    aliases = pd.read_csv(args.aliases)
    entities = pd.read_csv(args.entities)
    priority = pd.read_csv(args.priority)

    projects = build_projects(long_bids)
    bidder_results, duplicate_actual_units = build_bidder_results(long_bids, aliases, projects)

    # Add canonical_name via competitor name registry
    _registry_path = Path(
        "ci_model/model_1_wenyu/01_candidates/outputs/competitor_name_registry - name_variants.csv"
    )
    if _registry_path.exists():
        registry = pd.read_csv(_registry_path)
        registry["_key"] = registry["raw_name_variant"].str.upper().str.strip()
        bidder_results["_key"] = bidder_results["raw_bidder_name"].str.upper().str.strip()
        bidder_results = bidder_results.merge(
            registry[["_key", "comp_name"]].drop_duplicates("_key"),
            on="_key", how="left"
        ).rename(columns={"comp_name": "canonical_name"}).drop(columns="_key")
        bidder_results["canonical_name"] = bidder_results["canonical_name"].fillna(
            bidder_results["raw_bidder_name"]
        )
    else:
        bidder_results["canonical_name"] = bidder_results["raw_bidder_name"]
    panel = build_project_competitor_panel(projects, bidder_results, priority, entities)
    panel = add_gap_to_low(panel)
    audit = audit_panel(panel, bidder_results)
    project_type_audit = build_project_type_audit(projects)

    panel_written = write_panel(panel, Path(args.panel_output))

    Path(args.projects_output).parent.mkdir(parents=True, exist_ok=True)
    projects.to_csv(args.projects_output, index=False)
    bidder_results.to_csv(args.bidder_results_output, index=False)
    Path(args.project_type_audit_output).parent.mkdir(parents=True, exist_ok=True)
    project_type_audit.to_csv(args.project_type_audit_output, index=False)

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
    print(f"  project type audit:    {args.project_type_audit_output}")
    print(f"  rows:                  {audit['rows']}")
    print(f"  projects:              {audit['projects']}")
    print(f"  competitors:           {audit['competitors']}")
    print(f"  positive rate:         {audit['positive_rate']:.4f}")
    print(f"  avg candidates/project:{audit['average_candidates_per_project']:.2f}")
    print(f"  winner errors:         {audit['winner_without_bid_errors']}")
    print(f"  bidder count mismatches:{audit['bidder_count_mismatched_projects']}")


if __name__ == "__main__":
    main()
