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


def test_find_conflicts_flags_same_key_different_plan_uid_but_still_writes():
    """Rule 4: a second, different PDF landing on the same project_natural_key is flagged, not
    skipped — the exact collision build_project_natural_key's hash suffix is meant to prevent for
    provisional keys, still possible for two genuinely different PDFs of the SAME real project."""
    _cleanup()
    try:
        bpw.upsert(_row(KEY, plan_uid="original_uid"), list(_row(KEY).keys()))

        result = bpw.upsert(_row(KEY, plan_uid="a_different_uid"), list(_row(KEY).keys()))
        assert result["duplicate_flag"] is True
        assert "same_key_different_plan_uid" in (result["duplicate_reason"] or "")

        # Rule 4 in effect: the row was still written (flagged, not dropped).
        with ci_db.get_conn() as conn, conn.cursor() as cur:
            cur.execute("select duplicate_flag, duplicate_reason from scratch.bid_projects "
                        "where project_natural_key = %s", (KEY,))
            row = cur.fetchone()
            assert row["duplicate_flag"] is True
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
            "bid_deadline": "2024-06-15",
        },
        "quantities": [{"label": "MIX", "value": 500.0, "unit": "t"}],
        "gotchas": [],
        "archetype": "Mill & Overlay",
    }
    try:
        result = report_svc.write_bid_project(payload)
        assert result is not None, "write_bid_project() returned None — check logs for the swallowed exception"
        assert result["inserted"] is True

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
            cur.execute("delete from scratch.bid_projects where project_natural_key like 'MN_STEARNS_CO_MELROSE%'")
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
