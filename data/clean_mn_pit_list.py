#!/usr/bin/env python3
"""
MN Pit List — Consolidated Cleaning Pipeline

Inputs:
    data/raw/MN Pit List.xlsx
    /tmp/tl_2022_us_county.zip          (auto-downloaded from Census TIGER if not present)
    data/cleaning_review/access_standardization.csv

Outputs:
    data/processed/MN_pit_list_cleaned.csv

Passes:
    1. Structural cleanup + county verification via spatial join
    2. County spelling corrections + county_flag assignment
    3. Access field standardization → access_type + access_company
    4. (Latitude, Longitude) duplicate detection — flags and sinks repeats so lat/lon can serve
       as a clean unique key downstream (e.g. the Supabase push)
"""

import os
import re
import urllib.request
import pandas as pd
import geopandas as gpd

RAW_FILE      = "data/raw/MN Pit List.xlsx"
OUTPUT_FILE   = "data/processed/MN_pit_list_cleaned.csv"
SHAPEFILE     = "/tmp/tl_2022_us_county.zip"
SHAPEFILE_URL = "https://www2.census.gov/geo/tiger/TIGER2022/COUNTY/tl_2022_us_county.zip"
LOOKUP_FILE   = "data/cleaning_review/access_standardization.csv"

SPELLING_FIXES = {
    "Marschall": "Marshall",
    "Le Suer":   "Le Sueur",
    "Mclead":    "McLeod",
    "Washinton": "Washington",
    "Fairbault": "Faribault",
}

NON_ADJACENT = {
    ("Chisago",    "Dakota"),
    ("Wilkin",     "Yellow Medicine"),
    ("Clearwater", "Otter Tail"),
    ("Pipestone",  "Hubbard"),
    ("Red Lake",   "Hubbard"),
}

CSI_VARIANTS    = {"CSI", "Csi"}
CLOSED_VARIANTS = {"Old Pit / closed up", "Closed up/ old pit", "Closed up/ Old CSI pit"}
KR_VARIANTS     = {"Knife River", "Knife river", "Knife RIver"}


def norm(s):
    if pd.isna(s):
        return ""
    return s.strip().upper().replace(" ", "").replace(".", "").replace("'", "")


def pass1_structural(raw_file, shapefile, shapefile_url):
    df = pd.read_excel(raw_file)

    df = df.drop(columns=["Unnamed: 6", "Unnamed: 7", "Unnamed: 8", "Unnamed: 9"])
    df = df.rename(columns={"County ": "County", "Rating  1-10": "Rating"})
    df["State"] = "MN"

    if not os.path.exists(shapefile):
        print("Downloading Census TIGER county shapefile...")
        urllib.request.urlretrieve(shapefile_url, shapefile)

    counties = gpd.read_file(shapefile)
    mn_counties = counties[counties["STATEFP"] == "27"][["NAME", "geometry"]].copy()

    gdf = gpd.GeoDataFrame(
        df.copy(),
        geometry=gpd.points_from_xy(df["Longitude"], df["Latitude"]),
        crs=mn_counties.crs,
    )

    joined = gpd.sjoin(gdf, mn_counties, how="left", predicate="within")
    df["county_from_coords"] = joined["NAME"].values
    df["county_match"] = df.apply(
        lambda r: norm(r["County"]) == norm(r["county_from_coords"]), axis=1
    )

    print(f"Pass 1 — County match summary:")
    print(f"  Matched:    {df['county_match'].sum()}")
    print(f"  Outside MN: {df['county_from_coords'].isna().sum()}")
    print(f"  Mismatched: {(~df['county_match'] & df['county_from_coords'].notna()).sum()}")

    return df


def pass2_county_corrections(df):
    df["county_original"] = df["County"]

    cat1_mask = df["County"].isin(SPELLING_FIXES.keys())
    df.loc[cat1_mask, "County"] = df.loc[cat1_mask, "County"].map(SPELLING_FIXES)
    print(f"\nPass 2 — fixed {cat1_mask.sum()} spelling errors")

    df["county_match"] = df.apply(
        lambda r: norm(r["County"]) == norm(r["county_from_coords"]), axis=1
    )

    def assign_flag(row):
        if pd.isna(row["county_from_coords"]):
            return "outside_mn"
        if (row["County"], row["county_from_coords"]) in NON_ADJACENT:
            return "review"
        if row["county_match"]:
            return "ok"
        return "adjacent_boundary"

    df["county_flag"] = df.apply(assign_flag, axis=1)

    cat2_mask = df["county_flag"] == "adjacent_boundary"
    df.loc[cat2_mask, "County"] = df.loc[cat2_mask, "county_from_coords"]
    df.loc[cat2_mask, "county_flag"] = "ok"
    print(f"Pass 2 — updated {cat2_mask.sum()} adjacent-boundary counties to match coordinates")

    df["county_match"] = df.apply(
        lambda r: norm(r["County"]) == norm(r["county_from_coords"]), axis=1
    )

    print(f"\ncounty_flag distribution:")
    print(df["county_flag"].value_counts().to_string())

    return df


def pass3_access_fields(df, lookup_file):
    lookup = pd.read_csv(lookup_file).set_index("access_name")["canonical_name"].to_dict()

    def normalize_access(val):
        if pd.isna(val):
            return None
        val = str(val).strip()
        val = re.sub(r"\s+", " ", val)
        val = re.sub(r"^​", "", val)   # remove zero-width space
        return val

    def assign_access_type(val):
        if val is None:
            return "unknown"
        if val == "Everyone":
            return "open"
        if val in CSI_VARIANTS:
            return "client"
        if val in CLOSED_VARIANTS:
            return "closed"
        if val in KR_VARIANTS:
            return "knife_river_pending"
        return "competitor"

    def assign_access_company(val, access_type):
        if access_type != "competitor":
            return None
        return lookup.get(val, "NOT_IN_BIDDER_LIST")

    df["_access_norm"]   = df["Access"].apply(normalize_access)
    df["access_type"]    = df["_access_norm"].apply(assign_access_type)
    df["access_company"] = df.apply(
        lambda r: assign_access_company(r["_access_norm"], r["access_type"]), axis=1
    )
    df = df.drop(columns=["_access_norm"])

    print("\nPass 3 — access_type distribution:")
    print(df["access_type"].value_counts().to_string())
    print("\nPass 3 — access_company distribution (competitor rows only):")
    comp = df[df["access_type"] == "competitor"]
    print(comp["access_company"].value_counts().to_string())

    return df


def pass4_lat_lon_duplicates(df):
    """Flag exact (Latitude, Longitude) repeats for manual review and sink them to the bottom of
    the file, so latitude+longitude can serve as a clean unique key everywhere downstream (e.g.
    the Supabase push). Keeps each coordinate pair's first occurrence in place, unflagged; every
    later occurrence at that same coordinate is flagged 'duplicate_lat_lon' and moved down --
    most are exact full-row duplicates, but a few carry a genuinely different Rating at the same
    spot, which is exactly the kind of conflict that needs a human decision, not a silent drop."""
    df = df.copy()
    is_dup = df.duplicated(subset=["Latitude", "Longitude"], keep="first")
    df["duplicate_flag"] = is_dup.map({True: "duplicate_lat_lon", False: "ok"})

    print(f"\nPass 4 — {int(is_dup.sum())} row(s) share a (Latitude, Longitude) with an earlier "
          f"row; flagged 'duplicate_lat_lon' and moved to the bottom for manual review.")

    return pd.concat([df[~is_dup], df[is_dup]], ignore_index=True)


# County columns are QA/audit intermediates from Pass 1-2's spatial verification -- Pass 2's
# correction logic needs them internally (e.g. county_flag == "adjacent_boundary" triggers
# overwriting County with county_from_coords), but nothing downstream reads them once County
# itself is corrected. Dropped from the saved file as of 2026-07-29; not from the passes.
_AUDIT_ONLY_COLUMNS = ["county_from_coords", "county_match", "county_flag", "county_original"]


def main():
    df = pass1_structural(RAW_FILE, SHAPEFILE, SHAPEFILE_URL)
    df = pass2_county_corrections(df)
    df = pass3_access_fields(df, LOOKUP_FILE)
    df = pass4_lat_lon_duplicates(df)
    df = df.drop(columns=_AUDIT_ONLY_COLUMNS)
    os.makedirs("data/processed", exist_ok=True)
    df.to_csv(OUTPUT_FILE, index=False)
    print(f"\nSaved: {OUTPUT_FILE}")
    print(f"Shape: {df.shape}")


if __name__ == "__main__":
    main()
