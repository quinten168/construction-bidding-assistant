"""
Feature 4 — projects table: view scratch.bid_projects (one row per historical letting) and edit a
project's material-quantity fields in place (Supabase, see docs/DATA_ACCESS_SCRATCH.md).

View + edit, no create. Everything except the seven material-quantity columns is read-only here:
identity fields (project_natural_key, bid_date, state/county/location) and project_type are
display-only.

DELETE (#55): scratch.bid_results references bid_projects with ON DELETE CASCADE, so a real DELETE
here would silently destroy every bid result hand-entered against a project, with no recovery —
those rows aren't regenerable from a pipeline run. This module never issues one; soft_delete_project()
sets `deleted_at` instead, and every read in this module (and the live-stats/capacity readers in
competitor_stats_live.py and capacity_live.py) filters `deleted_at is null`, so a soft-deleted
project simply stops appearing everywhere without touching its bid_results. No HTTP endpoint or UI
wires to soft_delete_project() yet — it exists as a safe primitive for a future cleanup/reconciliation
script to call instead of writing a raw DELETE.
"""
from __future__ import annotations

from . import ci_db
from .observability import get_logger

log = get_logger("bid_assistant.project_admin")

MATERIAL_FIELDS = [
    "mix_tons", "grading_yards", "base_tons", "shldr_tons", "mill_sy", "crush_tons", "stock_tons",
]


class ValidationError(ValueError):
    pass


def list_projects(search: str | None = None) -> list[dict]:
    sql = "select * from scratch.bid_projects where deleted_at is null"
    params: list = []
    if search:
        sql += " and (project_name ilike %s or county ilike %s)"
        like = f"%{search}%"
        params += [like, like]
    sql += " order by bid_date desc nulls last"
    with ci_db.get_conn() as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchall()


def update_project_materials(project_natural_key: str, fields: dict) -> dict:
    """Edit any subset of the seven material-quantity columns for one project. Any key outside
    MATERIAL_FIELDS is rejected rather than silently ignored, so a frontend bug that sends e.g.
    project_name can't quietly slip past this endpoint's read-only boundary."""
    unknown = set(fields) - set(MATERIAL_FIELDS)
    if unknown:
        raise ValidationError(f"Not editable here: {', '.join(sorted(unknown))}.")
    if not fields:
        raise ValidationError("No fields to update.")

    parsed: dict[str, float | None] = {}
    for f, v in fields.items():
        if v is None or v == "":
            parsed[f] = None
            continue
        n = float(v)
        if n < 0:
            raise ValidationError(f"{f} cannot be negative.")
        parsed[f] = n

    set_clause = ", ".join(f"{c} = %({c})s" for c in parsed)
    with ci_db.get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            f"update scratch.bid_projects set {set_clause}, updated_at = now() "
            "where project_natural_key = %(project_natural_key)s and deleted_at is null",
            {**parsed, "project_natural_key": project_natural_key},
        )
        if cur.rowcount == 0:
            raise ValidationError(f"No project found with key {project_natural_key!r}.")
        cur.execute(
            "select * from scratch.bid_projects where project_natural_key = %s",
            (project_natural_key,),
        )
        row = cur.fetchone()

    log.info("project materials updated: %s (%s)", project_natural_key, ", ".join(parsed))
    return {"project": row}


def soft_delete_project(project_natural_key: str) -> dict:
    """Mark a project deleted without ever issuing a hard DELETE — see module docstring (#55) for
    why. Distinguishes "doesn't exist" from "already deleted" so a caller isn't misled into thinking
    a retry would help."""
    with ci_db.get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "update scratch.bid_projects set deleted_at = now() "
            "where project_natural_key = %s and deleted_at is null",
            (project_natural_key,),
        )
        if cur.rowcount == 0:
            cur.execute(
                "select deleted_at from scratch.bid_projects where project_natural_key = %s",
                (project_natural_key,),
            )
            existing = cur.fetchone()
            if existing is None:
                raise ValidationError(f"No project found with key {project_natural_key!r}.")
            raise ValidationError(f"{project_natural_key!r} is already deleted.")

    log.info("project soft-deleted: %s", project_natural_key)
    return {"project_natural_key": project_natural_key}
