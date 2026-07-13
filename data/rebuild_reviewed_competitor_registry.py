#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import re
from pathlib import Path

import pandas as pd


def norm(value: object) -> str:
    return re.sub(r"\s+", " ", str(value).upper().strip())


class UnionFind:
    def __init__(self, values: list[str]) -> None:
        self.parent = {value: value for value in values}

    def find(self, value: str) -> str:
        self.parent.setdefault(value, value)
        if self.parent[value] != value:
            self.parent[value] = self.find(self.parent[value])
        return self.parent[value]

    def union(self, left: str, right: str) -> None:
        left_root, right_root = self.find(left), self.find(right)
        if left_root != right_root:
            self.parent[right_root] = left_root


def competitor_id(canonical_name: str) -> str:
    slug = re.sub(r"[^A-Z0-9]+", "_", norm(canonical_name)).strip("_")[:36]
    digest = hashlib.sha1(norm(canonical_name).encode("utf-8")).hexdigest()[:8].upper()
    return f"CMP_{slug}_{digest}"


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply reviewed competitor merge decisions.")
    parser.add_argument("--aliases", default="reference/competitor_aliases.csv")
    parser.add_argument("--entities", default="reference/competitor_entities.csv")
    parser.add_argument("--priority", default="reference/competitor_priority.csv")
    parser.add_argument(
        "--review",
        default="data/cleaning_review/fuzzy_merge_candidates_reviewed.csv",
    )
    parser.add_argument(
        "--final-list",
        default="data/cleaning_review/final_full_competitor_list.csv",
    )
    parser.add_argument("--audit-output", default="outputs/final_v3_pit/competitor_mapping_audit.csv")
    args = parser.parse_args()

    aliases = pd.read_csv(args.aliases).copy()
    old_entities = pd.read_csv(args.entities).copy()
    priority = pd.read_csv(args.priority).copy()
    review = pd.read_csv(args.review).copy()
    final_list = pd.read_csv(args.final_list).copy()
    final_name_map = {
        norm(value): str(value).strip()
        for value in final_list["standardized_company_name"].dropna()
    }

    aliases["_raw_key"] = aliases["raw_bidder_name"].map(norm)
    raw_keys = sorted(aliases["_raw_key"].dropna().unique())
    uf = UnionFind(raw_keys)

    merge_rows = review[review["decision"].astype(str).str.upper().eq("MERGE")].copy()
    canonical_votes: dict[str, list[str]] = {}
    for row in merge_rows.itertuples(index=False):
        left, right = norm(row.company_a), norm(row.company_b)
        uf.union(left, right)

    for row in merge_rows.itertuples(index=False):
        root = uf.find(norm(row.company_a))
        canonical_votes.setdefault(root, []).append(str(row.canonical_name).strip())

    members: dict[str, list[str]] = {}
    for key in raw_keys:
        members.setdefault(uf.find(key), []).append(key)

    raw_display = dict(zip(aliases["_raw_key"], aliases["raw_bidder_name"]))
    special_canonical = {
        "RECHNAGLE": "RECHNAGLE CONST MANAGEMENT",
        "NORTHERN IMPROV": "NORTHERN IMPROVEMENT COMPANY",
        "JAG CRUSHING": "JAG CRUSHING",
        "MARK SAND & GRAVEL CO.": "MARK SAND & GRAVEL COMPANY",
        "REEDE CONSTRUCTION": "REEDE CONSTRUCTION INC",
        "WAGNER COMPANY": "WAGNER CONSTRUCTION INC DBA WAGNER PLACE",
        "JOURNEY GROUP CONSTRUCTION": "JOURNEY GROUP COMPANIES",
        "CEDAR VALLEY CORP": "CEDAR VALLEY PAVING",
        "JR FERCHE": "JR FERCHE",
        "KNIFE RIVER": "KNIFE RIVER MINNESOTA",
    }
    excluded_artifacts = {"EST TOTAL", "ENG ESTIMATE", "EST VALUE"}

    canonical_by_root: dict[str, str] = {}
    for root, keys in members.items():
        final_matches = sorted(set(keys).intersection(final_name_map))
        if len(final_matches) == 1:
            canonical = final_name_map[final_matches[0]]
        elif len(final_matches) > 1:
            raise ValueError(f"Multiple final-list matches for component: {final_matches}")
        else:
            joined = " | ".join(sorted(keys))
            canonical = next(
                (value for token, value in special_canonical.items() if token in joined),
                "",
            )
            if not canonical and set(keys).issubset(excluded_artifacts):
                continue
            if not canonical:
                raise ValueError(f"No final-list mapping for component: {joined}")
        canonical_by_root[root] = canonical

    aliases["_root"] = aliases["_raw_key"].map(uf.find)
    aliases = aliases[aliases["_root"].isin(canonical_by_root)].copy()
    aliases["canonical_name"] = aliases["_root"].map(canonical_by_root)
    aliases["competitor_unit_id"] = aliases["canonical_name"].map(competitor_id)
    merged_raw_keys = {
        norm(value)
        for value in pd.concat([merge_rows["company_a"], merge_rows["company_b"]]).dropna()
    }
    aliases["mapping_status"] = aliases["_raw_key"].map(
        lambda key: "reviewed_merge" if key in merged_raw_keys else "reviewed_keep_separate"
    )
    aliases = aliases.drop_duplicates("_raw_key", keep="first")

    new_entities = (
        aliases[["competitor_unit_id", "canonical_name"]]
        .drop_duplicates()
        .rename(columns={"canonical_name": "standard_name"})
        .sort_values("standard_name")
        .reset_index(drop=True)
    )
    new_entities["parent_company"] = ""
    new_entities["operating_region"] = ""
    new_entities["contractor_type"] = ""
    new_entities["active_flag"] = 1
    new_entities["review_status"] = "reviewed_2026_06"

    old_to_new = aliases[["_raw_key", "competitor_unit_id"]].merge(
        pd.read_csv(args.aliases).assign(
            _raw_key=lambda frame: frame["raw_bidder_name"].map(norm)
        )[["_raw_key", "competitor_unit_id"]].rename(
            columns={"competitor_unit_id": "old_competitor_unit_id"}
        ),
        on="_raw_key",
        how="left",
    )
    priority_new = priority.merge(
        old_to_new[["old_competitor_unit_id", "competitor_unit_id"]].drop_duplicates(),
        left_on="competitor_unit_id",
        right_on="old_competitor_unit_id",
        how="left",
        suffixes=("_old", ""),
    )
    priority_new["competitor_unit_id"] = priority_new["competitor_unit_id"].fillna(
        priority_new["competitor_unit_id_old"]
    )
    priority_new = priority_new[priority.columns].drop_duplicates().reset_index(drop=True)

    audit = aliases[["raw_bidder_name", "competitor_unit_id", "canonical_name", "mapping_status"]].copy()
    audit["review_decision_source"] = "fuzzy_merge_candidates_reviewed.csv"

    aliases_out = aliases[
        ["raw_bidder_name", "competitor_unit_id", "valid_from", "valid_to", "mapping_status", "notes"]
    ].sort_values("raw_bidder_name")
    aliases_out.to_csv(args.aliases, index=False)
    new_entities.to_csv(args.entities, index=False)
    priority_new.to_csv(args.priority, index=False)
    audit_path = Path(args.audit_output)
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    audit.to_csv(audit_path, index=False)

    print("Reviewed competitor registry rebuilt")
    print(f"  raw aliases:       {len(aliases_out):,}")
    print(f"  reviewed merges:   {len(merge_rows):,}")
    print(f"  competitor units:  {len(new_entities):,}")
    print(f"  priority rows:      {len(priority_new):,}")
    print(f"  audit:              {audit_path}")


if __name__ == "__main__":
    main()
