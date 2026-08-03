#!/usr/bin/env python3
"""
Reverse geocode a (latitude, longitude) into city / county / state / zip.

Runs as the 6th `process_pdf` stage, immediately after the midpoint stage
(`apps/api/backend/midpoint_bridge.py`) that produces the coordinates this consumes. Its reason to
exist is `project_natural_key`:

    project_natural_key = {state}_{county}_{city}_{bid_date}

`scratch.bid_projects` is keyed on it, and **city is the one component plan_reader cannot extract
from a plan set**. There is no city field in `01_pipeline/schema.py` and no prospect of one. The
midpoint stage already turns route/milepost into coordinates, and a coordinate does yield a city,
so the gap closes here rather than by adding another extraction target.

PROVENANCE, NOT OVERWRITES
--------------------------
This module never replaces an extracted value. `county` in particular is extracted from the plan
AND available here, and the two disagree: 10 of the 117 corpus rows have a county that is `?` or
names two counties at once. Both values are carried, in separate columns, with a provenance tag —
contract §4.5's `coordinate_provenance` pattern applied to every geocoded field. A consumer that
prefers the geocoded county is choosing to, rather than doing it by accident (contract §5).

KNOWN AND ACCEPTED IMPRECISION
------------------------------
A geocoded city is the nearest locality to a **road midpoint**, which is not necessarily the city
the DOT used to name the project. Some generated keys will therefore not match how historical rows
were keyed. This was accepted deliberately on 2026-08-03: getting rows into the table matters more
than getting the key final, and `project_natural_key` is a natural key, so it can be recomputed
table-wide with an UPDATE once the composition is settled with the CI workstream.

CREDENTIALS
-----------
Reads `GOOGLE_GEOCODING_API_KEY` from the environment. This is a **server-side** key and must be
distinct from `NEXT_PUBLIC_GOOGLE_MAPS_API_KEY`, which the pit-list page ships to the browser and
which is therefore public and referrer-restricted. A referrer-restricted key will not work here;
restrict this one by IP or leave it unrestricted but Geocoding-API-only.

Derived from a prior-project implementation (`reverse_geocode_latlon` and its rounded-coordinate
cache). That original hardcoded its API key in a file kept in iCloud; the key has been reported for
rotation and is deliberately not reproduced anywhere in this repo.
"""
from __future__ import annotations

import os
import time
from typing import Optional

import requests

GEOCODE_URL = "https://maps.googleapis.com/maps/api/geocode/json"

# Google's address_components type -> the field we want. Order matters within each tuple: the first
# type present wins. `postal_town` is the fallback for localities that Google does not tag as
# `locality`, which is rare in the six operating states but free to support.
_CITY_TYPES = ("locality", "postal_town", "sublocality", "administrative_area_level_3")
_COUNTY_TYPE = "administrative_area_level_2"
_STATE_TYPE = "administrative_area_level_1"
_ZIP_TYPE = "postal_code"

# Rounding to 3 decimal places is ~110 m. Two midpoints that close resolve to the same locality, so
# this collapses float jitter without ever merging genuinely different towns. Carried over from the
# original implementation.
_CACHE_PRECISION = 3

# Bounded so a long batch cannot grow it without limit. Plans are processed one at a time on the
# live path, so this is really a guard for the CLI/backfill case.
_MAX_CACHE = 4096
_cache: dict[tuple[float, float], Optional[dict]] = {}

# Google's published Geocoding limit is 50 QPS; this is far under it and exists to be polite on
# bursty backfills rather than to satisfy a documented requirement.
_THROTTLE_SECONDS = 0.05

PROVENANCE = "reverse_geocode"


class GeocodeConfigError(RuntimeError):
    """No API key. Raised only by the CLI; the library path returns None instead."""


def _api_key() -> str:
    key = os.environ.get("GOOGLE_GEOCODING_API_KEY", "").strip()
    if not key:
        raise GeocodeConfigError(
            "GOOGLE_GEOCODING_API_KEY is not set. This is a server-side key and must NOT be the "
            "same value as NEXT_PUBLIC_GOOGLE_MAPS_API_KEY, which is public."
        )
    return key


def _components(result: dict) -> dict[str, dict]:
    """address_components -> {type: {"long": ..., "short": ...}}."""
    out: dict[str, dict] = {}
    for comp in result.get("address_components", []):
        for t in comp.get("types", []):
            out.setdefault(t, {"long": comp.get("long_name"), "short": comp.get("short_name")})
    return out


def reverse_geocode_latlon(lat, lon, *, timeout: int = 30) -> Optional[dict]:
    """{city, county, state, zip, provenance, formatted_address} or None.

    Returns None rather than raising on every failure path — a missing city must degrade the
    natural key, never fail the report. Same fail-open convention as midpoint_bridge.compute_midpoint
    and competitor_live.generate.
    """
    if lat is None or lon is None:
        return None
    try:
        lat_f, lon_f = float(lat), float(lon)
    except (TypeError, ValueError):
        return None
    if lat_f != lat_f or lon_f != lon_f:  # NaN
        return None

    try:
        key = _api_key()
    except GeocodeConfigError:
        return None

    try:
        resp = requests.get(
            GEOCODE_URL,
            params={"latlng": f"{lat_f},{lon_f}", "key": key},
            timeout=timeout,
        )
        resp.raise_for_status()
        body = resp.json()
    except Exception:
        return None

    # Google signals application errors in the body with HTTP 200 — the same "don't trust an HTTP
    # 200" failure class as CLAUDE.md rough edge 2 and rough edge 6 (road_midpoint's DOT lookups).
    # ZERO_RESULTS is a legitimate empty answer; anything else is a real failure, and both return
    # None here because the caller cannot act differently on them.
    if body.get("status") not in ("OK", "ZERO_RESULTS"):
        return None
    results = body.get("results") or []
    if not results:
        return None

    comp = _components(results[0])

    city = None
    for t in _CITY_TYPES:
        if t in comp:
            city = comp[t]["long"]
            break

    # short_name for state, so this yields "MN" and not "Minnesota" — bid_projects.state and the
    # contract's join_key prefix are both two-letter. The original implementation used long_name
    # here; this is a deliberate divergence, not an oversight.
    state = comp.get(_STATE_TYPE, {}).get("short")

    # Google returns "Stearns County"; the trailing "County" is stripped downstream by
    # 01_pipeline/join_key.normalize_county per contract §3. Left intact here so the raw API answer
    # stays inspectable.
    county = comp.get(_COUNTY_TYPE, {}).get("long")

    return {
        "city": city,
        "county": county,
        "state": state,
        "zip": comp.get(_ZIP_TYPE, {}).get("long"),
        "provenance": PROVENANCE,
        "formatted_address": results[0].get("formatted_address"),
    }


def reverse_geocode_cached(lat, lon, *, timeout: int = 30) -> Optional[dict]:
    """reverse_geocode_latlon with the rounded-coordinate cache. Carried over from the original."""
    if lat is None or lon is None:
        return None
    try:
        key = (round(float(lat), _CACHE_PRECISION), round(float(lon), _CACHE_PRECISION))
    except (TypeError, ValueError):
        return None

    if key in _cache:
        return _cache[key]

    info = reverse_geocode_latlon(lat, lon, timeout=timeout)

    if len(_cache) >= _MAX_CACHE:
        _cache.clear()
    _cache[key] = info
    time.sleep(_THROTTLE_SECONDS)
    return info


def _main() -> int:
    import argparse
    import json

    ap = argparse.ArgumentParser(description="Reverse geocode a lat/lon to city/county/state/zip.")
    ap.add_argument("latitude", type=float)
    ap.add_argument("longitude", type=float)
    args = ap.parse_args()

    _api_key()  # fail loudly here, unlike the library path
    out = reverse_geocode_cached(args.latitude, args.longitude)
    if out is None:
        print("no result (or lookup failed)")
        return 1
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
