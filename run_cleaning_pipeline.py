#!/usr/bin/env python3
"""
Full cleaning pipeline for CSI_data_combined.csv.

Applies all passes documented in docs/CHANGELOG.md:
  Pass 1  — DATE, TIME, LOCATION, location_flag, Lat/Lon, PREVAILING WAGES, materials, BOX
  Pass 2  — Typed project ID extraction + composite keys + duplicate candidates
  Pass 3  — BIDDER name standardization (ampersand / whitespace) + BIDDER_*_TOTAL to float
  Pass 3c — Apply v1 bidder-name merges (38 variations → 19 groups)
  Pass 4  — Apply v2 bidder-name merges (134 variations → 58 groups) + delete ENGINEERS ESTIMATE
  Pass 3b — Pivot to long format
  Pass 5  — Apply v3 additional bidder-name merges (14 variations)

Inputs:
    data/processed/CSI_data_combined.csv          (raw combined, produced by combine step)
    data/cleaning_review/bidder_standardization_v1.csv
    data/cleaning_review/bidder_standardization_v2.csv
    data/cleaning_review/bidder_standardization_v3.csv

Outputs:
    data/processed/CSI_data_combined.csv          (wide format, fully cleaned)
    data/processed/CSI_data_long_format.csv       (long format, one row per bidder)
    data/cleaning_review/bidder_full_company_list.csv
    data/cleaning_review/duplicate_project_review.csv
"""

import re
import math
import pandas as pd

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
RAW_2024_FILE         = "data/raw/CSI_data_2024.csv"
RAW_2025_FILE         = "data/raw/CSI_data_2025.csv"
COMBINED_FILE         = "data/processed/CSI_data_combined.csv"
LONG_FORMAT_FILE      = "data/processed/CSI_data_long_format.csv"
COMPANY_LIST_FILE     = "data/cleaning_review/bidder_full_company_list.csv"
DUPLICATE_REVIEW_FILE = "data/cleaning_review/duplicate_project_review.csv"

BIDDER_MERGE_V1 = "data/cleaning_review/bidder_standardization_v1.csv"
BIDDER_MERGE_V2 = "data/cleaning_review/bidder_standardization_v2.csv"
BIDDER_MERGE_V3 = "data/cleaning_review/bidder_standardization_v3.csv"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _distance_miles(lat1, lon1, lat2, lon2):
    r = 3958.8
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.atan2(math.sqrt(a), math.sqrt(1 - a))


# ===========================================================================
# Pass 1a — DATE: reformat to YYYY-MM-DD
# ===========================================================================
def clean_date(df):
    df["DATE"] = pd.to_datetime(df["DATE"], errors="coerce").dt.strftime("%Y-%m-%d")
    return df


# ===========================================================================
# Pass 1b — TIME: reformat to 24-hour HH:MM
# ===========================================================================
def _parse_time(t):
    if pd.isnull(t):
        return None
    t = str(t).strip()
    t = re.sub(r"\s*(MDT|MST|MTD|MT)\b", "", t, flags=re.IGNORECASE).strip()
    t = re.sub(r"\(.*?\)", "", t).strip()               # strip parenthetical notes e.g. "(MT)"
    t = re.sub(r"(\d{1,2}:\d{2}):\d{2}", r"\1", t)    # strip extra seconds
    if re.match(r"^\d{1,2}:\d{2}$", t):
        hour = int(t.split(":")[0])
        t = f"{t} {'PM' if hour <= 8 else 'AM'}"
    try:
        return pd.to_datetime(t, format="%I:%M %p").strftime("%H:%M")
    except Exception:
        try:
            return pd.to_datetime(t).strftime("%H:%M")
        except Exception:
            return None


def clean_time(df):
    df["TIME"] = df["TIME"].apply(_parse_time)
    return df


# ===========================================================================
# Pass 1c — LOCATION: parse into County, City, State
# ===========================================================================
STATE_ABBR = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas",
    "CA": "California", "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware",
    "FL": "Florida", "GA": "Georgia", "HI": "Hawaii", "ID": "Idaho",
    "IL": "Illinois", "IN": "Indiana", "IA": "Iowa", "KS": "Kansas",
    "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MD": "Maryland",
    "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota", "MS": "Mississippi",
    "MO": "Missouri", "MT": "Montana", "NE": "Nebraska", "NV": "Nevada",
    "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York",
    "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma",
    "OR": "Oregon", "PA": "Pennsylvania", "RI": "Rhode Island", "SC": "South Carolina",
    "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas", "UT": "Utah",
    "VT": "Vermont", "VA": "Virginia", "WA": "Washington", "WV": "West Virginia",
    "WI": "Wisconsin", "WY": "Wyoming",
}

MANUAL_OVERRIDES = {
    "Kenmare": "North Dakota",
    "Collegeville": "Minnesota",
    "Alexander": "North Dakota",
}


def _parse_location(loc):
    if pd.isnull(loc):
        return None, None, None
    text = re.sub(r"\(.*?\)", "", str(loc)).strip()

    # Try state at end of string (simple case: "STEARNS CO MN")
    state = None
    m = re.search(r"\b([A-Z]{2})\s*$", text)
    if m and m.group(1) in STATE_ABBR:
        state = STATE_ABBR[m.group(1)]
        text = text[: m.start()].strip().rstrip(",").strip()

    city = None
    for pattern in [
        r"CITY\s+OF\s+([A-Z\s]+?)(?:,|$)",
        r",\s*CITY\s+OF\s+([A-Z\s]+?)$",
        r"-\s*CITY\s+OF\s+([A-Z\s]+?)$",
    ]:
        cm = re.search(pattern, text, re.IGNORECASE)
        if cm:
            city = cm.group(1).strip().title()
            text = text[: cm.start()].strip().rstrip("-,").strip()
            break

    if city is None:
        # Trailing ", CITYNAME" or "- CITYNAME" — but stop before consuming state-embedded segments
        cm = re.search(r"[,\-]\s*([A-Z][A-Z\s]+)$", text, re.IGNORECASE)
        if cm:
            possible = cm.group(1).strip()
            # Don't treat CO/COUNTY or known state abbreviations as city
            if (not re.search(r"\bCO\b|\bCOUNTY\b", possible, re.IGNORECASE)
                    and possible.upper() not in STATE_ABBR):
                city = possible.title()
                text = text[: cm.start()].strip()

    # Fallback 1: state at end of remaining text after city extraction
    # Handles "GRAND FORKS ND, CITY OF GRAND FORKS" → after city: text="GRAND FORKS ND"
    if state is None:
        m2 = re.search(r"\b([A-Z]{2})\s*$", text)
        if m2 and m2.group(1) in STATE_ABBR:
            state = STATE_ABBR[m2.group(1)]
            text = text[: m2.start()].strip().rstrip(",").strip()

    # Fallback 2: state embedded as "CO MN" inside county string (e.g. "STEARNS CO MN, MELROSE")
    if state is None:
        m3 = re.search(r"\b(?:CO|COUNTY)\s+([A-Z]{2})\b", text, re.IGNORECASE)
        if m3 and m3.group(1).upper() in STATE_ABBR:
            state = STATE_ABBR[m3.group(1).upper()]
            text = (text[: m3.start(1)] + text[m3.end(1):]).strip().rstrip(",- ").strip()

    if state is None:
        for kw, sn in MANUAL_OVERRIDES.items():
            if kw.lower() in text.lower() or (city and kw.lower() in city.lower()):
                state = sn
                break

    county = re.sub(r"\s+", " ", text).strip().rstrip(",").strip() or None
    return county, city, state


def parse_location(df):
    parsed = df["LOCATION"].apply(_parse_location)
    df["County"] = [p[0] for p in parsed]
    df["City"]   = [p[1] for p in parsed]
    df["State"]  = [p[2] for p in parsed]
    return df


# ===========================================================================
# Pass 1d — location_flag (county centroid method, 75-mile threshold)
# ===========================================================================
def add_location_flag(df):
    def _parse_latlon(s):
        if pd.isnull(s):
            return None, None
        m = re.match(r"\s*([\-\d\.]+)\s*,\s*([\-\d\.]+)\s*", str(s))
        return (float(m.group(1)), float(m.group(2))) if m else (None, None)

    coords = df["PROJECT LOCATION"].apply(_parse_latlon)
    df["_lat"] = [c[0] for c in coords]
    df["_lon"] = [c[1] for c in coords]

    multi = df["County"].apply(lambda x: bool(x and "," in str(x)))
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
        return "review" if _distance_miles(row["_lat"], row["_lon"], c["c_lat"], c["c_lon"]) > 75 else "ok"

    df["location_flag"] = df.apply(_flag, axis=1)
    df = df.drop(columns=["_lat", "_lon"])
    return df


# ===========================================================================
# Pass 1e — Split PROJECT LOCATION into Latitude / Longitude
# ===========================================================================
def split_project_location(df):
    def _lat(s):
        if pd.isnull(s): return None
        m = re.match(r"\s*([\-\d\.]+)\s*,", str(s))
        return float(m.group(1)) if m else None

    def _lon(s):
        if pd.isnull(s): return None
        m = re.match(r"[\-\d\.]+\s*,\s*([\-\d\.]+)", str(s))
        return float(m.group(1)) if m else None

    df["Latitude"]  = df["PROJECT LOCATION"].apply(_lat)
    df["Longitude"] = df["PROJECT LOCATION"].apply(_lon)
    return df


# ===========================================================================
# Pass 2 — Typed project ID extraction + composite keys + duplicate candidates
# ===========================================================================
STATE_FEDERAL_PREFIX = (
    r"BRO-B|BRO|BRF-B|BRF|BRJ|BRP-BRC|BRC|BW|ARP|ER\d{2}|"
    r"NHU|NH|IM|PT|SS|SC|SU|UGP|TAC|TAU|AC-NHU|HEU-CPU|"
    r"SFP|FSX|TWP|HES|RAI-HES|RBD-XA-SS|RON|EM|P-PH|PH|P"
)

ID_PATTERNS = [
    ("CSI_JOB",         "csi_job_id",             re.compile(r"\bJOB\s*#?\s*(\d{5})\b", re.IGNORECASE)),
    ("STATE_FEDERAL",   "state_federal_project_id", re.compile(r"\b((?:SAP|SP)\s*#?\s*\d{2,4}\s*-\s*\d{1,4}(?:\s*-\s*\d{1,4})?)\b", re.IGNORECASE)),
    ("STATE_FEDERAL",   "state_federal_project_id", re.compile(r"\b(SAP'?S?\s+\d{2,4}\s*-\s*\d{1,4}(?:\s*-\s*\d{1,4})?)\b", re.IGNORECASE)),
    ("STATE_FEDERAL",   "state_federal_project_id", re.compile(r"\b(SP\s+[A-Z]\d{4,}-\d{1,4}(?:\s*&\s*\d{1,4})?)\b", re.IGNORECASE)),
    ("STATE_FEDERAL",   "state_federal_project_id", re.compile(r"\b((?:" + STATE_FEDERAL_PREFIX + r")(?:-[A-Z]{1,5})*\s*[- ]?\s*\d[-A-Z0-9(), ]*)\b", re.IGNORECASE)),
    ("CONTRACT_ID",     "contract_id",             re.compile(r"\bCONT(?:RACT)?\s*ID\s*#?\s*(\d{5,6})\b", re.IGNORECASE)),
    ("CONTRACT_ID",     "contract_id",             re.compile(r"\bCONT(?:RACT)?\s+NO\.?\s*([A-Z0-9-]{4,})\b", re.IGNORECASE)),
    ("PCN",             "state_federal_project_id", re.compile(r"\b(PCN\s+[A-Z0-9]{3,5})\b", re.IGNORECASE)),
    ("COUNTY_PROJECT",  "local_project_id",        re.compile(r"\b(CP\s*-?\s*(?:\d{2,4}(?:[-(][A-Z0-9).]+)+|[A-Z]{2,}\d+[A-Z0-9.-]*))\b", re.IGNORECASE)),
    ("COUNTY_PROJECT",  "local_project_id",        re.compile(r"\b(CP\s*#?\s*\d{2,5}[A-Z0-9:-]*(?:,\s*CP\s*\d{2,5}[A-Z0-9:-]*)*)\b", re.IGNORECASE)),
    ("AIP",             "local_project_id",        re.compile(r"\bAIP\s*(?:NO\.?\s*)?#?\s*([0-9][-0-9/]+(?:-\d{4})?)\b", re.IGNORECASE)),
    ("AIP",             "local_project_id",        re.compile(r"\bAIG\s*(?:NO\.?\s*)?#?\s*([0-9][-0-9/ &]+(?:-\d{4})?)\b", re.IGNORECASE)),
    ("IOWA_CALL",       "local_project_id",        re.compile(r"\b(CALL\s+\d+\s+\d{2,3}-[A-Z0-9-]+)\b", re.IGNORECASE)),
    ("IOWA_CALL",       "local_project_id",        re.compile(r"\b(CALL\s+(?:NO\.?\s*)?\d+\s+(?:\d{2,3}-[A-Z0-9-]+|[A-Z]{1,6}-?[A-Z0-9]*\d[A-Z0-9().-]*(?:--?\d{1,3})?))\b", re.IGNORECASE)),
    ("LOCAL_OWNER_CODE","local_project_id",        re.compile(r"\b(ID\s+\d{2,3}-[A-Z0-9-]+)\b", re.IGNORECASE)),
    ("LOCAL_OWNER_CODE","local_project_id",        re.compile(r"\b(P\.?I\.?\s*NO\.?\s*[A-Z0-9.-]*\d[A-Z0-9.-]*)\b", re.IGNORECASE)),
    ("LOCAL_OWNER_CODE","local_project_id",        re.compile(r"\b(PROJ(?:ECT)?\.?\s*(?:(?:NO\.?|#)\s*)?[A-Z0-9][A-Z0-9.-]*(?:\s+[A-Z0-9][A-Z0-9.-]*){0,2}\s*\d[A-Z0-9.-]*)\b", re.IGNORECASE)),
    ("LOCAL_OWNER_CODE","local_project_id",        re.compile(r"\b((?:BMI|MBI)\s*(?:PROJ(?:ECT)?\s*)?(?:NO\.?|#)?\s*[A-Z0-9.]+\d[A-Z0-9.]*)\b", re.IGNORECASE)),
    ("LOCAL_OWNER_CODE","local_project_id",        re.compile(r"\b((?:CIP|ST|BR|NR|PH|PN|PR|WC|EC)\d{0,2}-[A-Z0-9][A-Z0-9-]*|WC\d{2}-[A-Z0-9]+|EC\d{2}-\d+)\b", re.IGNORECASE)),
    ("LOCAL_OWNER_CODE","local_project_id",        re.compile(r"(?<!ITEM )(?<!ITEM #)(#\d{3,6}\b|\b(?!(?:US|TH|ND|SD|IA|MN|CR|CSAH|HWY)\d)[A-Z]{2,6}\d{2,}[A-Z0-9.-]*\b|\b(?!(?:US|TH|ND|SD|IA|MN|CR|CSAH|HWY)-)[A-Z]{2,6}-\d{2,}[A-Z0-9().-]*\b)", re.IGNORECASE)),
]

ID_PRIORITY = {
    "CSI_JOB": 1, "STATE_FEDERAL": 2, "CONTRACT_ID": 3, "PCN": 4,
    "COUNTY_PROJECT": 5, "AIP": 6, "IOWA_CALL": 7, "LOCAL_OWNER_CODE": 8,
}


def _normalize_project_id(value):
    value = re.sub(r"\s+", " ", str(value)).strip(" -,.")
    value = re.split(
        r"\s+-\s+|\s+(?:GRADING|GRADE|STRUCTURE|REMOVE|REMOVAL|BIT|HMA|"
        r"ASPHALT|MILL|PCC|SURFACING|RECONSTRUCTION|RECONST|COLD|BOX|"
        r"CURB|FIELD|APPROACH|INTERSECTION|PIPE|SHARED|ROADWAY|BRIDGE|"
        r"SD\b|ND\b|US\b|I\b|CR\b|CSAH\b|TH\b|HWY\b)",
        value, maxsplit=1, flags=re.IGNORECASE,
    )[0].strip(" -,.")
    return re.sub(r"\s*-\s*", "-", value).upper()


def _overlaps(span, spans):
    s, e = span
    return any(s < ue and e > us for us, ue in spans)


def _extract_project_ids(text):
    if pd.isnull(text):
        return []
    project = str(text)
    matches, used_spans = [], []
    for pid_type, target_field, pattern in ID_PATTERNS:
        for m in pattern.finditer(project):
            if _overlaps(m.span(), used_spans):
                continue
            raw = m.group(0).strip()
            value = m.group(1).strip() if m.lastindex else raw
            if value.count("(") > value.count(")") and m.end() < len(project) and project[m.end()] == ")":
                raw += ")"; value += ")"
            normalized = _normalize_project_id(value)
            if len(normalized) < 3:
                continue
            matches.append({"type": pid_type, "field": target_field, "raw": raw,
                            "value": normalized, "priority": ID_PRIORITY[pid_type], "span": m.span()})
            used_spans.append(m.span())

    unique, seen = [], set()
    for match in sorted(matches, key=lambda x: (x["priority"], x["span"][0])):
        key = (match["type"], match["value"])
        if key not in seen:
            unique.append(match); seen.add(key)
    return unique


def extract_identifiers(df):
    extracted = df["PROJECT"].apply(_extract_project_ids)
    primary   = extracted.apply(lambda ids: ids[0] if ids else None)

    def _ids_for(ids, field):
        vals = [m["value"] for m in ids if m["field"] == field]
        return "; ".join(vals) if vals else None

    df["csi_job_id"]             = extracted.apply(lambda ids: _ids_for(ids, "csi_job_id"))
    df["state_federal_project_id"] = extracted.apply(lambda ids: _ids_for(ids, "state_federal_project_id"))
    df["contract_id"]            = extracted.apply(lambda ids: _ids_for(ids, "contract_id"))
    df["local_project_id"]       = extracted.apply(lambda ids: _ids_for(ids, "local_project_id"))
    df["state_project_id"]       = df["state_federal_project_id"]
    df["project_id_type"]        = primary.apply(lambda x: x["type"]  if x else None)
    df["project_id_raw"]         = primary.apply(lambda x: x["raw"]   if x else None)
    df["primary_project_id"]     = primary.apply(lambda x: x["value"] if x else None)
    df["secondary_project_ids"]  = extracted.apply(
        lambda ids: "; ".join(f'{m["type"]}:{m["value"]}' for m in ids[1:]) if len(ids) > 1 else None
    )
    return df


def _norm_key(value):
    if pd.isnull(value):
        return ""
    text = re.sub(r"\(MOVED FROM[^)]*\)", " ", str(value).upper())
    text = re.sub(r"[^A-Z0-9]+", " ", text)
    text = re.sub(r"\b(PROJECT|PROJ|IMPROVEMENTS|IMPROVEMENT|CONSTRUCTION|"
                  r"RECONSTRUCTION|REHABILITATION|REPAIR|THE|AND)\b", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _norm_dup(value):
    text = _norm_key(value)
    text = re.sub(r"\b20\d{2}\b", " YEAR ", text)
    text = re.sub(r"\bITEM\s*#?\s*\d+\b", " ITEM ", text)
    text = re.sub(r"\bPHASE\s*\d+\b", " PHASE ", text)
    text = re.sub(r"\bPART\s+[A-Z]\b", " PART ", text)
    text = re.sub(r"\b(NO|DIST|DISTRICT|ETC)\b", " ", text)
    tokens = [t for t in re.sub(r"\s+", " ", text).strip().split() if len(t) > 2]
    return " ".join(tokens[:10])


def add_composite_keys(df):
    loc = (
        df["State"].fillna("").str.upper().str.strip() + "|"
        + df["County"].fillna("").str.upper().str.strip() + "|"
        + df["City"].fillna("").str.upper().str.strip()
    )
    proj_norm = df["PROJECT"].apply(_norm_key)

    df["strict_key"]         = df["DATE"].fillna("").str.strip() + "|" + loc + "|" + proj_norm
    df["project_group_key"]  = loc + "|" + proj_norm
    df["duplicate_match_key"] = loc + "|" + df["PROJECT"].apply(_norm_dup)

    group_sizes = df.groupby("duplicate_match_key")["PROJECT"].transform("size")
    date_counts = df.groupby("duplicate_match_key")["DATE"].transform("nunique")
    year_counts = df.groupby("duplicate_match_key")["bid_year"].transform("nunique")
    id_counts   = df.groupby("primary_project_id", dropna=True)["PROJECT"].transform("size")

    df["duplicate_candidate"] = (
        (df["duplicate_match_key"].str.len() > 5)
        & (group_sizes > 1)
        & ((date_counts > 1) | (year_counts > 1) | (id_counts > 1))
    )
    df["duplicate_match_reason"] = None
    df.loc[df["duplicate_candidate"] & (year_counts > 1),  "duplicate_match_reason"] = "same project_group_key across bid years"
    df.loc[df["duplicate_candidate"] & (year_counts <= 1), "duplicate_match_reason"] = "same project_group_key across dates"
    df.loc[df["duplicate_candidate"] & (id_counts > 1),    "duplicate_match_reason"] = "same extracted ID or loose project key"
    return df


def write_duplicate_review(df):
    review_cols = ["bid_year", "DATE", "LOCATION", "PROJECT", "primary_project_id",
                   "project_id_type", "project_id_raw", "project_group_key",
                   "duplicate_match_key", "duplicate_match_reason"]
    review = df[df["duplicate_candidate"]].copy()
    review.insert(0, "record_id", review.index)
    review = review[["record_id"] + review_cols].sort_values(["project_group_key", "DATE", "record_id"])
    review["decision"] = ""
    review.to_csv(DUPLICATE_REVIEW_FILE, index=False)
    print(f"    → duplicate review rows: {len(review)}")
    return df


# ===========================================================================
# Pass 1e — PREVAILING WAGES: YES/NO → 1/0
# ===========================================================================
def clean_prevailing_wages(df):
    df["PREVAILING WAGES"] = df["PREVAILING WAGES"].str.strip().str.upper().map({"YES": 1, "NO": 0})
    return df


# ===========================================================================
# Pass 1f — Material quantity columns: string → float
# ===========================================================================
MATERIAL_COLS = ["MIX TN", "GRADE CY", "BASE TN", "SHLDR TN", "MILL SY", "CRUSH TN", "STOCK TN"]

def clean_material_columns(df):
    for col in MATERIAL_COLS:
        if col in df.columns:
            df[col] = (
                df[col].astype(str).str.replace(",", "", regex=False).str.strip()
                .replace({"nan": None, "": None, "None": None})
            )
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


# ===========================================================================
# Pass 1g — BOX: X/null → 1/0
# ===========================================================================
def clean_box(df):
    df["BOX"] = df["BOX"].apply(lambda x: 1 if str(x).strip().upper() == "X" else 0)
    return df


# ===========================================================================
# Pass 3a — BIDDER_*_NAME: ampersand / whitespace / null normalization
# ===========================================================================
def _standardize_bidder_name(name):
    if pd.isnull(name):
        return None
    name = str(name).strip()
    if not name or name.upper() == "NAN":
        return None
    name = re.sub(r"\s+AND\s+", " & ", name, flags=re.IGNORECASE)
    name = re.sub(r"\s*&\s*", " & ", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name


def clean_bidder_names(df):
    for col in [c for c in df.columns if c.startswith("BIDDER_") and c.endswith("_NAME")]:
        df[col] = df[col].apply(_standardize_bidder_name)
    return df


# ===========================================================================
# Pass 3b — BIDDER_*_TOTAL: string → float  (handles "$" prefix and multi-amount cells)
# ===========================================================================
def _parse_bid_total(raw):
    """
    Parse a BIDDER_*_TOTAL cell to float.
    - Single amount: "$1,273,463.90" → 1273463.90
    - Multi-amount (breakdown + grand total): "$543,789 $160,972 $8,634 $713,396" →
        if last ≈ sum(others): use last (grand total)
        otherwise: use first (primary/base bid)
    - Trailing bare "$": "$ 814,163.64 $" → 814163.64
    """
    if pd.isnull(raw):
        return None
    s = str(raw).strip()
    if not s or s.lower() in ("nan", "none", ""):
        return None

    # Extract all numeric dollar amounts in order
    amounts = []
    for m in re.finditer(r"\$?\s*([\d,]+(?:\.\d+)?)", s):
        val_str = m.group(1).replace(",", "").strip()
        if val_str:
            try:
                amounts.append(float(val_str))
            except ValueError:
                pass

    if not amounts:
        return None
    if len(amounts) == 1:
        return amounts[0]

    # Multiple amounts: check if last equals sum of the rest (grand total pattern)
    last = amounts[-1]
    rest_sum = sum(amounts[:-1])
    if rest_sum > 0 and abs(last - rest_sum) / rest_sum < 0.01:
        return last     # last is confirmed grand total
    return amounts[0]   # fall back to primary/base bid (first amount)


def clean_bidder_totals(df):
    for col in [c for c in df.columns if c.startswith("BIDDER_") and c.endswith("_TOTAL")]:
        df[col] = df[col].apply(_parse_bid_total)
    return df


# ===========================================================================
# Name-merge passes — apply variation→core_name mappings to BIDDER_*_NAME cols
# ===========================================================================
def _apply_name_mapping(df, mapping):
    name_cols = [c for c in df.columns if c.startswith("BIDDER_") and c.endswith("_NAME")]
    replacements = 0
    for col in name_cols:
        mask = df[col].isin(mapping)
        replacements += mask.sum()
        df.loc[mask, col] = df.loc[mask, col].map(mapping)
    return df, replacements


def apply_v1_merges(df):
    v1 = pd.read_csv(BIDDER_MERGE_V1)
    mapping = dict(zip(v1["raw_value"], v1["standardized_value"]))
    df, n = _apply_name_mapping(df, mapping)
    print(f"    → Pass 3c (v1): {len(mapping)} mappings, {n} replacements")
    return df


def apply_v2_merges(df):
    v2 = pd.read_csv(BIDDER_MERGE_V2)
    merge_rows = v2[v2["client_decision"] == "MERGE"]
    mapping = dict(zip(merge_rows["variation"], merge_rows["core_name"]))
    df, n = _apply_name_mapping(df, mapping)
    print(f"    → Pass 4 (v2): {len(mapping)} mappings, {n} replacements")
    return df


def apply_v3_merges(df):
    v3 = pd.read_csv(BIDDER_MERGE_V3)
    merge_rows = v3[v3["your_decision"].str.lower() == "merge"]
    mapping = dict(zip(merge_rows["current_variation"], merge_rows["recommended_core_name"]))
    df, n = _apply_name_mapping(df, mapping)
    print(f"    → Pass 5 (v3): {len(mapping)} mappings, {n} replacements")
    return df


# ===========================================================================
# Pass 3b — Pivot wide → long (one row per bidder per project)
# ===========================================================================
def pivot_to_long_format(df):
    name_cols  = [c for c in df.columns if c.startswith("BIDDER_") and c.endswith("_NAME")]
    total_cols = [c for c in df.columns if c.startswith("BIDDER_") and c.endswith("_TOTAL")]
    meta_cols  = [c for c in df.columns if c not in name_cols + total_cols]
    sequences  = [int(c.split("_")[1]) for c in name_cols]

    rows = []
    for _, row in df.iterrows():
        meta = row[meta_cols].to_dict()
        for seq, nc, tc in zip(sequences, name_cols, total_cols):
            name = row[nc]
            if pd.isnull(name) or not str(name).strip():
                continue
            rows.append({**meta, "BIDDER_NAME": name, "BID_AMOUNT": row[tc], "bidder_sequence": seq})

    long_df = pd.DataFrame(rows)
    long_df = long_df.sort_values(["DATE", "LOCATION", "PROJECT", "bidder_sequence"]).reset_index(drop=True)
    return long_df


def delete_engineers_estimate(long_df):
    mask = long_df["BIDDER_NAME"].str.contains("ENGINEER", case=False, na=False)
    deleted = mask.sum()
    long_df = long_df[~mask].reset_index(drop=True)
    print(f"    → Deleted {deleted} ENGINEERS ESTIMATE rows")
    return long_df


# ===========================================================================
# Company list
# ===========================================================================
def build_company_list(long_df):
    stats = long_df["BIDDER_NAME"].value_counts().reset_index()
    stats.columns = ["company_name", "bid_frequency"]
    total = stats["bid_frequency"].sum()
    stats["bid_frequency_%"]     = (stats["bid_frequency"] / total * 100).round(1)
    stats["cum_bid_frequency_%"] = stats["bid_frequency_%"].cumsum().round(1)
    stats["winning_bid_frequency"] = long_df[long_df["bidder_sequence"] == 1]["BIDDER_NAME"].value_counts().reindex(stats["company_name"]).fillna(0).astype(int).values
    stats["client_decision"] = ""
    return stats


# ===========================================================================
# City fill — county seat lookup
# ===========================================================================
_COUNTY_SEATS = {
    # Iowa
    ("BUENA VISTA", "Iowa"): "Storm Lake",   ("BUTLER",    "Iowa"): "Allison",
    ("CARROLL",     "Iowa"): "Carroll",       ("CASS",      "Iowa"): "Atlantic",
    ("CERRO GORDO", "Iowa"): "Mason City",    ("CHEROKEE",  "Iowa"): "Cherokee",
    ("CLARKE",      "Iowa"): "Osceola",       ("CLAY",      "Iowa"): "Spencer",
    ("CRAWFORD",    "Iowa"): "Denison",       ("DALLAS",    "Iowa"): "Adel",
    ("EMMET",       "Iowa"): "Estherville",   ("FAYETTE",   "Iowa"): "West Union",
    ("FLOYD",       "Iowa"): "Charles City",  ("FRANKLIN",  "Iowa"): "Hampton",
    ("GREENE",      "Iowa"): "Jefferson",     ("GRUNDY",    "Iowa"): "Grundy Center",
    ("HAMILTON",    "Iowa"): "Webster City",  ("HANCOCK",   "Iowa"): "Garner",
    ("HARDIN",      "Iowa"): "Eldora",        ("HARRISON",  "Iowa"): "Logan",
    ("HUMBOLDT",    "Iowa"): "Dakota City",   ("KOSSUTH",   "Iowa"): "Algona",
    ("LYON",        "Iowa"): "Rock Rapids",   ("MADISON",   "Iowa"): "Winterset",
    ("MAHASKA",     "Iowa"): "Oskaloosa",     ("MARION",    "Iowa"): "Knoxville",
    ("MARSHALL",    "Iowa"): "Marshalltown",  ("MONONA",    "Iowa"): "Onawa",
    ("OBRIEN",      "Iowa"): "Primghar",      ("O'BRIEN",   "Iowa"): "Primghar",
    ("OSCEOLA",     "Iowa"): "Sibley",        ("PALO ALTO", "Iowa"): "Emmetsburg",
    ("PLYMOUTH",    "Iowa"): "Le Mars",       ("POCAHONTAS","Iowa"): "Pocahontas",
    ("POLK",        "Iowa"): "Des Moines",    ("POWESHIEK", "Iowa"): "Montezuma",
    ("SAC",         "Iowa"): "Sac City",      ("SHELBY",    "Iowa"): "Harlan",
    ("SIOUX",       "Iowa"): "Orange City",   ("STORY",     "Iowa"): "Nevada",
    ("TAMA",        "Iowa"): "Toledo",        ("WEBSTER",   "Iowa"): "Fort Dodge",
    ("WINNEBAGO",   "Iowa"): "Forest City",   ("WOODBURY",  "Iowa"): "Sioux City",
    ("WORTH",       "Iowa"): "Northwood",     ("WRIGHT",    "Iowa"): "Clarion",
    # Minnesota
    ("AITKIN",        "Minnesota"): "Aitkin",       ("BECKER",      "Minnesota"): "Detroit Lakes",
    ("BELTRAMI",      "Minnesota"): "Bemidji",      ("BENTON",      "Minnesota"): "Foley",
    ("BIG STONE",     "Minnesota"): "Ortonville",   ("BLUE EARTH",  "Minnesota"): "Mankato",
    ("BROWN",         "Minnesota"): "New Ulm",      ("CARLTON",     "Minnesota"): "Carlton",
    ("CARVER",        "Minnesota"): "Chaska",       ("CASS",        "Minnesota"): "Walker",
    ("CHIPPEWA",      "Minnesota"): "Montevideo",   ("CHISAGO",     "Minnesota"): "Center City",
    ("CLAY",          "Minnesota"): "Moorhead",     ("CLEARWATER",  "Minnesota"): "Bagley",
    ("COTTONWOOD",    "Minnesota"): "Windom",       ("CROW WING",   "Minnesota"): "Brainerd",
    ("DOUGLAS",       "Minnesota"): "Alexandria",   ("FARIBAULT",   "Minnesota"): "Blue Earth",
    ("FREEBORN",      "Minnesota"): "Albert Lea",   ("GRANT",       "Minnesota"): "Elbow Lake",
    ("HUBBARD",       "Minnesota"): "Park Rapids",  ("ISANTI",      "Minnesota"): "Cambridge",
    ("ITASCA",        "Minnesota"): "Grand Rapids", ("JACKSON",     "Minnesota"): "Jackson",
    ("KANABEC",       "Minnesota"): "Mora",         ("KANDIYOHI",   "Minnesota"): "Willmar",
    ("KITTSON",       "Minnesota"): "Hallock",      ("KOOCHICHING", "Minnesota"): "International Falls",
    ("LAC QUI PARLE", "Minnesota"): "Madison",      ("LE SUEUR",    "Minnesota"): "Le Center",
    ("LINCOLN",       "Minnesota"): "Ivanhoe",      ("LYON",        "Minnesota"): "Marshall",
    ("MAHNOMEN",      "Minnesota"): "Mahnomen",     ("MARSHALL",    "Minnesota"): "Warren",
    ("MARTIN",        "Minnesota"): "Fairmont",     ("MCLEOD",      "Minnesota"): "Glencoe",
    ("MEEKER",        "Minnesota"): "Litchfield",   ("MILLE LACS",  "Minnesota"): "Milaca",
    ("MORRISON",      "Minnesota"): "Little Falls", ("MURRAY",      "Minnesota"): "Slayton",
    ("NICOLLET",      "Minnesota"): "St. Peter",    ("NOBLES",      "Minnesota"): "Worthington",
    ("NORMAN",        "Minnesota"): "Ada",          ("OTTER TAIL",  "Minnesota"): "Fergus Falls",
    ("PENNINGTON",    "Minnesota"): "Thief River Falls", ("PINE",   "Minnesota"): "Pine City",
    ("PIPESTONE",     "Minnesota"): "Pipestone",    ("POLK",        "Minnesota"): "Crookston",
    ("POPE",          "Minnesota"): "Glenwood",     ("RED LAKE",    "Minnesota"): "Red Lake Falls",
    ("REDWOOD",       "Minnesota"): "Redwood Falls",("RENVILLE",    "Minnesota"): "Olivia",
    ("RICE",          "Minnesota"): "Faribault",    ("ROCK",        "Minnesota"): "Luverne",
    ("ROSEAU",        "Minnesota"): "Roseau",       ("SCOTT",       "Minnesota"): "Shakopee",
    ("SHERBURNE",     "Minnesota"): "Elk River",    ("SIBLEY",      "Minnesota"): "Gaylord",
    ("STEARNS",       "Minnesota"): "St. Cloud",    ("STEELE",      "Minnesota"): "Owatonna",
    ("STEVENS",       "Minnesota"): "Morris",       ("SWIFT",       "Minnesota"): "Benson",
    ("TODD",          "Minnesota"): "Long Prairie",  ("TRAVERSE",   "Minnesota"): "Wheaton",
    ("WABASHA",       "Minnesota"): "Wabasha",      ("WADENA",      "Minnesota"): "Wadena",
    ("WASECA",        "Minnesota"): "Waseca",       ("WATONWAN",    "Minnesota"): "St. James",
    ("WILKIN",        "Minnesota"): "Breckenridge", ("WRIGHT",      "Minnesota"): "Buffalo",
    ("YELLOW MEDICINE","Minnesota"): "Granite Falls",
    # Montana
    ("BIG HORN",    "Montana"): "Hardin",      ("CUSTER",      "Montana"): "Miles City",
    ("DAWSON",      "Montana"): "Glendive",    ("FALLON",      "Montana"): "Baker",
    ("GARFIELD",    "Montana"): "Jordan",      ("MCCONE",      "Montana"): "Circle",
    ("PONDERA",     "Montana"): "Conrad",      ("PRAIRIE",     "Montana"): "Terry",
    ("RICHLAND",    "Montana"): "Sidney",      ("ROSEBUD",     "Montana"): "Forsyth",
    ("SHERIDAN",    "Montana"): "Plentywood",  ("YELLOWSTONE", "Montana"): "Billings",
    # Nebraska
    ("BOYD",      "Nebraska"): "Butte",        ("BURT",      "Nebraska"): "Tekamah",
    ("BUTLER",    "Nebraska"): "David City",   ("CASS",      "Nebraska"): "Plattsmouth",
    ("CEDAR",     "Nebraska"): "Hartington",   ("CUMING",    "Nebraska"): "West Point",
    ("CUSTER",    "Nebraska"): "Broken Bow",   ("DAKOTA",    "Nebraska"): "Dakota City",
    ("DAWSON",    "Nebraska"): "Lexington",    ("DIXON",     "Nebraska"): "Ponca",
    ("DODGE",     "Nebraska"): "Fremont",      ("DOUGLAS",   "Nebraska"): "Omaha",
    ("HOLT",      "Nebraska"): "O'Neill",      ("HOWARD",    "Nebraska"): "St. Paul",
    ("KEYA PAHA", "Nebraska"): "Springview",  ("KNOX",      "Nebraska"): "Center",
    ("LANCASTER", "Nebraska"): "Lincoln",      ("MADISON",   "Nebraska"): "Madison",
    ("MERRICK",   "Nebraska"): "Central City", ("NANCE",     "Nebraska"): "Fullerton",
    ("PLATTE",    "Nebraska"): "Columbus",     ("POLK",      "Nebraska"): "Osceola",
    ("SANDERS",   "Nebraska"): "Wahoo",        ("SAUNDERS",  "Nebraska"): "Wahoo",
    ("SARPY",     "Nebraska"): "Papillion",    ("STANTON",   "Nebraska"): "Stanton",
    ("THURSTON",  "Nebraska"): "Pender",
    # North Dakota
    ("ADAMS",         "North Dakota"): "Hettinger",   ("BARNES",    "North Dakota"): "Valley City",
    ("BENSON",        "North Dakota"): "Minnewaukan", ("BILLINGS",  "North Dakota"): "Medora",
    ("BOTTINEAU",     "North Dakota"): "Bottineau",   ("BOWMAN",    "North Dakota"): "Bowman",
    ("BURKE",         "North Dakota"): "Bowbells",    ("BURLEIGH",  "North Dakota"): "Bismarck",
    ("BURLIEGH",      "North Dakota"): "Bismarck",    # typo variant
    ("CASS",          "North Dakota"): "Fargo",       ("CAVALIER",  "North Dakota"): "Langdon",
    ("DICKEY",        "North Dakota"): "Ellendale",   ("DIVIDE",    "North Dakota"): "Crosby",
    ("DUNN",          "North Dakota"): "Manning",     ("EDDY",      "North Dakota"): "New Rockford",
    ("EMMONS",        "North Dakota"): "Linton",      ("FOSTER",    "North Dakota"): "Carrington",
    ("GOLDEN VALLEY", "North Dakota"): "Beach",       ("GRAND FORKS","North Dakota"): "Grand Forks",
    ("GRANT",         "North Dakota"): "Carson",      ("GRIGGS",    "North Dakota"): "Cooperstown",
    ("HETTINGER",     "North Dakota"): "Mott",        ("KIDDER",    "North Dakota"): "Steele",
    ("LAMOURE",       "North Dakota"): "LaMoure",     ("LOGAN",     "North Dakota"): "Napoleon",
    ("MCHENRY",       "North Dakota"): "Towner",      ("MCINTOSH",  "North Dakota"): "Ashley",
    ("MCKENZIE",      "North Dakota"): "Watford City",("MCLEAN",    "North Dakota"): "Washburn",
    ("MERCER",        "North Dakota"): "Stanton",     ("MORTON",    "North Dakota"): "Mandan",
    ("MOUNTRAIL",     "North Dakota"): "Stanley",     ("NELSON",    "North Dakota"): "Lakota",
    ("PEMBINA",       "North Dakota"): "Cavalier",    ("PIERCE",    "North Dakota"): "Rugby",
    ("RAMSEY",        "North Dakota"): "Devils Lake",  ("RANSOM",   "North Dakota"): "Lisbon",
    ("RENVILLE",      "North Dakota"): "Mohall",      ("RICHLAND",  "North Dakota"): "Wahpeton",
    ("ROLETTE",       "North Dakota"): "Rolla",       ("SARGENT",   "North Dakota"): "Forman",
    ("SEARGENT",      "North Dakota"): "Forman",      # typo variant
    ("SHERIDAN",      "North Dakota"): "McClusky",    ("SHERDIAN",  "North Dakota"): "McClusky",  # typo
    ("SIOUX",         "North Dakota"): "Fort Yates",  ("SLOPE",     "North Dakota"): "Amidon",
    ("STARK",         "North Dakota"): "Dickinson",   ("STEELE",    "North Dakota"): "Finley",
    ("STUTSMAN",      "North Dakota"): "Jamestown",   ("TOWNER",    "North Dakota"): "Cando",
    ("TRAILL",        "North Dakota"): "Hillsboro",   ("WALSH",     "North Dakota"): "Grafton",
    ("WARD",          "North Dakota"): "Minot",       ("WELLS",     "North Dakota"): "Fessenden",
    ("WILLIAMS",      "North Dakota"): "Williston",
    # South Dakota
    ("AURORA",        "South Dakota"): "Plankinton",  ("BEADLE",    "South Dakota"): "Huron",
    ("BENNETT",       "South Dakota"): "Martin",      ("BON HOMME", "South Dakota"): "Tyndall",
    ("BROOKINGS",     "South Dakota"): "Brookings",   ("BROWN",     "South Dakota"): "Aberdeen",
    ("BRULE",         "South Dakota"): "Chamberlain", ("BUFFALO",   "South Dakota"): "Gann Valley",
    ("BUTTE",         "South Dakota"): "Belle Fourche",("CHARLES MIX","South Dakota"): "Lake Andes",
    ("CLARK",         "South Dakota"): "Clark",       ("CLAY",      "South Dakota"): "Vermillion",
    ("CODINGTON",     "South Dakota"): "Watertown",   ("CORSON",    "South Dakota"): "McIntosh",
    ("CUSTER",        "South Dakota"): "Custer",      ("DAVISON",   "South Dakota"): "Mitchell",
    ("DAY",           "South Dakota"): "Webster",     ("DEUEL",     "South Dakota"): "Clear Lake",
    ("DEWEY",         "South Dakota"): "Timber Lake", ("DOUGLAS",   "South Dakota"): "Armour",
    ("EDMUNDS",       "South Dakota"): "Ipswich",     ("FALL RIVER","South Dakota"): "Hot Springs",
    ("FAULK",         "South Dakota"): "Faulkton",    ("GRANT",     "South Dakota"): "Milbank",
    ("GREGORY",       "South Dakota"): "Burke",       ("HAAKON",    "South Dakota"): "Philip",
    ("HAMLIN",        "South Dakota"): "Hayti",       ("HAND",      "South Dakota"): "Miller",
    ("HANSON",        "South Dakota"): "Alexandria",  ("HARDING",   "South Dakota"): "Buffalo",
    ("HUGHES",        "South Dakota"): "Pierre",      ("HUTCHINSON","South Dakota"): "Olivet",
    ("HYDE",          "South Dakota"): "Highmore",    ("JACKSON",   "South Dakota"): "Kadoka",
    ("JERAULD",       "South Dakota"): "Wessington Springs", ("JONES","South Dakota"): "Murdo",
    ("KINGSBURY",     "South Dakota"): "De Smet",     ("LAKE",      "South Dakota"): "Madison",
    ("LAWRENCE",      "South Dakota"): "Deadwood",    ("LINCOLN",   "South Dakota"): "Canton",
    ("LYMAN",         "South Dakota"): "Kennebec",    ("MARSHALL",  "South Dakota"): "Britton",
    ("MCCOOK",        "South Dakota"): "Salem",       ("MEADE",     "South Dakota"): "Sturgis",
    ("MELLETTE",      "South Dakota"): "White River", ("MINER",     "South Dakota"): "Howard",
    ("MINNEHAHA",     "South Dakota"): "Sioux Falls", ("MOODY",     "South Dakota"): "Flandreau",
    ("OGLALA LAKOTA", "South Dakota"): "Pine Ridge",  ("PENNINGTON","South Dakota"): "Rapid City",
    ("PERKINS",       "South Dakota"): "Bison",       ("POTTER",    "South Dakota"): "Gettysburg",
    ("ROBERTS",       "South Dakota"): "Sisseton",    ("SANBORN",   "South Dakota"): "Woonsocket",
    ("SPINK",         "South Dakota"): "Redfield",    ("STANLEY",   "South Dakota"): "Fort Pierre",
    ("SULLY",         "South Dakota"): "Onida",       ("TODD",      "South Dakota"): "Winner",
    ("TRIPP",         "South Dakota"): "Winner",      ("UNION",     "South Dakota"): "Elk Point",
    ("WALWORTH",      "South Dakota"): "Selby",       ("YANKTON",   "South Dakota"): "Yankton",
    ("ZIEBACH",       "South Dakota"): "Dupree",
}


def _county_seat_for_row(county_str, state_str):
    """Return county seat city for a County+State row, or None."""
    if pd.isna(county_str) or pd.isna(state_str):
        return None

    # Check for explicit 'CITY OF X' in the county field first
    m = re.search(r'CITY OF\s+(.+?)(?:\s*$)', str(county_str), re.IGNORECASE)
    if m:
        city = m.group(1).strip().rstrip('"').strip()
        if not re.search(r'\d|DOT\s|DIST\b|AWARD|STATUS|REJECT', city, re.IGNORECASE):
            return city.title()

    # Extract primary (first) county name
    s = str(county_str).strip().upper()
    s = re.sub(r'\b(MN|ND|SD|IA|NE|MT)\b', '', s).strip()
    primary = re.split(r'[&,]', s)[0].strip()
    primary = re.sub(r'\s+(?:COS?|COUNTY)\b.*$', '', primary, flags=re.IGNORECASE).strip()
    primary = re.sub(r'\s*-\s*.*$', '', primary).strip()

    state = str(state_str).strip()

    # Try primary county against the row's state
    seat = _COUNTY_SEATS.get((primary, state))
    if seat:
        return seat

    # Fallback: try all states (handles cross-state county entries)
    for (c, _s), v in _COUNTY_SEATS.items():
        if c == primary:
            return v

    return None


def fill_city_from_county_seat(df):
    """Fill null City values using county seat lookup (county-only rows have no parsed city)."""
    null_mask = df["City"].isna()
    df = df.copy()
    for idx in df[null_mask].index:
        city = _county_seat_for_row(df.at[idx, "County"], df.at[idx, "State"])
        if city:
            df.at[idx, "City"] = city
    return df


# ===========================================================================
# MAIN
# ===========================================================================
def main():
    print("=" * 70)
    print("CSI Full Cleaning Pipeline")
    print("=" * 70)

    # Always rebuild from raw source files so the pipeline is fully reproducible
    print("\n[Combine] Building raw combined file from source CSVs...")
    df24 = pd.read_csv(RAW_2024_FILE, dtype=str, keep_default_na=False)
    df25 = pd.read_csv(RAW_2025_FILE, dtype=str, keep_default_na=False)
    df24["bid_year"] = "2024"
    df25["bid_year"] = "2025"
    df = pd.concat([df24, df25], ignore_index=True)
    cols = ["bid_year"] + [c for c in df.columns if c != "bid_year"]
    df = df[cols]
    # Convert empty strings to NaN for proper null handling downstream
    df = df.replace("", pd.NA)
    print(f"  2024: {len(df24)} rows  |  2025: {len(df25)} rows  |  combined: {len(df)} rows, {len(df.columns)} columns")

    # bid_year as int
    df["bid_year"] = pd.to_numeric(df["bid_year"], errors="coerce").astype("Int64")

    print("\n[Pass 1a] DATE → YYYY-MM-DD")
    df = clean_date(df)
    print(f"  nulls after: {df['DATE'].isna().sum()}")

    print("\n[Pass 1b] TIME → HH:MM (24-hour)")
    df = clean_time(df)
    print(f"  nulls after: {df['TIME'].isna().sum()}")

    print("\n[Pass 1c] LOCATION → County / City / State")
    df = parse_location(df)
    print(f"  County nulls: {df['County'].isna().sum()}, State nulls: {df['State'].isna().sum()}")

    print("\n[Pass 1c+] Fill null City values from county seat lookup")
    df = fill_city_from_county_seat(df)
    print(f"  City nulls remaining: {df['City'].isna().sum()}")

    print("\n[Pass 1d] location_flag (county centroid, 75-mile threshold)")
    df = add_location_flag(df)
    print(f"  {df['location_flag'].value_counts().to_dict()}")

    print("\n[Pass 1e] PROJECT LOCATION → Latitude / Longitude")
    df = split_project_location(df)
    print(f"  Lat nulls: {df['Latitude'].isna().sum()}, Lon nulls: {df['Longitude'].isna().sum()}")

    print("\n[Pass 2] Extract typed project IDs")
    df = extract_identifiers(df)
    print(f"  primary_project_id coverage: {df['primary_project_id'].notna().sum()} / {len(df)}")

    print("\n[Pass 2] Add composite keys + duplicate candidates")
    df = add_composite_keys(df)
    df = write_duplicate_review(df)

    print("\n[Pass 1f] PREVAILING WAGES → 1/0")
    df = clean_prevailing_wages(df)

    print("\n[Pass 1g] Material quantity columns → float")
    df = clean_material_columns(df)

    print("\n[Pass 1h] BOX → 1/0")
    df = clean_box(df)

    print("\n[Pass 3a] BIDDER_*_NAME: normalize ampersands / whitespace / nulls")
    df = clean_bidder_names(df)

    print("\n[Pass 3b] BIDDER_*_TOTAL → float  (strips $ and commas, handles 2025 format)")
    df = clean_bidder_totals(df)
    null_b1 = df["BIDDER_1_TOTAL"].isna().sum()
    name_b1 = df["BIDDER_1_NAME"].notna().sum()
    mismatch = (df["BIDDER_1_NAME"].notna() & df["BIDDER_1_TOTAL"].isna()).sum()
    print(f"  BIDDER_1_TOTAL nulls: {null_b1}  (mismatch vs name: {mismatch})")

    print("\n[Pass 3c] Apply v1 bidder-name merges to wide format")
    df = apply_v1_merges(df)

    print("\n[Pass 4]  Apply v2 bidder-name merges to wide format")
    df = apply_v2_merges(df)

    print("\n[Pass 5]  Apply v3 additional bidder-name merges to wide format")
    df = apply_v3_merges(df)

    print("\n[Save] Writing wide format (CSI_data_combined.csv)...")
    df.to_csv(COMBINED_FILE, index=False)
    print(f"  {len(df)} rows, {len(df.columns)} columns")

    print("\n[Pass 3b] Pivot to long format (one row per bidder per project)")
    long_df = pivot_to_long_format(df)
    print(f"  Raw long rows: {len(long_df)}")

    print("\n[Pass 3c] Remove ENGINEERS ESTIMATE entries")
    long_df = delete_engineers_estimate(long_df)

    print("\n[Save] Writing long format (CSI_data_long_format.csv)...")
    long_df.to_csv(LONG_FORMAT_FILE, index=False)
    print(f"  {len(long_df)} rows, {len(long_df.columns)} columns")

    print("\n[Save] Regenerating company list...")
    company_df = build_company_list(long_df)
    company_df.to_csv(COMPANY_LIST_FILE, index=False)
    print(f"  {len(company_df)} unique competitors")
    print(f"  Top 5: {company_df.head(5)[['company_name','bid_frequency']].to_string(index=False)}")

    print("\n" + "=" * 70)
    print("PIPELINE COMPLETE")
    print(f"  Wide format : {COMBINED_FILE}  ({len(df)} rows × {len(df.columns)} cols)")
    print(f"  Long format : {LONG_FORMAT_FILE}  ({len(long_df)} rows × {len(long_df.columns)} cols)")
    print(f"  Company list: {COMPANY_LIST_FILE}  ({len(company_df)} companies)")
    print(f"  Dup review  : {DUPLICATE_REVIEW_FILE}")
    print("=" * 70)


if __name__ == "__main__":
    main()
