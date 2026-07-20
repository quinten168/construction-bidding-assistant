#!/usr/bin/env python3
"""
07_gotcha_prefilter.py  —  PHASE 2: keyword pre-filter → LLM gotcha judge → `gotchas` long table.

A cheap keyword gate in front of the expensive LLM gotcha judge. Per plan:

  full_markdown ─split on <!-- page N -->─► page texts
        │  Part A (zero API): scan each page for the 20 taxonomy trigger sets
        ▼
   {flag_type: [candidate pages]}  ── zero triggers anywhere ──► skip_entirely (NO LLM call)
        │  Part B: send ONLY the candidate-page excerpts to ONE Sonnet judge per plan
        ▼  judge confirms real-vs-boilerplate → {code, evidence, page, confidence}
        ▼  Part C: write one `gotchas` row per confirmed instance (flags.csv shape, idempotent),
           set plan_metrics.has_phasing, roll up gotcha_count + weighted gotcha_burden_tier, add cost.

WHY a pre-filter: most pages carry no gotcha, and a few plans carry none at all. The keyword scan is
free and recall-first (it over-fires on purpose); the LLM is the precision filter and only ever sees
the candidate pages, which keeps cost near Phase 1's ~$0.076/plan. A plan with zero triggers costs $0.

Scope = PHASE 2 ONLY. Does NOT wire into s3/s4 (Phase 3), does NOT compute messiness_score or
spatial_fragmentation. Reads plans from the DB; idempotent + resumable; recall-first pre-filter.

Run:
    cd 01_Summer_2026
    python3 pipelines/plan_reader/04_tools/07_gotcha_prefilter.py                 # Part A + recall + first 3 judge calls
    python3 pipelines/plan_reader/04_tools/07_gotcha_prefilter.py --continue       # judge the rest (after cost review)
    python3 pipelines/plan_reader/04_tools/07_gotcha_prefilter.py --prefilter-only # Part A + recall check, no API
"""
import os
import re
import sys
import csv
import json
import sqlite3
from pathlib import Path

TOOLS_DIR    = Path(__file__).resolve().parent
MODULE_ROOT  = TOOLS_DIR.parent                                  # .../plan_reader
PIPELINE_DIR = MODULE_ROOT / "01_pipeline"
sys.path.insert(0, str(PIPELINE_DIR))
import s3_extract as extract     # noqa: E402 — reuse call_json + MODEL (one Claude/JSON path; no API at import)

# --- paths -------------------------------------------------------------------
DB_PATH    = MODULE_ROOT / "csi_v2.db"
GOTCHA_CSV = MODULE_ROOT / "05_knowledge" / "gotcha_taxonomy.csv"   # the pre-filter's source of truth
FLAGS_CSV  = MODULE_ROOT / "02_outputs" / "flags.csv"              # the s4 recall benchmark (103 rows)

# --- config ------------------------------------------------------------------
# These three appear in nearly every contract's boilerplate, so keyword presence is NOT enough — the
# LLM must judge a real instance (an actual wage determination / DBE goal % / LD rate) vs boilerplate.
# (We never auto-emit on keyword anyway — every gotcha comes from the judge — but we also never skip a
# plan that has only these firing.)
ALWAYS_JUDGE = {"prevailing_wage", "dbe_goal", "liquidated_damages"}

MAX_JUDGE_CALLS   = 3          # STOP + report cost after this many LLM calls; --continue raises it
JUDGE_CHAR_BUDGET = 60_000     # cap total candidate-page text sent to the judge per plan
JUDGE_PER_PAGE_CAP = 8_000     # truncate any single huge (pooled CAD) candidate page
JUDGE_MAX_TOKENS  = 4096       # gotcha lists are short; candidate-page slicing keeps input small
PRICE_PER_MTOK_IN, PRICE_PER_MTOK_OUT = 3.0, 15.0   # Sonnet 4.6 list price (token counts are exact)

# weighted burden: decision_driver gotchas weigh 2x, pricing_input 1x. Cuts are PROVISIONAL — the script
# prints the weighted score per plan so T can calibrate against the 8 plans (see handoff).
BURDEN_CUTS = [(0, "None"), (4, "Low"), (9, "Medium"), (10 ** 9, "High")]   # score <= cut → tier

_PAGE_MARKER = re.compile(r"<!-- page (\d+) -->")


# --- taxonomy load (CSV = source of truth; it carries `relevance`, taxonomy.py does not) -------------
def load_taxonomy():
    """Return {gotcha_type: {family, relevance, definition, triggers:[...]}}. Trigger cells are
    `|`-delimited; phrases with ' / ' alternates ('Phase 1 / Phase 2', 'Memorandum of Agreement / MOA')
    are split into independent variants so each side matches on its own. Recall-first."""
    tax = {}
    for row in csv.DictReader(open(GOTCHA_CSV)):
        gtype = (row["gotcha_type"] or "").strip()
        if not gtype:
            continue
        variants = []
        for phrase in (row["triggers"] or "").split("|"):
            phrase = phrase.strip()
            if not phrase:
                continue
            # Split ' / ' alternates into separate matchable variants.
            variants.extend(p.strip() for p in phrase.split(" / ") if p.strip())
        tax[gtype] = {
            "family": (row["family"] or "").strip(),
            "relevance": (row["relevance"] or "").strip(),
            "definition": (row["definition"] or "").strip(),
            "triggers": variants,
        }
    return tax


def _norm(text):
    """Lowercase + collapse all whitespace to single spaces, so a trigger phrase matches even when the
    markdown wrapped it across lines/cells. Used for both the page text and the trigger phrase."""
    return re.sub(r"\s+", " ", (text or "").lower())


# --- Part A: the keyword pre-filter (zero API) ------------------------------------------------------
def pages_from_markdown(full_markdown):
    """{page_no: page_text} from the <!-- page N --> markers (same numbering s4 cited)."""
    parts = _PAGE_MARKER.split(full_markdown or "")
    out = {}
    for i in range(1, len(parts), 2):
        out[int(parts[i])] = parts[i + 1] if i + 1 < len(parts) else ""
    return out


def prefilter(full_markdown, tax):
    """Return ({flag_type: [candidate_page_nos]}, skip_entirely, page_texts).
    A trigger variant firing (substring, normalized) on page p makes p a candidate page for that type.
    Recall-first: over-firing is fine — the LLM is the precision filter; a missed page is the only failure."""
    page_texts = pages_from_markdown(full_markdown)
    norm_pages = {pno: _norm(txt) for pno, txt in page_texts.items()}
    candidates = {}
    for gtype, t in tax.items():
        variants = [_norm(v) for v in t["triggers"]]
        hit_pages = [pno for pno, ntxt in norm_pages.items() if any(v in ntxt for v in variants)]
        if hit_pages:
            candidates[gtype] = sorted(hit_pages)
    skip_entirely = len(candidates) == 0
    return candidates, skip_entirely, page_texts


# --- Part B: the LLM judge (only candidate pages) ---------------------------------------------------
def _taxonomy_block(tax):
    return "\n".join(f"- {code} — {t['definition']}" for code, t in tax.items())


GOTCHA_PROMPT = """You are reviewing candidate pages from a highway bid plan for cost/risk "gotchas".
These pages were keyword-flagged, so many are boilerplate — your job is to confirm which gotchas are
ACTUALLY, SPECIFICALLY present (a real project instance, not generic contract boilerplate).

From the TAXONOMY below, return a JSON array; each item:
  {{"code": <exact taxonomy code>, "evidence": <short quote/paraphrase>, "page": <the N from [page N]>,
    "confidence": "high"|"medium"|"low"}}
Only include a gotcha the pages actually support with a specific instance. For prevailing_wage / dbe_goal
/ liquidated_damages, include ONLY a real determination/goal%/rate — NOT generic Davis-Bacon or
good-faith boilerplate. Use the exact codes. Return [] if none.

TAXONOMY (code — definition):
{taxonomy}

Candidate pages (each tagged [page N]):
{context}

Return ONLY the JSON array."""


def build_judge_context(candidates, page_texts):
    """Gather the union of candidate pages, strongest first (a page firing more distinct flag_types is
    more gotcha-dense), within the char budget, then back into reading order. Returns (context, pages)."""
    fires_per_page = {}
    for pages in candidates.values():
        for p in pages:
            fires_per_page[p] = fires_per_page.get(p, 0) + 1
    ranked = sorted(fires_per_page, key=lambda p: (-fires_per_page[p], p))
    chosen, total = [], 0
    for p in ranked:
        txt = (page_texts.get(p) or "")[:JUDGE_PER_PAGE_CAP]
        if chosen and total + len(txt) > JUDGE_CHAR_BUDGET:
            continue
        chosen.append(p)
        total += len(txt)
    chosen.sort()
    context = "\n\n".join(f"[page {p}]\n{(page_texts.get(p) or '')[:JUDGE_PER_PAGE_CAP]}" for p in chosen)
    return context, chosen


def judge(candidates, page_texts, tax):
    """One Claude call over the candidate pages → (confirmed_gotchas, usage). Each confirmed gotcha is
    {flag_type, family, evidence, page, confidence}, deduped to the highest-confidence instance per type."""
    context, _ = build_judge_context(candidates, page_texts)
    api_key = os.environ.get("ANTHROPIC_API_KEY") or extract.lib.ENV_PATH.read_text().split("'")[1]
    import anthropic
    client = anthropic.Anthropic(api_key=api_key)
    resp = client.messages.create(
        model=extract.MODEL, max_tokens=JUDGE_MAX_TOKENS,
        messages=[{"role": "user", "content": GOTCHA_PROMPT.format(
            taxonomy=_taxonomy_block(tax), context=context)}],
    )
    raw = resp.content[0].text.strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    try:
        data = json.loads(raw)
        data = data if isinstance(data, list) else []
    except json.JSONDecodeError:
        data = []

    rank = {"high": 3, "medium": 2, "low": 1, "": 0}
    by_code = {}
    for g in data:
        code = g.get("code") if isinstance(g, dict) else None
        if code not in tax:
            continue
        try:
            page = int(g.get("page")) if g.get("page") not in (None, "", "null") else None
        except (ValueError, TypeError):
            page = None
        conf = str(g.get("confidence") or "").lower()
        conf = conf if conf in ("high", "medium", "low") else ""
        item = {"flag_type": code, "family": tax[code]["family"],
                "evidence": str(g.get("evidence", ""))[:300], "page": page, "confidence": conf}
        prev = by_code.get(code)
        if prev is None or rank[conf] > rank[prev["confidence"]]:
            by_code[code] = item
    return list(by_code.values()), resp.usage


# --- Part C: writes (idempotent, flags.csv shape) ---------------------------------------------------
def section_for_page(conn, plan_id, page):
    """Best-effort section label for a gotcha's page: the sections row whose [page_start, page_end]
    contains it. section_type is NULL until Jay normalizes, so fall back to raw_heading, else NULL."""
    if page is None:
        return None
    row = conn.execute(
        "SELECT section_type, raw_heading FROM sections WHERE plan_id=? AND page_start<=? AND page_end>=? "
        "ORDER BY page_start DESC LIMIT 1", (plan_id, page, page)).fetchone()
    if not row:
        return None
    return row[0] or row[1] or None


def burden_tier(score):
    for cut, tier in BURDEN_CUTS:
        if score <= cut:
            return tier
    return "High"


def write_gotchas(conn, plan_id, source_file, gotchas, tax, cost):
    """Write the confirmed gotchas (idempotent: replace this plan's rows) + roll up plan_metrics."""
    conn.execute("DELETE FROM gotchas WHERE plan_id=?", (plan_id,))
    for g in gotchas:
        conn.execute(
            "INSERT INTO gotchas (plan_id, source_file, section, flag_type, family, evidence, page, confidence) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (plan_id, source_file, section_for_page(conn, plan_id, g["page"]), g["flag_type"],
             g["family"], g["evidence"], g["page"], g["confidence"]))

    has_phasing = 1 if any(g["flag_type"] == "phasing_staging" for g in gotchas) else 0
    weighted = sum(2 if tax.get(g["flag_type"], {}).get("relevance") == "decision_driver" else 1
                   for g in gotchas)
    tier = burden_tier(weighted)
    # extraction_cost ACCUMULATES across phases — add, don't clobber Phase 1's fallback cost.
    conn.execute(
        "UPDATE plan_metrics SET has_phasing=?, gotcha_count=?, gotcha_burden_tier=?, "
        "extraction_cost = COALESCE(extraction_cost, 0) + ? WHERE plan_id=?",
        (has_phasing, len(gotchas), tier, cost, plan_id))
    conn.commit()
    return has_phasing, weighted, tier


# --- recall validation (Part A vs flags.csv, zero API) ----------------------------------------------
def validate_recall(candidate_maps, tax):
    """For every gotcha-taxonomy instance in flags.csv, confirm the pre-filter marked its (plan_id, page)
    as a candidate page for that flag_type. Recall must be 100% — a miss means widen the trigger set in
    the CSV (data edit), not a code patch. Returns (recall, misses)."""
    if not FLAGS_CSV.exists():
        print("  ! flags.csv not found — cannot validate recall")
        return None, []
    rows = [r for r in csv.DictReader(open(FLAGS_CSV)) if r["flag_type"] in tax]
    misses = []
    for r in rows:
        pid, ftype, page = r["plan_id"], r["flag_type"], (r.get("page") or "").strip()
        cand = candidate_maps.get(pid, {}).get(ftype, [])
        if not page:
            continue
        if int(page) not in cand:
            misses.append((pid, ftype, page))
    hit = len(rows) - len(misses)
    recall = hit / len(rows) if rows else 1.0
    return recall, misses


def usd(usage):
    return round(usage.input_tokens / 1e6 * PRICE_PER_MTOK_IN
                + usage.output_tokens / 1e6 * PRICE_PER_MTOK_OUT, 4)


# --- main --------------------------------------------------------------------
def main():
    prefilter_only = "--prefilter-only" in sys.argv
    max_calls = 10 ** 9 if "--continue" in sys.argv else MAX_JUDGE_CALLS
    force = "--force" in sys.argv

    tax = load_taxonomy()
    conn = sqlite3.connect(DB_PATH)
    plans = conn.execute(
        "SELECT plan_id, source_file, full_markdown FROM plans WHERE convert_status='converted'"
    ).fetchall()

    # ---- Part A: pre-filter every plan (free) + validate recall before spending a cent ----
    print("=== Part A: keyword pre-filter (zero API) ===")
    candidate_maps, skips = {}, []
    page_text_cache = {}
    for plan_id, _src, md in plans:
        cands, skip, page_texts = prefilter(md, tax)
        candidate_maps[plan_id] = cands
        page_text_cache[plan_id] = page_texts
        if skip:
            skips.append(plan_id)
        n_pages = sum(len(p) for p in cands.values())
        print(f"  {plan_id:42s} types_fired={len(cands):2d}  candidate_pages(by type)={n_pages:3d}"
              f"{'  [skip_entirely]' if skip else ''}")

    recall, misses = validate_recall(candidate_maps, tax)
    print(f"\n  Pre-filter recall vs flags.csv gotcha rows: "
          f"{recall*100:.1f}%  ({'PASS' if recall == 1.0 else 'FAIL'})")
    if misses:
        print("  MISSES (widen these triggers in gotcha_taxonomy.csv, then re-run — do NOT patch code):")
        for pid, ftype, page in misses:
            print(f"    {pid}  {ftype}  p.{page}")
    print(f"  skip_entirely plans: {skips or '(none)'}")

    if prefilter_only or (recall is not None and recall < 1.0):
        if recall is not None and recall < 1.0:
            print("\n>>> Recall < 100% — STOPPING before any LLM spend. Widen triggers + re-run. <<<")
        conn.close()
        return

    # ---- Part B/C: judge candidate pages (skip_entirely → no call; resumable; cost-checkpointed) ----
    print("\n=== Part B/C: LLM judge on candidate pages (measured) ===")
    cost_log, api_calls = [], 0
    for plan_id, source_file, md in plans:
        # resumable: a plan already judged (gotcha_count set) is skipped — no dup rows, no re-spend.
        already = conn.execute("SELECT gotcha_count FROM plan_metrics WHERE plan_id=?",
                               (plan_id,)).fetchone()
        if already and already[0] is not None and not force:
            continue

        cands = candidate_maps[plan_id]
        if not cands:                                   # skip_entirely → zero API spend
            conn.execute("UPDATE plan_metrics SET has_phasing=0, gotcha_count=0, gotcha_burden_tier=? "
                         "WHERE plan_id=?", ("None", plan_id))
            conn.commit()
            print(f"  · {plan_id:42s} skip_entirely — 0 gotchas, $0")
            continue

        if api_calls >= max_calls:
            print(f"  ⏸ {plan_id:42s} HELD — hit the {max_calls}-call cost checkpoint (re-run --continue)")
            continue

        gotchas, usage = judge(cands, page_text_cache[plan_id], tax)
        api_calls += 1
        cost = usd(usage)
        has_phasing, weighted, tier = write_gotchas(conn, plan_id, source_file, gotchas, tax, cost)
        cost_log.append({"plan_id": plan_id, "in": usage.input_tokens, "out": usage.output_tokens,
                         "cost": cost, "n": len(gotchas), "weighted": weighted, "tier": tier})
        print(f"  ✓ {plan_id:42s} gotchas={len(gotchas):2d} burden={tier:6s}(w={weighted:2d}) "
              f"phasing={has_phasing} tokens={usage.input_tokens:,}/{usage.output_tokens:,} ${cost:.4f}")

    # ---- cost checkpoint ----
    print("\n-- Cost checkpoint --")
    if cost_log:
        tot = sum(r["cost"] for r in cost_log)
        avg = tot / len(cost_log)
        for r in cost_log:
            print(f"    {r['plan_id']:42s} ${r['cost']:.4f}  ({r['in']:,}in/{r['out']:,}out, {r['n']} gotchas)")
        print(f"  judge calls: {api_calls}  total ${tot:.4f}  avg ${avg:.4f}/plan")
        print(f"  projection @ ${avg:.4f}/plan: 100-plan corpus ≈ ${avg*100:.2f} "
              f"(Sonnet 4.6 @ ${PRICE_PER_MTOK_IN}/${PRICE_PER_MTOK_OUT} per MTok)")
        held = conn.execute("SELECT COUNT(*) FROM plan_metrics WHERE gotcha_count IS NULL").fetchone()[0]
        if held and max_calls != 10 ** 9:
            print(f"  >>> {held} plan(s) HELD — REVIEW COST, then re-run with --continue. <<<")
    else:
        print("  No paid judge calls this run.")
    conn.close()


if __name__ == "__main__":
    main()
