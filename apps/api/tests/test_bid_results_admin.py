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
from backend import competitor_registry_admin as cra  # noqa: E402

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
        # UNKNOWN_BIDDER plus every raw bidder name any test in this file submits — submit_bid_results
        # auto-registers a needs-review registry stub for any name it doesn't recognize (see
        # test_unknown_bidder_gets_needs_review_registry_row below), and those stubs outlive the
        # bid_projects delete (registry isn't FK'd to bid_projects). Left uncleaned, they leaked
        # across runs and once caused two different raw names to resolve to the same comp_name,
        # colliding on bid_results' (project_natural_key, competitor_unit_id) primary key.
        cur.execute(
            "delete from scratch.competitor_name_registry where raw_name_variant = any(%s)",
            ([UNKNOWN_BIDDER, "ZZTEST Bidder Low", "ZZTEST Bidder High"]
             + [f"ZZTEST Bidder {i}" for i in range(6)],),
        )


def test_project_with_no_results_appears_in_picker():
    _reset_project()
    try:
        rows = bra.list_projects_missing_results(search="ZZTEST County")
        assert any(r["project_natural_key"] == TEST_PROJECT_KEY for r in rows)
    finally:
        _cleanup()


def test_provisional_project_now_appears_in_picker():
    """Task #4 — the key_provisional exclusion is gone: a provisional row is offered as a
    data-entry target like any other project, not silently hidden. Both original reasons for
    hiding it are resolved (#70 via the lat/long key redesign, #55 via soft delete)."""
    with ci_db.get_conn() as conn, conn.cursor() as cur:
        cur.execute("delete from scratch.bid_projects where project_natural_key = %s", (TEST_PROJECT_KEY,))
        cur.execute(
            "insert into scratch.bid_projects "
            "(project_natural_key, state, county, bid_date, key_provisional, key_provisional_reason) "
            "values (%s, 'MN', 'ZZTEST County', '2024-01-01', true, 'sentinel:bid_date')",
            (TEST_PROJECT_KEY,),
        )
    try:
        rows = bra.list_projects_missing_results(search="ZZTEST County")
        hit = next((r for r in rows if r["project_natural_key"] == TEST_PROJECT_KEY), None)
        assert hit is not None, "a provisional project must still appear in the picker"
        assert hit["key_provisional"] is True
        assert hit["key_provisional_reason"] == "sentinel:bid_date"
    finally:
        _cleanup()


def test_submit_happy_path_computes_rank():
    _reset_project()
    try:
        result = bra.submit_bid_results(TEST_PROJECT_KEY, [
            {"raw_bidder_name": "ZZTEST Bidder Low", "bid_amount": 900},
            {"raw_bidder_name": "ZZTEST Bidder High", "bid_amount": 1100},
        ])
        assert result["entries_saved"] == 2

        with ci_db.get_conn() as conn, conn.cursor() as cur:
            cur.execute(
                "select raw_bidder_name, bid_rank, did_win from scratch.bid_results "
                "where project_natural_key = %s order by bid_rank", (TEST_PROJECT_KEY,)
            )
            rows = cur.fetchall()
            # No is_winner was supplied — did_win is derived purely from bid_amount, so the lower
            # of the two entered amounts must be the one flagged as the winner.
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
            {"raw_bidder_name": UNKNOWN_BIDDER, "bid_amount": 500},
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


def test_accepts_more_than_five_entries():
    """The old MAX_ENTRIES=5 cap is gone — a letting that drew more than 5 bidders must be
    recordable in one submission."""
    _reset_project()
    try:
        entries = [{"raw_bidder_name": f"ZZTEST Bidder {i}", "bid_amount": 100 + i} for i in range(6)]
        result = bra.submit_bid_results(TEST_PROJECT_KEY, entries)
        assert result["entries_saved"] == 6
    finally:
        _cleanup()


def test_rejects_tied_lowest_bid_on_submit():
    _reset_project()
    try:
        with pytest.raises(bra.ValidationError):
            bra.submit_bid_results(TEST_PROJECT_KEY, [
                {"raw_bidder_name": "ZZTEST Bidder Low", "bid_amount": 100},
                {"raw_bidder_name": "ZZTEST Bidder High", "bid_amount": 100},
            ])
    finally:
        _cleanup()


def test_rejects_project_that_already_has_results():
    _reset_project()
    try:
        bra.submit_bid_results(TEST_PROJECT_KEY, [
            {"raw_bidder_name": "ZZTEST Bidder Low", "bid_amount": 100},
        ])
        with pytest.raises(bra.ValidationError):
            bra.submit_bid_results(TEST_PROJECT_KEY, [
                {"raw_bidder_name": "ZZTEST Bidder High", "bid_amount": 200},
            ])
    finally:
        _cleanup()


def test_update_bid_amount_flips_winner():
    """did_win is never client-settable — it's recomputed for the whole project whenever a
    bid_amount changes, so editing the higher bidder down below the other one must flip the
    winner (and bid_rank) on both rows, not just the one edited."""
    _reset_project()
    try:
        bra.submit_bid_results(TEST_PROJECT_KEY, [
            {"raw_bidder_name": "ZZTEST Bidder Low", "bid_amount": 900},
            {"raw_bidder_name": "ZZTEST Bidder High", "bid_amount": 1100},
        ])
        high_id = ci_db.normalize("ZZTEST Bidder High")
        low_id = ci_db.normalize("ZZTEST Bidder Low")

        result = bra.update_bid_result(TEST_PROJECT_KEY, high_id, {"bid_amount": 500})
        rows = {r["competitor_unit_id"]: r for r in result["rows"]}
        assert rows[high_id]["did_win"] is True and rows[high_id]["bid_rank"] == 1
        assert rows[low_id]["did_win"] is False and rows[low_id]["bid_rank"] == 2
    finally:
        _cleanup()


def test_update_bid_amount_rejects_tie_and_leaves_rows_unchanged():
    _reset_project()
    try:
        bra.submit_bid_results(TEST_PROJECT_KEY, [
            {"raw_bidder_name": "ZZTEST Bidder Low", "bid_amount": 900},
            {"raw_bidder_name": "ZZTEST Bidder High", "bid_amount": 1100},
        ])
        high_id = ci_db.normalize("ZZTEST Bidder High")

        with pytest.raises(bra.ValidationError):
            bra.update_bid_result(TEST_PROJECT_KEY, high_id, {"bid_amount": 900})

        # Rejected before any write — both rows must still hold their original values.
        with ci_db.get_conn() as conn, conn.cursor() as cur:
            cur.execute(
                "select competitor_unit_id, bid_amount, bid_rank, did_win from scratch.bid_results "
                "where project_natural_key = %s order by bid_rank", (TEST_PROJECT_KEY,)
            )
            rows = {r["competitor_unit_id"]: r for r in cur.fetchall()}
            assert rows[ci_db.normalize("ZZTEST Bidder Low")]["bid_amount"] == 900
            assert rows[ci_db.normalize("ZZTEST Bidder Low")]["did_win"] is True
            assert rows[high_id]["bid_amount"] == 1100
            assert rows[high_id]["did_win"] is False
    finally:
        _cleanup()


def test_list_bid_results_shows_current_comp_name_after_consolidate():
    """list_bid_results' registry join is presentation-only -- competitor_unit_id on the stored row
    never changes, but current_comp_name must reflect a later consolidate."""
    raw_name = "ZZTEST Consolidate Display Bidder"
    old_name, new_name = "ZZTEST Consolidate Display Old", "ZZTEST Consolidate Display New"
    extra_registry_names = [raw_name, old_name, new_name]

    def _cleanup_registry():
        with ci_db.get_conn() as conn, conn.cursor() as cur:
            cur.execute(
                "delete from scratch.competitor_name_registry where raw_name_variant = any(%s)",
                (extra_registry_names,),
            )

    _reset_project()
    _cleanup_registry()
    with ci_db.get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "insert into scratch.competitor_name_registry (raw_name_variant, comp_name) values (%s, %s)",
            (raw_name, old_name),
        )
    try:
        bra.submit_bid_results(TEST_PROJECT_KEY, [
            {"raw_bidder_name": raw_name, "bid_amount": 500},
        ])
        rows = bra.list_bid_results(search="ZZTEST County")
        row = next(r for r in rows if r["project_natural_key"] == TEST_PROJECT_KEY)
        assert row["current_comp_name"] == old_name  # not yet consolidated

        cra.consolidate([raw_name], new_name)

        rows = bra.list_bid_results(search="ZZTEST County")
        row = next(r for r in rows if r["project_natural_key"] == TEST_PROJECT_KEY)
        assert row["competitor_unit_id"] == old_name    # stored fact, untouched by consolidate
        assert row["current_comp_name"] == new_name      # display resolves forward
    finally:
        _cleanup()
        _cleanup_registry()
