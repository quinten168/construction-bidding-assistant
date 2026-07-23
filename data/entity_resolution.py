#!/usr/bin/env python3
"""Competitor entity resolution utilities.

Maps raw bidder names from historical bid records to stable competitor
operating-unit IDs. This is intentionally separate from model training.
"""

from __future__ import annotations

import pandas as pd


def apply_registry_mapping(
    bids: pd.DataFrame,
    registry: pd.DataFrame,
    bidder_col: str = "bidder_name",
) -> pd.DataFrame:
    """Map raw bidder names to competitor_unit_id using the competitor name
    registry as the single source of truth for identity: competitor_unit_id
    *is* the registry's comp_name, not a separately-assigned ID.

    Rows whose raw name isn't in the registry yet ("unmapped"), or is present
    but still awaiting a comp_name ("needs_review"), fall back to the
    normalized raw name itself so nothing is dropped — they just aren't
    merged with any other variant until the registry is updated.
    """
    required_bid_columns = {bidder_col}
    required_registry_columns = {"raw_name_variant", "comp_name"}

    missing_bid_columns = required_bid_columns - set(bids.columns)
    missing_registry_columns = required_registry_columns - set(registry.columns)

    if missing_bid_columns:
        raise ValueError(f"Missing bid columns: {sorted(missing_bid_columns)}")

    if missing_registry_columns:
        raise ValueError(f"Missing registry columns: {sorted(missing_registry_columns)}")

    def _norm(series: pd.Series) -> pd.Series:
        return (
            series.astype("string")
            .str.upper()
            .str.strip()
            .str.replace(r"\s+", " ", regex=True)
        )

    result = bids.copy()
    result["_normalized_bidder_name"] = _norm(result[bidder_col])

    lookup = registry.copy()
    lookup["_normalized_bidder_name"] = _norm(lookup["raw_name_variant"])
    lookup["comp_name"] = lookup["comp_name"].astype("string").str.strip()
    lookup = lookup.dropna(subset=["_normalized_bidder_name"])
    lookup = lookup.drop_duplicates(subset=["_normalized_bidder_name"], keep="first")

    result = result.merge(
        lookup[["_normalized_bidder_name", "comp_name"]],
        on="_normalized_bidder_name",
        how="left",
        validate="many_to_one",
    )

    in_registry = result["_normalized_bidder_name"].isin(
        lookup["_normalized_bidder_name"]
    )
    resolved = result["comp_name"].notna() & (result["comp_name"] != "")

    result["mapping_status"] = "unmapped"
    result.loc[in_registry, "mapping_status"] = "needs_review"
    result.loc[resolved, "mapping_status"] = "registry_mapped"

    result["competitor_unit_id"] = result["comp_name"].where(
        resolved, result["_normalized_bidder_name"]
    )

    return result.drop(columns=["_normalized_bidder_name", "comp_name"])
