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

import logging
import os
import time
from typing import Optional

import requests

GEOCODE_URL = "https://maps.googleapis.com/maps/api/geocode/json"

# Every failure path here returns None (see reverse_geocode_latlon's docstring on why it must never
# raise). That made a fixable misconfiguration and a legitimate empty answer indistinguishable, and
# it hid a REQUEST_DENIED/billing-disabled outage until someone read the raw HTTP body by hand
# (issue #56). The return value stays None; the LOG does the distinguishing. A real failure is
# ERROR and names Google's verbatim status; ZERO_RESULTS is DEBUG, because it is not a failure.
log = logging.getLogger("plan_reader.reverse_geocode")

# Google's `status` values that mean "your request never ran" as opposed to "there is nothing here".
# All are operator-actionable — a key, a billing account, a quota, or a malformed request.
_HARD_FAILURE_STATUSES = frozenset({
    "REQUEST_DENIED",       # bad/absent/restricted key, or billing not enabled on the GCP project
    "OVER_QUERY_LIMIT",     # quota or rate cap
    "OVER_DAILY_LIMIT",     # billing disabled / expired card / daily cap
    "INVALID_REQUEST",      # malformed latlng
    "UNKNOWN_ERROR",        # Google-side transient; retryable
})

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
    return _lookup(lat, lon, timeout=timeout)[0]


def _lookup(lat, lon, *, timeout: int = 30) -> tuple[Optional[dict], bool]:
    """(result, definitive). `definitive` is True when Google actually answered — an OK result or
    a real ZERO_RESULTS — and False when the request never ran (no key, transport error, or an
    operator-actionable status such as REQUEST_DENIED).

    Only the caller can act on that difference, and exactly one does: reverse_geocode_cached, which
    must memoise a definitive empty answer but must NOT memoise a failure. See issue #56 — the two
    were previously identical Nones, so an outage poisoned the cache for the life of the process.
    """
    if lat is None or lon is None:
        return None, False
    try:
        lat_f, lon_f = float(lat), float(lon)
    except (TypeError, ValueError):
        log.error("geocode: non-numeric coordinate (%r, %r) — stage skipped", lat, lon)
        return None, False
    if lat_f != lat_f or lon_f != lon_f:  # NaN
        log.error("geocode: NaN coordinate (%r, %r) — stage skipped", lat, lon)
        return None, False

    try:
        key = _api_key()
    except GeocodeConfigError as e:
        # Operator-actionable and previously silent: with no key the stage is a no-op and every
        # project_natural_key silently takes the UNKNOWN city sentinel.
        log.error("geocode: DISABLED — %s", e)
        return None, False

    try:
        resp = requests.get(
            GEOCODE_URL,
            params={"latlng": f"{lat_f},{lon_f}", "key": key},
            timeout=timeout,
        )
        resp.raise_for_status()
        body = resp.json()
    except Exception as e:                                    # noqa: BLE001 — must never raise
        log.error("geocode: transport/HTTP failure for (%s, %s) — %s: %s",
                  lat_f, lon_f, type(e).__name__, e)
        return None, False

    # Google signals application errors in the body with HTTP 200 — the same "don't trust an HTTP
    # 200" failure class as CLAUDE.md rough edge 2 and rough edge 6 (road_midpoint's DOT lookups).
    # ZERO_RESULTS is a legitimate empty answer. Everything else is operator-actionable, and the
    # two must not look alike in the logs even though both still return None (issue #56).
    status = body.get("status")
    if status in _HARD_FAILURE_STATUSES:
        log.error(
            "geocode: Google returned HTTP 200 with status=%s for (%s, %s) — THIS IS NOT "
            "'no city here', it is a request that never ran. error_message=%r. "
            "Until fixed, every project_natural_key takes the UNKNOWN city sentinel.",
            status, lat_f, lon_f, body.get("error_message"),
        )
        return None, False
    if status not in ("OK", "ZERO_RESULTS"):
        log.error("geocode: unrecognised Google status=%r for (%s, %s) — error_message=%r",
                  status, lat_f, lon_f, body.get("error_message"))
        return None, False

    results = body.get("results") or []
    if not results:
        # The one genuinely-empty answer: Google ran the query and there is no locality here.
        # Definitive, so the cache may keep it — re-asking cannot produce a different answer.
        log.debug("geocode: ZERO_RESULTS for (%s, %s) — no locality at this coordinate",
                  lat_f, lon_f)
        return None, True

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
    }, True


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

    info, definitive = _lookup(lat, lon, timeout=timeout)

    # Cache definitive answers only (issue #56) — an OK result, or a real ZERO_RESULTS, both of
    # which re-asking cannot change. A FAILURE is never cached: the REQUEST_DENIED seen on
    # 2026-08-03 (billing disabled) used to be memoised for the life of the process, so every
    # coordinate tried during the outage kept returning None even AFTER billing was fixed, and a
    # batch begun before the fix could never recover without a restart. A true no-locality
    # coordinate is still memoised, so this does not reintroduce the repeat-API-call cost that
    # test_a_none_result_is_cached_too guards.
    if definitive:
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
