"""
road_midpoint.py

Finds the geographic midpoint along a road construction project route
given a state, route number, begin milepost, and end milepost.

Supports: MN, ND, SD, NE (M-value geometry interpolation from state DOT feature services)
          IA, MT (ArcGIS LRS API with auto-detected route IDs)

Usage:
    python road_midpoint.py --state MN --route 94 --begin 71.00 --end 83.00
"""
# PEP 604 ("float | None") is used in find_midpoint's signature below. Without this import that
# annotation is EVALUATED at def-time and raises TypeError on Python 3.9, which took down the whole
# FastAPI backend: midpoint_bridge imports this module at module scope, report.py imports that, and
# app.py imports report. The project now pins >=3.10 (pyproject.toml), but this line makes the
# module import-safe on 3.9 regardless, since it is also run standalone as a CLI. See issue #53.
from __future__ import annotations

import argparse
import json
import sys
import requests


# ---------------------------------------------------------------------------
# State configuration
# ---------------------------------------------------------------------------

# Minnesota: the original LRS endpoint is no longer publicly accessible.
# We use the MNDOT_TRAFFIC_DATA LRS Route Labels layer, which stores M-values
# (mileposts) as the third coordinate in each route's polyline geometry.
MN_TRAFFIC_URL = (
    "https://dotapp9.dot.state.mn.us/egis12/rest/services/"
    "TFA/MNDOT_TRAFFIC_DATA/MapServer/9"
)

# North Dakota: the rcrs_dynamic feature service stores M-values (reference posts)
# directly in the route polyline geometry for mainline routes.
# Mainline routes are identified by RouteId ending in '000M'.
# Routes are filtered by HWY_CHAR (highway number as string), not ROUTE_ID
# (which is an internal integer with no relation to the highway number).
ND_FEATURE_URL = (
    "https://gis.dot.nd.gov/ArcGIS/rest/services/external/rcrs_dynamic/MapServer/0"
)

# South Dakota: the DOT_MileageReferenceMarkers service contains point features
# with actual MRM values (matching plan sheet MRM values) and direct lat/lon
# coordinates. Routes are queried by the 'highway' field (zero-padded 3-digit
# format, e.g., '044' for Hwy 44). The 'mrm' field is a fixed-format decimal
# string (e.g., '409.00'). We bracket the target MRM with adjacent markers and
# linearly interpolate the coordinates.
SD_MRM_URL = (
    "https://sdgis.sd.gov/dot/rest/services/TIM/DOT_MileageReferenceMarkers/MapServer/0"
)

# Nebraska: the HighwaysMajorMinorsLocalRamps_RefPostRoutes service stores
# M-values (reference posts) directly in route polyline geometry.
# RouteID is zero-padded to 3 digits (e.g., route 80 -> '080', route 680 -> '680').
NE_FEATURE_URL = (
    "https://services8.arcgis.com/ovrd81pb0zC79CeU/arcgis/rest/services/"
    "HighwaysMajorMinorsLocalRamps_RefPostRoutes_7_25/FeatureServer/0"
)

# Iowa: the RAMS LRS has a complex route ID format: S{system:5d}{route:04d}{direction}
# System codes: 00191 = Interstate, 00192 = US Route, 00193 = Iowa State Route
# Direction: E/W for east-west routes, N/S for north-south routes
# We auto-detect the route ID by querying the Reference Posts layer.
IA_LRS_URL = (
    "https://gis.iowadot.gov/rams/rest/services/lrs/MapServer/exts/LRSServer"
)
IA_REFPOST_URL = (
    "https://gis.iowadot.gov/rams/rest/services/lrs/MapServer/98"
)

# Montana: ALTIS LRS uses internal route IDs (e.g. C000094A for I-94 mainline).
# The Signed Route layer maps signed route codes (I-94, US-2, MT-200) to these IDs.
# We auto-detect the route ID by querying the Signed Route layer.
MT_LRS_URL = (
    "https://app.mdt.mt.gov/arcgis/rest/services/ALTIS/ALTIS_API/MapServer/exts/LRSServer"
)
MT_SIGNED_ROUTE_URL = (
    "https://app.mdt.mt.gov/arcgis/rest/services/ALTIS/ALTIS_API/MapServer/23"
)

# No remaining states use the generic LRS approach.
LRS_STATES = {}


# ---------------------------------------------------------------------------
# Minnesota M-value geometry approach
# ---------------------------------------------------------------------------

def mn_measure_to_latlon(route: str, measure: float) -> tuple[float, float]:
    """
    Finds the lat/lon for a MN route at the given milepost by querying the
    MNDOT_TRAFFIC_DATA LRS Route Labels layer, which embeds M-values (mileposts)
    directly in the route polyline geometry.

    Tries Interstate (system 01) first, then State Trunk Highway (system 03).
    Route ID format: {system:02d}00000000000{route:03d}-I

    Returns (latitude, longitude) in WGS84.
    """
    route_num = int(route)
    candidate_ids = [
        f"0100000000000{route_num:03d}-I",  # Interstate
        f"0300000000000{route_num:03d}-I",  # State Trunk Highway
    ]

    for route_id in candidate_ids:
        params = {
            "f": "json",
            "where": f"ROUTE_ID = '{route_id}'",
            "outFields": "ROUTE_ID",
            "returnGeometry": "true",
            "returnM": "true",
            "outSR": "4326",
        }
        resp = requests.get(f"{MN_TRAFFIC_URL}/query", params=params, timeout=30)
        resp.raise_for_status()
        features = resp.json().get("features", [])
        if not features:
            continue

        for path in features[0]["geometry"]["paths"]:
            m_values = [pt[2] for pt in path]
            if min(m_values) <= measure <= max(m_values):
                for i in range(len(path) - 1):
                    m0, m1 = path[i][2], path[i + 1][2]
                    if m0 <= measure <= m1:
                        t = (measure - m0) / (m1 - m0)
                        lon = path[i][0] + t * (path[i + 1][0] - path[i][0])
                        lat = path[i][1] + t * (path[i + 1][1] - path[i][1])
                        return lat, lon

    raise RuntimeError(
        f"MN route {route} not found at milepost {measure:.4f}. "
        f"Tried route IDs: {candidate_ids}. "
        f"Check that the route number and milepost are correct."
    )


# ---------------------------------------------------------------------------
# North Dakota M-value geometry approach
# ---------------------------------------------------------------------------

def nd_measure_to_latlon(route: str, measure: float) -> tuple[float, float]:
    """
    Finds the lat/lon for an ND route at the given reference post by querying
    the rcrs_dynamic feature service, which embeds M-values (reference posts)
    directly in mainline route polyline geometry.

    Queries by HWY_CHAR (highway number) and filters for mainline routes
    (RouteId ending in '000M'). Searches all matching features and paths for
    the one containing the target measure, then linearly interpolates.

    Returns (latitude, longitude) in WGS84.
    """
    params = {
        "f": "json",
        "where": f"HWY_CHAR = '{route}' AND RouteId LIKE '%000M'",
        "outFields": "RouteId",
        "returnGeometry": "true",
        "returnM": "true",
        "outSR": "4326",
    }
    resp = requests.get(f"{ND_FEATURE_URL}/query", params=params, timeout=30)
    resp.raise_for_status()
    features = resp.json().get("features", [])

    if not features:
        raise RuntimeError(
            f"ND route {route}: no mainline geometry found. "
            f"Check that the route number matches what is on the plan sheet."
        )

    for feat in features:
        for path in feat["geometry"]["paths"]:
            m_values = [pt[2] for pt in path]
            if min(m_values) <= measure <= max(m_values):
                for i in range(len(path) - 1):
                    m0, m1 = path[i][2], path[i + 1][2]
                    if m0 <= measure <= m1:
                        t = (measure - m0) / (m1 - m0)
                        lon = path[i][0] + t * (path[i + 1][0] - path[i][0])
                        lat = path[i][1] + t * (path[i + 1][1] - path[i][1])
                        return lat, lon

    raise RuntimeError(
        f"ND route {route}: no path found containing RP {measure:.4f}. "
        f"Check that the route number and RP values are correct."
    )


# ---------------------------------------------------------------------------
# South Dakota MRM marker interpolation approach
# ---------------------------------------------------------------------------

def sd_measure_to_latlon(route: str, measure: float) -> tuple[float, float]:
    """
    Finds the lat/lon for an SD state highway at the given MRM by querying
    the DOT_MileageReferenceMarkers service, which has point features with
    direct lat/lon coordinates at each MRM marker.

    The 'mrm' field is a zero-padded decimal string (e.g., '409.00'). We
    query a ±5 MRM window around the target, find the two markers that bracket
    it, and linearly interpolate their coordinates.

    Returns (latitude, longitude) in WGS84.
    """
    highway = route.zfill(3)
    lo = f"{max(0.0, measure - 5.0):06.2f}"
    hi = f"{measure + 5.0:06.2f}"
    params = {
        "f": "json",
        "where": f"highway = '{highway}' AND mrm >= '{lo}' AND mrm <= '{hi}'",
        "outFields": "mrm,mrm_longitude,mrm_latitude",
        "returnGeometry": "false",
        "orderByFields": "mrm",
    }
    resp = requests.get(f"{SD_MRM_URL}/query", params=params, timeout=30)
    resp.raise_for_status()
    features = resp.json().get("features", [])

    if not features:
        raise RuntimeError(
            f"SD route {route}: no MRM markers found near MRM {measure:.4f}. "
            f"Check that the route number is correct."
        )

    markers = sorted(
        [
            (
                float(f["attributes"]["mrm"]),
                f["attributes"]["mrm_longitude"],
                f["attributes"]["mrm_latitude"],
            )
            for f in features
        ],
        key=lambda x: x[0],
    )

    for i in range(len(markers) - 1):
        m0, lon0, lat0 = markers[i]
        m1, lon1, lat1 = markers[i + 1]
        if m0 <= measure <= m1:
            t = (measure - m0) / (m1 - m0)
            lon = lon0 + t * (lon1 - lon0)
            lat = lat0 + t * (lat1 - lat0)
            return lat, lon

    raise RuntimeError(
        f"SD route {route}: MRM {measure:.4f} not bracketed by available markers "
        f"({markers[0][0]:.2f}–{markers[-1][0]:.2f}). "
        f"Check that the route number and MRM values are correct."
    )


# ---------------------------------------------------------------------------
# Nebraska M-value geometry approach
# ---------------------------------------------------------------------------

def ne_measure_to_latlon(route: str, measure: float) -> tuple[float, float]:
    """
    Finds the lat/lon for a Nebraska route at the given reference post by
    querying the HighwaysMajorMinorsLocalRamps_RefPostRoutes feature service,
    which embeds M-values (reference posts) directly in route polyline geometry.

    RouteID is zero-padded to 3 digits (e.g., route 80 -> '080', 680 -> '680').

    Returns (latitude, longitude) in WGS84.
    """
    route_id = route.zfill(3)
    params = {
        "f": "json",
        "where": f"RouteID = '{route_id}'",
        "outFields": "RouteID",
        "returnGeometry": "true",
        "returnM": "true",
        "outSR": "4326",
    }
    resp = requests.get(f"{NE_FEATURE_URL}/query", params=params, timeout=30)
    resp.raise_for_status()
    features = resp.json().get("features", [])

    if not features:
        raise RuntimeError(
            f"NE route {route} (RouteID='{route_id}'): no geometry found. "
            f"Check that the route number is correct."
        )

    for feat in features:
        for path in feat["geometry"]["paths"]:
            m_values = [pt[2] for pt in path]
            if min(m_values) <= measure <= max(m_values):
                for i in range(len(path) - 1):
                    m0, m1 = path[i][2], path[i + 1][2]
                    if m0 <= measure <= m1:
                        t = (measure - m0) / (m1 - m0)
                        lon = path[i][0] + t * (path[i + 1][0] - path[i][0])
                        lat = path[i][1] + t * (path[i + 1][1] - path[i][1])
                        return lat, lon

    raise RuntimeError(
        f"NE route {route}: no path found containing RP {measure:.4f}. "
        f"Check that the route number and reference post values are correct."
    )


# ---------------------------------------------------------------------------
# Montana ALTIS LRS approach
# ---------------------------------------------------------------------------

def mt_measure_to_latlon(route: str, measure: float) -> tuple[float, float]:
    """
    Finds lat/lon for a Montana route at the given reference post using the
    MDT ALTIS LRS.

    Montana route IDs are internal (e.g. C000094A for I-94 mainline). The
    Signed Route layer maps signed route codes to these IDs. We try the route
    number as Interstate (I-{route}), US (US-{route}), and Montana state
    (MT-{route}) in order, using the first ROUTE_ID that locates successfully.
    Roadbed 'A' (mainline) is preferred over 'D' (divided opposite direction).

    Returns (latitude, longitude) in WGS84.
    """
    candidates = [f"I-{route}", f"US-{route}", f"MT-{route}", f"S-{route}"]

    route_ids = []
    for code in candidates:
        params = {
            "f": "json",
            "where": f"SIGNED_ROUTE_CODE = '{code}'",
            "outFields": "ROUTE_ID,FROM_MEASURE,TO_MEASURE",
            "returnGeometry": "false",
        }
        resp = requests.get(f"{MT_SIGNED_ROUTE_URL}/query", params=params, timeout=30)
        resp.raise_for_status()
        for feat in resp.json().get("features", []):
            a = feat["attributes"]
            if a["FROM_MEASURE"] <= measure <= a["TO_MEASURE"]:
                route_ids.append(a["ROUTE_ID"])
        if route_ids:
            break

    if not route_ids:
        raise RuntimeError(
            f"MT route {route}: no signed route found covering RP {measure:.4f}. "
            f"Tried codes: {candidates}. Check the route number and RP values."
        )

    # Prefer roadbed A over D
    route_ids.sort(key=lambda r: (r[-1] != "A", r))

    for route_id in route_ids:
        payload = {
            "f": "json",
            "outSR": 4326,
            "locations": json.dumps([{"routeId": route_id, "measure": measure}]),
        }
        resp2 = requests.post(
            f"{MT_LRS_URL}/networkLayers/26/measureToGeometry",
            data=payload, timeout=30,
        )
        resp2.raise_for_status()
        locs = resp2.json().get("locations", [])
        if locs and locs[0].get("status") == "esriLocatingOK":
            geom = locs[0]["geometry"]
            return geom["y"], geom["x"]

    raise RuntimeError(
        f"MT route {route}: LRS could not locate RP {measure:.4f} "
        f"on any of: {route_ids}."
    )


# ---------------------------------------------------------------------------
# Iowa LRS approach
# ---------------------------------------------------------------------------

def ia_measure_to_latlon(route: str, measure: float) -> tuple[float, float]:
    """
    Finds lat/lon for an Iowa state highway at the given milepost using the
    Iowa DOT RAMS LRS.

    Iowa LRS route IDs have the format: S{system:5d}{route:04d}{direction}
      system: 00191 = Interstate, 00192 = US Route, 00193 = Iowa State Route
      direction: E/W (east-west routes) or N/S (north-south routes)

    The correct route ID is auto-detected by querying the Reference Posts layer
    for records near the target measure, then measureToGeometry is called with
    that route ID.

    Returns (latitude, longitude) in WGS84.
    """
    route_padded = str(int(route)).zfill(4)

    # Find the route ID by querying Reference Posts near the target measure
    params = {
        "f": "json",
        "where": (
            f"MEASURE >= {measure - 2.0} AND MEASURE <= {measure + 2.0} "
            f"AND ROUTE_ID LIKE '%{route_padded}%'"
        ),
        "outFields": "ROUTE_ID,MEASURE",
        "returnGeometry": "false",
        "resultRecordCount": 10,
    }
    resp = requests.get(f"{IA_REFPOST_URL}/query", params=params, timeout=30)
    resp.raise_for_status()
    features = resp.json().get("features", [])

    if not features:
        raise RuntimeError(
            f"IA route {route}: no reference posts found near milepost {measure:.4f}. "
            f"Check that the route number and milepost are correct."
        )

    # Collect unique route IDs; prefer E/N over W/S (primary travel direction)
    route_ids = sorted(
        {f["attributes"]["ROUTE_ID"] for f in features},
        key=lambda r: (r[-1] in "WS", r),
    )
    route_id = route_ids[0]

    payload = {
        "f": "json",
        "outSR": 4326,
        "locations": json.dumps([{"routeId": route_id, "measure": measure}]),
    }
    resp2 = requests.post(
        f"{IA_LRS_URL}/networkLayers/0/measureToGeometry",
        data=payload, timeout=30,
    )
    resp2.raise_for_status()
    data = resp2.json()

    locations = data.get("locations", [])
    if not locations or locations[0].get("status") != "esriLocatingOK":
        status = locations[0].get("status") if locations else "no locations returned"
        raise RuntimeError(
            f"Iowa LRS could not locate route {route_id} at milepost {measure:.4f}. "
            f"Status: {status}."
        )

    geom = locations[0]["geometry"]
    return geom["y"], geom["x"]




# ---------------------------------------------------------------------------
# Main logic
# ---------------------------------------------------------------------------

# Gross length vs. (end - begin) is expected to diverge slightly on projects
# with station equations. Above this threshold (miles), warn that the two
# don't agree so the user can double check the plan sheet.
_LENGTH_MISMATCH_WARNING_MI = 0.05


def find_midpoint(
    state: str, route: str, begin_mp: float, total_length: float, end_mp: float | None = None
) -> tuple[float, float]:
    """
    Returns the (latitude, longitude) of the midpoint along the road segment,
    computed as the first reference point plus half of the total gross length.

    end_mp, if given, is not used in the calculation — it's printed alongside
    the implied (end - begin) distance as a cross-check against total_length,
    since plan sheets with multiple SP blocks and station equations can show
    a gross length that doesn't exactly match end - begin.
    """
    mid_mp = begin_mp + total_length / 2.0
    print(f"  Begin milepost      : {begin_mp}")
    print(f"  Total gross length  : {total_length:.4f} mi")
    print(f"  Mid milepost        : {mid_mp:.4f}")

    if end_mp is not None:
        implied_length = end_mp - begin_mp
        diff = abs(implied_length - total_length)
        print(f"  End milepost        : {end_mp}  (end - begin = {implied_length:.4f} mi)")
        if diff > _LENGTH_MISMATCH_WARNING_MI:
            print(
                f"  WARNING: gross length ({total_length:.4f} mi) and end - begin "
                f"({implied_length:.4f} mi) differ by {diff:.4f} mi. Check for station "
                f"equations on the plan sheet.",
                file=sys.stderr,
            )

    if state == "MN":
        print(f"  Method         : MNDOT_TRAFFIC_DATA M-value interpolation (MN)")
        return mn_measure_to_latlon(route, mid_mp)
    elif state == "ND":
        print(f"  Method         : ND rcrs_dynamic M-value interpolation (ND)")
        return nd_measure_to_latlon(route, mid_mp)
    elif state == "SD":
        print(f"  Method         : SD DOT_MileageReferenceMarkers interpolation (SD)")
        return sd_measure_to_latlon(route, mid_mp)
    elif state == "NE":
        print(f"  Method         : NE RefPostRoutes M-value interpolation (NE)")
        return ne_measure_to_latlon(route, mid_mp)
    elif state == "IA":
        print(f"  Method         : Iowa DOT RAMS LRS (IA)")
        return ia_measure_to_latlon(route, mid_mp)
    elif state == "MT":
        print(f"  Method         : Montana ALTIS LRS (MT)")
        return mt_measure_to_latlon(route, mid_mp)
    else:
        raise ValueError(
            f"State '{state}' is not supported. "
            f"Supported states: MN, ND, SD, NE, IA, MT"
        )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

# States where the MRM/milepost + suffix is already in miles (e.g. SD: 406.32+0.022 = 406.342)
# vs states where the suffix is in hundredths and must be divided by 100 (e.g. MN: 71+00.444 = 71.00444)
_MRM_DECIMAL_STATES = {"SD"}

def parse_milepost(value: str, state: str = "") -> float:
    """
    Parses a milepost/reference-post value into decimal miles.

    Two formats are supported:
      - Decimal:       "71.004"      → 71.004
      - MN station:    "71+00.444"   → 71 + 00.444/100 = 71.00444
      - SD MRM:        "406.32+0.022"→ 406.32 + 0.022  = 406.342
    """
    if "+" in value:
        major, minor = value.split("+")
        if state.upper() in _MRM_DECIMAL_STATES:
            return float(major) + float(minor)
        return float(major) + float(minor) / 100.0
    return float(value)


def parse_length(value: str) -> float:
    """
    Parses a total gross length in miles. Accepts a single value or a
    comma-separated list of per-SP-block gross lengths (read directly off
    the plan sheet's GROSS LENGTH rows), which are summed.

        "12.517"                → 12.517
        "3.175,7.138,2.204"     → 12.517
    """
    return sum(float(part) for part in value.split(","))


def main():
    parser = argparse.ArgumentParser(
        description="Find the geographic midpoint of a road construction project segment."
    )
    parser.add_argument("--state", required=True, help="Two-letter state code (MN, ND, SD, MT, IA, NE)")
    parser.add_argument("--route", required=True, help="Route number (e.g. 94, 29, 2)")
    parser.add_argument(
        "--begin",
        required=True,
        help="Begin milepost (first/overall reference point) — decimal (71.004) or station format (71+00.444)",
    )
    parser.add_argument(
        "--length",
        required=True,
        help=(
            "Total gross length in miles, from the plan sheet's GROSS LENGTH row(s). "
            "Accepts a comma-separated list of per-SP-block lengths, which are summed "
            "(e.g. 3.175,7.138,2.204)"
        ),
    )
    parser.add_argument(
        "--end",
        required=False,
        default=None,
        help=(
            "End milepost — decimal or station format. Optional; not used in the "
            "calculation, only printed as a cross-check against --length"
        ),
    )
    args = parser.parse_args()

    state = args.state.upper()
    route = args.route
    begin_mp = parse_milepost(args.begin, state)
    total_length = parse_length(args.length)
    end_mp = parse_milepost(args.end, state) if args.end is not None else None

    print(f"\nFinding midpoint for:")
    print(f"  State          : {state}")
    print(f"  Route          : {route}")

    try:
        lat, lon = find_midpoint(state, route, begin_mp, total_length, end_mp)
        print(f"\nMidpoint coordinates:")
        print(f"  Latitude  : {lat:.6f}")
        print(f"  Longitude : {lon:.6f}")
        print(f"\n  Google Maps: https://maps.google.com/?q={lat},{lon}")
    except Exception as e:
        print(f"\nError: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
