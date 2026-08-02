"""
Integration tests for backend/pit_list_admin.py against the real scratch.mn_pit_list table
(Supabase, see docs/DATA_ACCESS_SCRATCH.md).

Skipped entirely unless SUPABASE_TEAM_DB_URL is set — there's no local mock for this table, same
as this repo's existing data tests read real CSVs directly (test_tools.py). Every test uses
clearly-fake ZZTEST-tagged coordinates/names and cleans up after itself in a finally block, so it's
safe to point at the real `scratch` schema without leaving test rows behind.

Run: SUPABASE_TEAM_DB_URL='postgresql://...' python -m pytest tests/test_pit_list_admin.py -q
"""
from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.skipif(
    not os.environ.get("SUPABASE_TEAM_DB_URL"),
    reason="SUPABASE_TEAM_DB_URL not set — needs a live Supabase scratch schema connection",
)

from backend import pit_list_admin as pla  # noqa: E402

# Coordinates far outside any real Minnesota pit (middle of Lake Superior-ish/out of state on
# purpose) so a real duplicate can never collide with this test data.
LAT_A, LON_A = 89.9001, -179.9001
LAT_B, LON_B = 89.9002, -179.9002


def _cleanup(*coords):
    for lat, lon in coords:
        try:
            pla.delete_pit(lat, lon)
        except pla.ValidationError:
            pass


def test_create_and_delete_pit():
    _cleanup((LAT_A, LON_A))
    try:
        pla.create_pit({
            "latitude": LAT_A, "longitude": LON_A, "name": "ZZTEST Pit A",
            "county": "ZZTEST County", "state": "MN",
        })
        rows = pla.list_pits(search="ZZTEST Pit A")
        assert any(r["latitude"] == LAT_A and r["longitude"] == LON_A for r in rows)
    finally:
        _cleanup((LAT_A, LON_A))
    with pytest.raises(pla.ValidationError):
        pla.delete_pit(LAT_A, LON_A)  # already gone


def test_exact_coordinate_duplicate_is_blocked():
    _cleanup((LAT_A, LON_A))
    try:
        pla.create_pit({"latitude": LAT_A, "longitude": LON_A, "name": "ZZTEST Pit A", "county": "ZZTEST County"})
        with pytest.raises(pla.ValidationError):
            pla.create_pit({"latitude": LAT_A, "longitude": LON_A, "name": "ZZTEST Pit A Again", "county": "ZZTEST County"})
    finally:
        _cleanup((LAT_A, LON_A))


def test_name_county_match_warns_but_force_creates():
    _cleanup((LAT_A, LON_A), (LAT_B, LON_B))
    try:
        pla.create_pit({"latitude": LAT_A, "longitude": LON_A, "name": "ZZTEST Shared Name", "county": "ZZTEST County"})

        with pytest.raises(pla.DuplicateWarning) as exc:
            pla.create_pit({"latitude": LAT_B, "longitude": LON_B, "name": "ZZTEST Shared Name", "county": "ZZTEST County"})
        assert exc.value.payload["warning"] == "possible_duplicate"

        # force=True proceeds despite the warning
        pla.create_pit({"latitude": LAT_B, "longitude": LON_B, "name": "ZZTEST Shared Name", "county": "ZZTEST County"}, force=True)
        rows = pla.list_pits(search="ZZTEST Shared Name")
        assert len(rows) == 2
    finally:
        _cleanup((LAT_A, LON_A), (LAT_B, LON_B))


def test_update_pit_fields():
    _cleanup((LAT_A, LON_A))
    try:
        pla.create_pit({"latitude": LAT_A, "longitude": LON_A, "name": "ZZTEST Pit A", "county": "ZZTEST County", "rating": 1})
        pla.update_pit(LAT_A, LON_A, {"rating": 5})
        rows = pla.list_pits(search="ZZTEST Pit A")
        assert rows[0]["rating"] == 5
    finally:
        _cleanup((LAT_A, LON_A))


def test_access_company_must_be_in_registry():
    _cleanup((LAT_A, LON_A))
    try:
        with pytest.raises(pla.ValidationError):
            pla.create_pit({
                "latitude": LAT_A, "longitude": LON_A, "name": "ZZTEST Pit A",
                "county": "ZZTEST County", "access_company": "ZZTEST Not A Real Competitor",
            })
    finally:
        _cleanup((LAT_A, LON_A))
