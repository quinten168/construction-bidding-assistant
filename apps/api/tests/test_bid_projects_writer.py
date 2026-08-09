"""
Integration tests for backend/bid_projects_writer.py (#37) and its wiring through
backend/report.py::write_bid_project() (the plan_reader -> scratch.bid_projects seam), against the
real scratch.bid_projects table (Supabase, see docs/DATA_ACCESS_SCRATCH.md).

Skipped entirely unless SUPABASE_TEAM_DB_URL is set (same convention as test_bid_results_admin.py).
Uses clearly-fake ZZTEST project keys and cleans up after itself.

Run: SUPABASE_TEAM_DB_URL='postgresql://...' python -m pytest tests/test_bid_projects_writer.py -q
"""
from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.skipif(
    not os.environ.get("SUPABASE_TEAM_DB_URL"),
    reason="SUPABASE_TEAM_DB_URL not set — needs a live Supabase scratch schema connection",
)

from backend import bid_projects_writer as bpw  # noqa: E402
from backend import ci_db  # noqa: E402
from backend import report as report_svc  # noqa: E402

KEY = "ZZTEST_MN_STEARNS_CO_MELROSE_2024-01-01"
KEY_B = "ZZTEST_MN_STEARNS_CO_MELROSE_2024-01-02"


def _cleanup():
    with ci_db.get_conn() as conn, conn.cursor() as cur:
        cur.execute("delete from scratch.bid_projects where project_natural_key like 'ZZTEST_%'")


def _raw_insert(row: dict):
    """Bypass bpw.upsert() (and therefore find_location_match) entirely -- for setting up a
    pre-existing-data fixture that the location-match feature itself would never produce (e.g. two
    distinct rows that already share a location), so tests can exercise the ambiguous-match case."""
    cols = sorted(row)
    with ci_db.get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            f"insert into scratch.bid_projects ({', '.join(cols)}) "
            f"values ({', '.join('%s' for _ in cols)})",
            [row[c] for c in cols])


def _row(key: str, **overrides) -> dict:
    row = {
        "project_natural_key": key, "state": "MN", "county": "STEARNS CO",
        "bid_date": "2024-01-01", "plan_uid": "zztestuid01", "join_key": "MN~stearns~ZZTEST",
        "row_source": "plan_reader", "mix_tons": 1000.0,
        "duplicate_flag": False, "duplicate_reason": None,
    }
    row.update(overrides)
    return row


def test_upsert_inserts_a_new_row():
    _cleanup()
    try:
        result = bpw.upsert(_row(KEY), list(_row(KEY).keys()))
        assert result["inserted"] is True
        assert result["project_natural_key"] == KEY

        with ci_db.get_conn() as conn, conn.cursor() as cur:
            cur.execute("select state, mix_tons, row_source from scratch.bid_projects "
                        "where project_natural_key = %s", (KEY,))
            row = cur.fetchone()
            assert row is not None
            assert row["state"] == "MN"
            assert row["mix_tons"] == 1000.0
            assert row["row_source"] == "plan_reader"
    finally:
        _cleanup()


def test_upsert_on_conflict_updates_the_existing_row():
    _cleanup()
    try:
        first = bpw.upsert(_row(KEY, mix_tons=1000.0), list(_row(KEY).keys()))
        assert first["inserted"] is True

        second = bpw.upsert(_row(KEY, mix_tons=2500.0), list(_row(KEY).keys()))
        assert second["inserted"] is False  # xmax=0 check: this was an UPDATE, not a fresh INSERT

        with ci_db.get_conn() as conn, conn.cursor() as cur:
            cur.execute("select count(*) as n, max(mix_tons) as mt from scratch.bid_projects "
                        "where project_natural_key = %s", (KEY,))
            row = cur.fetchone()
            assert row["n"] == 1               # no duplicate row, upsert not insert-again
            assert row["mt"] == 2500.0          # value from the second call won
    finally:
        _cleanup()


def test_never_deletes_project_natural_key_on_conflict():
    """Rule 1: _NEVER_UPDATE protects the primary key itself even when everything else changes."""
    _cleanup()
    try:
        bpw.upsert(_row(KEY), list(_row(KEY).keys()))
        bpw.upsert(_row(KEY, state="ND"), list(_row(KEY).keys()))
        with ci_db.get_conn() as conn, conn.cursor() as cur:
            cur.execute("select project_natural_key from scratch.bid_projects "
                        "where project_natural_key = %s", (KEY,))
            assert cur.fetchone()["project_natural_key"] == KEY
    finally:
        _cleanup()


def test_same_key_different_plan_uid_disambiguates_instead_of_overwriting():
    """Rule 4 (updated): a second, different PDF landing on the same project_natural_key must NOT
    silently overwrite the first plan's row via `on conflict ... do update`. The first row survives
    untouched under its original key; the second plan lands as a new, flagged row under a
    disambiguated (`_2`-suffixed) key instead."""
    _cleanup()
    try:
        first = bpw.upsert(_row(KEY, plan_uid="original_uid", mix_tons=1000.0), list(_row(KEY).keys()))
        assert first["inserted"] is True

        result = bpw.upsert(
            _row(KEY, plan_uid="a_different_uid", mix_tons=2500.0), list(_row(KEY).keys()))
        assert result["inserted"] is True
        assert result["project_natural_key"] == f"{KEY}_2"
        assert result["duplicate_flag"] is True
        assert "same_key_different_plan_uid" in (result["duplicate_reason"] or "")

        with ci_db.get_conn() as conn, conn.cursor() as cur:
            cur.execute(
                "select project_natural_key, plan_uid, mix_tons, duplicate_flag "
                "from scratch.bid_projects where project_natural_key like %s "
                "order by project_natural_key", (f"{KEY}%",))
            rows = cur.fetchall()
            assert len(rows) == 2, "the original row must survive alongside the new one, not be replaced"
            original, new = rows[0], rows[1]
            assert original["project_natural_key"] == KEY
            assert original["plan_uid"] == "original_uid"
            assert original["mix_tons"] == 1000.0          # untouched by the second upsert
            assert original["duplicate_flag"] is False     # never touched, never flagged
            assert new["project_natural_key"] == f"{KEY}_2"
            assert new["plan_uid"] == "a_different_uid"
            assert new["mix_tons"] == 2500.0
            assert new["duplicate_flag"] is True
    finally:
        _cleanup()


def test_a_third_colliding_plan_gets_the_next_incremented_suffix():
    """The counter keeps incrementing past _2 — proves _find_free_key doesn't just handle the
    two-plan case."""
    _cleanup()
    try:
        bpw.upsert(_row(KEY, plan_uid="uid_1"), list(_row(KEY).keys()))
        bpw.upsert(_row(KEY, plan_uid="uid_2"), list(_row(KEY).keys()))
        third = bpw.upsert(_row(KEY, plan_uid="uid_3"), list(_row(KEY).keys()))
        assert third["project_natural_key"] == f"{KEY}_3"

        with ci_db.get_conn() as conn, conn.cursor() as cur:
            cur.execute("select count(*) as n from scratch.bid_projects "
                        "where project_natural_key like %s", (f"{KEY}%",))
            assert cur.fetchone()["n"] == 3
    finally:
        _cleanup()


def test_no_conflict_between_two_genuinely_different_projects():
    _cleanup()
    try:
        bpw.upsert(_row(KEY, plan_uid="uid_a"), list(_row(KEY).keys()))
        result = bpw.upsert(
            _row(KEY_B, plan_uid="uid_b", join_key="MN~stearns~ZZTESTB"), list(_row(KEY_B).keys()))
        assert result["duplicate_flag"] is False
        assert result["inserted"] is True
    finally:
        _cleanup()


def test_write_bid_project_end_to_end_from_a_plan_payload():
    """The actual wiring added to report.py: a verified plan_payload dict (the same shape
    apply_verification() returns) goes in, a real scratch.bid_projects row comes out."""
    _cleanup()
    payload = {
        "plan_id": "zztest-plan-1",
        "content_hash": "zztestcontenthash01",
        "identity": {
            "state": "MN", "county": "Stearns", "location": "TH 23, Melrose",
            "sp_number": "SP 7305-45", "geocoded_city": "Melrose",
            "bid_deadline": "2024-06-15", "latitude": 45.67, "longitude": -94.81,
        },
        "quantities": [{"label": "MIX", "value": 500.0, "unit": "t"}],
        "gotchas": [],
        "archetype": "Mill & Overlay",
    }
    try:
        result = report_svc.write_bid_project(payload)
        assert result is not None, "write_bid_project() returned None — check logs for the swallowed exception"
        assert result["inserted"] is True
        # key is now {state}_{county}_{bid_date}_{lat}_{lon}, no longer city-based — non-provisional
        # since state/county/bid_date/lat/long are all present, matching a real verified payload.
        assert result["project_natural_key"] == "MN_STEARNS_CO_2024-06-15_45.670_-94.810"

        with ci_db.get_conn() as conn, conn.cursor() as cur:
            cur.execute(
                "select state, plan_reader_archetype, row_source from scratch.bid_projects "
                "where project_natural_key = %s", (result["project_natural_key"],),
            )
            row = cur.fetchone()
            assert row is not None
            assert row["state"] == "MN"
            assert row["plan_reader_archetype"] == "Mill & Overlay"
            assert row["row_source"] == "plan_reader"
    finally:
        with ci_db.get_conn() as conn, conn.cursor() as cur:
            cur.execute("delete from scratch.bid_projects where project_natural_key like 'MN_STEARNS_CO_2024-06-15%'")
        _cleanup()


def test_write_bid_project_never_raises_when_the_writer_errors(monkeypatch):
    """Fail-open: a DB/writer failure must never propagate into the finalize endpoint. Patches the
    writer to raise rather than exercising a real error path, so this can't accidentally write a
    non-ZZTEST-keyed row (an empty/garbage payload still produces a real, non-namespaced
    project_natural_key via the sentinel-key fallback — not safe to actually upsert here)."""
    def _boom(*a, **kw):
        raise RuntimeError("simulated writer failure")

    monkeypatch.setattr(bpw, "upsert", _boom)
    result = report_svc.write_bid_project({
        "plan_id": "zztest-plan-error", "identity": {"state": "MN"}, "quantities": [],
    })
    assert result is None


# --- location-match redirect (rule 5) --------------------------------------------------------------
# All fixtures below add project_latitude/project_longitude on top of _row()'s defaults, since a row
# with no location signal is exactly what test_no_location_match_when_location_fields_missing checks
# falls back to today's insert-under-own-key behavior.

def test_location_match_redirects_second_write_onto_first_row():
    """A re-scan of the same physical project (same state/county/lat/lon) computing a DIFFERENT
    project_natural_key -- e.g. a corrected bid_date -- updates the existing row instead of forking
    a second one. This is the exact Kandiyohi Co. scenario from 2026-08-08."""
    _cleanup()
    try:
        first_row = _row(KEY, plan_uid="uid_first",
                          project_latitude=45.671, project_longitude=-94.812)
        first = bpw.upsert(first_row, list(first_row.keys()))
        assert first["inserted"] is True
        assert first["merged_into"] is None

        second_row = _row(KEY_B, plan_uid="uid_second",
                           project_latitude=45.671, project_longitude=-94.812)
        second = bpw.upsert(second_row, list(second_row.keys()))
        assert second["merged_into"] == KEY
        assert second["project_natural_key"] == KEY
        assert second["inserted"] is False  # updated the first row, did not insert a new one

        with ci_db.get_conn() as conn, conn.cursor() as cur:
            cur.execute("select count(*) as n from scratch.bid_projects "
                        "where project_natural_key in (%s, %s)", (KEY, KEY_B))
            assert cur.fetchone()["n"] == 1  # no fork -- KEY_B was never written as its own row
    finally:
        _cleanup()


def test_location_match_fills_gaps_without_nulling_existing_values():
    """The merge-path SET clause is coalesce(excluded.col, table.col): a worse/partial re-scan that
    detects fewer quantities must not erase numbers a better prior scan already found."""
    _cleanup()
    try:
        first_row = _row(KEY, plan_uid="uid_first", mix_tons=500.0,
                          project_latitude=45.671, project_longitude=-94.812)
        bpw.upsert(first_row, list(first_row.keys()))

        second_row = _row(KEY_B, plan_uid="uid_second", mix_tons=None,
                           project_latitude=45.671, project_longitude=-94.812)
        bpw.upsert(second_row, list(second_row.keys()))

        with ci_db.get_conn() as conn, conn.cursor() as cur:
            cur.execute("select mix_tons from scratch.bid_projects where project_natural_key = %s", (KEY,))
            assert cur.fetchone()["mix_tons"] == 500.0  # not nulled out by the second scan's gap
    finally:
        _cleanup()


def test_location_match_new_non_null_value_overwrites():
    """The other half of fill-gaps-only: a fresh NON-null value still wins, so a genuine correction
    (the whole reason this feature exists) actually lands."""
    _cleanup()
    try:
        first_row = _row(KEY, plan_uid="uid_first", mix_tons=500.0,
                          project_latitude=45.671, project_longitude=-94.812)
        bpw.upsert(first_row, list(first_row.keys()))

        second_row = _row(KEY_B, plan_uid="uid_second", mix_tons=750.0,
                           project_latitude=45.671, project_longitude=-94.812)
        bpw.upsert(second_row, list(second_row.keys()))

        with ci_db.get_conn() as conn, conn.cursor() as cur:
            cur.execute("select mix_tons from scratch.bid_projects where project_natural_key = %s", (KEY,))
            assert cur.fetchone()["mix_tons"] == 750.0
    finally:
        _cleanup()


def test_no_location_match_beyond_tolerance():
    """~0.01 degrees latitude is roughly 1.1km -- well past the 3-decimal/~111m tolerance
    build_project_natural_key itself uses. Two genuinely different nearby projects must not merge."""
    _cleanup()
    try:
        first_row = _row(KEY, plan_uid="uid_first",
                          project_latitude=45.671, project_longitude=-94.812)
        bpw.upsert(first_row, list(first_row.keys()))

        second_row = _row(KEY_B, plan_uid="uid_second",
                           project_latitude=45.681, project_longitude=-94.812)
        result = bpw.upsert(second_row, list(second_row.keys()))
        assert result["merged_into"] is None
        assert result["project_natural_key"] == KEY_B
        assert result["inserted"] is True

        with ci_db.get_conn() as conn, conn.cursor() as cur:
            cur.execute("select count(*) as n from scratch.bid_projects "
                        "where project_natural_key in (%s, %s)", (KEY, KEY_B))
            assert cur.fetchone()["n"] == 2
    finally:
        _cleanup()


def test_no_location_match_when_location_fields_missing():
    """A row with no lat/long at all (e.g. a CLI-ingested plan that never went through the midpoint
    lookup) has no location signal to match on -- must fall back to today's behavior, not error."""
    _cleanup()
    try:
        first_row = _row(KEY, plan_uid="uid_first",
                          project_latitude=45.671, project_longitude=-94.812)
        bpw.upsert(first_row, list(first_row.keys()))

        second_row = _row(KEY_B, plan_uid="uid_second")  # no project_latitude/project_longitude
        result = bpw.upsert(second_row, list(second_row.keys()))
        assert result["merged_into"] is None
        assert result["project_natural_key"] == KEY_B
    finally:
        _cleanup()


def test_no_location_match_when_ambiguous():
    """Two distinct rows already share this location -- pre-existing data the merge feature itself
    would never produce (it always redirects onto the first match, so it can't create a second).
    Seeded directly via _raw_insert to simulate that state. Refuse to guess which one to merge into
    rather than picking one arbitrarily."""
    _cleanup()
    try:
        _raw_insert(_row(KEY, plan_uid="uid_existing_a",
                          project_latitude=45.671, project_longitude=-94.812))
        _raw_insert(_row(KEY_B, plan_uid="uid_existing_b",
                          project_latitude=45.671, project_longitude=-94.812))

        third_key = f"{KEY}_THIRD"
        third_row = _row(third_key, plan_uid="uid_third",
                          project_latitude=45.671, project_longitude=-94.812)
        result = bpw.upsert(third_row, list(third_row.keys()))
        assert result["merged_into"] is None
        assert result["project_natural_key"] == third_key
        assert result["inserted"] is True
    finally:
        _cleanup()
