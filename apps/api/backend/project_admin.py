"""
Feature 4 — projects table: view scratch.bid_projects (one row per historical letting) and edit a
project's material-quantity fields in place (Supabase, see docs/DATA_ACCESS_SCRATCH.md).

View + edit only, no create/delete — same shape as the bid-results table
(backend/bid_results_admin.py's list_bid_results/update_bid_result). Everything except the seven
material-quantity columns is read-only here: identity fields (project_natural_key,
bid_date, state/county/location) and project_type are display-only.
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
    sql = "select * from scratch.bid_projects"
    params: list = []
    if search:
        sql += " where project_name ilike %s or county ilike %s"
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
            "where project_natural_key = %(project_natural_key)s",
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
