"""
Integration tests for backend/bid_results_admin.py against the real scratch.bid_projects /
scratch.bid_results / scratch.competitor_name_registry tables (Supabase, see
docs/DATA_ACCESS_SCRATCH.md).

Skipped entirely unless SUPABASE_TEAM_DB_URL is set (see test_pit_list_admin.py for the same
convention). Uses a clearly-fake ZZTEST project key and cleans up after itself.

Run: SUPABASE_TEAM_DB_URL='postgresql://...' python -m pytest tests/test_bid_results_admin.py -q
"""
from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.skipif(
    not os.environ.get("SUPABASE_TEAM_DB_URL"),
    reason="SUPABASE_TEAM_DB_URL not set — needs a live Supabase scratch schema connection",
)

from backend import bid_results_admin as bra  # noqa: E402
from backend import ci_db  # noqa: E402

TEST_PROJECT_KEY = "ZZTEST_PROJECT_BID_ENTRY_1"
UNKNOWN_BIDDER = "ZZTEST Brand New Bidder Co"


def _reset_project():
    with ci_db.get_conn() as conn, conn.cursor() as cur:
        cur.execute("delete from scratch.bid_projects where project_natural_key = %s", (TEST_PROJECT_KEY,))
        cur.execute(
            "insert into scratch.bid_projects (project_natural_key, state, county, bid_date) "
            "values (%s, 'MN', 'ZZTEST County', '2024-01-01')",
            (TEST_PROJECT_KEY,),
        )


def _cleanup():
    with ci_db.get_conn() as conn, conn.cursor() as cur:
        cur.execute("delete from scratch.bid_projects where project_natural_key = %s", (TEST_PROJECT_KEY,))
        cur.execute("delete from scratch.competitor_name_registry where raw_name_variant = %s", (UNKNOWN_BIDDER,))


def test_project_with_no_results_appears_in_picker():
    _reset_project()
    try:
        rows = bra.list_projects_missing_results(search="ZZTEST County")
        assert any(r["project_natural_key"] == TEST_PROJECT_KEY for r in rows)
    finally:
        _cleanup()


def test_submit_happy_path_computes_rank():
    _reset_project()
    try:
        result = bra.submit_bid_results(TEST_PROJECT_KEY, [
            {"raw_bidder_name": "ZZTEST Bidder Low", "bid_amount": 900, "is_winner": True},
            {"raw_bidder_name": "ZZTEST Bidder High", "bid_amount": 1100, "is_winner": False},
        ])
        assert result["entries_saved"] == 2

        with ci_db.get_conn() as conn, conn.cursor() as cur:
            cur.execute(
                "select raw_bidder_name, bid_rank, did_win from scratch.bid_results "
                "where project_natural_key = %s order by bid_rank", (TEST_PROJECT_KEY,)
            )
            rows = cur.fetchall()
            assert rows[0]["raw_bidder_name"] == "ZZTEST Bidder Low"
            assert rows[0]["bid_rank"] == 1 and rows[0]["did_win"] is True
            assert rows[1]["bid_rank"] == 2 and rows[1]["did_win"] is False
    finally:
        _cleanup()


def test_unknown_bidder_gets_needs_review_registry_row():
    _reset_project()
    try:
        with ci_db.get_conn() as conn, conn.cursor() as cur:
            cur.execute("delete from scratch.competitor_name_registry where raw_name_variant = %s", (UNKNOWN_BIDDER,))

        bra.submit_bid_results(TEST_PROJECT_KEY, [
            {"raw_bidder_name": UNKNOWN_BIDDER, "bid_amount": 500, "is_winner": True},
        ])

        with ci_db.get_conn() as conn, conn.cursor() as cur:
            cur.execute(
                "select comp_name from scratch.competitor_name_registry where raw_name_variant = %s",
                (UNKNOWN_BIDDER,),
            )
            row = cur.fetchone()
            assert row is not None
            assert (row["comp_name"] or "") == ""  # needs_review: blank comp_name

            cur.execute(
                "select mapping_status from scratch.bid_results where project_natural_key = %s",
                (TEST_PROJECT_KEY,),
            )
            assert cur.fetchone()["mapping_status"] == "needs_review"
    finally:
        _cleanup()


def test_rejects_more_than_five_entries():
    _reset_project()
    try:
        entries = [{"raw_bidder_name": f"ZZTEST Bidder {i}", "bid_amount": 100 + i, "is_winner": i == 0}
                   for i in range(6)]
        with pytest.raises(bra.ValidationError):
            bra.submit_bid_results(TEST_PROJECT_KEY, entries)
    finally:
        _cleanup()


def test_rejects_zero_or_multiple_winners():
    _reset_project()
    try:
        with pytest.raises(bra.ValidationError):
            bra.submit_bid_results(TEST_PROJECT_KEY, [
                {"raw_bidder_name": "A", "bid_amount": 100, "is_winner": False},
                {"raw_bidder_name": "B", "bid_amount": 200, "is_winner": False},
            ])
        with pytest.raises(bra.ValidationError):
            bra.submit_bid_results(TEST_PROJECT_KEY, [
                {"raw_bidder_name": "A", "bid_amount": 100, "is_winner": True},
                {"raw_bidder_name": "B", "bid_amount": 200, "is_winner": True},
            ])
    finally:
        _cleanup()


def test_rejects_project_that_already_has_results():
    _reset_project()
    try:
        bra.submit_bid_results(TEST_PROJECT_KEY, [
            {"raw_bidder_name": "A", "bid_amount": 100, "is_winner": True},
        ])
        with pytest.raises(bra.ValidationError):
            bra.submit_bid_results(TEST_PROJECT_KEY, [
                {"raw_bidder_name": "B", "bid_amount": 200, "is_winner": True},
            ])
    finally:
        _cleanup()
