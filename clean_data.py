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
    pip install pandas
"""

import re
import os
import math
import pandas as pd

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE = os.path.dirname(os.path.abspath(__file__))
FILE_2024 = os.path.join(BASE, "CSI_data_2024.csv")
FILE_2025 = os.path.join(BASE, "CSI_data_2025.csv")
OUTPUT    = os.path.join(BASE, "CSI_data_combined.csv")
DUPLICATE_REVIEW_OUTPUT = os.path.join(BASE, "duplicate_project_review.csv")


def _distance_miles(lat1, lon1, lat2, lon2):
    """Great-circle distance in miles; avoids requiring geopy for this script."""
    radius_miles = 3958.8
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = (
        math.sin(dphi / 2) ** 2
        + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    )
    return 2 * radius_miles * math.atan2(math.sqrt(a), math.sqrt(1 - a))


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
        dist = _distance_miles(row["_lat"], row["_lon"], c["c_lat"], c["c_lon"])
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
# CHANGE 10 — Extract typed project identifiers from PROJECT
# ===========================================================================
STATE_FEDERAL_PREFIX = (
    r"BRO-B|BRO|BRF-B|BRF|BRJ|BRP-BRC|BRC|BW|ARP|ER\d{2}|"
    r"NHU|NH|IM|PT|SS|SC|SU|UGP|TAC|TAU|AC-NHU|HEU-CPU|"
    r"SFP|FSX|TWP|HES|RAI-HES|RBD-XA-SS|RON|EM|P-PH|PH|P"
)

ID_PATTERNS = [
    ("CSI_JOB", "csi_job_id", re.compile(r"\bJOB\s*#?\s*(\d{5})\b", re.IGNORECASE)),
    ("STATE_FEDERAL", "state_federal_project_id", re.compile(r"\b((?:SAP|SP)\s*#?\s*\d{2,4}\s*-\s*\d{1,4}(?:\s*-\s*\d{1,4})?)\b", re.IGNORECASE)),
    ("STATE_FEDERAL", "state_federal_project_id", re.compile(r"\b(SAP'?S?\s+\d{2,4}\s*-\s*\d{1,4}(?:\s*-\s*\d{1,4})?)\b", re.IGNORECASE)),
    ("STATE_FEDERAL", "state_federal_project_id", re.compile(r"\b(SP\s+[A-Z]\d{4,}-\d{1,4}(?:\s*&\s*\d{1,4})?)\b", re.IGNORECASE)),
    ("STATE_FEDERAL", "state_federal_project_id", re.compile(r"\b((?:" + STATE_FEDERAL_PREFIX + r")(?:-[A-Z]{1,5})*\s*[- ]?\s*\d[-A-Z0-9(), ]*)\b", re.IGNORECASE)),
    ("CONTRACT_ID", "contract_id", re.compile(r"\bCONT(?:RACT)?\s*ID\s*#?\s*(\d{5,6})\b", re.IGNORECASE)),
    ("CONTRACT_ID", "contract_id", re.compile(r"\bCONT(?:RACT)?\s+NO\.?\s*([A-Z0-9-]{4,})\b", re.IGNORECASE)),
    ("PCN", "state_federal_project_id", re.compile(r"\b(PCN\s+[A-Z0-9]{3,5})\b", re.IGNORECASE)),
    ("COUNTY_PROJECT", "local_project_id", re.compile(r"\b(CP\s*-?\s*(?:\d{2,4}(?:[-(][A-Z0-9).]+)+|[A-Z]{2,}\d+[A-Z0-9.-]*))\b", re.IGNORECASE)),
    ("COUNTY_PROJECT", "local_project_id", re.compile(r"\b(CP\s*#?\s*\d{2,5}[A-Z0-9:-]*(?:,\s*CP\s*\d{2,5}[A-Z0-9:-]*)*)\b", re.IGNORECASE)),
    ("AIP", "local_project_id", re.compile(r"\bAIP\s*(?:NO\.?\s*)?#?\s*([0-9][-0-9/]+(?:-\d{4})?)\b", re.IGNORECASE)),
    ("AIP", "local_project_id", re.compile(r"\bAIG\s*(?:NO\.?\s*)?#?\s*([0-9][-0-9/ &]+(?:-\d{4})?)\b", re.IGNORECASE)),
    ("IOWA_CALL", "local_project_id", re.compile(r"\b(CALL\s+\d+\s+\d{2,3}-[A-Z0-9-]+)\b", re.IGNORECASE)),
    ("IOWA_CALL", "local_project_id", re.compile(r"\b(CALL\s+(?:NO\.?\s*)?\d+\s+(?:\d{2,3}-[A-Z0-9-]+|[A-Z]{1,6}-?[A-Z0-9]*\d[A-Z0-9().-]*(?:--?\d{1,3})?))\b", re.IGNORECASE)),
    ("LOCAL_OWNER_CODE", "local_project_id", re.compile(r"\b(ID\s+\d{2,3}-[A-Z0-9-]+)\b", re.IGNORECASE)),
    ("LOCAL_OWNER_CODE", "local_project_id", re.compile(r"\b(P\.?I\.?\s*NO\.?\s*[A-Z0-9.-]*\d[A-Z0-9.-]*)\b", re.IGNORECASE)),
    ("LOCAL_OWNER_CODE", "local_project_id", re.compile(r"\b(PROJ(?:ECT)?\.?\s*(?:(?:NO\.?|#)\s*)?[A-Z0-9][A-Z0-9.-]*(?:\s+[A-Z0-9][A-Z0-9.-]*){0,2}\s*\d[A-Z0-9.-]*)\b", re.IGNORECASE)),
    ("LOCAL_OWNER_CODE", "local_project_id", re.compile(r"\b((?:BMI|MBI)\s*(?:PROJ(?:ECT)?\s*)?(?:NO\.?|#)?\s*[A-Z0-9.]+\d[A-Z0-9.]*)\b", re.IGNORECASE)),
    ("LOCAL_OWNER_CODE", "local_project_id", re.compile(r"\b((?:CIP|ST|BR|NR|PH|PN|PR|WC|EC)\d{0,2}-[A-Z0-9][A-Z0-9-]*|WC\d{2}-[A-Z0-9]+|EC\d{2}-\d+)\b", re.IGNORECASE)),
    ("LOCAL_OWNER_CODE", "local_project_id", re.compile(r"(?<!ITEM )(?<!ITEM #)(#\d{3,6}\b|\b(?!(?:US|TH|ND|SD|IA|MN|CR|CSAH|HWY)\d)[A-Z]{2,6}\d{2,}[A-Z0-9.-]*\b|\b(?!(?:US|TH|ND|SD|IA|MN|CR|CSAH|HWY)-)[A-Z]{2,6}-\d{2,}[A-Z0-9().-]*\b)", re.IGNORECASE)),
]

ID_PRIORITY = {
    "CSI_JOB": 1,
    "STATE_FEDERAL": 2,
    "CONTRACT_ID": 3,
    "PCN": 4,
    "COUNTY_PROJECT": 5,
    "AIP": 6,
    "IOWA_CALL": 7,
    "LOCAL_OWNER_CODE": 8,
}


def _normalize_project_id(value):
    value = re.sub(r"\s+", " ", str(value)).strip(" -,.")
    value = re.split(
        r"\s+-\s+|\s+(?:GRADING|GRADE|STRUCTURE|REMOVE|REMOVAL|BIT|HMA|"
        r"ASPHALT|MILL|PCC|SURFACING|RECONSTRUCTION|RECONST|COLD|BOX|"
        r"CURB|FIELD|APPROACH|INTERSECTION|PIPE|SHARED|ROADWAY|BRIDGE|"
        r"SD\b|ND\b|US\b|I\b|CR\b|CSAH\b|TH\b|HWY\b)",
        value,
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0].strip(" -,.")
    value = re.sub(r"\s*-\s*", "-", value)
    return value.upper()


def _overlaps(span, spans):
    start, end = span
    return any(start < used_end and end > used_start for used_start, used_end in spans)


def _extract_project_ids(text):
    if pd.isnull(text):
        return []

    project = str(text)
    matches = []
    used_spans = []

    for project_id_type, target_field, pattern in ID_PATTERNS:
        for m in pattern.finditer(project):
            if _overlaps(m.span(), used_spans):
                continue

            raw = m.group(0).strip()
            value = m.group(1).strip() if m.lastindex else raw
            if value.count("(") > value.count(")") and m.end() < len(project) and project[m.end()] == ")":
                raw += ")"
                value += ")"
            normalized = _normalize_project_id(value)
            if len(normalized) < 3:
                continue

            matches.append({
                "type": project_id_type,
                "field": target_field,
                "raw": raw,
                "value": normalized,
                "priority": ID_PRIORITY[project_id_type],
                "span": m.span(),
            })
            used_spans.append(m.span())

    unique = []
    seen = set()
    for match in sorted(matches, key=lambda x: (x["priority"], x["span"][0])):
        key = (match["type"], match["value"])
        if key not in seen:
            unique.append(match)
            seen.add(key)
    return unique


def _ids_for_field(matches, field):
    values = [m["value"] for m in matches if m["field"] == field]
    return "; ".join(values) if values else None


def _primary_id(matches):
    if not matches:
        return None
    return matches[0]


def extract_identifiers(df):
    extracted = df["PROJECT"].apply(_extract_project_ids)
    primary = extracted.apply(_primary_id)

    df["csi_job_id"] = extracted.apply(lambda ids: _ids_for_field(ids, "csi_job_id"))
    df["state_federal_project_id"] = extracted.apply(lambda ids: _ids_for_field(ids, "state_federal_project_id"))
    df["contract_id"] = extracted.apply(lambda ids: _ids_for_field(ids, "contract_id"))
    df["local_project_id"] = extracted.apply(lambda ids: _ids_for_field(ids, "local_project_id"))

    # Backward-compatible alias used by earlier analysis files.
    df["state_project_id"] = df["state_federal_project_id"]

    df["project_id_type"] = primary.apply(lambda x: x["type"] if x else None)
    df["project_id_raw"] = primary.apply(lambda x: x["raw"] if x else None)
    df["primary_project_id"] = primary.apply(lambda x: x["value"] if x else None)
    df["secondary_project_ids"] = extracted.apply(
        lambda ids: "; ".join(f'{m["type"]}:{m["value"]}' for m in ids[1:]) if len(ids) > 1 else None
    )
    return df


# ===========================================================================
# CHANGE 11 — Add composite keys and duplicate review flags
# ===========================================================================
def _normalize_key_text(value):
    if pd.isnull(value):
        return ""
    text = str(value).upper()
    text = re.sub(r"\(MOVED FROM[^)]*\)", " ", text)
    text = re.sub(r"[^A-Z0-9]+", " ", text)
    text = re.sub(
        r"\b(PROJECT|PROJ|IMPROVEMENTS|IMPROVEMENT|CONSTRUCTION|"
        r"RECONSTRUCTION|REHABILITATION|REPAIR|THE|AND)\b",
        " ",
        text,
    )
    return re.sub(r"\s+", " ", text).strip()


def _normalize_duplicate_text(value):
    text = _normalize_key_text(value)
    text = re.sub(r"\b20\d{2}\b", " YEAR ", text)
    text = re.sub(r"\bITEM\s*#?\s*\d+\b", " ITEM ", text)
    text = re.sub(r"\bPHASE\s*\d+\b", " PHASE ", text)
    text = re.sub(r"\bPART\s+[A-Z]\b", " PART ", text)
    text = re.sub(r"\b(NO|DIST|DISTRICT|ETC)\b", " ", text)
    tokens = [t for t in re.sub(r"\s+", " ", text).strip().split(" ") if len(t) > 2]
    return " ".join(tokens[:10])


def add_composite_keys(df):
    location_part = (
        df["State"].fillna("").astype(str).str.upper().str.strip()
        + "|"
        + df["County"].fillna("").astype(str).str.upper().str.strip()
        + "|"
        + df["City"].fillna("").astype(str).str.upper().str.strip()
    )
    project_part = df["PROJECT"].apply(_normalize_key_text)

    df["strict_key"] = (
        df["DATE"].fillna("").astype(str).str.strip()
        + "|"
        + location_part
        + "|"
        + project_part
    )
    df["project_group_key"] = location_part + "|" + project_part
    df["duplicate_match_key"] = location_part + "|" + df["PROJECT"].apply(_normalize_duplicate_text)

    group_sizes = df.groupby("duplicate_match_key")["PROJECT"].transform("size")
    date_counts = df.groupby("duplicate_match_key")["DATE"].transform("nunique")
    year_counts = df.groupby("duplicate_match_key")["bid_year"].transform("nunique")
    id_counts = df.groupby("primary_project_id", dropna=True)["PROJECT"].transform("size")

    df["duplicate_candidate"] = (
        (df["duplicate_match_key"].str.len() > 5)
        & (group_sizes > 1)
        & ((date_counts > 1) | (year_counts > 1) | (id_counts > 1))
    )
    df["duplicate_match_reason"] = None
    df.loc[df["duplicate_candidate"] & (year_counts > 1), "duplicate_match_reason"] = "same project_group_key across bid years"
    df.loc[df["duplicate_candidate"] & (year_counts <= 1), "duplicate_match_reason"] = "same project_group_key across dates"
    df.loc[df["duplicate_candidate"] & (id_counts > 1), "duplicate_match_reason"] = "same extracted ID or loose project key"
    return df


def write_duplicate_review(df):
    review_cols = [
        "bid_year", "DATE", "LOCATION", "PROJECT", "primary_project_id",
        "project_id_type", "project_id_raw", "project_group_key",
        "duplicate_match_key", "duplicate_match_reason"
    ]
    review = df[df["duplicate_candidate"]].copy()
    review.insert(0, "record_id", review.index)
    review = review[["record_id"] + review_cols].sort_values(
        ["project_group_key", "DATE", "record_id"]
    )
    review["decision"] = ""
    review.to_csv(DUPLICATE_REVIEW_OUTPUT, index=False)
    return df


# ===========================================================================
# CHANGE 12 — Convert PREVAILING WAGES YES/NO → 1/0
# ===========================================================================
def clean_prevailing_wages(df):
    mapping = {"YES": 1, "NO": 0}
    df["PREVAILING WAGES"] = df["PREVAILING WAGES"].str.strip().str.upper().map(mapping)
    return df


# ===========================================================================
# CHANGE 13 — Convert material columns from string to float
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
# CHANGE 14 — Convert BOX from X/null → 1/0
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

    print("Step 10: Extracting typed project identifiers...")
    df = extract_identifiers(df)

    print("Step 11: Adding composite keys and duplicate flags...")
    df = add_composite_keys(df)
    df = write_duplicate_review(df)

    print("Step 12: Converting PREVAILING WAGES to 1/0...")
    df = clean_prevailing_wages(df)

    print("Step 13: Converting material columns to float...")
    df = clean_material_columns(df)

    print("Step 14: Converting BOX to 1/0...")
    df = clean_box(df)

    df.to_csv(OUTPUT, index=False)
    print(f"\nDone. Output saved to: {OUTPUT}")
    print(f"Duplicate review table saved to: {DUPLICATE_REVIEW_OUTPUT}")
    print(f"Final shape: {df.shape[0]} rows × {df.shape[1]} columns")


if __name__ == "__main__":
    main()
