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

4. **Insert and flag, never silently skip.** When identity is ambiguous the row is still written,
   with `duplicate_flag` set and `duplicate_reason` saying why. A visible duplicate is recoverable;
   a silently dropped plan is not.
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


def find_conflicts(row: dict, *, conn) -> tuple[bool, Optional[str]]:
    """Is this row ambiguous against what is already in the table? (flag, reason).

    Two questions, deliberately separate from "does the primary key already exist" — a PK match is
    an ordinary upsert of the same project, not a duplicate:

      * same `join_key`, different `plan_uid` → two different PDFs claim one project (#41's exact
        question: when are two PDFs one project?).
      * same `plan_uid`, different `project_natural_key` → the same PDF has landed under two keys,
        which is what a changed city or a reparsed bid_date does.
    """
    jkey, uid, pnk = row.get("join_key"), row.get("plan_uid"), row.get("project_natural_key")
    with conn.cursor() as cur:
        if jkey and uid:
            cur.execute(
                f"select project_natural_key, plan_uid from {TABLE} "
                "where join_key = %s and plan_uid is distinct from %s limit 1", (jkey, uid))
            if hit := cur.fetchone():
                return True, f"same_join_key_different_plan_uid:{hit['project_natural_key']}"
        if uid and pnk:
            cur.execute(
                f"select project_natural_key from {TABLE} "
                "where plan_uid = %s and project_natural_key is distinct from %s limit 1",
                (uid, pnk))
            if hit := cur.fetchone():
                return True, f"same_plan_uid_different_key:{hit['project_natural_key']}"
    return False, None


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

        dup, reason = find_conflicts(row, conn=c)
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
                  "duplicate_flag": dup, "duplicate_reason": reason, "dry_run": dry_run}
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
