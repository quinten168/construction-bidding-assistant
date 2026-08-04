#!/usr/bin/env python3
"""
First-principles single-factor rule scorers.

Each function computes a score for every (project_natural_key, competitor_unit_id) pair in a
full-universe candidate panel (all 700+ known competitors, no pre-filtering).
Higher score = better competitor for that project. All computations use only
information available strictly before the project's bid_date (as-of safe).
"""
from __future__ import annotations

import re

import numpy as np
import pandas as pd

EARTH_RADIUS_MILES = 3958.7613
MATERIAL_COLUMNS = [
    "mix_tons",
    "grading_yards",
    "base_tons",
    "shldr_tons",
    "mill_sy",
    "crush_tons",
    "stock_tons",
]
MIN_MATERIAL_HISTORY = 3  # a material column only counts if the company has >=3 prior bids with qty > 0


def _normalize_key(value: object) -> str:
    if pd.isna(value):
        return ""
    text = str(value).upper()
    text = re.sub(r"\b(COUNTY|CNTY|CTY|CO)\b", "", text)
    text = text.replace("&", " AND ")
    text = re.sub(r"[^A-Z0-9]+", "", text)
    return text


def _haversine_miles(lat1: float, lon1: float, lat2: pd.Series, lon2: pd.Series) -> pd.Series:
    lat1_rad = np.radians(lat1)
    lon1_rad = np.radians(lon1)
    lat2_rad = np.radians(pd.to_numeric(lat2, errors="coerce"))
    lon2_rad = np.radians(pd.to_numeric(lon2, errors="coerce"))
    dlat = lat2_rad - lat1_rad
    dlon = lon2_rad - lon1_rad
    a = np.sin(dlat / 2.0) ** 2 + np.cos(lat1_rad) * np.cos(lat2_rad) * np.sin(dlon / 2.0) ** 2
    return 2 * EARTH_RADIUS_MILES * np.arcsin(np.sqrt(a))


def build_company_pit_locations(pit_list: pd.DataFrame, bidder_results: pd.DataFrame) -> dict[str, tuple[float, float, float]]:
    """Map competitor_unit_id -> (lat, lon, unused) for the nearest of their owned pits.

    Only ~21 companies in the MN pit list own a pit (access_type == 'competitor').
    Companies without an owned pit are absent from the returned dict, and callers
    should treat them as having no computable distance (rank last).
    """
    owned = pit_list[pit_list["access_type"] == "competitor"].copy()
    owned["Latitude"] = pd.to_numeric(owned["Latitude"], errors="coerce")
    owned["Longitude"] = pd.to_numeric(owned["Longitude"], errors="coerce")
    owned = owned.dropna(subset=["Latitude", "Longitude"])

    name_map: dict[str, str] = {}
    for _, row in bidder_results.drop_duplicates("raw_bidder_name").iterrows():
        unit_id = row.get("competitor_unit_id")
        if pd.isna(unit_id):
            continue
        key = _normalize_key(row["raw_bidder_name"])
        if key and key not in name_map:
            name_map[key] = str(unit_id)

    owned["competitor_unit_id"] = owned["access_company"].map(_normalize_key).map(name_map)
    owned = owned.dropna(subset=["competitor_unit_id"])

    locations: dict[str, list[tuple[float, float]]] = {}
    for _, row in owned.iterrows():
        locations.setdefault(row["competitor_unit_id"], []).append((row["Latitude"], row["Longitude"]))
    return locations


def score_distance_rule(
    candidates: pd.DataFrame,
    project_lat: float,
    project_lon: float,
    project_state: str,
    company_pit_locations: dict[str, list[tuple[float, float]]],
) -> pd.Series:
    """Pure distance rule: closer to the project's nearest self-owned pit = higher score.

    Only computable for MN projects (pit data is MN-only) and for the ~21 companies
    that own an MN pit. Everyone else gets a large default distance (score = -9999),
    so they effectively rank last, tied.
    """
    if project_state != "MN" or pd.isna(project_lat) or pd.isna(project_lon):
        return pd.Series(-9999.0, index=candidates.index)

    distances = []
    for unit_id in candidates["competitor_unit_id"]:
        pits = company_pit_locations.get(str(unit_id))
        if not pits:
            distances.append(9999.0)
            continue
        lats = pd.Series([p[0] for p in pits])
        lons = pd.Series([p[1] for p in pits])
        distances.append(float(_haversine_miles(project_lat, project_lon, lats, lons).min()))
    return -pd.Series(distances, index=candidates.index)


def score_capacity_size_fit(
    candidates: pd.DataFrame,
    project_row: pd.Series,
    prior_bids: pd.DataFrame,
) -> pd.Series:
    """Capacity rule (variant A): project-material-scale fit.

    Only compares materials the project actually requires (qty > 0) against each
    company's historical average on that same material. A company is not penalized
    for having unrelated historical capability the current project doesn't need --
    an earlier version compared against every material column unconditionally
    (treating "not needed here" as a target of zero), which systematically
    penalized larger/more diversified companies and made the rule anti-correlated
    with actual winners. Restricting to project-relevant materials only fixed that.

    For each project-relevant material with >= MIN_MATERIAL_HISTORY prior bids
    (qty > 0) for a given company, compare log1p(project_qty) to log1p(company's
    average historical qty on that material). Score = -mean(|gap|) across
    qualifying materials (higher is a better size fit). Companies with no
    qualifying material fall back to the cohort-wide mean size_fit_score computed
    over companies that do qualify; projects with no material quantities at all
    fall back to a neutral 0.0 for every candidate.
    """
    needed_cols = [
        col for col in MATERIAL_COLUMNS
        if pd.notna(project_row.get(col)) and float(project_row.get(col)) > 0
    ]
    if not needed_cols:
        return pd.Series(0.0, index=candidates.index)

    project_log_qty = {col: np.log1p(float(project_row[col])) for col in needed_cols}

    company_scores: dict[str, float] = {}
    for unit_id, frame in prior_bids.groupby("competitor_unit_id"):
        gaps = []
        for col in needed_cols:
            qty = pd.to_numeric(frame[col], errors="coerce").fillna(0)
            qty = qty[qty > 0]
            if len(qty) < MIN_MATERIAL_HISTORY:
                continue
            company_avg_log = np.log1p(qty.mean())
            gaps.append(abs(project_log_qty[col] - company_avg_log))
        if gaps:
            company_scores[str(unit_id)] = -float(np.mean(gaps))

    fallback = float(np.mean(list(company_scores.values()))) if company_scores else 0.0
    return candidates["competitor_unit_id"].astype(str).map(company_scores).fillna(fallback)


def score_capacity_volume(candidates: pd.DataFrame, prior_bids: pd.DataFrame) -> pd.Series:
    """Capacity rule (variant B): raw historical scale, no project-fit involved.

    Score = log1p(total historical bid dollar volume) as of bid_date. Pure "how big
    is this company's book of business", independent of the current project.
    """
    volume = (
        prior_bids.assign(bid_amount=pd.to_numeric(prior_bids["bid_amount"], errors="coerce").fillna(0))
        .groupby("competitor_unit_id")["bid_amount"]
        .sum()
    )
    volume_log = np.log1p(volume.clip(lower=0))
    return candidates["competitor_unit_id"].astype(str).map(volume_log).fillna(0.0)


def restrict_and_score_historical_winrate(
    candidates: pd.DataFrame,
    project_row: pd.Series,
    prior_bids: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.Series]:
    """Historical win-rate rule, restricted to same-state candidates only.

    Candidate pool is first cut down to companies with >=1 prior bid in the
    project's state (no cross-state selection). Score = win rate for the
    project's project_type within that state; falls back to the company's
    overall same-state win rate if it has no history for that specific type.
    """
    state = project_row.get("state")
    project_type = project_row.get("project_type")

    same_state = prior_bids[prior_bids["state"] == state]
    eligible_ids = set(same_state["competitor_unit_id"].astype(str))
    restricted = candidates[candidates["competitor_unit_id"].astype(str).isin(eligible_ids)].copy()
    if restricted.empty:
        return restricted, pd.Series(dtype=float)

    same_type = same_state[same_state["project_type"] == project_type]
    type_bids = same_type.groupby("competitor_unit_id").size()
    type_wins = same_type.groupby("competitor_unit_id")["did_win"].sum()
    type_rate = (type_wins / type_bids).replace([np.inf, -np.inf], np.nan)

    state_bids = same_state.groupby("competitor_unit_id").size()
    state_wins = same_state.groupby("competitor_unit_id")["did_win"].sum()
    state_rate = (state_wins / state_bids).replace([np.inf, -np.inf], np.nan)

    ids = restricted["competitor_unit_id"].astype(str)
    scores = ids.map(type_rate)
    scores = scores.fillna(ids.map(state_rate)).fillna(0.0)
    scores.index = restricted.index
    return restricted, scores
