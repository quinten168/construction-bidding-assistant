"""
Live candidate prediction for a genuinely new project — one with no row of its own in the CI
corpus's training panel (pipelines/ci_model/03_training/outputs/ranking_predictions.csv), so
competitor_live.py's live-generation and competitor_report.py's static match both have nothing to
key off (both require an EXISTING project_natural_key). This module is the live-inference analogue
of pipelines/ci_model/03_training/train_simple_rule_baseline.py for exactly one ad-hoc project:
same candidate-pool definition, same 4 features (county/type/state win counts + size_fit), and the
SAME already-fitted weights (03_training/outputs/simple_rule_baseline_weights.json) — applied fresh
against live Postgres data instead of matching a precomputed training-panel row.

The weights are read, never refit, here. Refitting needs a label (did_bid — did this candidate
actually bid), which does not exist for a project that has not been let yet; there is nothing to
fit against for a single new project. What CAN legitimately change over time is the whole model
being periodically retrained on the growing historical corpus (train_simple_rule_baseline.py, run
again as a batch job) — a separate, offline concern from this module, which only ever scores with
whatever weights that job last produced.

Fail-open like every other *_live.py module in this tree (capacity_live.py, competitor_stats_live.py):
any error, or an empty/unloadable weights file, returns None, so a genuinely new plan without a
prediction still gets the rest of its report rather than a broken one.
"""
from __future__ import annotations

import json
from math import log1p

from . import ci_db
from . import competitor_report as cr
from .config import CI_MODEL_JSON
from .observability import get_logger

log = get_logger("bid_assistant.competitor_predict_live")

MIN_MATERIAL_BIDS = 3
# quantities keys this module understands — the same 7 columns train_simple_rule_baseline.py's
# MATERIALS list and project_admin.py's MATERIAL_FIELDS both use. A fixed whitelist, not
# caller-supplied strings, because these get interpolated into a SQL column list below.
_MATERIAL_COLS = ("mix_tons", "grading_yards", "base_tons", "shldr_tons",
                   "mill_sy", "crush_tons", "stock_tons")
# final_report.py's `quantities` list uses these short display labels, not the DB column names.
LABEL_TO_MATERIAL_COL = {
    "MIX": "mix_tons", "GRADE": "grading_yards", "BASE": "base_tons",
    "SHLDR": "shldr_tons", "MILL": "mill_sy", "CRUSH": "crush_tons", "STOCK": "stock_tons",
}


def _load_weights() -> dict[str, float] | None:
    try:
        data = json.loads(CI_MODEL_JSON.read_text())
    except Exception as e:                                    # noqa: BLE001 — missing/corrupt file
        log.warning("could not load fitted weights from %s: %s", CI_MODEL_JSON, e)
        return None
    weights = data.get("weights")
    if not weights or not data.get("fit"):
        # fit: false means train_simple_rule_baseline.py fell back to the hand-picked constants
        # (see that module's FALLBACK_WEIGHTS) — still usable, weights is populated either way.
        return weights or None
    return weights


def _candidate_pool(conn, state: str, before_date: str) -> set[str]:
    """Everyone who has bid in this state before this project's date, plus CSI's own tracked
    ("priority") competitors from the registry. Mirrors build_project_competitor_panel.py's
    candidate definition minus `actual_competitors` — unknowable for a project that has not been
    let yet, unlike the historical projects that panel is built from."""
    with conn.cursor() as cur:
        cur.execute(
            "select distinct br.competitor_unit_id "
            "from scratch.bid_results br join scratch.bid_projects bp using (project_natural_key) "
            "where upper(bp.state) = upper(%(state)s) and bp.bid_date < %(before_date)s",
            {"state": state, "before_date": before_date},
        )
        historical = {r["competitor_unit_id"] for r in cur.fetchall()}

        cur.execute(
            "select distinct comp_name from scratch.competitor_name_registry "
            "where top_competitors_tag is not null and top_competitors_tag != ''"
        )
        priority = {r["comp_name"] for r in cur.fetchall() if r["comp_name"]}

    return historical | priority


def _score_candidates(
    conn, candidates: set[str], county: str, state: str, project_type: str | None,
    before_date: str, quantities: dict[str, float], weights: dict[str, float],
) -> list[tuple[str, float]]:
    """One query for every candidate's win history, then the same log1p(win_count)-weighted linear
    combination train_simple_rule_baseline.py::build_simple_rule_score() computes for historical
    projects — just scored against this one ad-hoc project's own county/state/type/quantities
    instead of a training-panel row's. County matching uses competitor_report.norm_county() (an
    exact match on the normalized token — NOT a substring/LIKE match, which produces real false
    positives on this data; see #77's "Clark" -> "CLARKE CO" class of bug)."""
    if not candidates:
        return []
    target_county = cr.norm_county(county)
    target_state = (state or "").strip().upper()
    target_type = (project_type or "").strip().upper() or None
    material_cols = [c for c in _MATERIAL_COLS if quantities.get(c, 0) > 0]

    select_cols = ", ".join(f"bp.{c}" for c in material_cols) if material_cols else "null as _unused"
    with conn.cursor() as cur:
        cur.execute(
            f"select br.competitor_unit_id, br.did_win, bp.county, bp.state, bp.project_type, "
            f"{select_cols} "
            "from scratch.bid_results br join scratch.bid_projects bp using (project_natural_key) "
            "where br.competitor_unit_id = any(%(ids)s) and bp.bid_date < %(before_date)s",
            {"ids": list(candidates), "before_date": before_date},
        )
        rows = cur.fetchall()

    win_county: dict[str, int] = {}
    win_type: dict[str, int] = {}
    win_state: dict[str, int] = {}
    # cid -> material -> [log1p(qty), ...] over this candidate's WON projects with that material present
    material_logs: dict[str, dict[str, list[float]]] = {}

    for r in rows:
        if not r["did_win"]:
            continue
        cid = r["competitor_unit_id"]
        if (r["state"] or "").strip().upper() == target_state:
            win_state[cid] = win_state.get(cid, 0) + 1
        if cr.norm_county(r["county"]) == target_county:
            win_county[cid] = win_county.get(cid, 0) + 1
        if target_type and (r["project_type"] or "").strip().upper() == target_type:
            win_type[cid] = win_type.get(cid, 0) + 1
        for m in material_cols:
            qty = r.get(m)
            if qty and qty > 0:
                material_logs.setdefault(cid, {}).setdefault(m, []).append(log1p(float(qty)))

    # size_fit: this project's active materials vs. each candidate's own historical average
    # (>= MIN_MATERIAL_BIDS qualifying won projects with that material present). Leakage-safe
    # neutral fallback for candidates without enough material history — the population mean of the
    # OTHER candidates' real fit values, same rationale as train_simple_rule_baseline.py's: 0 would
    # be this metric's best possible value, so defaulting to it would silently reward missing data.
    per_cid_fit: dict[str, float] = {}
    for cid in candidates:
        fits = []
        for m in material_cols:
            vals = material_logs.get(cid, {}).get(m, [])
            if len(vals) >= MIN_MATERIAL_BIDS:
                fits.append(-abs(log1p(quantities[m]) - (sum(vals) / len(vals))))
        if fits:
            per_cid_fit[cid] = sum(fits) / len(fits)
    fallback_fit = (sum(per_cid_fit.values()) / len(per_cid_fit)) if per_cid_fit else 0.0

    scored = []
    for cid in candidates:
        score = (
            weights.get("county", 0) * log1p(win_county.get(cid, 0))
            + weights.get("type", 0) * log1p(win_type.get(cid, 0))
            + weights.get("state", 0) * log1p(win_state.get(cid, 0))
            + weights.get("size_fit", 0) * per_cid_fit.get(cid, fallback_fit)
        )
        scored.append((cid, score))

    scored.sort(key=lambda t: t[1], reverse=True)
    return scored


def predict_report(
    county: str, state: str, project_type: str | None, bid_date: str,
    quantities: dict[str, float], source_id: str, top_n: int = 5,
) -> dict | None:
    """Live-inference analogue of the CI corpus lookup, for a project with no history of its own —
    builds its own candidate pool and scores it from live Postgres data instead of matching an
    existing ranking_predictions.csv row. Returns the SAME dict shape
    competitor_report.match_report()/competitor_live.live_report() do (every key present, just
    empty except `competitors`/`summary`), so every downstream consumer — the manual-competitor
    merge, competitor_stats_live.compute_stats(), render_markdown(), report-card.tsx — works
    completely unmodified; they cannot tell a predicted list from a matched one.

    None (never raises) if state is blank, the weights file is missing/unfit, or any query fails.
    """
    if not state:
        return None
    weights = _load_weights()
    if not weights:
        return None
    try:
        with ci_db.get_conn() as conn:
            candidates = _candidate_pool(conn, state, bid_date)
            scored = _score_candidates(conn, candidates, county, state, project_type, bid_date,
                                       quantities, weights)
    except Exception as e:                                    # noqa: BLE001 — must never break assembly
        log.warning("predict_report: query failed, no live prediction: %s", e)
        return None

    names = [cid for cid, _ in scored[:top_n]]
    location = ", ".join(p for p in (county, state) if p)
    return {
        "project_id": source_id, "location": location, "county": county, "state": state,
        "bid_date": bid_date, "work_type": project_type or "", "condition": "", "materials": [],
        "pits": {}, "summary": {"analyzed": len(names), "narrative": ""},
        "competitors": names, "attrs": {}, "deep_dives": {}, "source_file": "",
        "_match": {"confidence": "predicted",
                   "basis": "live candidate model, no CI corpus match", "date_gap_days": None},
    }
