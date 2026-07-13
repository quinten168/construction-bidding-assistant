#!/usr/bin/env python3
"""
MN Pit List — Pass 3: Access Field Standardization

Inputs:
    data/processed/MN_pit_list_cleaned.csv          (output of Pass 2)
    data/cleaning_review/access_standardization.csv  (lookup: raw name → canonical bidder name)

Outputs:
    data/processed/MN_pit_list_cleaned.csv  (updated in place)
      - New column: access_type  (open / unknown / client / competitor / knife_river_pending / closed)
      - New column: access_company  (canonical bidder name for competitor-type pits)

access_type definitions:
    open                  — "Everyone"; all competitors may use this pit
    unknown               — blank/NaN; treated as open for model purposes
    client                — CSI's own pits; excluded from competitor scoring,
                            kept for future CSI bid-decision model
    competitor            — restricted to a named company; access_company holds
                            the canonical bidder name from bidder_full_company_list.csv
    knife_river_pending   — "Knife River"; disambiguation pending between
                            KNIFE RIVER CORPORATION D/B/A KNIFE RIVER MIDWEST and
                            NORTHSTAR MATERIALS INC DBA KNIFE RIVER MATERIALS
    closed                — decommissioned pit; excluded from model

How access_company was derived:
    1. Fuzzy matched all 41 unique competitor Access names against 819 canonical
       bidder names using rapidfuzz token_sort_ratio (same normalizer as
       fuzzy_company_match.py).
    2. Confirmed / corrected matches using Claude Code analysis — no external API call.
    3. Result saved to data/cleaning_review/access_standardization.csv.
    4. 22 of 41 names mapped to canonical bidder names.
    5. 19 names marked NOT_IN_BIDDER_LIST (private pit owners not in CSI bid history).
"""

import re
import pandas as pd

INPUT_FILE       = "data/processed/MN_pit_list_cleaned.csv"
LOOKUP_FILE      = "data/cleaning_review/access_standardization.csv"

df     = pd.read_csv(INPUT_FILE)
lookup = pd.read_csv(LOOKUP_FILE).set_index("access_name")["canonical_name"].to_dict()

CSI_VARIANTS    = {"CSI", "Csi"}
CLOSED_VARIANTS = {"Old Pit / closed up", "Closed up/ old pit", "Closed up/ Old CSI pit"}
KR_VARIANTS     = {"Knife River", "Knife river", "Knife RIver"}

def normalize_access(val):
    """Strip whitespace and invisible characters from raw Access value."""
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

df.to_csv(INPUT_FILE, index=False)

print("access_type distribution:")
print(df["access_type"].value_counts().to_string())
print("\naccess_company distribution (competitor rows only):")
comp = df[df["access_type"] == "competitor"]
print(comp["access_company"].value_counts().to_string())
print(f"\nSaved: {INPUT_FILE}")
