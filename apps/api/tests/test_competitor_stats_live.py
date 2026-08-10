"""
Integration tests for backend/competitor_stats_live.py's pit-access split against the real
scratch.mn_pit_list table (Supabase, see docs/DATA_ACCESS_SCRATCH.md).

Skipped entirely unless SUPABASE_TEAM_DB_URL is set (see test_pit_list_admin.py for the same
convention). Uses clearly-fake ZZTEST pit rows and cleans up after itself.

Run: SUPABASE_TEAM_DB_URL='postgresql://...' python -m pytest tests/test_competitor_stats_live.py -q
"""
from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.skipif(
    not os.environ.get("SUPABASE_TEAM_DB_URL"),
    reason="SUPABASE_TEAM_DB_URL not set — needs a live Supabase scratch schema connection",
)

from backend import ci_db  # noqa: E402
from backend import competitor_stats_live as csl  # noqa: E402

PROJECT_LAT, PROJECT_LON = 46.0000, -94.0000
OPEN_PIT_LATLON = (46.0100, -94.0000)          # ~0.69 mi from the project — accessible to everyone
OWNED_PIT_LATLON = (46.0050, -94.0000)         # ~0.35 mi from the project — exclusive to the owner

OWNER_ID = "ZZTEST PIT OWNER CO"
OTHER_ID = "ZZTEST UNRELATED CO"


def _seed_pits():
    with ci_db.get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "delete from scratch.mn_pit_list where latitude = any(%s) and longitude = any(%s)",
            ([OPEN_PIT_LATLON[0], OWNED_PIT_LATLON[0]], [OPEN_PIT_LATLON[1], OWNED_PIT_LATLON[1]]),
        )
        cur.execute(
            "insert into scratch.mn_pit_list "
            "(latitude, longitude, name, access, county, rating, state, access_type, access_company) "
            "values (%s, %s, 'ZZTEST Open Pit', 'Everyone', 'ZZTEST County', 8, 'MN', 'open', null)",
            OPEN_PIT_LATLON,
        )
        cur.execute(
            "insert into scratch.mn_pit_list "
            "(latitude, longitude, name, access, county, rating, state, access_type, access_company) "
            "values (%s, %s, 'ZZTEST Owned Pit', %s, 'ZZTEST County', 6, 'MN', 'competitor', %s)",
            (*OWNED_PIT_LATLON, OWNER_ID, OWNER_ID),
        )


def _cleanup():
    with ci_db.get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "delete from scratch.mn_pit_list where latitude = any(%s) and longitude = any(%s)",
            ([OPEN_PIT_LATLON[0], OWNED_PIT_LATLON[0]], [OPEN_PIT_LATLON[1], OWNED_PIT_LATLON[1]]),
        )


def test_pit_access_returns_owned_pit_stats():
    """_pit_access() now reports only owned/private pits per competitor -- open-access pits are a
    project-wide fact reported once by nearest_open_pits(), not duplicated per competitor."""
    _seed_pits()
    try:
        with ci_db.get_conn() as conn:
            result = csl._pit_access(conn, [OWNER_ID, OTHER_ID], PROJECT_LAT, PROJECT_LON)

        owner_stats = result[OWNER_ID]
        other_stats = result[OTHER_ID]

        assert "nearest_open_pit" not in owner_stats
        assert "open_pits_within_25mi_count" not in owner_stats

        # Competitor-specific figure: only the owner sees the private pit.
        assert owner_stats["nearest_owned_pit"]["name"] == "ZZTEST Owned Pit"
        assert owner_stats["owned_pits_within_25mi_count"] == 1

        assert other_stats["nearest_owned_pit"] is None
        assert other_stats["owned_pits_within_25mi_count"] == 0
    finally:
        _cleanup()


def test_nearest_open_pits_sorted_and_limited():
    """The project-level nearest-open-pits lookup -- no radius cutoff, just the closest N by
    distance, sorted ascending."""
    far_lat, far_lon = 46.5000, -94.0000       # ~34.6 mi from the project -- outside the old 25mi
    with ci_db.get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "delete from scratch.mn_pit_list where latitude = any(%s) and longitude = any(%s)",
            ([OPEN_PIT_LATLON[0], far_lat], [OPEN_PIT_LATLON[1], far_lon]),
        )
        cur.execute(
            "insert into scratch.mn_pit_list "
            "(latitude, longitude, name, access, county, rating, state, access_type, access_company) "
            "values (%s, %s, 'ZZTEST Open Pit', 'Everyone', 'ZZTEST County', 8, 'MN', 'open', null)",
            OPEN_PIT_LATLON,
        )
        cur.execute(
            "insert into scratch.mn_pit_list "
            "(latitude, longitude, name, access, county, rating, state, access_type, access_company) "
            "values (%s, %s, 'ZZTEST Far Open Pit', 'Everyone', 'ZZTEST County', 5, 'MN', 'open', null)",
            (far_lat, far_lon),
        )
    try:
        result = csl.nearest_open_pits(PROJECT_LAT, PROJECT_LON, limit=1)
        assert result is not None
        assert len(result) == 1
        assert result[0]["name"] == "ZZTEST Open Pit"          # nearer one wins, even though a
                                                                 # farther pit also exists

        # Large limit so both ZZTEST pits are guaranteed present regardless of how much real
        # production data exists near this coordinate; filter to just ours before checking order.
        result_all = csl.nearest_open_pits(PROJECT_LAT, PROJECT_LON, limit=10_000)
        zztest_names = [p["name"] for p in result_all if p["name"].startswith("ZZTEST")]
        assert zztest_names.index("ZZTEST Open Pit") < zztest_names.index("ZZTEST Far Open Pit")
    finally:
        with ci_db.get_conn() as conn, conn.cursor() as cur:
            cur.execute(
                "delete from scratch.mn_pit_list where latitude = any(%s) and longitude = any(%s)",
                ([OPEN_PIT_LATLON[0], far_lat], [OPEN_PIT_LATLON[1], far_lon]),
            )


def test_nearest_open_pits_no_coordinates():
    assert csl.nearest_open_pits(None, None) is None
