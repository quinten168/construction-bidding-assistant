"""Write an assembled plan_reader record into `scratch.bid_projects`. (#37)

Pairs with `01_pipeline/bid_projects_record.py`, which does the pure assembly. This half owns the
database and nothing else: it takes a dict of column → value and upserts it.

THE FOUR RULES, all settled 2026-08-03 and all enforced here rather than merely documented:

1. **Upsert only. There is no DELETE in this module, and there must never be one** — not in dedupe,
   not as delete-then-insert, not as a "cleanup". `scratch.bid_results` has
   `... references scratch.bid_projects(project_natural_key) ON DELETE CASCADE`, so any DELETE here
   silently destroys that project's bid results. Changing the FK to RESTRICT is a separate call
   (#55) and has deliberately not been made, which means this rule is the only thing standing
   between a cleanup script and data loss.

2. **Never fuzzy-match column names.** The INSERT is built from the mapping YAML's declared targets,
   intersected with the columns that actually exist in the table. A payload field absent from the
   YAML is not written; a YAML target absent from the table is reported loudly, not guessed at.

3. **`row_source = 'plan_reader'` on every row**, so the CI batch push can be taught to leave our
   rows alone (`where bid_projects.row_source is distinct from 'plan_reader'`). That guard lives in
   `data/push_supabase_bid_data.py` and is a separate, owner-reviewed change.

4. **Insert and flag, never silently skip — and never silently overwrite either.** When identity is
   ambiguous the row is still written, with `duplicate_flag` set and `duplicate_reason` saying why.
   For most ambiguity types that already means a fresh row under its own already-distinct key. But
   `find_conflicts()`'s `same_key_different_plan_uid` case is different: two genuinely different
   plans computed the *identical* `project_natural_key`, and since that's the literal primary key,
   proceeding as-is would silently overwrite the first plan's row via `on conflict ... do update` —
   worse than skipping, since the flag would only ever appear on the row that did the overwriting.
   `upsert()` reacts to that one case specifically by disambiguating the key (`_find_free_key`)
   before writing, so the original row survives untouched and the new plan lands as a visible,
   flagged, genuinely new row instead.

5. **A re-scan of the same physical project updates that project's row, even if `project_natural_key`
   itself changed.** `project_natural_key` includes `bid_date`, so a plan re-scanned after a
   previously-unparsed bid_date gets corrected computes a genuinely different key — without
   `find_location_match()`, that forks a second row for one real project (observed for real,
   Kandiyohi Co., 2026-08-08). `state`+`county`+`latitude`/`longitude` don't move between scans of
   the same project, so a match on those redirects the write onto the EXISTING row instead. On that
   redirected write only, a fresh non-null value overwrites but a fresh null never blanks an existing
   value — protects against a worse/partial re-scan erasing quantities a better prior scan found.
"""
from __future__ import annotations

from typing import Any, Iterable, Optional

from . import ci_db
from .observability import get_logger

log = get_logger("bid_assistant.bid_projects_writer")

TABLE = "scratch.bid_projects"

# Columns the writer must never overwrite on conflict. `processed_at` records when the plan first
# went through the pipeline and is meant to be stable; `updated_at` is the DB's own moving value.
_NEVER_UPDATE = {"project_natural_key", "processed_at", "updated_at"}

# Postgres types for the columns the mapping declares as additions, keyed by the YAML's target_type.
_TYPE_SQL = {
    "text": "text",
    "integer": "integer",
    "boolean": "boolean",
    "double precision": "double precision",
    "timestamptz": "timestamptz",
    "date": "date",
}


class WriterError(RuntimeError):
    """Something the caller must fix, as opposed to a row-level data problem."""


def existing_columns(table: str = TABLE, *, conn=None) -> set[str]:
    """The columns the table actually has right now. Read from the catalogue, never assumed.

    `data/push_supabase_bid_data.py::BID_PROJECTS_DDL` declares 19 columns while the live table has
    58, because `create table if not exists` never reconciles an existing table. So the DDL constant
    is not a usable description of the schema and this function exists instead of trusting it.
    """
    schema, _, name = table.partition(".")
    sql = ("select column_name from information_schema.columns "
           "where table_schema = %s and table_name = %s")
    if conn is not None:
        with conn.cursor() as cur:
            cur.execute(sql, (schema, name))
            return {r["column_name"] for r in cur.fetchall()}
    with ci_db.get_conn() as c, c.cursor() as cur:
        cur.execute(sql, (schema, name))
        return {r["column_name"] for r in cur.fetchall()}


def additive_ddl(mapping: dict, table: str = TABLE) -> list[str]:
    """`add column if not exists` for every column the mapping declares as an addition.

    Returned rather than executed, so a human can read the statements before any schema changes.
    Additive only — this function cannot emit a DROP or an ALTER TYPE, by construction.
    """
    stmts = []
    for entry in mapping.get("new_columns") or []:
        target = entry["target"]
        sqltype = _TYPE_SQL.get(entry.get("target_type"))
        if sqltype is None:
            raise WriterError(
                f"mapping declares {target!r} with unmapped target_type "
                f"{entry.get('target_type')!r}; refusing to guess a Postgres type")
        clause = f"alter table {table} add column if not exists {target} {sqltype}"
        default = entry.get("default")
        if default is not None:
            literal = {True: "true", False: "false"}.get(default, default)
            clause += f" default {literal}"
        stmts.append(clause)
    return stmts


def _writable(row: dict, table_cols: set[str], declared: Iterable[str]) -> tuple[dict, list[str]]:
    """Intersect the assembled row with (a) the mapping's declared targets and (b) the table's real
    columns. Returns the writable subset and the list of declared-but-absent columns."""
    declared = set(declared)
    unknown = sorted(c for c in declared if c not in table_cols)
    writable = {k: v for k, v in row.items() if k in declared and k in table_cols}
    return writable, unknown


def find_conflicts(row: dict, *, conn, table: str = TABLE) -> tuple[bool, Optional[str]]:
    """Is this row ambiguous against what is already in the table? (flag, reason).

    `table` is a parameter and NOT the module constant. It was the constant until 2026-08-03, which
    meant a dummy-table run silently probed the REAL scratch.bid_projects for conflicts — so it both
    gave the wrong answer and read production during a run whose entire point was not to touch it.

    Three questions, deliberately separate from "does the primary key already exist as the SAME
    plan" — that is an ordinary upsert of one project, not a duplicate:

      * same `join_key`, different `plan_uid` → two different PDFs claim one project (#41's exact
        question: when are two PDFs one project?).
      * same `plan_uid`, different `project_natural_key` → the same PDF has landed under two keys,
        which is what a changed city or a reparsed bid_date does.
    """
    jkey, uid, pnk = row.get("join_key"), row.get("plan_uid"), row.get("project_natural_key")
    with conn.cursor() as cur:
        # The dangerous one, and the reason this check exists at all. Two DIFFERENT plans can
        # assemble the SAME project_natural_key whenever both take sentinels — e.g. two ND plans
        # with no extractable county and no parseable bid date both key to
        # ND_UNKNOWN_UNKNOWN_1900-01-01. `on conflict (project_natural_key) do update` then makes
        # the second plan OVERWRITE the first, silently, and the corpus quietly loses a project.
        # That is worse than the skip rule 4 forbids: a skip loses the new row, this loses the old
        # one. Observed for real on the 3-plan dummy run of 2026-08-03.
        if pnk and uid:
            cur.execute(
                f"select plan_uid, source_file from {table} "
                "where project_natural_key = %s and plan_uid is distinct from %s limit 1",
                (pnk, uid))
            if hit := cur.fetchone():
                return True, (f"same_key_different_plan_uid:{hit['plan_uid']}"
                              f" ({hit.get('source_file')}) — THIS UPSERT OVERWRITES THAT ROW")
        if jkey and uid:
            cur.execute(
                f"select project_natural_key, plan_uid from {table} "
                "where join_key = %s and plan_uid is distinct from %s limit 1", (jkey, uid))
            if hit := cur.fetchone():
                return True, f"same_join_key_different_plan_uid:{hit['project_natural_key']}"
        if uid and pnk:
            cur.execute(
                f"select project_natural_key from {table} "
                "where plan_uid = %s and project_natural_key is distinct from %s limit 1",
                (uid, pnk))
            if hit := cur.fetchone():
                return True, f"same_plan_uid_different_key:{hit['project_natural_key']}"
    return False, None


def find_location_match(row: dict, *, conn, table: str = TABLE) -> Optional[str]:
    """Is this row's location already on file under a different project_natural_key? (matched key,
    or None).

    `project_natural_key` (`build_project_natural_key`) includes `bid_date` as a component, so a
    plan re-scanned after a previously-unparsed bid_date gets corrected computes a DIFFERENT key —
    and without this check, `upsert()` forks a second row for the same physical project. Observed
    for real, Kandiyohi Co., 2026-08-08: two different `plan_uid`s (different files), same
    state/county/lat/lon, two separate rows in `scratch.bid_projects`.

    `state` + `county` + `latitude`/`longitude` stay constant across re-scans of the same project
    regardless of which file was uploaded or how `bid_date` parsed, so they're the signal used here
    instead — rounded to 3 decimals (~111m), the same tolerance `build_project_natural_key` already
    uses for the key itself, so "same location" means the same thing in both places.

    Returns None (no redirect) rather than guess when zero or more than one distinct existing key
    matches — ambiguity here should fall back to today's flag-and-insert behavior, not a merge.
    """
    state, county = row.get("state"), row.get("county")
    lat, lon = row.get("project_latitude"), row.get("project_longitude")
    pnk = row.get("project_natural_key")
    if not (state and county and lat is not None and lon is not None):
        return None
    with conn.cursor() as cur:
        cur.execute(
            f"select distinct project_natural_key from {table} "
            "where state = %s and county = %s "
            "and round(project_latitude::numeric, 3) = round(%s::numeric, 3) "
            "and round(project_longitude::numeric, 3) = round(%s::numeric, 3) "
            "and project_natural_key is distinct from %s",
            (state, county, lat, lon, pnk))
        hits = cur.fetchall()
    if len(hits) != 1:
        return None
    return hits[0]["project_natural_key"]


def _find_free_key(base_key: str, *, conn, table: str) -> str:
    """Called only when find_conflicts() reports same_key_different_plan_uid — base_key is already
    taken by a genuinely different plan (not a re-drop of the same PDF, which upserts normally).
    Append a running counter, mirroring the _1/_2/_3 suffix pattern already visible on the
    historical rows (e.g. 4 real distinct projects all sharing one base key)."""
    def _taken(key: str) -> bool:
        with conn.cursor() as cur:
            cur.execute(f"select 1 from {table} where project_natural_key = %s limit 1", (key,))
            return cur.fetchone() is not None

    n = 2
    while _taken(f"{base_key}_{n}"):
        n += 1
    return f"{base_key}_{n}"


def upsert(row: dict, declared_columns: Iterable[str], *, table: str = TABLE,
           conn=None, dry_run: bool = False) -> dict[str, Any]:
    """Upsert one assembled row. Returns a result dict describing exactly what happened.

    Never deletes. On conflict, updates every writable column except `_NEVER_UPDATE`.
    """
    owns_conn = conn is None
    ctx = ci_db.get_conn() if owns_conn else _null_ctx(conn)
    with ctx as c:
        table_cols = existing_columns(table, conn=c)
        writable, unknown = _writable(row, table_cols, declared_columns)

        if "project_natural_key" not in writable or not writable["project_natural_key"]:
            raise WriterError("row has no project_natural_key; refusing to write an unkeyed row")

        # Same physical project already on file under a different key (see find_location_match's
        # docstring) — redirect onto it instead of forking a new row. Takes priority over (and skips
        # entirely) find_conflicts()/`_find_free_key`'s collision handling below: those exist to
        # catch an UNINTENTIONAL collision on the key this row itself computed, which is a different
        # question from the deliberate merge decided here, and running them afterwards against the
        # redirected key would just re-disambiguate away from the row we intentionally chose.
        matched_key = find_location_match(row, conn=c, table=table)
        location_matched = bool(matched_key and matched_key != writable["project_natural_key"])
        if location_matched:
            log.info("bid_projects: %s matches existing project %s by location — updating in place "
                      "instead of forking", writable["project_natural_key"], matched_key)
            writable["project_natural_key"] = matched_key

        dup, reason = (False, None)
        if not location_matched:
            dup, reason = find_conflicts(row, conn=c, table=table)
            if dup and reason and reason.startswith("same_key_different_plan_uid:"):
                # The dangerous case: writing under this key would silently overwrite a genuinely
                # different plan's row (see find_conflicts' docstring). Write under a disambiguated
                # key instead of proceeding — the original row is left completely untouched.
                new_key = _find_free_key(writable["project_natural_key"], conn=c, table=table)
                log.warning("bid_projects: %s collides with a different plan (%s) — writing as %s instead",
                            writable["project_natural_key"], reason, new_key)
                writable["project_natural_key"] = new_key
            if dup:
                # Rule 4: flag, never skip. The row still lands.
                if "duplicate_flag" in table_cols:
                    writable["duplicate_flag"] = True
                if "duplicate_reason" in table_cols:
                    writable["duplicate_reason"] = reason
                log.warning("bid_projects: ambiguous identity for %s — %s (writing anyway, flagged)",
                            writable["project_natural_key"], reason)

        cols = sorted(writable)
        updatable = [c for c in cols if c not in _NEVER_UPDATE]
        if location_matched:
            # Fill gaps only: a fresh non-null value overwrites, but a fresh null never blanks out a
            # value the existing row already has. This is the only path where a DIFFERENT scan (not
            # the one that originated this row) is being written onto it, so a blurrier/partial
            # re-scan that detects fewer quantities must not erase numbers already on file.
            set_parts = [f"{c} = coalesce(excluded.{c}, {table}.{c})" for c in updatable]
        else:
            set_parts = [f"{c} = excluded.{c}" for c in updatable]
        # updated_at is `default now()` with NO trigger, so it fires on INSERT and never again —
        # which made it identical to processed_at and destroyed the distinction the mapping doc
        # draws between them (processed_at = when the plan was processed, stable; updated_at = last
        # edit, moving). Set it explicitly here. This fixes OUR writer only; the CI side upserts
        # into the same table and has the same defect, and the durable fix is a trigger owned by the
        # CI workstream — see the ticket, same shape as #55.
        if "updated_at" in table_cols:
            set_parts.append("updated_at = now()")
        sql = (
            f"insert into {table} ({', '.join(cols)}) "
            f"values ({', '.join('%s' for _ in cols)}) "
            f"on conflict (project_natural_key) do update set "
            + ", ".join(set_parts)
            + " returning (xmax = 0) as inserted"
        )
        result = {"project_natural_key": writable["project_natural_key"],
                  "columns_written": len(cols), "declared_not_in_table": unknown,
                  "duplicate_flag": dup, "duplicate_reason": reason, "dry_run": dry_run,
                  "merged_into": matched_key if location_matched else None}
        if dry_run:
            result["sql"] = sql
            result["values"] = {c: writable[c] for c in cols}
            return result
        with c.cursor() as cur:
            cur.execute(sql, [writable[c] for c in cols])
            # xmax = 0 distinguishes a fresh INSERT from an UPDATE, so the run report can say which.
            result["inserted"] = bool(cur.fetchone()["inserted"])
        return result


class _null_ctx:
    """Use a caller-supplied connection without taking ownership of its lifecycle."""

    def __init__(self, conn):
        self._conn = conn

    def __enter__(self):
        return self._conn

    def __exit__(self, *a):
        return False
