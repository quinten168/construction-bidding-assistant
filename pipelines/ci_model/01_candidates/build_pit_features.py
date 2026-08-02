#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "shared"))

import numpy as np
import pandas as pd

from io_utils import read_table, write_table
from config import DEFAULT_CANDIDATE_RULE


EARTH_RADIUS_MILES = 3958.7613


PIT_FEATURE_COLUMNS = [
    "project_location_source",
    "project_location_confidence",
    "project_location_missing",
    "project_location_pit_county_centroid",
    # Open pits — marginal bands (non-cumulative) to avoid multicollinearity
    "nearest_open_pit_miles",
    "open_pits_lt_10mi",
    "open_pits_10_25mi",
    "open_pits_25_50mi",
    "best_open_pit_rating_within_25mi",
    "avg_open_pit_rating_within_25mi",
    # Unknown-access pits
    "nearest_unknown_access_pit_miles",
    "unknown_access_pits_within_25mi",
    "has_unknown_access_pit_within_25mi",
    # Accessible pits (open + unknown + owned) — marginal bands
    "nearest_accessible_pit_miles",
    "accessible_pits_lt_10mi",
    "accessible_pits_10_25mi",
    "accessible_pits_25_50mi",
    "best_accessible_pit_rating_within_25mi",
    "avg_accessible_pit_rating_within_25mi",
    # Owned/restricted pits
    "nearest_owned_or_restricted_pit_miles",
    "owned_or_restricted_pits_within_25mi",
    "best_owned_or_restricted_pit_rating_within_25mi",
    "has_competitor_restricted_pit_within_25mi",
    # Knife River pending
    "nearest_knife_river_pending_pit_miles",
    "knife_river_pending_pits_within_25mi",
    # Competitive advantage
    "competitor_pit_distance_advantage_vs_open",
    "competitor_pit_distance_advantage_vs_market_median",
    "has_clear_pit_advantage",
]

DISTANCE_FEATURE_COLUMNS = [
    col
    for col in PIT_FEATURE_COLUMNS
    if col.startswith("nearest_") or col.endswith("_miles")
]

COUNT_FEATURE_COLUMNS = [
    col
    for col in PIT_FEATURE_COLUMNS
    if "_within_" in col
    or col.startswith("has_")
    or col.endswith("_lt_10mi")
    or col.endswith("_10_25mi")
    or col.endswith("_25_50mi")
    or col in {"project_location_missing", "project_location_pit_county_centroid"}
]

RATING_FEATURE_COLUMNS = [col for col in PIT_FEATURE_COLUMNS if "rating" in col]

ADVANTAGE_FEATURE_COLUMNS = [
    "competitor_pit_distance_advantage_vs_open",
    "competitor_pit_distance_advantage_vs_market_median",
]


def normalize_key(value: object) -> str:
    if pd.isna(value):
        return ""
    text = str(value).upper()
    text = re.sub(r"\b(COUNTY|CNTY|CTY|CO)\b", "", text)
    text = text.replace("&", " AND ")
    text = re.sub(r"[^A-Z0-9]+", "", text)
    return text


def normalize_county(value: object) -> str:
    if pd.isna(value):
        return ""
    text = str(value).upper()
    text = re.sub(r"\b(COUNTY|CNTY|CTY|CO)\b", "", text)
    text = re.sub(r"[^A-Z0-9]+", "", text)
    return text


def first_existing(columns: list[str], candidates: list[str]) -> str | None:
    lowered = {col.lower(): col for col in columns}
    for candidate in candidates:
        if candidate.lower() in lowered:
            return lowered[candidate.lower()]
    return None


def haversine_miles(
    lat1: float,
    lon1: float,
    lat2: pd.Series,
    lon2: pd.Series,
) -> pd.Series:
    lat1_rad = np.radians(lat1)
    lon1_rad = np.radians(lon1)
    lat2_rad = np.radians(pd.to_numeric(lat2, errors="coerce"))
    lon2_rad = np.radians(pd.to_numeric(lon2, errors="coerce"))
    dlat = lat2_rad - lat1_rad
    dlon = lon2_rad - lon1_rad
    a = np.sin(dlat / 2.0) ** 2 + np.cos(lat1_rad) * np.cos(lat2_rad) * np.sin(dlon / 2.0) ** 2
    return 2 * EARTH_RADIUS_MILES * np.arcsin(np.sqrt(a))


def min_or_nan(values: pd.Series) -> float:
    values = pd.to_numeric(values, errors="coerce").dropna()
    if values.empty:
        return np.nan
    return float(values.min())


def count_within(values: pd.Series, miles: float) -> int:
    values = pd.to_numeric(values, errors="coerce").dropna()
    return int((values <= miles).sum())


def count_between(values: pd.Series, lo: float, hi: float) -> int:
    """Count pits with distance in the half-open interval [lo, hi)."""
    values = pd.to_numeric(values, errors="coerce").dropna()
    return int(((values >= lo) & (values < hi)).sum())


def best_rating_within(frame: pd.DataFrame, miles: float) -> float:
    nearby = frame.loc[frame["distance_miles"] <= miles, "Rating"]
    nearby = pd.to_numeric(nearby, errors="coerce").dropna()
    if nearby.empty:
        return np.nan
    return float(nearby.max())


def avg_rating_within(frame: pd.DataFrame, miles: float) -> float:
    nearby = frame.loc[frame["distance_miles"] <= miles, "Rating"]
    nearby = pd.to_numeric(nearby, errors="coerce").dropna()
    if nearby.empty:
        return np.nan
    return float(nearby.mean())


def is_knife_river_unit(competitor_unit_id: str) -> bool:
    """True for any Knife River division (e.g. 'KNIFE RIVER - ST. CLOUD').

    competitor_unit_id is now the competitor_name_registry's comp_name itself
    (see data/entity_resolution.py apply_registry_mapping), so this is a plain
    name check — no separate ID lookup needed.
    """
    return normalize_key(competitor_unit_id).startswith("KNIFERIVER")


def build_bidder_name_map(bidder_results: pd.DataFrame) -> dict[str, str]:
    """Build normalize(raw_bidder_name) → competitor_unit_id from bidder_results.
    This produces TMP_ IDs that match the candidate panel."""
    name_map: dict[str, str] = {}
    if "raw_bidder_name" not in bidder_results.columns:
        return name_map
    for _, row in bidder_results.drop_duplicates("raw_bidder_name").iterrows():
        unit_id = row.get("competitor_unit_id")
        if pd.isna(unit_id):
            continue
        key = normalize_key(row["raw_bidder_name"])
        if key and key not in name_map:
            name_map[key] = str(unit_id)
    return name_map


def prepare_pits(
    pits: pd.DataFrame,
    bidder_results: pd.DataFrame | None = None,
) -> pd.DataFrame:
    result = pits.copy()
    result["Latitude"] = pd.to_numeric(result["Latitude"], errors="coerce")
    result["Longitude"] = pd.to_numeric(result["Longitude"], errors="coerce")
    result["Rating"] = pd.to_numeric(result.get("Rating"), errors="coerce")
    result["access_type"] = result.get("access_type", "unknown").fillna("unknown").astype(str)
    result["county_key"] = result.get("County", "").map(normalize_county)

    name_map: dict[str, str] = {}
    if bidder_results is not None and not bidder_results.empty:
        name_map.update(build_bidder_name_map(bidder_results))

    result["access_company_unit_id"] = (
        result.get("access_company", pd.Series(index=result.index, dtype=object))
        .map(normalize_key)
        .map(name_map)
    )
    return result.dropna(subset=["Latitude", "Longitude"])


def build_pit_county_centroids(pits: pd.DataFrame) -> pd.DataFrame:
    county_pits = pits[pits["county_key"] != ""].copy()
    centroids = (
        county_pits.groupby(["State", "county_key"], dropna=False)
        .agg(project_latitude=("Latitude", "mean"), project_longitude=("Longitude", "mean"))
        .reset_index()
    )
    centroids["project_location_source"] = "pit_county_centroid"
    centroids["project_location_confidence"] = "low"
    return centroids


def load_county_centroids(path: str | None) -> pd.DataFrame:
    if not path:
        return pd.DataFrame()
    centroids = pd.read_csv(path)
    lat_col = first_existing(list(centroids.columns), ["project_latitude", "county_latitude", "latitude", "lat"])
    lon_col = first_existing(list(centroids.columns), ["project_longitude", "county_longitude", "longitude", "lon", "lng"])
    if lat_col is None or lon_col is None:
        raise ValueError("County centroid file must include latitude and longitude columns.")
    state_col = first_existing(list(centroids.columns), ["state", "State"])
    county_col = first_existing(list(centroids.columns), ["county", "County", "county_name"])
    if county_col is None:
        raise ValueError("County centroid file must include a county column.")
    result = pd.DataFrame(
        {
            "State": centroids[state_col] if state_col else "MN",
            "county_key": centroids[county_col].map(normalize_county),
            "project_latitude": pd.to_numeric(centroids[lat_col], errors="coerce"),
            "project_longitude": pd.to_numeric(centroids[lon_col], errors="coerce"),
            "project_location_source": "county_centroid",
            "project_location_confidence": "medium",
        }
    )
    return result.dropna(subset=["project_latitude", "project_longitude"])


def add_project_locations(
    panel: pd.DataFrame,
    projects: pd.DataFrame,
    pits: pd.DataFrame,
    county_centroids: pd.DataFrame | None = None,
    use_pit_county_centroids: bool = True,
) -> pd.DataFrame:
    project_cols = ["project_natural_key", "state", "county"]
    lat_col = first_existing(list(projects.columns), ["project_latitude", "project_lat", "latitude", "lat"])
    lon_col = first_existing(list(projects.columns), ["project_longitude", "project_lon", "longitude", "lon", "lng"])
    if lat_col and lon_col:
        project_cols.extend([lat_col, lon_col])

    available_cols = [col for col in project_cols if col in projects.columns]
    result = panel.merge(
        projects[available_cols].drop_duplicates("project_natural_key"),
        on="project_natural_key",
        how="left",
        suffixes=("", "_project"),
    )
    result["county_key"] = result.get("county", "").map(normalize_county)

    if lat_col and lon_col:
        result["project_latitude"] = pd.to_numeric(result[lat_col], errors="coerce")
        result["project_longitude"] = pd.to_numeric(result[lon_col], errors="coerce")
        has_exact = result["project_latitude"].notna() & result["project_longitude"].notna()
        result["project_location_source"] = np.where(has_exact, "project_coordinates", "missing")
        result["project_location_confidence"] = np.where(has_exact, "high", "missing")
    else:
        result["project_latitude"] = np.nan
        result["project_longitude"] = np.nan
        result["project_location_source"] = "missing"
        result["project_location_confidence"] = "missing"

    centroid_frames = []
    if county_centroids is not None and not county_centroids.empty:
        centroid_frames.append(county_centroids)
    if use_pit_county_centroids:
        centroid_frames.append(build_pit_county_centroids(pits))

    missing_location = result["project_latitude"].isna() | result["project_longitude"].isna()
    for centroids in centroid_frames:
        if not missing_location.any():
            break
        lookup_cols = [
            "State",
            "county_key",
            "project_latitude",
            "project_longitude",
            "project_location_source",
            "project_location_confidence",
        ]
        merged = result.loc[missing_location, ["state", "county_key"]].merge(
            centroids[lookup_cols],
            left_on=["state", "county_key"],
            right_on=["State", "county_key"],
            how="left",
        )
        fillable = merged["project_latitude"].notna() & merged["project_longitude"].notna()
        target_index = result.loc[missing_location].index[fillable.to_numpy()]
        for col in [
            "project_latitude",
            "project_longitude",
            "project_location_source",
            "project_location_confidence",
        ]:
            result.loc[target_index, col] = merged.loc[fillable, col].to_numpy()
        missing_location = result["project_latitude"].isna() | result["project_longitude"].isna()

    return result


def aggregate_group(prefix: str, frame: pd.DataFrame, features: dict[str, object]) -> None:
    distances = frame["distance_miles"] if not frame.empty else pd.Series(dtype=float)
    features[f"nearest_{prefix}_pit_miles"] = min_or_nan(distances)

    if prefix in {"open", "accessible"}:
        # Marginal (non-cumulative) bands to avoid multicollinearity
        features[f"{prefix}_pits_lt_10mi"]  = count_between(distances, 0, 10)
        features[f"{prefix}_pits_10_25mi"]  = count_between(distances, 10, 25)
        features[f"{prefix}_pits_25_50mi"]  = count_between(distances, 25, 50)
        features[f"best_{prefix}_pit_rating_within_25mi"] = best_rating_within(frame, 25)
        features[f"avg_{prefix}_pit_rating_within_25mi"]  = avg_rating_within(frame, 25)
    elif prefix == "owned_or_restricted":
        features["owned_or_restricted_pits_within_25mi"] = count_within(distances, 25)
        features[f"best_{prefix}_pit_rating_within_25mi"] = best_rating_within(frame, 25)
    elif prefix == "unknown_access":
        features["unknown_access_pits_within_25mi"]    = count_within(distances, 25)
        features["has_unknown_access_pit_within_25mi"] = int(count_within(distances, 25) > 0)
    elif prefix == "knife_river_pending":
        features["knife_river_pending_pits_within_25mi"] = count_within(distances, 25)


def build_features_for_row(
    row: pd.Series,
    pits: pd.DataFrame,
    pit_distances: pd.DataFrame | None = None,
) -> dict[str, object]:
    features: dict[str, object] = {
        "project_natural_key": row["project_natural_key"],
        "competitor_unit_id": str(row["competitor_unit_id"]),
        "project_location_source": row.get("project_location_source", "missing"),
        "project_location_confidence": row.get("project_location_confidence", "missing"),
    }
    features["project_location_missing"] = int(features["project_location_source"] == "missing")
    features["project_location_pit_county_centroid"] = int(
        features["project_location_source"] == "pit_county_centroid"
    )

    lat = pd.to_numeric(row.get("project_latitude"), errors="coerce")
    lon = pd.to_numeric(row.get("project_longitude"), errors="coerce")
    if pd.isna(lat) or pd.isna(lon):
        for col in PIT_FEATURE_COLUMNS:
            features.setdefault(col, np.nan if col in DISTANCE_FEATURE_COLUMNS else 0)
        features["project_location_source"] = "missing"
        features["project_location_confidence"] = "missing"
        features["project_location_missing"] = 1
        features["project_location_pit_county_centroid"] = 0
        return features

    if pit_distances is None:
        pit_distances = pits.copy()
        pit_distances["distance_miles"] = haversine_miles(
            lat,
            lon,
            pit_distances["Latitude"],
            pit_distances["Longitude"],
        )

    competitor_unit_id = str(row["competitor_unit_id"])
    open_pits = pit_distances[pit_distances["access_type"] == "open"]
    unknown_pits = pit_distances[pit_distances["access_type"] == "unknown"]
    owned_pits = pit_distances[
        (pit_distances["access_type"] == "competitor")
        & (pit_distances["access_company_unit_id"] == competitor_unit_id)
    ]
    knife_pending = pit_distances[pit_distances["access_type"] == "knife_river_pending"]
    if is_knife_river_unit(competitor_unit_id) and not knife_pending.empty:
        # Pending pits aren't assigned to a specific division in the pit list,
        # so every Knife River division shares access to the same pool.
        owned_pits = pd.concat([owned_pits, knife_pending], ignore_index=True)
    accessible_pits = pd.concat([open_pits, unknown_pits, owned_pits], ignore_index=True)

    aggregate_group("open", open_pits, features)
    aggregate_group("unknown_access", unknown_pits, features)
    aggregate_group("accessible", accessible_pits, features)
    aggregate_group("owned_or_restricted", owned_pits, features)
    aggregate_group("knife_river_pending", knife_pending, features)

    features["has_competitor_restricted_pit_within_25mi"] = int(
        features.get("owned_or_restricted_pits_within_25mi", 0) > 0
    )
    nearest_open = features.get("nearest_open_pit_miles")
    nearest_owned = features.get("nearest_owned_or_restricted_pit_miles")
    market_median = min_or_nan(pit_distances["distance_miles"]) if pit_distances.empty else float(
        pd.to_numeric(pit_distances["distance_miles"], errors="coerce").median()
    )
    if pd.notna(nearest_open) and pd.notna(nearest_owned):
        features["competitor_pit_distance_advantage_vs_open"] = nearest_open - nearest_owned
    else:
        features["competitor_pit_distance_advantage_vs_open"] = np.nan
    if pd.notna(market_median) and pd.notna(nearest_owned):
        features["competitor_pit_distance_advantage_vs_market_median"] = market_median - nearest_owned
    else:
        features["competitor_pit_distance_advantage_vs_market_median"] = np.nan
    features["has_clear_pit_advantage"] = int(
        pd.notna(nearest_open)
        and pd.notna(nearest_owned)
        and nearest_owned <= 25
        and (nearest_open - nearest_owned) >= 10
    )
    return features


def build_features_for_project_rows(
    project_rows: pd.DataFrame,
    pits: pd.DataFrame,
) -> list[dict[str, object]]:
    first = project_rows.iloc[0]
    lat = pd.to_numeric(first.get("project_latitude"), errors="coerce")
    lon = pd.to_numeric(first.get("project_longitude"), errors="coerce")
    if pd.isna(lat) or pd.isna(lon):
        return [
            build_features_for_row(row, pits, pit_distances=None)
            for _, row in project_rows.iterrows()
        ]

    pit_distances = pits.copy()
    pit_distances["distance_miles"] = haversine_miles(
        lat,
        lon,
        pit_distances["Latitude"],
        pit_distances["Longitude"],
    )

    open_pits = pit_distances[pit_distances["access_type"] == "open"]
    unknown_pits = pit_distances[pit_distances["access_type"] == "unknown"]
    shared_accessible = pd.concat([open_pits, unknown_pits], ignore_index=True)
    knife_pending = pit_distances[pit_distances["access_type"] == "knife_river_pending"]
    owned_by_unit = {
        str(unit_id): frame
        for unit_id, frame in pit_distances[
            pit_distances["access_type"] == "competitor"
        ].groupby("access_company_unit_id", dropna=True)
    }

    common: dict[str, object] = {
        "project_location_source": first.get("project_location_source", "missing"),
        "project_location_confidence": first.get("project_location_confidence", "missing"),
    }
    common["project_location_missing"] = int(common["project_location_source"] == "missing")
    common["project_location_pit_county_centroid"] = int(
        common["project_location_source"] == "pit_county_centroid"
    )
    aggregate_group("open", open_pits, common)
    aggregate_group("unknown_access", unknown_pits, common)
    aggregate_group("knife_river_pending", knife_pending, common)

    shared_accessible_features: dict[str, object] = {}
    aggregate_group("accessible", shared_accessible, shared_accessible_features)
    empty_owned_features: dict[str, object] = {}
    aggregate_group(
        "owned_or_restricted",
        pd.DataFrame(columns=["distance_miles", "Rating"]),
        empty_owned_features,
    )

    market_median = float(
        pd.to_numeric(pit_distances["distance_miles"], errors="coerce").median()
    )

    feature_rows = []
    for _, row in project_rows.iterrows():
        competitor_unit_id = str(row["competitor_unit_id"])
        features: dict[str, object] = {
            "project_natural_key": row["project_natural_key"],
            "competitor_unit_id": competitor_unit_id,
            **common,
        }
        owned_pits = owned_by_unit.get(
            competitor_unit_id,
            pd.DataFrame(columns=pit_distances.columns),
        )
        if is_knife_river_unit(competitor_unit_id) and not knife_pending.empty:
            # Pending pits aren't assigned to a specific division in the pit
            # list, so every Knife River division shares access to the same
            # pool (computed independently per project distance).
            owned_pits = pd.concat([owned_pits, knife_pending], ignore_index=True)
        if owned_pits.empty:
            features.update(shared_accessible_features)
            features.update(empty_owned_features)
        else:
            accessible_pits = pd.concat([shared_accessible, owned_pits], ignore_index=True)
            aggregate_group("accessible", accessible_pits, features)
            aggregate_group("owned_or_restricted", owned_pits, features)
        features["has_competitor_restricted_pit_within_25mi"] = int(
            features.get("owned_or_restricted_pits_within_25mi", 0) > 0
        )

        nearest_open = features.get("nearest_open_pit_miles")
        nearest_owned = features.get("nearest_owned_or_restricted_pit_miles")
        if pd.notna(nearest_open) and pd.notna(nearest_owned):
            features["competitor_pit_distance_advantage_vs_open"] = nearest_open - nearest_owned
        else:
            features["competitor_pit_distance_advantage_vs_open"] = np.nan
        if pd.notna(market_median) and pd.notna(nearest_owned):
            features["competitor_pit_distance_advantage_vs_market_median"] = (
                market_median - nearest_owned
            )
        else:
            features["competitor_pit_distance_advantage_vs_market_median"] = np.nan
        features["has_clear_pit_advantage"] = int(
            pd.notna(nearest_open)
            and pd.notna(nearest_owned)
            and nearest_owned <= 25
            and (nearest_open - nearest_owned) >= 10
        )
        feature_rows.append(features)
    return feature_rows


def fill_pit_feature_defaults(features: pd.DataFrame) -> pd.DataFrame:
    result = features.copy()
    for col in DISTANCE_FEATURE_COLUMNS:
        if col in result.columns:
            result[col] = pd.to_numeric(result[col], errors="coerce").fillna(9999.0)
    for col in COUNT_FEATURE_COLUMNS + RATING_FEATURE_COLUMNS + ADVANTAGE_FEATURE_COLUMNS:
        if col in result.columns:
            result[col] = pd.to_numeric(result[col], errors="coerce").fillna(0)
    return result


def build_pit_features(
    panel: pd.DataFrame,
    projects: pd.DataFrame,
    pits: pd.DataFrame,
    bidder_results: pd.DataFrame | None = None,
    county_centroids: pd.DataFrame | None = None,
    use_pit_county_centroids: bool = True,
) -> pd.DataFrame:
    required = {"project_natural_key", "competitor_unit_id"}
    missing = required.difference(panel.columns)
    if missing:
        raise ValueError(f"Panel is missing required columns: {sorted(missing)}")

    prepared_pits = prepare_pits(pits, bidder_results)
    rows = panel[["project_natural_key", "competitor_unit_id"]].drop_duplicates().copy()
    rows["competitor_unit_id"] = rows["competitor_unit_id"].astype(str)
    rows = add_project_locations(
        panel=rows,
        projects=projects,
        pits=prepared_pits,
        county_centroids=county_centroids,
        use_pit_county_centroids=use_pit_county_centroids,
    )

    feature_rows = []
    for _, project_rows in rows.groupby("project_natural_key", sort=False):
        feature_rows.extend(build_features_for_project_rows(project_rows, prepared_pits))
    result = pd.DataFrame(feature_rows)
    ordered_cols = ["project_natural_key", "competitor_unit_id", *PIT_FEATURE_COLUMNS]
    for col in ordered_cols:
        if col not in result.columns:
            result[col] = np.nan
    result = fill_pit_feature_defaults(result[ordered_cols])

    # Pit data covers Minnesota only — zero out all pit features for other states
    # and add a binary flag so the model knows when pit features are meaningful.
    state_map = rows[["project_natural_key", "state"]].drop_duplicates("project_natural_key")
    result = result.merge(state_map, on="project_natural_key", how="left")
    non_mn = result["state"].fillna("").str.upper().ne("MN")
    result["pit_applicable"] = (~non_mn).astype(int)
    for col in DISTANCE_FEATURE_COLUMNS:
        if col in result.columns:
            result.loc[non_mn, col] = 9999.0
    for col in COUNT_FEATURE_COLUMNS + RATING_FEATURE_COLUMNS + ADVANTAGE_FEATURE_COLUMNS:
        if col in result.columns:
            result.loc[non_mn, col] = 0
    result = result.drop(columns=["state"])

    mn_pct = 100 * (~non_mn).mean()
    print(f"  pit_applicable: {(~non_mn).sum():,} MN rows ({mn_pct:.1f}%) — "
          f"{non_mn.sum():,} non-MN rows zeroed out")

    final_cols = ["project_natural_key", "competitor_unit_id", "pit_applicable", *PIT_FEATURE_COLUMNS]
    return result[final_cols].sort_values(["project_natural_key", "competitor_unit_id"]).reset_index(drop=True)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build project × competitor pit-derived features for Model 1."
    )
    parser.add_argument("--panel", default="data/processed/model1/ranking_training_panel.parquet")
    parser.add_argument("--projects", default="data/processed/projects.parquet")
    parser.add_argument("--pits", default="data/processed/MN_pit_list_cleaned.csv")
    parser.add_argument("--bidder-results", default="data/processed/bidder_results.parquet")
    parser.add_argument("--candidate-rule", default=DEFAULT_CANDIDATE_RULE)
    parser.add_argument("--county-centroids", default=None)
    parser.add_argument("--no-pit-county-centroid-fallback", action="store_true")
    parser.add_argument("--output", default="data/processed/model1/pit_features.parquet")
    args = parser.parse_args()

    panel = read_table(args.panel)
    if "candidate_rule_version" in panel.columns:
        panel = panel[panel["candidate_rule_version"] == args.candidate_rule].copy()
    projects = read_table(args.projects)
    pits = pd.read_csv(args.pits)
    bidder_results = read_table(args.bidder_results) if args.bidder_results else None
    county_centroids = load_county_centroids(args.county_centroids)

    features = build_pit_features(
        panel=panel,
        projects=projects,
        pits=pits,
        bidder_results=bidder_results,
        county_centroids=county_centroids,
        use_pit_county_centroids=not args.no_pit_county_centroid_fallback,
    )
    written = write_table(features, args.output)
    print("Pit features complete")
    print(f"  candidate rule:         {args.candidate_rule}")
    print(f"  output:                 {written}")
    print(f"  rows:                   {len(features):,}")
    print(f"  projects:               {features['project_natural_key'].nunique():,}")
    print(f"  competitors:            {features['competitor_unit_id'].nunique():,}")
    print("  location source counts:")
    print(features["project_location_source"].value_counts(dropna=False).to_string())


if __name__ == "__main__":
    main()
