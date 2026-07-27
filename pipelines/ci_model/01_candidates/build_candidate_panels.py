#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "shared"))

import argparse

import numpy as np
import pandas as pd

from build_training_panel import build_ranking_training_panel, build_training_audit_panel
from candidate_audit import (
    audit_candidate_rules,
    audit_candidate_rules_by_project_type,
    missed_reason_by_project_type,
    missed_actual_bidders,
)
from candidate_filter import (
    CANDIDATE_RULES,
    build_all_rule_candidate_sets,
    build_v3_candidate_set,
)
from config import CLIENT_UNIT_IDS, COMPETITOR_REGISTRY_PATH, DEFAULT_CANDIDATE_RULE, DISCOVERY_TIER, PRIORITY_TIER, TIER_COL
from io_utils import read_table, write_table


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build Model 1 rule candidates, audit panel, and ranking panel."
    )
    parser.add_argument("--projects", default="data/processed/projects.parquet")
    parser.add_argument("--bidder-results", default="data/processed/bidder_results.parquet")
    parser.add_argument("--registry", default=str(COMPETITOR_REGISTRY_PATH),
                        help="Path to competitor_name_registry - name_variants.csv")
    parser.add_argument(
        "--include-legacy-rules",
        action="store_true",
        help="Also build the 15 legacy comparison pools. Default output is V3 only.",
    )
    parser.add_argument("--near-low-threshold", type=float, default=0.05)
    parser.add_argument(
        "--rule-candidates-output",
        default="data/processed/model1/rule_candidate_set.parquet",
    )
    parser.add_argument(
        "--audit-panel-output",
        default="data/processed/model1/training_audit_panel.parquet",
    )
    parser.add_argument(
        "--ranking-panel-output",
        default="data/processed/model1/ranking_training_panel.parquet",
    )
    _STEP_OUT = Path(__file__).resolve().parent / "outputs"
    parser.add_argument(
        "--candidate-audit-output",
        default=str(_STEP_OUT / "candidate_filter_audit.csv"),
    )
    parser.add_argument(
        "--candidate-audit-by-project-type-output",
        default=str(_STEP_OUT / "candidate_filter_audit_by_project_type.csv"),
    )
    parser.add_argument(
        "--missed-bidders-output",
        default=str(_STEP_OUT / "missed_actual_bidders.csv"),
    )
    parser.add_argument(
        "--missed-reason-summary-output",
        default=str(_STEP_OUT / "missed_actual_bidders_reason_summary.csv"),
    )
    parser.add_argument(
        "--missed-reason-by-project-type-output",
        default=str(_STEP_OUT / "missed_actual_bidders_reason_by_project_type.csv"),
    )
    args = parser.parse_args()

    projects = read_table(args.projects)
    bidder_results = read_table(args.bidder_results)
    registry = pd.read_csv(args.registry, dtype=str)
    # Propagate Top Competitors Tag across all raw_name_variants sharing the same comp_name.
    # If any variant of a company has tag=1, all variants get tag=1.
    priority_comp_names = set(
        registry.loc[registry["Top Competitors Tag"] == "1", "comp_name"].dropna().str.strip()
    )
    registry.loc[registry["comp_name"].isin(priority_comp_names), "Top Competitors Tag"] = "1"

    # Resolve priority competitor_unit_ids via raw_name_variant → raw_bidder_name mapping
    top_raw_variants = set(
        registry[registry["Top Competitors Tag"] == "1"]["raw_name_variant"]
        .dropna().str.upper()
    )
    priority = (
        bidder_results[bidder_results["raw_bidder_name"].str.upper().isin(top_raw_variants)]
        [["competitor_unit_id"]]
        .drop_duplicates()
    ) if "raw_bidder_name" in bidder_results.columns else pd.DataFrame(columns=["competitor_unit_id"])

    # No entity-active-date registry is maintained; entities=None skips that filter.
    v3_candidates = build_v3_candidate_set(
        projects=projects,
        bidder_results=bidder_results,
        priority_competitors=priority,
        entities=None,
    )
    if args.include_legacy_rules:
        legacy_candidates = build_all_rule_candidate_sets(
            projects=projects,
            bidder_results=bidder_results,
            priority_competitors=priority,
            entities=None,
        )
        rule_candidate_set = pd.concat(
            [v3_candidates, legacy_candidates], ignore_index=True, sort=False
        )
        rule_versions = [DEFAULT_CANDIDATE_RULE, *[rule.name for rule in CANDIDATE_RULES]]
    else:
        rule_candidate_set = v3_candidates
        rule_versions = [DEFAULT_CANDIDATE_RULE]

    # Remove client company — the tool is used BY them, so they are never a competitor.
    before = len(rule_candidate_set)
    rule_candidate_set = rule_candidate_set[
        ~rule_candidate_set["competitor_unit_id"].isin(CLIENT_UNIT_IDS)
    ]
    if before > len(rule_candidate_set):
        print(f"  Removed {before - len(rule_candidate_set):,} client rows "
              f"({CLIENT_UNIT_IDS}) from candidate set.")

    rule_candidate_set[TIER_COL] = np.where(
        rule_candidate_set["source_priority"], PRIORITY_TIER, DISCOVERY_TIER
    )
    training_audit_panel = build_training_audit_panel(
        rule_candidate_set=rule_candidate_set,
        projects=projects,
        bidder_results=bidder_results,
        near_low_threshold=args.near_low_threshold,
        rule_versions=rule_versions,
    )
    ranking_training_panel = build_ranking_training_panel(training_audit_panel)
    candidate_audit = audit_candidate_rules(training_audit_panel)
    candidate_audit_by_project_type = audit_candidate_rules_by_project_type(
        training_audit_panel
    )
    missed = missed_actual_bidders(training_audit_panel, projects, bidder_results)
    missed_reason_summary = (
        missed.groupby(["candidate_rule_version", "miss_reason"], dropna=False)
        .size()
        .reset_index(name="missed_actual_bidders")
        .sort_values(
            ["candidate_rule_version", "missed_actual_bidders"],
            ascending=[True, False],
        )
    )
    missed_reason_type_summary = missed_reason_by_project_type(missed)

    written_rule = write_table(rule_candidate_set, args.rule_candidates_output)
    written_audit = write_table(training_audit_panel, args.audit_panel_output)
    written_ranking = write_table(ranking_training_panel, args.ranking_panel_output)

    Path(args.candidate_audit_output).parent.mkdir(parents=True, exist_ok=True)
    candidate_audit.to_csv(args.candidate_audit_output, index=False)
    candidate_audit_by_project_type.to_csv(
        args.candidate_audit_by_project_type_output,
        index=False,
    )
    missed.to_csv(args.missed_bidders_output, index=False)
    missed_reason_summary.to_csv(args.missed_reason_summary_output, index=False)
    missed_reason_type_summary.to_csv(
        args.missed_reason_by_project_type_output,
        index=False,
    )

    print("Model 1 candidate panels complete")
    print(f"  rule candidates:       {written_rule} ({len(rule_candidate_set):,} rows)")
    print(f"  training audit panel:  {written_audit} ({len(training_audit_panel):,} rows)")
    print(f"  ranking training panel:{written_ranking} ({len(ranking_training_panel):,} rows)")
    print(f"  candidate audit:       {args.candidate_audit_output}")
    print(f"  audit by project type: {args.candidate_audit_by_project_type_output}")
    print(f"  missed bidders:        {args.missed_bidders_output}")
    print(f"  miss reason summary:   {args.missed_reason_summary_output}")
    print(f"  miss reason by type:   {args.missed_reason_by_project_type_output}")
    print()
    print(candidate_audit.to_string(index=False))


if __name__ == "__main__":
    main()
