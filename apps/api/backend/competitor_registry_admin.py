"""
Feature 3 — competitor name registry CRUD: add/consolidate/remove rows in
scratch.competitor_name_registry (Supabase, see docs/DATA_ACCESS_SCRATCH.md).

consolidate() is registry-only, by explicit 2026-07-31 request: it renames raw_name_variant rows
onto a new canonical comp_name and does NOT touch scratch.bid_results.competitor_unit_id. Before
this change it cascaded the rename into bid_results (joining on raw_bidder_name, not the old
competitor_unit_id, to avoid collateral damage across raw names sharing an old comp_name — see
docs/ARCHITECTURE.md §9 and CLAUDE.md rough edge 7 for that prior design). Narrowing the scope
means competitor_unit_id in bid_results is no longer guaranteed to equal the registry's current
comp_name for a raw name after a consolidate — that invariant (docs/ARCHITECTURE.md §6/rough edge
5) now only holds until the next batch re-run of entity_resolution.apply_registry_mapping()
(data/build_project_competitor_panel.py) / push_supabase_bid_data.py, not live in this admin tool.

Fuzzy-duplicate detection reuses the same approach as data/update_name_registry.py's
suggest_comp(): rapidfuzz token_sort_ratio against normalized names, threshold 80.
"""
from __future__ import annotations

from rapidfuzz import fuzz

from . import ci_db
from .ci_db import normalize
from .observability import get_logger

log = get_logger("bid_assistant.competitor_registry_admin")

FUZZY_THRESHOLD = 80


class ValidationError(ValueError):
    pass


class DuplicateWarning(Exception):
    """Not fatal — a similarly-named competitor already exists and `force` wasn't set."""

    def __init__(self, payload: dict):
        self.payload = payload
        super().__init__(payload.get("message", "possible duplicate"))


def list_registry(needs_review_only: bool = False, search: str | None = None) -> list[dict]:
    sql = "select * from scratch.competitor_name_registry"
    clauses, params = [], []
    if needs_review_only:
        clauses.append("(comp_name is null or comp_name = '')")
    if search:
        clauses.append("(raw_name_variant ilike %s or comp_name ilike %s)")
        like = f"%{search}%"
        params += [like, like]
    if clauses:
        sql += " where " + " and ".join(clauses)
    sql += " order by comp_name, raw_name_variant"
    with ci_db.get_conn() as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchall()


def add_competitor(name: str, top_competitors_tag: str | None = None, force: bool = False) -> dict:
    """Bootstrap a brand-new canonical competitor as a self-referencing row
    (raw_name_variant = comp_name), the same shape an exact auto-confirmed match produces today."""
    name = (name or "").strip()
    if not name:
        raise ValidationError("A competitor name is required.")
    norm = normalize(name)

    with ci_db.get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "select raw_name_variant, comp_name from scratch.competitor_name_registry "
            "where upper(regexp_replace(raw_name_variant, '\\s+', ' ', 'g')) = %s "
            "   or upper(regexp_replace(comp_name, '\\s+', ' ', 'g')) = %s",
            (norm, norm),
        )
        exact = cur.fetchone()
        if exact is not None:
            raise ValidationError(f"{name!r} already exists in the registry (exact match).")

        if not force:
            cur.execute(
                "select distinct comp_name from scratch.competitor_name_registry "
                "where comp_name is not null and comp_name != ''"
            )
            best_score, best_comp = 0, ""
            for (comp,) in ((r["comp_name"],) for r in cur.fetchall()):
                score = fuzz.token_sort_ratio(norm, normalize(comp))
                if score > best_score:
                    best_score, best_comp = score, comp
            if best_score >= FUZZY_THRESHOLD:
                raise DuplicateWarning({
                    "warning": "possible_duplicate",
                    "message": f"{name!r} looks similar to existing competitor {best_comp!r}. Continue anyway?",
                    "existing": {"comp_name": best_comp, "score": best_score},
                })

        cur.execute(
            "insert into scratch.competitor_name_registry "
            "(raw_name_variant, comp_name, source, top_competitors_tag, source_batch) "
            "values (%s, %s, 'manual', %s, 'webapp_competitor_admin')",
            (name, name, top_competitors_tag),
        )
    log.info("competitor added: %s", name)
    return {"comp_name": name}


def consolidate(raw_name_variants: list[str], target_comp_name: str) -> dict:
    """Merge one or more existing raw-name rows onto one canonical comp_name (a plain rename is
    the single-element case). Registry-only — does not touch scratch.bid_results. See the module
    docstring for what that means for the competitor_unit_id/comp_name invariant."""
    if not raw_name_variants:
        raise ValidationError("At least one raw name variant is required.")
    target_comp_name = (target_comp_name or "").strip()
    if not target_comp_name:
        raise ValidationError("A target competitor name is required.")

    normalized_variants = [normalize(v) for v in raw_name_variants]

    with ci_db.get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "update scratch.competitor_name_registry set comp_name = %s, updated_at = now() "
            "where upper(regexp_replace(raw_name_variant, '\\s+', ' ', 'g')) = any(%s)",
            (target_comp_name, normalized_variants),
        )
        registry_updated = cur.rowcount

    log.info(
        "consolidated %d raw name(s) into %s (registry rows: %d; bid_results untouched)",
        len(raw_name_variants), target_comp_name, registry_updated,
    )
    return {"target_comp_name": target_comp_name, "registry_rows_updated": registry_updated}


def remove_competitor(comp_name: str) -> dict:
    """Remove every raw_name_variant row under this canonical comp_name — blocked if any
    scratch.bid_results row still references it (no reassignment flow; consolidate first)."""
    comp_name = (comp_name or "").strip()
    if not comp_name:
        raise ValidationError("A competitor name is required.")

    with ci_db.get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "select count(*) as n from scratch.bid_results where competitor_unit_id = %s", (comp_name,)
        )
        referenced = cur.fetchone()["n"]
        if referenced:
            raise ValidationError(
                f"Cannot remove {comp_name!r} — {referenced} bid_results row(s) still reference it. "
                "Consolidate those rows into another competitor first."
            )

        cur.execute(
            "delete from scratch.competitor_name_registry where comp_name = %s", (comp_name,)
        )
        removed = cur.rowcount

    log.info("competitor removed: %s (%d registry row(s))", comp_name, removed)
    return {"comp_name": comp_name, "rows_removed": removed}
