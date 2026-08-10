"""
Integration tests for backend/competitor_registry_admin.py against the real
scratch.competitor_name_registry / scratch.bid_results tables (Supabase, see
docs/DATA_ACCESS_SCRATCH.md).

Skipped entirely unless SUPABASE_TEAM_DB_URL is set (no local mock for Postgres — see
test_pit_list_admin.py for the same convention). All fixtures use clearly-fake ZZTEST-tagged
names/keys and clean up after themselves in a finally block.

The consolidate test is the one that matters most: it sets up two raw-name rows that currently
share one old comp_name, consolidates only ONE of them, and asserts (a) the other raw name's
registry row is untouched, and (b) the consolidated raw name's bid_results.competitor_unit_id
doesn't change — consolidate is registry-only as of 2026-07-31 (see competitor_registry_admin.py's
module docstring); it used to cascade the rename into bid_results, joining on raw_bidder_name
rather than the old competitor_unit_id value specifically so two raw names sharing an old comp_name
wouldn't collide. That cascade is gone now, but the "only the selected raw name moves" guarantee on
the registry side still matters and is still what this test checks. (Only one of the two raw names
gets a bid_results row in the fixture — bid_results is keyed (project_natural_key,
competitor_unit_id), and both raw names resolve to the same competitor_unit_id for this project, so
a second row would collide on that key; the registry-row assertion alone covers the other name.)

Run: SUPABASE_TEAM_DB_URL='postgresql://...' python -m pytest tests/test_competitor_registry_admin.py -q
"""
from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.skipif(
    not os.environ.get("SUPABASE_TEAM_DB_URL"),
    reason="SUPABASE_TEAM_DB_URL not set — needs a live Supabase scratch schema connection",
)

from backend import ci_db  # noqa: E402
from backend import competitor_registry_admin as cra  # noqa: E402

TEST_PROJECT_KEY = "ZZTEST_PROJECT_CONSOLIDATE_1"


def _delete_registry_rows(*raw_names):
    with ci_db.get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "delete from scratch.competitor_name_registry where raw_name_variant = any(%s)",
            (list(raw_names),),
        )


def _cleanup_project():
    with ci_db.get_conn() as conn, conn.cursor() as cur:
        # cascades to bid_results via the FK's ON DELETE CASCADE
        cur.execute("delete from scratch.bid_projects where project_natural_key = %s", (TEST_PROJECT_KEY,))


def test_add_and_remove_competitor():
    name = "ZZTEST Solo Competitor"
    _delete_registry_rows(name)
    try:
        cra.add_competitor(name)
        rows = cra.list_registry(search=name)
        assert any(r["comp_name"] == name for r in rows)
        result = cra.remove_competitor(name)
        assert result["rows_removed"] == 1
    finally:
        _delete_registry_rows(name)


def test_exact_duplicate_is_blocked():
    name = "ZZTEST Duplicate Competitor"
    _delete_registry_rows(name)
    try:
        cra.add_competitor(name)
        with pytest.raises(cra.ValidationError):
            cra.add_competitor(name)
        with pytest.raises(cra.ValidationError):
            cra.add_competitor(name.lower())  # normalized match, case-insensitive
    finally:
        _delete_registry_rows(name)


def test_fuzzy_near_duplicate_warns_but_force_adds():
    base, near = "ZZTEST Fuzzy Match Company", "ZZTEST Fuzzy Match Compny"  # near-duplicate typo
    _delete_registry_rows(base, near)
    try:
        cra.add_competitor(base)
        with pytest.raises(cra.DuplicateWarning):
            cra.add_competitor(near)
        cra.add_competitor(near, force=True)
        rows = cra.list_registry(search="ZZTEST Fuzzy Match")
        assert len(rows) == 2
    finally:
        _delete_registry_rows(base, near)


def test_remove_blocked_when_referenced_in_bid_results():
    name = "ZZTEST Referenced Competitor"
    _delete_registry_rows(name)
    _cleanup_project()
    try:
        cra.add_competitor(name)
        with ci_db.get_conn() as conn, conn.cursor() as cur:
            cur.execute(
                "insert into scratch.bid_projects (project_natural_key, state, county, bid_date) "
                "values (%s, 'MN', 'ZZTEST County', '2024-01-01')",
                (TEST_PROJECT_KEY,),
            )
            cur.execute(
                "insert into scratch.bid_results "
                "(project_natural_key, competitor_unit_id, bid_amount, raw_bidder_name) "
                "values (%s, %s, 1000, %s)",
                (TEST_PROJECT_KEY, name, name),
            )
        with pytest.raises(cra.ValidationError):
            cra.remove_competitor(name)
    finally:
        _cleanup_project()
        _delete_registry_rows(name)


def test_remove_raw_name_variant_leaves_siblings_and_comp_name_alone():
    """Deleting one alias under a shared comp_name (e.g. one of several subsidiaries rolled up
    under a parent company) must not touch the other alias rows or the comp_name itself."""
    raw_a, raw_b = "ZZTEST Subsidiary A", "ZZTEST Subsidiary B"
    parent = "ZZTEST Parent Co"
    _delete_registry_rows(raw_a, raw_b, parent)
    try:
        with ci_db.get_conn() as conn, conn.cursor() as cur:
            cur.execute(
                "insert into scratch.competitor_name_registry (raw_name_variant, comp_name) "
                "values (%s, %s), (%s, %s), (%s, %s)",
                (parent, parent, raw_a, parent, raw_b, parent),
            )
        result = cra.remove_raw_name_variant(raw_a)
        assert result["rows_removed"] == 1

        rows = cra.list_registry(search=parent)
        remaining = {r["raw_name_variant"] for r in rows}
        assert remaining == {parent, raw_b}
    finally:
        _delete_registry_rows(raw_a, raw_b, parent)


def test_remove_raw_name_variant_blocked_when_last_row_is_referenced():
    """If this raw name is the LAST row for its comp_name and bid_results still references that
    comp_name, deleting it is equivalent to remove_competitor and gets the same protection."""
    name = "ZZTEST Solo Referenced Raw Name"
    _delete_registry_rows(name)
    _cleanup_project()
    try:
        cra.add_competitor(name)
        with ci_db.get_conn() as conn, conn.cursor() as cur:
            cur.execute(
                "insert into scratch.bid_projects (project_natural_key, state, county, bid_date) "
                "values (%s, 'MN', 'ZZTEST County', '2024-01-01')",
                (TEST_PROJECT_KEY,),
            )
            cur.execute(
                "insert into scratch.bid_results "
                "(project_natural_key, competitor_unit_id, bid_amount, raw_bidder_name) "
                "values (%s, %s, 1000, %s)",
                (TEST_PROJECT_KEY, name, name),
            )
        with pytest.raises(cra.ValidationError):
            cra.remove_raw_name_variant(name)
    finally:
        _cleanup_project()
        _delete_registry_rows(name)


def test_consolidate_only_touches_the_selected_raw_name_and_leaves_bid_results_alone():
    """Two raw-name rows share one old comp_name; consolidating only one of them must not rename
    the other registry row, and must not touch bid_results at all (consolidate is registry-only)."""
    raw_a, raw_b = "ZZTEST Raw Name A", "ZZTEST Raw Name B"
    old_name, new_name = "ZZTEST Old Shared Name", "ZZTEST New Canonical Name"
    _delete_registry_rows(raw_a, raw_b, old_name, new_name)
    _cleanup_project()
    try:
        with ci_db.get_conn() as conn, conn.cursor() as cur:
            cur.execute(
                "insert into scratch.competitor_name_registry (raw_name_variant, comp_name) values (%s, %s), (%s, %s)",
                (raw_a, old_name, raw_b, old_name),
            )
            cur.execute(
                "insert into scratch.bid_projects (project_natural_key, state, county, bid_date) "
                "values (%s, 'MN', 'ZZTEST County', '2024-01-01')",
                (TEST_PROJECT_KEY,),
            )
            # One row, not one per raw name: bid_results is keyed (project_natural_key,
            # competitor_unit_id), and raw_a/raw_b currently resolve to the SAME competitor_unit_id
            # (old_name) — a second row for the same project+competitor would collide on that key.
            # raw_b's half of the "untouched" assertion is covered by the registry-row check below;
            # it doesn't need its own bid_results row to prove consolidate never renamed it there.
            cur.execute(
                "insert into scratch.bid_results "
                "(project_natural_key, competitor_unit_id, bid_amount, raw_bidder_name) "
                "values (%s, %s, 1000, %s)",
                (TEST_PROJECT_KEY, old_name, raw_a),
            )

        result = cra.consolidate([raw_a], new_name)
        assert result["registry_rows_updated"] == 1
        assert "bid_results_rows_updated" not in result

        with ci_db.get_conn() as conn, conn.cursor() as cur:
            cur.execute("select comp_name from scratch.competitor_name_registry where raw_name_variant = %s", (raw_a,))
            assert cur.fetchone()["comp_name"] == new_name
            cur.execute("select comp_name from scratch.competitor_name_registry where raw_name_variant = %s", (raw_b,))
            assert cur.fetchone()["comp_name"] == old_name  # untouched

            # bid_results is never touched by consolidate now — raw_a's row keeps the old
            # competitor_unit_id even though its registry row did move.
            cur.execute(
                "select competitor_unit_id from scratch.bid_results where raw_bidder_name = %s", (raw_a,)
            )
            assert cur.fetchone()["competitor_unit_id"] == old_name
    finally:
        _cleanup_project()
        _delete_registry_rows(raw_a, raw_b, old_name, new_name)


def test_consolidate_bridges_the_retired_comp_name_forward():
    """A consolidated-away comp_name must resolve forward on its own -- a bid entered later under
    that retired name (or a historical bid_results row already stored under it) has to land on the
    new target through one registry lookup, not fork into a disconnected needs_review competitor."""
    raw_a = "ZZTEST Bridge Raw Name"
    old_name, new_name = "ZZTEST Bridge Old Name", "ZZTEST Bridge New Name"
    _delete_registry_rows(raw_a, old_name, new_name)
    _cleanup_project()
    try:
        with ci_db.get_conn() as conn, conn.cursor() as cur:
            cur.execute(
                "insert into scratch.competitor_name_registry (raw_name_variant, comp_name) values (%s, %s)",
                (raw_a, old_name),
            )
            cur.execute(
                "insert into scratch.bid_projects (project_natural_key, state, county, bid_date) "
                "values (%s, 'MN', 'ZZTEST County', '2024-01-01')",
                (TEST_PROJECT_KEY,),
            )
            cur.execute(
                "insert into scratch.bid_results "
                "(project_natural_key, competitor_unit_id, bid_amount, raw_bidder_name) "
                "values (%s, %s, 1000, %s)",
                (TEST_PROJECT_KEY, old_name, raw_a),
            )

        result = cra.consolidate([raw_a], new_name)
        assert result["retired_names_bridged"] == [old_name]

        # The retired comp_name itself must now be a resolvable lookup key, same normalized-match
        # style _resolve_bidder (bid_results_admin.py) uses for a brand-new bid entry.
        with ci_db.get_conn() as conn, conn.cursor() as cur:
            cur.execute(
                "select comp_name from scratch.competitor_name_registry "
                "where upper(regexp_replace(raw_name_variant, '\\s+', ' ', 'g')) = %s",
                (ci_db.normalize(old_name),),
            )
            assert cur.fetchone()["comp_name"] == new_name

            # Still registry-only -- the historical row already stored under the old comp_name
            # keeps that exact value; only the forward-lookup path changed, not the stored fact.
            cur.execute(
                "select competitor_unit_id from scratch.bid_results where raw_bidder_name = %s", (raw_a,)
            )
            assert cur.fetchone()["competitor_unit_id"] == old_name
    finally:
        _cleanup_project()
        _delete_registry_rows(raw_a, old_name, new_name)
