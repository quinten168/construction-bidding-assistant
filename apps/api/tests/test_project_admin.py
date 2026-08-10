"""
Integration tests for backend/project_admin.py, focused on soft_delete_project() (#55) — against
the real scratch.bid_projects table (Supabase, see docs/DATA_ACCESS_SCRATCH.md).

Skipped entirely unless SUPABASE_TEAM_DB_URL is set (same convention as test_bid_projects_writer.py).
Uses clearly-fake ZZTEST project keys and cleans up after itself.

Run: SUPABASE_TEAM_DB_URL='postgresql://...' python -m pytest tests/test_project_admin.py -q
"""
from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.skipif(
    not os.environ.get("SUPABASE_TEAM_DB_URL"),
    reason="SUPABASE_TEAM_DB_URL not set — needs a live Supabase scratch schema connection",
)

from backend import ci_db  # noqa: E402
from backend import project_admin as pa  # noqa: E402

KEY = "ZZTEST_MN_STEARNS_CO_2024-01-01_45.670_-94.810"


def _cleanup():
    with ci_db.get_conn() as conn, conn.cursor() as cur:
        cur.execute("delete from scratch.bid_results where project_natural_key like 'ZZTEST_%'")
        cur.execute("delete from scratch.bid_projects where project_natural_key like 'ZZTEST_%'")


def _insert_project(key: str = KEY, **overrides):
    row = {
        "project_natural_key": key, "state": "MN", "county": "STEARNS CO",
        "bid_date": "2024-01-01", "mix_tons": 1000.0, "row_source": "plan_reader",
    }
    row.update(overrides)
    cols = sorted(row)
    with ci_db.get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            f"insert into scratch.bid_projects ({', '.join(cols)}) values "
            f"({', '.join('%s' for _ in cols)})",
            [row[c] for c in cols],
        )


def test_soft_delete_sets_deleted_at_and_hides_from_list_projects():
    _cleanup()
    try:
        _insert_project()
        result = pa.soft_delete_project(KEY)
        assert result["project_natural_key"] == KEY

        with ci_db.get_conn() as conn, conn.cursor() as cur:
            cur.execute(
                "select deleted_at from scratch.bid_projects where project_natural_key = %s", (KEY,))
            assert cur.fetchone()["deleted_at"] is not None

        keys = {p["project_natural_key"] for p in pa.list_projects()}
        assert KEY not in keys
    finally:
        _cleanup()


def test_soft_delete_never_touches_bid_results():
    """The whole point of soft delete over a real DELETE (#55): bid_results survives untouched,
    no ON DELETE CASCADE ever fires because no DELETE is ever issued."""
    _cleanup()
    try:
        _insert_project()
        with ci_db.get_conn() as conn, conn.cursor() as cur:
            cur.execute(
                "insert into scratch.bid_results "
                "(project_natural_key, competitor_unit_id, raw_bidder_name, bid_amount, bid_rank, did_win) "
                "values (%s, 'ZZTEST COMPETITOR', 'ZZTEST COMPETITOR', 100.0, 1, true)",
                (KEY,),
            )

        pa.soft_delete_project(KEY)

        with ci_db.get_conn() as conn, conn.cursor() as cur:
            cur.execute(
                "select count(*) as n from scratch.bid_results where project_natural_key = %s", (KEY,))
            assert cur.fetchone()["n"] == 1, "bid_results must survive a soft delete of its project"
    finally:
        _cleanup()


def test_soft_delete_twice_raises_already_deleted_not_silent():
    _cleanup()
    try:
        _insert_project()
        pa.soft_delete_project(KEY)
        with pytest.raises(pa.ValidationError, match="already deleted"):
            pa.soft_delete_project(KEY)
    finally:
        _cleanup()


def test_soft_delete_nonexistent_project_raises():
    _cleanup()
    try:
        with pytest.raises(pa.ValidationError, match="No project found"):
            pa.soft_delete_project(KEY)
    finally:
        _cleanup()


def test_update_project_materials_blocked_on_deleted_project():
    _cleanup()
    try:
        _insert_project()
        pa.soft_delete_project(KEY)
        with pytest.raises(pa.ValidationError, match="No project found"):
            pa.update_project_materials(KEY, {"mix_tons": 500.0})
    finally:
        _cleanup()
