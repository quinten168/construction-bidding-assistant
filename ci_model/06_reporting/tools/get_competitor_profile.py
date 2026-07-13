"""
Tool 2 — get_competitor_profile

Extracts a human-readable competitor profile from feature values already
present in a ranking_predictions.csv row. No external lookup needed.
"""
from __future__ import annotations

import re

import pandas as pd


def display_name(unit_id: str) -> str:
    """Convert TMP_DUININCK_INC_D5ADC005 → Duininck Inc. (fallback only)."""
    name = unit_id
    if name.startswith("TMP_"):
        name = name[4:]
    name = re.sub(r"_[0-9A-Fa-f]{8}$", "", name)
    return name.replace("_", " ").title()


def get_competitor_profile(row: pd.Series, name_lookup: dict[str, str] | None = None) -> dict:
    """
    Return a competitor profile dict drawn from feature values in the row.

    Args:
        row: a single row from ranking_predictions.csv

    Returns:
        {
            competitor_id, display_name,
            total_bids, overall_bid_rate,
            days_since_last_bid,
            recent_3m, recent_6m, recent_12m,
            same_state_bids, same_county_bids,
            same_type_bids,
        }
    """
    def _int(col: str) -> int:
        return int(float(row.get(col, 0) or 0))

    def _float(col: str) -> float:
        return float(row.get(col, 0.0) or 0.0)

    unit_id = str(row.get("competitor_unit_id", ""))
    canonical = (name_lookup or {}).get(unit_id) or display_name(unit_id)

    return {
        "competitor_id":    unit_id,
        "display_name":     canonical,
        "total_bids":       _int("prior_bid_count"),
        "overall_bid_rate": _float("prior_bid_rate"),
        "days_since_last_bid": _int("days_since_last_bid"),
        "recent_3m":        _int("recent_3m_bid_count"),
        "recent_6m":        _int("recent_6m_bid_count"),
        "recent_12m":       _int("recent_12m_bid_count"),
        "same_state_bids":  _int("same_state_prior_bid_count"),
        "same_county_bids": _int("same_county_prior_bid_count"),
        "same_type_bids":   _int("same_type_prior_bid_count"),
    }
