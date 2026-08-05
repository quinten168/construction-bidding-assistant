"""
Final report — assemble + render + export.

The "final report" is a one-pager that fuses two teams' outputs for a single project:
  Section ① ② ③  PLAN READER  — snapshot, materials/quantities, gotchas (Go/No-Go vs Pricing)
  Section ④       COMPETITIVE LANDSCAPE — the matched Competitor Intel report (parsed markdown)

It takes either a live plan payload (what `report.py::process_pdf` returns after a PDF drop) or a
plan_id already in the corpus, attaches the competitor report matched on county+state+date
(`competitor_report.match_report`), and renders to markdown (the canonical view) with CSV + PDF
exports. No Claude calls — the summary line is deterministic so the MVP is transparent and cheap.

Gotcha source of truth: the deduped `public.gotchas` table in Supabase Postgres (it already
carries `decision_class` = go_no_go|pricing, page lists, and confidence). Moved off the local
csi_v2.db SQLite file on 2026-08-03 (#50). For a freshly dropped PDF that is not in the corpus yet,
we fall back to the live record's gotchas and map decision_class by code via the taxonomy CSV.
"""
from __future__ import annotations

import csv
import io
import json
import re
import subprocess
import tempfile
from functools import lru_cache
from pathlib import Path

from . import ci_db
from . import competitor_report as cr
from . import competitor_stats_live
from . import corrections
from .config import CORPUS_MESSAGES, CORPUS_OK, CSI_DB, PLAN_READER, corpus_state
from .observability import get_logger

log = get_logger("bid_assistant.final_report")

# Retained only so the retirement stays greppable and any stale import keeps resolving; no query
# in this module opens it any more (#50). The corpus now lives in Postgres, reached via ci_db.
DB_PATH = CSI_DB
PLANS_DIR = PLAN_READER / "00_input" / "plans"
GOTCHA_TAXONOMY = PLAN_READER / "05_knowledge" / "gotcha_taxonomy.csv"

_CONF_RANK = {"high": 3, "medium": 2, "low": 1, "": 0, None: 0}
_TOP_N_GOTCHAS = 25                                   # per side — effectively "all" (max ~20/plan),
                                                      # still confidence-ranked so the strongest lead
_EVIDENCE_CHARS = 300                                 # show (near-)verbatim evidence, not a stub
_QUNIT = {"hot_mix_tons": ("MIX", "t"), "base_tons": ("BASE", "t"),
          "grading_quantity": ("GRADE", "CY"), "shoulder_tons": ("SHLDR", "t"),
          "milling_sy": ("MILL", "SY"), "crushing_tons": ("CRUSH", "t"),
          "stockpile_tons": ("STOCK", "t")}


# --- gotcha loading -----------------------------------------------------------------------------
# The taxonomy CSV carries a `relevance` column (decision_driver | pricing_input); older/other
# exports used a `decision_class` column (go_no_go | pricing). Map BOTH → the two display buckets so
# a freshly-dropped plan's live gotchas are classified (not silently dropped, which showed 0/0).
_RELEVANCE_TO_CLASS = {"decision_driver": "go_no_go", "pricing_input": "pricing"}


@lru_cache(maxsize=1)
def _decision_class_map() -> dict:
    """code -> 'go_no_go'|'pricing' from the taxonomy CSV (used when a live record's gotchas don't
    carry decision_class). Accepts either the `decision_class` or the `relevance` column."""
    out = {}
    if GOTCHA_TAXONOMY.exists():
        for row in csv.DictReader(GOTCHA_TAXONOMY.open()):
            code = (row.get("gotcha_type") or "").strip()
            if not code or code.startswith("#"):
                continue
            dc = (row.get("decision_class") or "").strip()
            if dc not in ("go_no_go", "pricing"):        # fall back to the relevance column
                dc = _RELEVANCE_TO_CLASS.get((row.get("relevance") or "").strip(), "")
            if dc in ("go_no_go", "pricing"):
                out[code] = dc
    return out


def _rank_and_trim(items: list[dict]) -> list[dict]:
    """Rank gotchas by confidence then breadth (page_count) and keep the top N — the sleek shortlist."""
    items = sorted(items, key=lambda g: (_CONF_RANK.get(g.get("confidence"), 0),
                                         g.get("page_count") or 0), reverse=True)
    return items[:_TOP_N_GOTCHAS]


def _corpus_loaded(reader: str, plan_id: str) -> bool:
    """True when Postgres actually holds a plan corpus, checked fresh on every call.

    Logs at warning level when it does not, once per reader call site (not once per row), so a
    degraded read leaves a trace instead of silently rendering as a confident "zero gotchas".
    """
    state = corpus_state()
    if state == CORPUS_OK:
        return True
    log.warning("%s: no plan corpus (%s), returning None for plan_id=%s. The report will "
                "show no data for this plan, which is a setup problem, not an empty plan.",
                reader, CORPUS_MESSAGES[state], plan_id)
    return False


def _gotchas_from_db(plan_id: str) -> dict | None:
    """Pull deduped gotchas for a plan from Postgres, split Go/No-Go vs Pricing, top N each."""
    if not _corpus_loaded("_gotchas_from_db", plan_id):
        return None
    try:
        with ci_db.get_conn() as conn, conn.cursor() as cur:
            cur.execute(
                "select flag_type, family, decision_class, evidence, page, page_count, confidence "
                "from public.gotchas where plan_id = %s", (plan_id,))
            rows = cur.fetchall()
    except Exception:                                     # noqa: BLE001 — never break the report
        log.warning("_gotchas_from_db: query failed for plan_id=%s", plan_id, exc_info=True)
        return None
    if not rows:
        return None
    buckets = {"go_no_go": [], "pricing": []}
    for r in rows:
        dc = r["decision_class"] or _decision_class_map().get(r["flag_type"], "")
        if dc in buckets:
            buckets[dc].append({"code": r["flag_type"], "family": r["family"],
                                "evidence": r["evidence"], "page": r["page"],
                                "page_count": r["page_count"], "confidence": r["confidence"]})
    return {k: _rank_and_trim(v) for k, v in buckets.items()}


def _resolve_corpus_plan_id(identity: dict) -> str | None:
    """A freshly dropped PDF gets a throwaway UUID plan_id, so its gotchas miss the curated corpus
    set. Re-link it to the corpus plan by its SP/contract number (the distinctive digit-dash token,
    e.g. 'SAP 021-600-023' -> '021-600-023', which is embedded in the corpus plan_id). Returns the
    matching corpus plan_id that actually has gotcha rows, or None."""
    sp = (identity.get("sp_number") or "")
    m = re.search(r"\d{2,4}(?:[-\s]\d{2,4}){1,3}", sp)   # the numeric core, e.g. 021-600-023
    if not m:
        return None
    # Unlike the other two readers, this one has a specific plan to look up, so it can tell "there
    # is no corpus" (a setup problem) from "the corpus is loaded and this plan is not in it" (an
    # ordinary miss). They are logged at different levels so the distinction survives into the log
    # without anyone having to open the database.
    state = corpus_state()
    if state != CORPUS_OK:
        log.warning("_resolve_corpus_plan_id: no plan corpus (%s), cannot re-link SP %r. This is a "
                    "setup problem, not a corpus miss: check SUPABASE_TEAM_DB_URL and that "
                    "public.plans is populated.", CORPUS_MESSAGES[state], sp)
        return None
    core = m.group(0).replace(" ", "-")
    try:
        with ci_db.get_conn() as conn, conn.cursor() as cur:
            cur.execute(
                "select plan_id from public.gotchas where replace(plan_id,' ','-') like %s "
                "group by plan_id order by count(*) desc limit 1", (f"%{core}%",))
            row = cur.fetchone()
    except Exception:                                     # noqa: BLE001 — never break the report
        log.warning("_resolve_corpus_plan_id: query failed for core=%r", core, exc_info=True)
        return None
    if row is None:
        log.info("_resolve_corpus_plan_id: corpus is loaded but holds no plan matching %r "
                 "(from SP %r), treating as an ordinary corpus miss.", core, sp)
        return None
    return row["plan_id"]


def _gotchas_from_payload(payload_gotchas: list[dict]) -> dict:
    """Fallback: split a live record's gotchas (code/evidence/page/confidence) by taxonomy code."""
    dcmap = _decision_class_map()
    buckets = {"go_no_go": [], "pricing": []}
    for g in payload_gotchas or []:
        dc = dcmap.get(g.get("code"), "")
        if dc in buckets:
            buckets[dc].append({"code": g.get("code"), "family": None,
                                "evidence": g.get("evidence"), "page": g.get("page"),
                                "page_count": None, "confidence": g.get("confidence")})
    return {k: _rank_and_trim(v) for k, v in buckets.items()}


# --- assembly -----------------------------------------------------------------------------------
def _city_from_location(location: str) -> str:
    """First place-like segment of a location string, for a memorable name when county is missing.
    'White Shield, North Dakota – Awahu Village roadway improvements' -> 'White Shield'."""
    seg = re.split(r"[–—,\-]", (location or "").strip())[0].strip()
    # guard against a segment that's just the state name or empty
    return seg if len(seg) > 1 else ""


def _parse_lat_long(value: str) -> tuple[float, float] | None:
    """Parse a user-typed 'lat,lon' string (corrections.py's lat_long field, e.g. '45.62,-95.05')."""
    parts = re.split(r"[,\s]+", (value or "").strip())
    if len(parts) != 2:
        return None
    try:
        return float(parts[0]), float(parts[1])
    except ValueError:
        return None


def _short_place(identity: dict) -> str:
    """A clean memorable place: 'Douglas County, MN', else the city 'White Shield, ND', else state."""
    county = (identity.get("county") or "").strip()
    state = (identity.get("state") or "").strip()
    if county and state:
        return f"{county} County, {state}"
    city = _city_from_location(identity.get("location") or "")
    if city and city.lower() != state.lower():
        return f"{city}, {state}".strip(" ,")
    return county or state or ""


def _tldr(identity: dict, archetype: str, gotchas: dict) -> str:
    """One deterministic sentence: archetype + place + gotcha load. (No LLM in the MVP.)
    Uses the short 'County, ST' place — NOT the long stationing location string."""
    where = _short_place(identity) or "an unknown location"
    n_g, n_p = len(gotchas.get("go_no_go", [])), len(gotchas.get("pricing", []))
    lead = gotchas.get("go_no_go") or gotchas.get("pricing")
    watch = f" Top watch-item: {lead[0]['code'].replace('_', ' ')} (p.{lead[0]['page']})." if lead else ""
    wage = " Prevailing wage applies." if identity.get("prevailing_wages") in (True, "true", "Yes", "yes") else ""
    return (f"{archetype} project in {where}. "
            f"{n_g} go/no-go and {n_p} pricing gotchas flagged.{watch}{wage}").strip()


def _readable_title(plan_id: str, identity: dict) -> str:
    """A clean, memorable human title: 'Chippewa Co, MN' when county is known, else the city from
    the location ('White Shield, ND') so a county-less plan never shows a broken ' Co, ND'. The
    SP/contract number(s) live in the identity detail rows (a plan can bundle several SAP segments)."""
    county = (identity.get("county") or "").strip()
    state = (identity.get("state") or "").strip()
    if county:
        return f"{county} Co, {state}".strip(" ,")
    city = _city_from_location(identity.get("location") or "")
    if city and city.lower() != state.lower():
        return f"{city}, {state}".strip(" ,")
    return state or plan_id


# Sentinel for assemble()'s `predicted_competitors` param: distinguishes "caller has no cached
# prediction, compute fresh" (the default) from "caller has a cache hit and the cascade found
# nothing" (a legitimate `None` result that must NOT trigger a redundant recompute).
_NO_CACHED_PREDICTION = object()


def predict_competitors(identity: dict, archetype: str, quantities: list,
                         bid_date: str | None, pid: str, reports_dir: str | None = None) -> dict | None:
    """The three-tier competitor cascade, lifted out of `assemble()` so it can be invoked on its own
    (the predict-competitors endpoint calls this directly, before finalize, so the estimator sees the
    predicted list instead of typing names blind). LIVE generation, else a static match, else a live
    PREDICTION. Live = invoke the CI team's agent for a fresh report keyed to this exact project
    (county+state+date → their project_natural_key → generate). Falls back to matching a
    pre-generated report when the plan isn't in their corpus, the model repo is absent, or generation
    fails. Both of those require the project to ALREADY be a row in the CI corpus
    (ranking_predictions.csv / data/processed/projects.csv) -- i.e. a historical letting CSI already
    has bid data for. A genuinely new plan (nothing in CSI's history under this county+state+date)
    matches neither, and previously left `comp` as None with no competitor section at all.
    competitor_predict_live.predict_report() is the third fallback for exactly that case: it builds
    its own candidate pool and scores it live against Postgres, using the SAME already-fitted weights
    the CI model uses, rather than requiring a precomputed row."""
    when = bid_date or identity.get("construction_start") or identity.get("construction_end")
    comp = None
    if identity.get("county") or identity.get("state"):
        try:
            from . import competitor_live as cl
            comp = cl.live_report(identity.get("county", ""), identity.get("state", ""), when)
        except Exception as e:                           # noqa: BLE001 — live path must never break assembly
            log.warning("live competitor generation errored, falling back to static: %s", e)
        if comp is None:
            comp = cr.match_report(identity.get("county", ""), identity.get("state", ""),
                                   when, reports_dir=reports_dir)
        if comp is None:
            try:
                from . import competitor_predict_live as cpl
                qty_by_col = {
                    cpl.LABEL_TO_MATERIAL_COL[q["label"]]: q["value"]
                    for q in quantities if q.get("label") in cpl.LABEL_TO_MATERIAL_COL
                }
                comp = cpl.predict_report(
                    county=identity.get("county", "") or "", state=identity.get("state", "") or "",
                    project_type=archetype, bid_date=when or "", quantities=qty_by_col,
                    source_id=pid,
                )
            except Exception as e:                       # noqa: BLE001 — prediction must never break assembly
                log.warning("live candidate prediction errored: %s", e)
    return comp


def assemble(plan_payload: dict | None = None, plan_id: str | None = None,
             bid_date: str | None = None, reports_dir: str | None = None,
             manual_competitors: list[str] | None = None,
             predicted_competitors: dict | None = _NO_CACHED_PREDICTION) -> dict:
    """Build the structured final-report dict. Pass a live `plan_payload` (from report.process_pdf)
    OR a `plan_id` already in the corpus (loaded from its per-plan JSON). The competitor section is
    attached when a report matches the plan's county+state(+date). `manual_competitors` are names an
    estimator typed in themselves (the optional second verify-gate popup) -- appended to the SAME
    flat, rank-ordered `competitors` list as the model-predicted names (no separate tier: v3 dropped
    priority/discovery, and manual names never had a ranking score to begin with, so "tier" was
    never a meaningful axis to sort on), all scored by the one unified live-stats query below, not a
    second separate computation. A name that duplicates one already on the list is not re-added --
    see `comp["duplicate_names"]`, which the caller surfaces back to the estimator."""
    if plan_payload is None and plan_id:
        plan_payload = _payload_from_plan_id(plan_id)
    if plan_payload is None:
        raise ValueError("assemble() needs a plan_payload or a known plan_id")

    pid = plan_payload.get("plan_id") or plan_id or "unknown"
    identity = plan_payload.get("identity", {})
    # Human correction always outranks the automated road_midpoint value, and can fill it in when
    # automation found nothing (unsupported state, missing field, lookup failure). Applied HERE, not
    # in report.py, because a correction can be recorded after the PDF was already cached — assemble()
    # runs fresh on every render, so this is the only place that reliably sees a later correction.
    corr_latlong = corrections.corrected_values(pid).get("lat_long")
    if corr_latlong:
        parsed = _parse_lat_long(corr_latlong)
        if parsed:
            identity["latitude"], identity["longitude"] = parsed
    archetype = plan_payload.get("archetype") or "Unknown/NoQty"
    quantities = plan_payload.get("quantities", [])

    gotchas = _gotchas_from_db(pid)
    gotcha_source = "sqlite" if gotchas is not None else None
    if gotchas is None:                              # dropped PDF's UUID id → re-link to the corpus
        corpus_id = _resolve_corpus_plan_id(identity)
        if corpus_id:
            gotchas = _gotchas_from_db(corpus_id)
            gotcha_source = f"sqlite:{corpus_id}" if gotchas is not None else None
    if gotchas is None:                              # genuinely new plan → the live RAG record
        gotchas = _gotchas_from_payload(plan_payload.get("gotchas", []))
        gotcha_source = "live"

    # --- competitor section: a precomputed prediction (from the predict-competitors endpoint, run
    # right after the verify gate so the estimator sees it before the manual-add popup) takes
    # priority; otherwise run the same three-tier cascade here, unchanged from before this was
    # extracted into predict_competitors() (see above).
    when = bid_date or identity.get("construction_start") or identity.get("construction_end")
    if predicted_competitors is _NO_CACHED_PREDICTION:
        comp = predict_competitors(identity, archetype, quantities, when, pid, reports_dir=reports_dir)
    else:
        comp = predicted_competitors

    # --- manual competitors: the estimator's typed-in names get appended to the SAME flat
    # `competitors` list the model predicted -- no separate section, since they were never run
    # through the model's own prediction/ranking scoring (they don't need to be "predicted," the
    # estimator already asserts they'll bid), but every competitor on the report -- predicted or
    # manual alike -- gets its win_rate/bid_rate/capacity/pit_access from the SAME live-SQL
    # retrieval process below, run ONCE over the whole merged list, not a separate stats
    # computation per origin and not the old model "feature" columns (ranking_predictions.csv).
    manual_names = [n.strip() for n in (manual_competitors or []) if n and n.strip()]
    if manual_names and comp is None:
        # No predicted report at all (e.g. county+state never matched anything) -- manual names are
        # the only way stats show up for this plan, so build a bare skeleton for them to live in.
        comp = {
            "project_id": pid, "location": identity.get("location", ""),
            "county": identity.get("county", ""), "state": identity.get("state", ""),
            "bid_date": when or "", "work_type": "", "condition": "", "materials": [],
            "pits": {}, "summary": {"analyzed": 0, "narrative": ""},
            "competitors": [], "attrs": {}, "deep_dives": {}, "source_file": "",
        }
    duplicate_names: list[str] = []
    if manual_names and comp is not None:
        existing_lower = {c.strip().lower() for c in comp.get("competitors", [])}
        new_names = []
        for n in manual_names:
            key = n.strip().lower()
            if key in existing_lower:                    # dedup against predicted names AND
                duplicate_names.append(n)                 # against earlier names in this same batch
                continue
            existing_lower.add(key)
            new_names.append(n)
        if new_names:
            comp.setdefault("competitors", []).extend(new_names)
            comp.setdefault("user_added", []).extend(new_names)
            comp["summary"]["analyzed"] = len(comp["competitors"])
    if duplicate_names and comp is not None:
        comp["duplicate_names"] = duplicate_names

    if comp is not None and comp.get("competitors"):
        try:
            all_ids = list(comp["competitors"])
            # Scope project_type stats by THIS plan's own archetype (plan_reader's rule-based
            # classifier, computed from this same plan's extracted quantities -- available for
            # every dropped plan) rather than comp.get("work_type") (the CI report's derived label,
            # only present when a historical project was matched, and describing THAT project, not
            # necessarily this one). "Unknown/NoQty" means no quantities were extracted at all --
            # map it to None so this scope cleanly reports "no data" rather than a guaranteed-empty
            # string comparison against scratch.bid_projects.project_type.
            plan_project_type = archetype if archetype and archetype != "Unknown/NoQty" else None
            comp["stats"] = competitor_stats_live.compute_stats(
                all_ids, county=identity.get("county", "") or "", state=identity.get("state", "") or "",
                project_type=plan_project_type, before_date=when or "",
                project_lat=identity.get("latitude"), project_lon=identity.get("longitude"),
            )
        except Exception as e:                           # noqa: BLE001 -- stats must never break assembly
            log.warning("unified competitor stats computation failed: %s", e)
            comp["stats"] = {}

    return {
        "plan_id": pid,
        "title": _readable_title(pid, identity),
        "archetype": archetype,
        "pages": (plan_payload.get("structure") or {}).get("n_pages"),  # real page count for the UI
        "identity": identity,
        "tldr": _tldr(identity, archetype, gotchas),
        "quantities": quantities,
        "gotchas": gotchas,
        # NOTE: the literal 'sqlite' is HISTORICAL and is now a lie about the storage engine — the
        # curated set moved to Postgres in #50. Deliberately NOT renamed here: it is a wire value
        # this module branches on (_bar/note below) and apps/web carries (lib/chat-data.ts:74), so
        # renaming it is a behaviour change and belongs in its own commit, not a storage repoint.
        # It means "curated corpus set" as opposed to 'live' (fresh RAG). See #61.
        "gotcha_source": gotcha_source,              # 'sqlite[:id]' (curated) | 'live' (fresh RAG)
        "competitor": comp,                          # parsed report + ._match, or None
    }


def _payload_from_plan_id(plan_id: str) -> dict | None:
    """Reconstruct a plan_payload from a corpus plan's per-plan JSON (no pipeline re-run)."""
    jp = PLANS_DIR / plan_id / f"{plan_id}.json"
    if not jp.exists():
        return None
    rec = json.loads(jp.read_text())
    val = lambda f: (rec.get(f) or {}).get("value") if isinstance(rec.get(f), dict) else rec.get(f)
    quantities = []
    for fld, (label, unit) in _QUNIT.items():
        v = val(fld)
        if isinstance(v, (int, float)) and v:
            quantities.append({"label": label, "value": v, "unit": unit})
    identity = {"state": val("state"), "county": val("county"),
                "location": val("project_location"), "sp_number": val("sp_number"),
                "prevailing_wages": val("prevailing_wages"), "traffic_level": val("traffic_level"),
                "construction_start": val("construction_start"),
                "construction_end": val("construction_end"),
                "bid_deadline": val("bid_deadline"),
                "substantial_completion": val("substantial_completion"),
                "final_completion": val("final_completion"),
                "latitude": val("latitude"), "longitude": val("longitude")}
    # backfill county/state from the plan_id (e.g. '2025_DOUGLAS-CO-MN_…') when extraction left
    # them blank — the matcher joins on county+state, so a missing county silently weakens it.
    if not identity["county"] or not identity["state"]:
        if m := re.search(r"_([A-Za-z .]+?)-CO-([A-Za-z]{2})_", plan_id):
            identity["county"] = identity["county"] or m.group(1).replace("-", " ").title()
            st = m.group(2).upper()
            identity["state"] = identity["state"] or (st if st != "XX" else "")
    # archetype: prefer plan_metrics.work_type, else recompute is overkill for the MVP loader
    archetype = _work_type_from_db(plan_id) or "Unknown/NoQty"
    return {"plan_id": plan_id, "identity": identity, "archetype": archetype,
            "quantities": quantities, "gotchas": []}     # gotchas come from Postgres in assemble()


def _work_type_from_db(plan_id: str) -> str | None:
    if not _corpus_loaded("_work_type_from_db", plan_id):
        return None
    try:
        with ci_db.get_conn() as conn, conn.cursor() as cur:
            cur.execute("select work_type from public.plan_metrics where plan_id = %s", (plan_id,))
            row = cur.fetchone()
    except Exception:                                     # noqa: BLE001 — never break the report
        log.warning("_work_type_from_db: query failed for plan_id=%s", plan_id, exc_info=True)
        return None
    return row["work_type"] if row else None


# --- markdown render ----------------------------------------------------------------------------
def _bar(value: float, vmax: float, width: int = 10) -> str:
    n = 0 if vmax <= 0 else round(width * value / vmax)
    return "▇" * max(0, min(width, n))


def _gotcha_line(g: dict) -> str:
    """One gotcha as: **code** · p.N — "verbatim evidence". The quotes signal it is pulled text."""
    code = (g.get("code") or "").replace("_", " ")
    pg = f" · p.{g['page']}" if g.get("page") else ""
    ev = (g.get("evidence") or "").strip().replace("\n", " ")
    ev = (ev[:_EVIDENCE_CHARS].rstrip() + "…") if len(ev) > _EVIDENCE_CHARS else ev
    return f"- **{code}**{pg}" + (f' — "{ev}"' if ev else "")


_THREAT_EMOJI = {"HIGH": "🔴", "MEDIUM": "🟡", "LOW": "🟢"}


# --- competitor_stats_live formatting (mirrors report-card.tsx's fmtPct/fmtScoped/fmtTons) ------
def _fmt_pct(pct: float | None) -> str:
    return "—" if pct is None else f"{round(pct * 100)}%"


def _fmt_scoped(r: dict | None) -> str:
    if not r:
        return "—"
    wins, bids, total = r.get("wins"), r.get("bids"), r.get("total")
    if wins is not None and bids is not None:
        raw = f"{wins}/{bids}"
    elif bids is not None and total is not None:
        raw = f"{bids}/{total}"
    else:
        raw = None
    pct = _fmt_pct(r.get("pct"))
    return f"{raw} · {pct}" if raw else pct


def _fmt_tons(t: float | None) -> str:
    return "—" if t is None else f"{round(t):,} tons"


def _stats_lines(stats: dict) -> list[str]:
    """Format one competitor's live-retrieved figures (competitor_stats_live.compute_stats output)
    into export lines -- the SAME source report-card.tsx's CompetitorStatsBlock renders, so exports
    and the chat card never disagree."""
    lines = []
    wr = stats.get("win_rate")
    if wr:
        lines.append(f"Win rate — State {_fmt_scoped(wr.get('state'))} · "
                      f"County {_fmt_scoped(wr.get('county'))} · Type {_fmt_scoped(wr.get('project_type'))}")
    br = stats.get("bid_rate")
    if br:
        lines.append(f"Bid rate — State {_fmt_scoped(br.get('state'))} · "
                      f"County {_fmt_scoped(br.get('county'))} · Type {_fmt_scoped(br.get('project_type'))}")
    cap = stats.get("capacity")
    if cap:
        if cap.get("typical_capacity"):
            cap_line = (f"{_fmt_tons(cap.get('ytd_won'))} of {_fmt_tons(cap.get('typical_capacity'))} "
                        f"typical · {_fmt_pct(cap.get('capacity_pct'))}")
        else:
            cap_line = f"{_fmt_tons(cap.get('ytd_won'))} so far — no historical baseline yet"
        if cap.get("last_year_total") is not None:
            cap_line += f" (last year: {_fmt_tons(cap.get('last_year_total'))})"
        lines.append(f"Capacity — {cap_line}")
    pa = stats.get("pit_access")
    if pa:
        nearest = pa.get("nearest_pit")
        pit_line = (f"Nearest pit {nearest.get('name')} ({nearest.get('distance_miles', 0):.1f} mi)"
                    if nearest else "No usable pit found")
        pit_line += f" · {pa.get('pits_within_25mi_count', 0)} within 25mi"
        lines.append(f"Pit access — {pit_line}")
    return lines


def render_markdown(final: dict, include_dives: bool = True, ascii_bars: bool = True) -> str:
    """The canonical one-pager. Two render modes:
      • EXPORT (defaults: include_dives=True, ascii_bars=True) — self-contained: ASCII bars for
        quantities + the threat matrix, plus competitor deep dives. This is what MD/PDF/CSV ship.
      • CHAT  (include_dives=False, ascii_bars=False) — sleek: the Plotly charts render the
        quantities + threat visually, so the text drops the redundant bars and the long deep dives."""
    idn = final["identity"]
    md: list[str] = []
    md.append("# Bid Intelligence — Final Report")
    comp = final.get("competitor")
    extras = [x for x in (idn.get("location"),
                          f"Bid {comp['bid_date']}" if comp and comp.get("bid_date") else None) if x]
    md.append(f"**{final['title']}**" + ("  ·  " + "  ·  ".join(extras) if extras else ""))
    md.append("")
    md.append(f"> {final['tldr']}")
    md.append("")

    # ① snapshot
    md.append("## ① Plan Snapshot")
    wage = idn.get("prevailing_wages")
    wage_s = "Yes" if wage in (True, "true", "Yes", "yes") else ("No" if wage in (False, "false", "No", "no") else "—")
    rows = [("Archetype", f"**{final['archetype']}**"),
            ("Location", idn.get("location") or "—"),
            ("State / County", " / ".join(x for x in (idn.get("state"), idn.get("county")) if x) or "—"),
            ("SP / Contract #", idn.get("sp_number") or "—"),
            ("Prevailing wage", wage_s),
            ("Traffic level", idn.get("traffic_level") or "—")]
    md += ["| Field | Value |", "|---|---|"]
    md += [f"| {k} | {v} |" for k, v in rows]
    md.append("")

    # ② materials + quantities — ASCII bars in exports; compact list in chat (Plotly bar shown there)
    md.append("## ② Materials & Quantities")
    qs = final["quantities"]
    if not qs:
        md.append("_No bid-schedule quantities extracted._")
    elif ascii_bars:
        vmax = max((q["value"] for q in qs), default=0)
        md.append("```")
        for q in qs:
            md.append(f"{q['label']:<6}{q['value']:>11,.0f} {q['unit']:<3} {_bar(q['value'], vmax)}")
        md.append("```")
    else:
        md.append(" · ".join(f"**{q['label']}** {q['value']:,.0f} {q['unit']}" for q in qs))
    md.append("")

    # ③ gotchas — split by intent (the calibrated, page-cited verbatim flags)
    src = final.get("gotcha_source") or ""
    note = (" · _calibrated set_" if src.startswith("sqlite")
            else " · _live first-pass, re-verify_" if src == "live" else "")
    md.append("## ③ Gotchas" + note)
    g = final["gotchas"]
    md.append("**🚦 Go / No-Go** — should we bid at all?")
    md += [_gotcha_line(x) for x in g.get("go_no_go", [])] or ["- _none flagged_"]
    md.append("")
    md.append("**💲 Pricing** — what drives the number?")
    md += [_gotcha_line(x) for x in g.get("pricing", [])] or ["- _none flagged_"]
    md.append("")

    # ④ competitive landscape — CI team's v3 schema: a single flat top-N ranking, no tiers/scores
    md.append("## ④ Competitive Landscape")
    if not comp:
        md.append("_No competitor-intel report matched this project (by county + state + date)._")
        return "\n".join(md)

    s = comp["summary"]
    mt = comp.get("_match", {})
    names = comp.get("competitors", [])
    stats_map = comp.get("stats", {})
    md.append(f"**Top {s.get('analyzed', 0)} likely competitors**")
    wt = comp.get("work_type") or ""
    cond = comp.get("condition") or ""
    if wt or cond:
        md.append(f"_Work type: {wt}{(' · ' + cond) if cond else ''}._")
    pits = comp.get("pits", {})
    if pits.get("public"):
        md.append(f"_Pit access: {pits['public']}._")
    md.append("")
    md.append(f"_Source: {comp['source_file']} · matched on {mt.get('basis')} "
              f"({mt.get('confidence')} confidence)._")

    # exports get the full per-competitor stats dives; chat stays compact (name + a one-line
    # state win-rate summary inline)
    for name in names:
        st = stats_map.get(name)
        lines = _stats_lines(st) if st else []
        if include_dives and lines:
            md.append(f"\n### {name}")
            for line in lines:
                md.append(f"- {line}")
        else:
            state_wr = ((st or {}).get("win_rate") or {}).get("state") if st else None
            tail = f" — win rate {_fmt_scoped(state_wr)}" if state_wr else ""
            md.append(f"- **{name}**{tail}")

    return "\n".join(md)


# --- exports ------------------------------------------------------------------------------------
# "🚦 "/"💲 " (with the trailing space) map to "", not just the bare emoji: both appear as
# "**🚦 Go / No-Go**" / "**💲 Pricing**" in render_markdown's output, and dropping only the emoji
# would leave "** Go / No-Go**" -- a space right after the opening "**", which CommonMark (and
# therefore pandoc) does not treat as a valid emphasis start, so it prints literal asterisks
# instead of bolding. Swallowing the space along with the emoji keeps the delimiter adjacent to
# the first real character.
_EMOJI_FOR_PDF = {"🚦 ": "", "💲 ": "", "🔴": "[H]", "🟡": "[M]", "🟢": "[L]", "▇": "#",
                  "①": "1.", "②": "2.", "③": "3.", "④": "4.", "·": "-", "—": "-", "…": "...",
                  "“": '"', "”": '"', "’": "'"}


def _sanitize_for_latex(md: str) -> str:
    for k, v in _EMOJI_FOR_PDF.items():
        md = md.replace(k, v)
    return md


def to_markdown(final: dict) -> str:
    return render_markdown(final)


def to_csv(final: dict) -> str:
    """A tidy long CSV (section, item, value, detail, page) — analysis-friendly, opens in Numbers."""
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["section", "item", "value", "detail", "page"])
    idn = final["identity"]
    w.writerow(["snapshot", "archetype", final["archetype"], "", ""])
    for k in ("location", "state", "county", "sp_number", "prevailing_wages", "traffic_level"):
        w.writerow(["snapshot", k, idn.get(k) or "", "", ""])
    for q in final["quantities"]:
        w.writerow(["quantity", q["label"], q["value"], q["unit"], ""])
    for side in ("go_no_go", "pricing"):
        for g in final["gotchas"].get(side, []):
            w.writerow([f"gotcha_{side}", g.get("code"), g.get("confidence") or "",
                        (g.get("evidence") or "").replace("\n", " "), g.get("page") or ""])
    comp = final.get("competitor")
    if comp:
        stats_map = comp.get("stats", {})
        for i, name in enumerate(comp["competitors"], start=1):
            st = stats_map.get(name) or {}
            state_wr = (st.get("win_rate") or {}).get("state")
            state_br = (st.get("bid_rate") or {}).get("state")
            w.writerow(["competitor", name, f"rank {i}",
                        _fmt_scoped(state_wr), _fmt_scoped(state_br)])
    return buf.getvalue()


def to_pdf(final: dict, out_path: str | Path) -> Path | None:
    """Render the markdown to PDF via pandoc + xelatex (no new deps; same toolchain as the source
    reports). Emoji/box-drawing are sanitized to LaTeX-safe text first. Returns the path, or None
    if pandoc fails (caller falls back to offering the markdown)."""
    out_path = Path(out_path)
    md = _sanitize_for_latex(render_markdown(final))
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8") as f:
        f.write(md)
        src = f.name
    try:
        subprocess.run(
            ["pandoc", src, "-o", str(out_path), "--pdf-engine=xelatex",
             "-V", "geometry:margin=0.8in", "-V", "fontsize=10pt"],
            check=True, capture_output=True, timeout=120)
        return out_path if out_path.exists() else None
    except Exception as e:                            # pandoc/LaTeX missing or a render error
        log.warning("to_pdf failed: %s", e)
        return None
    finally:
        Path(src).unlink(missing_ok=True)


# --- manual smoke test --------------------------------------------------------------------------
if __name__ == "__main__":
    import sys
    pid = sys.argv[1] if len(sys.argv) > 1 else "2025_DOUGLAS-CO-MN_SAP-021-600-023_NOBID"
    rep = assemble(plan_id=pid, bid_date="2025-08-21")
    print(render_markdown(rep))
    print("\n\n===== CSV =====\n")
    print(to_csv(rep))
