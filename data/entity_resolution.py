#!/usr/bin/env python3
"""Competitor entity resolution utilities.

Maps raw bidder names from historical bid records to stable competitor
operating-unit IDs. This is intentionally separate from model training.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


def apply_competitor_mapping(
    bids: pd.DataFrame,
    aliases: pd.DataFrame,
    bidder_col: str = "bidder_name",
) -> pd.DataFrame:
    required_bid_columns = {bidder_col}
    required_alias_columns = {
        "raw_bidder_name",
        "competitor_unit_id",
        "mapping_status",
    }

    missing_bid_columns = required_bid_columns - set(bids.columns)
    missing_alias_columns = required_alias_columns - set(aliases.columns)

    if missing_bid_columns:
        raise ValueError(
            f"Missing bid columns: {sorted(missing_bid_columns)}"
        )

    if missing_alias_columns:
        raise ValueError(
            f"Missing alias columns: {sorted(missing_alias_columns)}"
        )

    result = bids.copy()
    mapping = aliases.copy()

    result["_normalized_bidder_name"] = (
        result[bidder_col]
        .astype("string")
        .str.upper()
        .str.strip()
        .str.replace(r"\s+", " ", regex=True)
    )

    mapping["_normalized_bidder_name"] = (
        mapping["raw_bidder_name"]
        .astype("string")
        .str.upper()
        .str.strip()
        .str.replace(r"\s+", " ", regex=True)
    )

    mapping = mapping.drop_duplicates(
        subset=["_normalized_bidder_name"],
        keep=False,
    )

    result = result.merge(
        mapping[
            [
                "_normalized_bidder_name",
                "competitor_unit_id",
                "mapping_status",
            ]
        ],
        on="_normalized_bidder_name",
        how="left",
        validate="many_to_one",
    )

    result["mapping_status"] = result["mapping_status"].fillna("unmapped")

    return result.drop(columns="_normalized_bidder_name")


def find_duplicate_aliases(
    aliases: pd.DataFrame,
) -> pd.DataFrame:
    """Return raw alias names that appear more than once after normalization."""

    required_alias_columns = {
        "raw_bidder_name",
        "competitor_unit_id",
        "mapping_status",
    }
    missing_alias_columns = required_alias_columns - set(aliases.columns)
    if missing_alias_columns:
        raise ValueError(
            f"Missing alias columns: {sorted(missing_alias_columns)}"
        )

    mapping = aliases.copy()
    mapping["_normalized_bidder_name"] = (
        mapping["raw_bidder_name"]
        .astype("string")
        .str.upper()
        .str.strip()
        .str.replace(r"\s+", " ", regex=True)
    )

    duplicate_mask = mapping.duplicated(
        subset=["_normalized_bidder_name"],
        keep=False,
    )
    return (
        mapping.loc[
            duplicate_mask,
            [
                "raw_bidder_name",
                "_normalized_bidder_name",
                "competitor_unit_id",
                "mapping_status",
            ],
        ]
        .sort_values(["_normalized_bidder_name", "competitor_unit_id"])
        .reset_index(drop=True)
    )


def build_mapping_audit(
    mapped_bids: pd.DataFrame,
    bidder_col: str = "bidder_name",
) -> pd.DataFrame:
    required_columns = {
        bidder_col,
        "competitor_unit_id",
        "mapping_status",
    }
    missing_columns = required_columns - set(mapped_bids.columns)
    if missing_columns:
        raise ValueError(f"Missing mapped bid columns: {sorted(missing_columns)}")

    audit = (
        mapped_bids.groupby(
            [bidder_col, "competitor_unit_id", "mapping_status"],
            dropna=False,
        )
        .size()
        .reset_index(name="record_count")
        .rename(
            columns={
                bidder_col: "raw_bidder_name",
            }
        )
        .sort_values(
            ["mapping_status", "record_count", "raw_bidder_name"],
            ascending=[True, False, True],
        )
        .reset_index(drop=True)
    )

    return audit[
        [
            "raw_bidder_name",
            "competitor_unit_id",
            "record_count",
            "mapping_status",
        ]
    ]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Map raw bidder names to competitor operating-unit IDs."
    )
    parser.add_argument(
        "--bids",
        default="data/processed/CSI_data_long_format.csv",
        help="Path to historical long-format bid records.",
    )
    parser.add_argument(
        "--aliases",
        default="reference/competitor_aliases.csv",
        help="Path to competitor alias mapping table.",
    )
    parser.add_argument(
        "--bidder-col",
        default="BIDDER_NAME",
        help="Bidder-name column in the bids table.",
    )
    parser.add_argument(
        "--audit-output",
        default="outputs/entity_registry/competitor_mapping_audit.csv",
        help="Path for raw-name mapping audit output.",
    )
    parser.add_argument(
        "--duplicate-output",
        default="outputs/entity_registry/duplicate_aliases.csv",
        help="Path for duplicate alias audit output.",
    )
    args = parser.parse_args()

    bids = pd.read_csv(args.bids)
    aliases = pd.read_csv(args.aliases)

    mapped = apply_competitor_mapping(
        bids=bids,
        aliases=aliases,
        bidder_col=args.bidder_col,
    )
    audit = build_mapping_audit(mapped, bidder_col=args.bidder_col)
    duplicates = find_duplicate_aliases(aliases)

    audit_output = Path(args.audit_output)
    duplicate_output = Path(args.duplicate_output)
    audit_output.parent.mkdir(parents=True, exist_ok=True)
    duplicate_output.parent.mkdir(parents=True, exist_ok=True)

    audit.to_csv(audit_output, index=False)
    duplicates.to_csv(duplicate_output, index=False)

    total_records = len(mapped)
    mapped_records = int(mapped["competitor_unit_id"].notna().sum())
    unmapped_records = int((mapped["mapping_status"] == "unmapped").sum())

    print("Competitor mapping audit complete")
    print(f"  total records:   {total_records}")
    print(f"  mapped records:  {mapped_records}")
    print(f"  unmapped records:{unmapped_records}")
    print(f"  duplicate alias rows: {len(duplicates)}")
    print(f"  audit output:    {audit_output}")
    print(f"  duplicate output:{duplicate_output}")


if __name__ == "__main__":
    main()
