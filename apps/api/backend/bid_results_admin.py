"""
Feature 1 — bid results entry: let an estimator fill in the top-5 bidders (and who won) for a
historical project that has none recorded yet.

Writes scratch.bid_results (Supabase, see docs/DATA_ACCESS_SCRATCH.md). A raw bidder name with no
match in scratch.competitor_name_registry gets a new
needs_review row auto-created there — the same behavior data/update_name_registry.py already
applies to batch-loaded data, kept consistent here so the review queue works the same way
regardless of how a name entered the system.
"""
from __future__ import annotations

from dataclasses import dataclass

from . import ci_db
from .ci_db import normalize
from .observability import get_logger

log = get_logger("bid_assistant.bid_results_admin")

MAX_ENTRIES = 5


class ValidationError(ValueError):
    pass


@dataclass
class BidEntry:
    raw_bidder_name: str
    bid_amount: float
    is_winner: bool


def list_projects_missing_results(search: str | None = None) -> list[dict]:
    """Projects in scratch.bid_projects with zero rows in scratch.bid_results — the picker for
    Feature 1. `search` optionally filters on county/project_name (ILIKE, either side)."""
    # `key_provisional` rows are no longer excluded (2026-08-08). This exclusion existed for two
    # reasons, both now resolved: the key being "about to change" once title-sheet extraction
    # landed (#70 — resolved differently: project_natural_key was rebuilt on lat/long instead of
    # city, so a provisional key is stable, not pending recomputation, and provisional is now the
    # rare exception rather than the norm), and the ON DELETE CASCADE risk of tidying up an
    # obviously-wrong row (#55 — resolved via soft delete; nothing in this codebase issues a hard
    # DELETE against bid_projects any more). A provisional row is offered like any other now, with
    # key_provisional/key_provisional_reason returned so the picker UI can flag it if it chooses to.
    # deleted_at is null still applies regardless (#55's soft-delete filter).
    sql = """
        select p.project_natural_key, p.project_name, p.county, p.state, p.bid_date, p.bid_year,
               p.key_provisional, p.key_provisional_reason
        from scratch.bid_projects p
        left join scratch.bid_results r on r.project_natural_key = p.project_natural_key
        where r.project_natural_key is null
          and p.deleted_at is null
    """
    params: list = []
    if search:
        sql += " and (p.county ilike %s or p.project_name ilike %s)"
        like = f"%{search}%"
        params += [like, like]
    sql += " order by p.bid_date desc nulls last"

    with ci_db.get_conn() as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchall()


def _resolve_bidder(cur, raw_name: str) -> tuple[str, str]:
    """Map a raw bidder name to (competitor_unit_id, mapping_status), auto-creating a needs_review
    registry row if the name isn't there at all. Mirrors data/entity_resolution.py's three-way
    logic (registry_mapped / needs_review / unmapped), evaluated one name at a time against the
    live table instead of a batch DataFrame merge."""
    norm = normalize(raw_name)
    cur.execute(
        "select comp_name from scratch.competitor_name_registry "
        "where upper(regexp_replace(raw_name_variant, '\\s+', ' ', 'g')) = trim(%s) limit 1",
        (norm,),
    )
    row = cur.fetchone()

    if row is None:
        # Not in the registry at all — auto-create a needs_review row, same as
        # update_name_registry.py does for a newly-seen raw name in batch-loaded data.
        cur.execute(
            "insert into scratch.competitor_name_registry "
            "(raw_name_variant, comp_name, source, source_batch) "
            "values (%s, '', 'bid_data', 'webapp_bid_entry') "
            "on conflict (raw_name_variant) do nothing",
            (raw_name.strip(),),
        )
        return norm, "needs_review"

    comp_name = (row["comp_name"] or "").strip()
    if comp_name:
        return comp_name, "registry_mapped"
    return norm, "needs_review"


def submit_bid_results(project_natural_key: str, entries: list[dict]) -> dict:
    """Insert 1-5 bid_results rows for a project that currently has none.
    `entries`: [{raw_bidder_name, bid_amount, is_winner}, ...]."""
    if not entries:
        raise ValidationError("At least one bidder is required.")
    if len(entries) > MAX_ENTRIES:
        raise ValidationError(f"At most {MAX_ENTRIES} bidders are supported per submission.")

    parsed = [
        BidEntry(
            raw_bidder_name=str(e.get("raw_bidder_name") or "").strip(),
            bid_amount=float(e["bid_amount"]),
            is_winner=bool(e.get("is_winner")),
        )
        for e in entries
    ]
    if any(not e.raw_bidder_name for e in parsed):
        raise ValidationError("Every entry needs a bidder name.")
    winners = [e for e in parsed if e.is_winner]
    if len(winners) != 1:
        raise ValidationError("Exactly one bidder must be marked as the winner.")

    # bid_rank: 1 = lowest entered amount, independent of who was marked the winner.
    ranked = sorted(range(len(parsed)), key=lambda i: parsed[i].bid_amount)
    rank_of = {i: r + 1 for r, i in enumerate(ranked)}

    with ci_db.get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "select 1 from scratch.bid_projects where project_natural_key = %s", (project_natural_key,)
        )
        if cur.fetchone() is None:
            raise ValidationError(f"No project found with key {project_natural_key!r}.")
        cur.execute(
            "select 1 from scratch.bid_results where project_natural_key = %s limit 1",
            (project_natural_key,),
        )
        if cur.fetchone() is not None:
            raise ValidationError(
                f"{project_natural_key} already has bid results — this feature only adds results "
                "for a project that has none yet."
            )

        for i, entry in enumerate(parsed):
            competitor_unit_id, mapping_status = _resolve_bidder(cur, entry.raw_bidder_name)
            cur.execute(
                """
                insert into scratch.bid_results
                    (project_natural_key, competitor_unit_id, bid_amount, bid_rank, did_win,
                     raw_bidder_name, mapping_status, source_batch)
                values (%s, %s, %s, %s, %s, %s, %s, 'webapp_bid_entry')
                on conflict (project_natural_key, competitor_unit_id) do update set
                    bid_amount = excluded.bid_amount, bid_rank = excluded.bid_rank,
                    did_win = excluded.did_win, raw_bidder_name = excluded.raw_bidder_name,
                    mapping_status = excluded.mapping_status, source_batch = excluded.source_batch,
                    updated_at = now()
                """,
                (
                    project_natural_key, competitor_unit_id, entry.bid_amount, rank_of[i],
                    entry.is_winner, entry.raw_bidder_name, mapping_status,
                ),
            )

    log.info("bid results submitted: %s (%d bidders)", project_natural_key, len(parsed))
    return {"project_natural_key": project_natural_key, "entries_saved": len(parsed)}


_RESULTS_JOIN_SQL = """
    select r.project_natural_key, r.competitor_unit_id, r.raw_bidder_name, r.bid_amount,
           r.bid_rank, r.did_win, r.mapping_status,
           p.project_name, p.county, p.state, p.bid_date, p.bid_year
    from scratch.bid_results r
    join scratch.bid_projects p on p.project_natural_key = r.project_natural_key
"""


def list_bid_results(search: str | None = None) -> list[dict]:
    """Every scratch.bid_results row, joined to its project — the full results table (as opposed to
    list_projects_missing_results, which is the entry-form picker and shows the opposite set: only
    projects with zero rows). One row per bidder per project, matching bid_results' own grain.
    `search` filters on project name, county, or bidder name (ILIKE, either side)."""
    sql = _RESULTS_JOIN_SQL
    params: list = []
    if search:
        sql += " where p.project_name ilike %s or p.county ilike %s or r.raw_bidder_name ilike %s"
        like = f"%{search}%"
        params += [like, like, like]
    sql += " order by p.bid_date desc nulls last, r.bid_rank asc nulls last"

    with ci_db.get_conn() as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchall()


def update_bid_result(project_natural_key: str, competitor_unit_id: str, fields: dict) -> dict:
    """Edit one cell of an already-recorded bid result: raw_bidder_name, bid_amount, and/or
    did_win, any subset. Unlike submit_bid_results (insert-only, blocked once a project has any
    rows), this is the results table's inline-edit path for a project that already has results.

    - A raw_bidder_name change re-resolves through the name registry (_resolve_bidder, same as
      submit). If that resolves to a *different* competitor_unit_id than the row currently has,
      the edit changes this row's primary key — blocked if the project already has a row at that
      new key (two raw names on one project must not collide onto one competitor mid-edit).
    - A bid_amount change recomputes bid_rank for every bidder on the project (rank is relative,
      not a per-row value).
    - A did_win=True edit clears the flag on every other bidder on the project first, mirroring
      the one-winner-per-project rule submit_bid_results enforces at insert time.

    Returns every bid_results row for the project post-edit (project-scoped, not the whole table)
    so the frontend can patch its table state without a full refetch.
    """
    with ci_db.get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "select * from scratch.bid_results where project_natural_key = %s and competitor_unit_id = %s",
            (project_natural_key, competitor_unit_id),
        )
        row = cur.fetchone()
        if row is None:
            raise ValidationError(
                f"No bid result found for {competitor_unit_id!r} on {project_natural_key!r}."
            )

        target_id = competitor_unit_id

        if "raw_bidder_name" in fields:
            new_name = str(fields["raw_bidder_name"] or "").strip()
            if not new_name:
                raise ValidationError("Bidder name cannot be blank.")
            if new_name != row["raw_bidder_name"]:
                new_id, mapping_status = _resolve_bidder(cur, new_name)
                if new_id != competitor_unit_id:
                    cur.execute(
                        "select 1 from scratch.bid_results "
                        "where project_natural_key = %s and competitor_unit_id = %s",
                        (project_natural_key, new_id),
                    )
                    if cur.fetchone() is not None:
                        raise ValidationError(
                            f"{project_natural_key} already has a bid result mapped to "
                            f"{new_id!r} — edit that row directly instead."
                        )
                    cur.execute(
                        "update scratch.bid_results set competitor_unit_id = %s, raw_bidder_name = %s, "
                        "mapping_status = %s, updated_at = now() "
                        "where project_natural_key = %s and competitor_unit_id = %s",
                        (new_id, new_name, mapping_status, project_natural_key, competitor_unit_id),
                    )
                    target_id = new_id
                else:
                    cur.execute(
                        "update scratch.bid_results set raw_bidder_name = %s, updated_at = now() "
                        "where project_natural_key = %s and competitor_unit_id = %s",
                        (new_name, project_natural_key, competitor_unit_id),
                    )

        if "bid_amount" in fields:
            new_amount = float(fields["bid_amount"])
            if new_amount <= 0:
                raise ValidationError("Bid amount must be positive.")
            cur.execute(
                "update scratch.bid_results set bid_amount = %s, updated_at = now() "
                "where project_natural_key = %s and competitor_unit_id = %s",
                (new_amount, project_natural_key, target_id),
            )
            cur.execute(
                "select competitor_unit_id, bid_amount from scratch.bid_results "
                "where project_natural_key = %s order by bid_amount asc",
                (project_natural_key,),
            )
            for rank, r in enumerate(cur.fetchall(), start=1):
                cur.execute(
                    "update scratch.bid_results set bid_rank = %s "
                    "where project_natural_key = %s and competitor_unit_id = %s",
                    (rank, project_natural_key, r["competitor_unit_id"]),
                )

        if "did_win" in fields:
            if bool(fields["did_win"]):
                cur.execute(
                    "update scratch.bid_results set did_win = false, updated_at = now() "
                    "where project_natural_key = %s",
                    (project_natural_key,),
                )
                cur.execute(
                    "update scratch.bid_results set did_win = true, updated_at = now() "
                    "where project_natural_key = %s and competitor_unit_id = %s",
                    (project_natural_key, target_id),
                )
            else:
                cur.execute(
                    "update scratch.bid_results set did_win = false, updated_at = now() "
                    "where project_natural_key = %s and competitor_unit_id = %s",
                    (project_natural_key, target_id),
                )

        cur.execute(
            _RESULTS_JOIN_SQL + " where r.project_natural_key = %s order by r.bid_rank asc nulls last",
            (project_natural_key,),
        )
        rows = cur.fetchall()

    log.info("bid result updated: %s / %s -> %s", project_natural_key, competitor_unit_id, target_id)
    return {"project_natural_key": project_natural_key, "rows": rows}
