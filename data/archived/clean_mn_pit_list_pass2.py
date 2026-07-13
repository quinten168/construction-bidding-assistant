#!/usr/bin/env python3
"""
MN Pit List — Pass 2: County Corrections

Inputs:
    data/processed/MN_pit_list_cleaned.csv  (output of Pass 1)

Outputs:
    data/processed/MN_pit_list_cleaned.csv  (updated in place)

Steps:
    1. Fix known County spelling errors (deterministic lookup)
    2. Update adjacent-boundary counties to match coordinates
    3. Add county_flag column (ok / review / outside_mn)

Decision rules:
    - Spelling errors: county name doesn't exist in MN; spatial join confirms correction
    - Adjacent boundary: trust coordinates over handwritten label for model accuracy
    - Non-adjacent mismatch: flag for manual review (can't determine which is wrong)
    - Outside MN shapefile: flag, keep in dataset (border-area pits still usable)
"""

import pandas as pd

INPUT_FILE = "data/processed/MN_pit_list_cleaned.csv"

df = pd.read_csv(INPUT_FILE)

if "county_original" not in df.columns:
    df["county_original"] = df["County"]

# ── Step 1: Fix spelling errors ───────────────────────────────────────────────
SPELLING_FIXES = {
    "Marschall": "Marshall",
    "Le Suer":   "Le Sueur",
    "Mclead":    "McLeod",
    "Washinton": "Washington",
    "Fairbault": "Faribault",
}
cat1_mask = df["County"].isin(SPELLING_FIXES.keys())
df.loc[cat1_mask, "County"] = df.loc[cat1_mask, "County"].map(SPELLING_FIXES)
print(f"Step 1: fixed {cat1_mask.sum()} spelling errors")

# ── Re-evaluate county_match after spelling fixes ─────────────────────────────
def norm(s):
    if pd.isna(s):
        return ""
    return s.strip().upper().replace(" ", "").replace(".", "").replace("'", "")

df["county_match"] = df.apply(
    lambda r: norm(r["County"]) == norm(r["county_from_coords"]), axis=1
)

# ── Step 2 & 3: Assign county_flag, then fix adjacent-boundary rows ───────────
# Non-adjacent pairs that need manual review (county and coords too far apart)
NON_ADJACENT = {
    ("Chisago",    "Dakota"),
    ("Wilkin",     "Yellow Medicine"),
    ("Clearwater", "Otter Tail"),
    ("Pipestone",  "Hubbard"),
    ("Red Lake",   "Hubbard"),
}

def assign_flag(row):
    if pd.isna(row["county_from_coords"]):
        return "outside_mn"
    if (row["County"], row["county_from_coords"]) in NON_ADJACENT:
        return "review"
    if row["county_match"]:
        return "ok"
    return "adjacent_boundary"

df["county_flag"] = df.apply(assign_flag, axis=1)

# Update adjacent-boundary counties to match coordinates
cat2_mask = df["county_flag"] == "adjacent_boundary"
df.loc[cat2_mask, "County"] = df.loc[cat2_mask, "county_from_coords"]
df.loc[cat2_mask, "county_flag"] = "ok"
print(f"Step 2: updated {cat2_mask.sum()} adjacent-boundary counties to match coordinates")

# ── Re-evaluate county_match after adjacent-boundary updates ──────────────────
df["county_match"] = df.apply(
    lambda r: norm(r["County"]) == norm(r["county_from_coords"]), axis=1
)

# ── Save ──────────────────────────────────────────────────────────────────────
df.to_csv(INPUT_FILE, index=False)

print(f"\ncounty_flag distribution:")
print(df["county_flag"].value_counts().to_string())
print(f"\nSaved: {INPUT_FILE}")
