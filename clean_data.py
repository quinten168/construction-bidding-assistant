"""
clean_data.py
=============
Reproduces every step documented in CHANGELOG.md for CSI_data_combined.csv.

Usage:
    python clean_data.py

Inputs  (same folder):
    CSI_data_2024.csv
    CSI_data_2025.csv

Output:
    CSI_data_combined.csv   (overwritten with all changes applied)

Dependencies:
    pip install pandas geopy
"""

import re
import os
import pandas as pd
from geopy.distance import geodesic

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE = os.path.dirname(os.path.abspath(__file__))
FILE_2024 = os.path.join(BASE, "CSI_data_2024.csv")
FILE_2025 = os.path.join(BASE, "CSI_data_2025.csv")
OUTPUT    = os.path.join(BASE, "CSI_data_combined.csv")


# ===========================================================================
# CHANGE 1 & 2 & 3  — Combine files, add bid_year, drop source column
# ===========================================================================
def combine_files(f2024, f2025):
    df24 = pd.read_csv(f2024, low_memory=False)
    df25 = pd.read_csv(f2025, low_memory=False)
    df24["bid_year"] = 2024
    df25["bid_year"] = 2025
    df = pd.concat([df24, df25], ignore_index=True)
    if "source" in df.columns:
        df = df.drop(columns=["source"])
    return df


# ===========================================================================
# CHANGE 4 — Reformat DATE to YYYY-MM-DD
# ===========================================================================
def clean_date(df):
    df["DATE"] = pd.to_datetime(df["DATE"], errors="coerce").dt.strftime("%Y-%m-%d")
    return df


# ===========================================================================
# CHANGE 5 — Reformat TIME to 24-hour HH:MM
# ===========================================================================
def _parse_time(t):
    if pd.isnull(t):
        return None
    t = str(t).strip()
    # Strip timezone labels and extra seconds
    t = re.sub(r'\s*(MDT|MST|MTD|MT)\b', '', t, flags=re.IGNORECASE).strip()
    t = re.sub(r'(\d{1,2}:\d{2}):\d{2}', r'\1', t)  # 10:00:00 AM → 10:00 AM
    # Handle bare "H:MM" with no AM/PM — assume PM if hour <= 8
    if re.match(r'^\d{1,2}:\d{2}$', t):
        hour = int(t.split(':')[0])
        suffix = 'PM' if hour <= 8 else 'AM'
        t = f"{t} {suffix}"
    try:
        return pd.to_datetime(t, format='%I:%M %p').strftime('%H:%M')
    except Exception:
        try:
            return pd.to_datetime(t).strftime('%H:%M')
        except Exception:
            return None

def clean_time(df):
    df["TIME"] = df["TIME"].apply(_parse_time)
    return df


# ===========================================================================
# CHANGE 6 — Parse LOCATION into County, City, State
# ===========================================================================
STATE_ABBR = {
    'AL':'Alabama','AK':'Alaska','AZ':'Arizona','AR':'Arkansas','CA':'California',
    'CO':'Colorado','CT':'Connecticut','DE':'Delaware','FL':'Florida','GA':'Georgia',
    'HI':'Hawaii','ID':'Idaho','IL':'Illinois','IN':'Indiana','IA':'Iowa',
    'KS':'Kansas','KY':'Kentucky','LA':'Louisiana','ME':'Maine','MD':'Maryland',
    'MA':'Massachusetts','MI':'Michigan','MN':'Minnesota','MS':'Mississippi',
    'MO':'Missouri','MT':'Montana','NE':'Nebraska','NV':'Nevada','NH':'New Hampshire',
    'NJ':'New Jersey','NM':'New Mexico','NY':'New York','NC':'North Carolina',
    'ND':'North Dakota','OH':'Ohio','OK':'Oklahoma','OR':'Oregon','PA':'Pennsylvania',
    'RI':'Rhode Island','SC':'South Carolina','SD':'South Dakota','TN':'Tennessee',
    'TX':'Texas','UT':'Utah','VT':'Vermont','VA':'Virginia','WA':'Washington',
    'WV':'West Virginia','WI':'Wisconsin','WY':'Wyoming',
}

# Manual overrides for rows where state abbreviation was missing in raw data
MANUAL_OVERRIDES = {
    'Kenmare':    'North Dakota',
    'Collegeville': 'Minnesota',
    'Alexander':  'North Dakota',
}

def _parse_location(loc):
    """Returns (county_str, city_str, state_str) from a raw LOCATION value."""
    if pd.isnull(loc):
        return None, None, None

    text = str(loc).strip()

    # Strip parenthetical notes like (MOVED FROM 08/03/23)
    text = re.sub(r'\(.*?\)', '', text).strip()

    # Extract state abbreviation (last 2-letter all-caps token)
    state = None
    m = re.search(r'\b([A-Z]{2})\s*$', text)
    if m and m.group(1) in STATE_ABBR:
        state = STATE_ABBR[m.group(1)]
        text = text[:m.start()].strip().rstrip(',').strip()

    # Extract city from "CITY OF X" or "- CITY" patterns
    city = None
    city_m = re.search(r'CITY\s+OF\s+([A-Z\s]+?)(?:,|$)', text, re.IGNORECASE)
    if city_m:
        city = city_m.group(1).strip().title()
        text = text[:city_m.start()].strip().rstrip('-').strip()
    else:
        city_m2 = re.search(r',\s*CITY\s+OF\s+([A-Z\s]+?)$', text, re.IGNORECASE)
        if city_m2:
            city = city_m2.group(1).strip().title()
            text = text[:city_m2.start()].strip()
        else:
            # "- CITY OF MANDAN" style at end
            city_m3 = re.search(r'-\s*CITY\s+OF\s+([A-Z\s]+?)$', text, re.IGNORECASE)
            if city_m3:
                city = city_m3.group(1).strip().title()
                text = text[:city_m3.start()].strip()

    # Extract city from "CITY, MANDAN" trailing pattern
    if city is None:
        city_m4 = re.search(r',\s*(CITY\s+OF\s+)?([A-Z][A-Z\s]+)$', text, re.IGNORECASE)
        if city_m4 and 'CO' not in city_m4.group(0).upper().split():
            possible_city = city_m4.group(2).strip().title()
            # Only treat as city if it doesn't look like a county name
            if not re.search(r'\bCO\b|\bCOUNTY\b', possible_city, re.IGNORECASE):
                city = possible_city
                text = text[:city_m4.start()].strip()

    # Apply manual override for state if still None
    if state is None:
        for keyword, state_name in MANUAL_OVERRIDES.items():
            if keyword.lower() in text.lower() or (city and keyword.lower() in city.lower()):
                state = state_name
                break

    # Remaining text is the county (may be multi-county)
    county_raw = re.sub(r'\s+', ' ', text).strip().rstrip(',').strip()
    # Normalize county names: strip " CO" suffix for cleanliness but keep full string
    county = county_raw if county_raw else None

    return county, city, state

def parse_location(df):
    parsed = df["LOCATION"].apply(_parse_location)
    df["County"] = [p[0] for p in parsed]
    df["City"]   = [p[1] for p in parsed]
    df["State"]  = [p[2] for p in parsed]
    return df


# ===========================================================================
# CHANGE 7 — Move bid_year to first column
# ===========================================================================
def reorder_columns(df):
    cols = ["bid_year"] + [c for c in df.columns if c != "bid_year"]
    return df[cols]


# ===========================================================================
# CHANGE 8 — Add location_flag (county centroid distance method)
# ===========================================================================
def add_location_flag(df):
    # Parse lat/lon temporarily for flagging (PROJECT LOCATION not yet split)
    def _parse_latlon(s):
        if pd.isnull(s):
            return None, None
        m = re.match(r'\s*([\-\d\.]+)\s*,\s*([\-\d\.]+)\s*', str(s))
        if m:
            return float(m.group(1)), float(m.group(2))
        return None, None

    coords = df["PROJECT LOCATION"].apply(_parse_latlon)
    df["_lat"] = [c[0] for c in coords]
    df["_lon"] = [c[1] for c in coords]

    # Identify multi-county rows
    multi = df["County"].apply(lambda x: bool(x and ',' in str(x)))

    # Build centroids from single-county rows only
    single = df[~multi & df["_lat"].notna() & df["County"].notna()].copy()
    centroids = (
        single.groupby("County")[["_lat", "_lon"]]
        .median()
        .rename(columns={"_lat": "c_lat", "_lon": "c_lon"})
    )

    def _flag(row):
        if pd.isnull(row["County"]):
            return "no_centroid"
        if multi[row.name]:
            return "multi_county"
        if pd.isnull(row["_lat"]):
            return "no_centroid"
        if row["County"] not in centroids.index:
            return "no_centroid"
        c = centroids.loc[row["County"]]
        dist = geodesic((row["_lat"], row["_lon"]), (c["c_lat"], c["c_lon"])).miles
        return "review" if dist > 75 else "ok"

    df["location_flag"] = df.apply(_flag, axis=1)
    df = df.drop(columns=["_lat", "_lon"])
    return df


# ===========================================================================
# CHANGE 9 — Split PROJECT LOCATION into Latitude and Longitude
# ===========================================================================
def split_project_location(df):
    def _lat(s):
        if pd.isnull(s): return None
        m = re.match(r'\s*([\-\d\.]+)\s*,', str(s))
        return float(m.group(1)) if m else None

    def _lon(s):
        if pd.isnull(s): return None
        m = re.match(r'[\-\d\.]+\s*,\s*([\-\d\.]+)', str(s))
        return float(m.group(1)) if m else None

    df["Latitude"]  = df["PROJECT LOCATION"].apply(_lat)
    df["Longitude"] = df["PROJECT LOCATION"].apply(_lon)
    return df


# ===========================================================================
# CHANGE 10 — Extract csi_job_id and state_project_id from PROJECT
# ===========================================================================
def extract_identifiers(df):
    def extract_csi_job_id(text):
        if pd.isnull(text): return None
        m = re.search(r'\bJOB\s+(\d{5})\b', str(text), re.IGNORECASE)
        return m.group(1) if m else None

    def extract_state_project_id(text):
        if pd.isnull(text): return None
        t = str(text)
        patterns = [
            r'SAP\s+[\d]+[\d\-]+[\d](?:(?:,\s*&?\s*SAP\s+[\d]+[\d\-]+[\d])*)?',
            r'CONTRACT\s+ID\s+\d+',
            r'\bSP\s+[\d]{3}-[\d][\d\-]+',
            r'\bIM[-\s][A-Z]?\s*[\d]+[\w\-\(\)]+',
            r'\bNH[-\s][A-Z]?\s*[\d]+[\w\-\(\)]+',
            r'\bBRJ[-\s][\w\-\(\)]+',
            r'\bBW-[\w\-\.]+',
            r'\bER\d{2}-[\w\-]+',
            r'\bARP[-\s][\w\-\(\)]+',
            r'\bPCN\s+[\w,\s]+?(?=\s+-|\s+ITEM|\s+COLD|\s+ASPH|\s+STRUCT|\s+LOW|$)',
        ]
        for pat in patterns:
            m = re.search(pat, t, re.IGNORECASE)
            if m:
                return m.group(0).strip().rstrip('-').strip()
        return None

    df["csi_job_id"]       = df["PROJECT"].apply(extract_csi_job_id)
    df["state_project_id"] = df["PROJECT"].apply(extract_state_project_id)
    return df


# ===========================================================================
# CHANGE 11 — Convert PREVAILING WAGES YES/NO → 1/0
# ===========================================================================
def clean_prevailing_wages(df):
    mapping = {"YES": 1, "NO": 0}
    df["PREVAILING WAGES"] = df["PREVAILING WAGES"].str.strip().str.upper().map(mapping)
    return df


# ===========================================================================
# CHANGE 12 — Convert material columns from string to float
# ===========================================================================
MATERIAL_COLS = ["MIX TN", "GRADE CY", "BASE TN", "SHLDR TN", "MILL SY", "CRUSH TN", "STOCK TN"]

def clean_material_columns(df):
    for col in MATERIAL_COLS:
        if col in df.columns:
            df[col] = (
                df[col].astype(str)
                .str.replace(",", "", regex=False)
                .str.strip()
                .replace({"nan": None, "": None, "None": None})
            )
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


# ===========================================================================
# CHANGE 13 — Convert BOX from X/null → 1/0
# ===========================================================================
def clean_box(df):
    df["BOX"] = df["BOX"].apply(lambda x: 1 if str(x).strip().upper() == "X" else 0)
    return df


# ===========================================================================
# MAIN — run all steps in order
# ===========================================================================
def main():
    print("Step 1-3: Combining files and adding bid_year...")
    df = combine_files(FILE_2024, FILE_2025)
    print(f"  → {len(df)} rows combined")

    print("Step 4: Cleaning DATE...")
    df = clean_date(df)

    print("Step 5: Cleaning TIME...")
    df = clean_time(df)

    print("Step 6: Parsing LOCATION into County / City / State...")
    df = parse_location(df)

    print("Step 7: Moving bid_year to first column...")
    df = reorder_columns(df)

    print("Step 8: Adding location_flag...")
    df = add_location_flag(df)

    print("Step 9: Splitting PROJECT LOCATION into Latitude / Longitude...")
    df = split_project_location(df)

    print("Step 10: Extracting csi_job_id and state_project_id...")
    df = extract_identifiers(df)

    print("Step 11: Converting PREVAILING WAGES to 1/0...")
    df = clean_prevailing_wages(df)

    print("Step 12: Converting material columns to float...")
    df = clean_material_columns(df)

    print("Step 13: Converting BOX to 1/0...")
    df = clean_box(df)

    df.to_csv(OUTPUT, index=False)
    print(f"\nDone. Output saved to: {OUTPUT}")
    print(f"Final shape: {df.shape[0]} rows × {df.shape[1]} columns")


if __name__ == "__main__":
    main()
