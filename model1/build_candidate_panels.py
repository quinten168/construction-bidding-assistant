#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from build_training_panel import build_ranking_training_panel, build_training_audit_panel
from candidate_audit import audit_candidate_rules, missed_actual_bidders
from candidate_filter import CANDIDATE_RULES, build_all_rule_candidate_sets
from io_utils import read_table, write_table


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build Model 1 rule candidates, audit panel, and ranking panel."
    )
    parser.add_argument("--projects", default="data/processed/projects.csv")
    parser.add_argument("--bidder-results", default="data/processed/bidder_results.csv")
    parser.add_argument("--priority", default="reference/competitor_priority.csv")
    parser.add_argument("--entities", default="reference/competitor_entities.csv")
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
    parser.add_argument(
        "--candidate-audit-output",
        default="outputs/model1/candidate_filter_audit.csv",
    )
    parser.add_argument(
        "--missed-bidders-output",
        default="outputs/model1/missed_actual_bidders.csv",
    )
    parser.add_argument(
        "--missed-reason-summary-output",
        default="outputs/model1/missed_actual_bidders_reason_summary.csv",
    )
    args = parser.parse_args()

    projects = pd.read_csv(args.projects)
    bidder_results = pd.read_csv(args.bidder_results)
    priority = pd.read_csv(args.priority)
    entities = pd.read_csv(args.entities)

    rule_candidate_set = build_all_rule_candidate_sets(
        projects=projects,
        bidder_results=bidder_results,
        priority_competitors=priority,
        entities=entities,
    )
    training_audit_panel = build_training_audit_panel(
        rule_candidate_set=rule_candidate_set,
        projects=projects,
        bidder_results=bidder_results,
        near_low_threshold=args.near_low_threshold,
        rule_versions=[rule.name for rule in CANDIDATE_RULES],
    )
    ranking_training_panel = build_ranking_training_panel(training_audit_panel)
    candidate_audit = audit_candidate_rules(training_audit_panel)
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

    written_rule = write_table(rule_candidate_set, args.rule_candidates_output)
    written_audit = write_table(training_audit_panel, args.audit_panel_output)
    written_ranking = write_table(ranking_training_panel, args.ranking_panel_output)

    Path(args.candidate_audit_output).parent.mkdir(parents=True, exist_ok=True)
    candidate_audit.to_csv(args.candidate_audit_output, index=False)
    missed.to_csv(args.missed_bidders_output, index=False)
    missed_reason_summary.to_csv(args.missed_reason_summary_output, index=False)

    print("Model 1 candidate panels complete")
    print(f"  rule candidates:       {written_rule} ({len(rule_candidate_set):,} rows)")
    print(f"  training audit panel:  {written_audit} ({len(training_audit_panel):,} rows)")
    print(f"  ranking training panel:{written_ranking} ({len(ranking_training_panel):,} rows)")
    print(f"  candidate audit:       {args.candidate_audit_output}")
    print(f"  missed bidders:        {args.missed_bidders_output}")
    print(f"  miss reason summary:   {args.missed_reason_summary_output}")
    print()
    print(candidate_audit.to_string(index=False))


if __name__ == "__main__":
    main()
