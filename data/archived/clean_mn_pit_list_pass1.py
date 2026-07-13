#!/usr/bin/env python3
"""
MN Pit List — Pass 1: Structural Cleanup + State + County Verification

Inputs:
    data/raw/MN Pit List.xlsx
    /tmp/tl_2022_us_county.zip  (auto-downloaded from Census TIGER if not present)

Outputs:
    data/processed/MN_pit_list_cleaned.csv

Steps:
    1. Drop embedded rating legend columns (Unnamed: 6-9)
    2. Rename columns for consistency
    3. Add State = "MN"
    4. Verify County against Latitude/Longitude via geopandas spatial join
       - Adds: county_from_coords, county_match
"""

import os
import urllib.request
import pandas as pd
import geopandas as gpd

RAW_FILE     = "data/raw/MN Pit List.xlsx"
OUTPUT_FILE  = "data/processed/MN_pit_list_cleaned.csv"
SHAPEFILE    = "/tmp/tl_2022_us_county.zip"
SHAPEFILE_URL = "https://www2.census.gov/geo/tiger/TIGER2022/COUNTY/tl_2022_us_county.zip"

# ── Load ──────────────────────────────────────────────────────────────────────
df = pd.read_excel(RAW_FILE)

# ── Step 1: Drop embedded rating legend columns ───────────────────────────────
df = df.drop(columns=["Unnamed: 6", "Unnamed: 7", "Unnamed: 8", "Unnamed: 9"])

# ── Step 2: Rename columns ────────────────────────────────────────────────────
df = df.rename(columns={"County ": "County", "Rating  1-10": "Rating"})

# ── Step 3: Add State ─────────────────────────────────────────────────────────
df["State"] = "MN"

# ── Step 4: County verification via spatial join ──────────────────────────────
if not os.path.exists(SHAPEFILE):
    print("Downloading Census TIGER county shapefile...")
    urllib.request.urlretrieve(SHAPEFILE_URL, SHAPEFILE)

counties = gpd.read_file(SHAPEFILE)
mn_counties = counties[counties["STATEFP"] == "27"][["NAME", "geometry"]].copy()

gdf = gpd.GeoDataFrame(
    df.copy(),
    geometry=gpd.points_from_xy(df["Longitude"], df["Latitude"]),
    crs=mn_counties.crs,
)

joined = gpd.sjoin(gdf, mn_counties, how="left", predicate="within")
df["county_from_coords"] = joined["NAME"].values

def norm(s):
    if pd.isna(s):
        return ""
    return s.strip().upper().replace(" ", "").replace(".", "").replace("'", "")

df["county_match"] = df.apply(
    lambda r: norm(r["County"]) == norm(r["county_from_coords"]), axis=1
)

# ── Save ──────────────────────────────────────────────────────────────────────
os.makedirs("data/processed", exist_ok=True)
df.to_csv(OUTPUT_FILE, index=False)

print(f"Saved: {OUTPUT_FILE}")
print(f"Shape: {df.shape}")
print(f"\nCounty match summary:")
print(f"  Matched:        {df['county_match'].sum()}")
print(f"  Outside MN:     {df['county_from_coords'].isna().sum()}")
print(f"  Mismatched:     {(~df['county_match'] & df['county_from_coords'].notna()).sum()}")
