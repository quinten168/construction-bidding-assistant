#!/usr/bin/env python3
"""
07_gotcha_extract.py  —  PHASE 2a: recall-first gotcha extraction (judge ALL prose pages).

This is the v2 method (replaces the deleted keyword-only "prefilter"). The mission is RECALL,
not cost: at 11-50 proposals we are building the knowledge base, so we do NOT do candidate
selection. We judge EVERY non-drawing prose page against the FULL 20-type taxonomy (pool, never
route), batched so a long plan never gets silently truncated.

Pipeline per plan (all paths/conventions reused from 04_tools/05_parse_bid_schedule.py):
  1. split full_markdown on "<!-- page N -->"  → drop drawing/CAD pages (lib.is_drawing_page) +
     known boilerplate fingerprints → candidate_pages = EVERY remaining PROSE page.
  2. carry a governing-heading map forward across pages (a section spans many pages) so each
     page can be tagged inline "[page N - under: <heading>]" → the judge can answer section_raw.
  3. partition candidate pages into ~40k-char batches; ONE Claude call per batch over the full
     20-type taxonomy; union the returned gotchas across batches.
  4. DEDUP on (plan_id, flag_type, page), keep highest confidence.
  5. keyword scan = TELEMETRY ONLY (trigger-growth log + skip_entirely signal) — never selects pages.
  6. write the deduped gotchas; roll up gotcha_count / go_no_go / pricing; set has_phasing;
     log gotcha_extraction_cost in its OWN column (never folded into shared extraction_cost).

Idempotent: DELETE FROM gotchas WHERE plan_id=? then insert (a plain re-run won't duplicate).

Run (3-plan HR12 checkpoint — the default scope when --checkpoint is passed):
    cd 01_Summer_2026
    python3 pipelines/plan_reader/04_tools/07_gotcha_extract.py --checkpoint
    python3 pipelines/plan_reader/04_tools/07_gotcha_extract.py --plan 2023_DUNN-CO-ND_CP-13_WON
    python3 pipelines/plan_reader/04_tools/07_gotcha_extract.py            # ALL converted plans
"""
import os
import re
import csv
import sys
import json
import sqlite3
from pathlib import Path

# --- module paths (reuse the pipeline's single-source-of-paths lib) ----------
TOOLS_DIR     = Path(__file__).resolve().parent
MODULE_ROOT   = TOOLS_DIR.parent                                 # .../plan_reader
PIPELINE_DIR  = MODULE_ROOT / "01_pipeline"
KNOWLEDGE_DIR = MODULE_ROOT / "05_knowledge"
sys.path.insert(0, str(PIPELINE_DIR))
import lib                              # noqa: E402  — paths, is_drawing_page, boilerplate, call_json key
import s3_extract as extract           # noqa: E402  — reuse call_json (one Claude/JSON path) + usage

# --- paths -------------------------------------------------------------------
DB_PATH      = MODULE_ROOT / "csi_v2.db"
TAXONOMY_CSV = KNOWLEDGE_DIR / "gotcha_taxonomy.csv"
OUT_DIR      = MODULE_ROOT / "02_outputs"

# --- the 3-plan HR12 checkpoint set (the only plans --checkpoint judges) ------
CHECKPOINT_PLANS = [
    "2023_DUNN-CO-ND_CP-13_WON",
    "2023_BROOKINGS-CO-SD_SURFACING_LOST",
    "2023_OTTER-TAIL-CO-MN_CP-4069-304_LOST",
]
# Known keyword-only misses that MUST survive the prose filter + close (smoke test, NOT a 100% gate).
KNOWN_MISSES = {
    "2023_DUNN-CO-ND_CP-13_WON":            [115],
    "2023_BROOKINGS-CO-SD_SURFACING_LOST":  [146, 152],
}

# --- LLM config (Sonnet 4.6, same as s4) -------------------------------------
MODEL = "claude-sonnet-4-6"
# Sonnet 4.6 list price per MILLION tokens — turns measured token counts into a $ estimate.
PRICE_PER_MTOK_IN  = 3.0
PRICE_PER_MTOK_OUT = 15.0
BATCH_CHAR_BUDGET  = 40_000     # ~10k tokens of page text per judge call (NEVER truncate — batch instead)
MAX_TOKENS_OUT     = 4096       # the judge can return many gotchas across a 40k batch

_PAGE_MARKER = re.compile(r"<!--\s*page\s+(\d+)\s*-->", re.I)
_CONF_RANK   = {"high": 3, "medium": 2, "low": 1, "": 0}


# --- taxonomy load (the 20 ACTIVE types; skip '#'-commented candidate rows) ---
def load_taxonomy():
    """Read gotcha_taxonomy.csv → {code: {family, decision_class, definition, triggers[list]}}.
    Skips '#'-prefixed candidate rows (tero/railroad/underground are active=0, recorded only)."""
    types = {}
    with open(TAXONOMY_CSV, newline="") as f:
        for row in csv.DictReader(f):
            code = (row.get("gotcha_type") or "").strip()
            if not code or code.startswith("#"):       # candidate/comment row — not judged
                continue
            triggers = [t.strip() for t in (row.get("triggers") or "").split("|") if t.strip()]
            types[code] = {
                "family": (row.get("family") or "").strip(),
                "decision_class": (row.get("decision_class") or "").strip(),
                "definition": (row.get("definition") or "").strip(),
                "triggers": triggers,
            }
    return types


# --- the judge prompt — SPLIT for prompt caching --------------------------------
# The SYSTEM half (instructions + the 20-type taxonomy) is byte-identical on every judge call of a run,
# so it goes behind a cache_control breakpoint and bills ~0.1x after the first write. The USER half (the
# per-batch prose pages) changes every call and stays uncached. NB: the static prefix must clear the
# model's minimum cacheable size (~2048 tokens on Sonnet 4.6) or caching silently no-ops — verified via
# usage.cache_read_input_tokens at the checkpoint.
GOTCHA_SYSTEM = """You are reviewing pages from a highway-construction bid plan for cost/risk "gotchas".
A gotcha is a plan requirement that raises a contractor's cost or risk and is easy to miss on a fast read.

From the TAXONOMY below, return a JSON array of the gotchas ACTUALLY PRESENT in the pages the user sends.
Judge every page against ALL 20 types (do not assume a type only lives in one kind of section).

EMIT AT MOST ONE OBJECT PER taxonomy code for this whole batch — collapse, do NOT repeat per page. A
document-wide requirement (e.g. QC inspection, traffic control, incidental scope) that recurs on many
pages is ONE gotcha: return it ONCE, list ALL the pages it appears on in "pages", and give the SINGLE
strongest evidence span. Do NOT return one object per page — that is the #1 mistake to avoid.

For each gotcha:
  {{"code": <exact taxonomy code>,
    "pages": [<every page number where this gotcha appears, from the "[page N - under: ...]" tags>],
    "primary_page": <the ONE page the evidence_quote is copied from>,
    "evidence_quote": <ONE short, contiguous, EXACT span copied from primary_page — a SINGLE sentence OR a
        SINGLE table row, <=160 characters. It MUST appear verbatim in that page: same words, same NAMES,
        same NUMBERS, same punctuation. Do NOT join two sentences, do NOT use "...", do NOT substitute or
        shorten any name/value, do NOT add words of your own. If the requirement spans several sentences,
        quote ONLY the single most decisive one. If the evidence is a table, copy EXACTLY ONE row.
        If you believe this gotcha IS present but you CANNOT find an exact supporting span, set
        evidence_quote to "" (empty) and confidence to "low" — NEVER invent or paraphrase a quote.>,
    "rationale": <<=180 chars: YOUR plain-language explanation of WHY this is a gotcha / what it costs.
        This is the ONLY place you may summarize or interpret. NEVER put interpretation in evidence_quote.>,
    "section_raw": <the verbatim governing heading the quote sits directly UNDER (the "under:" part of the
                    primary_page's tag), or null if none>,
    "confidence": "high"|"medium"|"low"}}

Rules:
- evidence_quote is a VERBATIM COPY, not a description. Only the rationale may summarize or interpret.
- Only include a gotcha the pages actually support. Do not invent gotchas. Use the EXACT codes. [] if none.
- One object per code. Merge recurrences into the "pages" list; never split the same code across objects.
- For prevailing_wage / dbe_goal / liquidated_damages: judge REAL-vs-boilerplate. A generic Davis-Bacon
  reference or a "No DBE Goal" form is NOT a gotcha; an actual wage determination / a real DBE goal % IS.
- section_raw is the heading the quote is under, NOT a neighboring provision on the same page.

TAXONOMY (code - definition):
{taxonomy}"""

GOTCHA_USER = """Pages (each tagged "[page N - under: <governing heading>]"):
{context}

Return ONLY the JSON array."""


def _taxonomy_block(types):
    return "\n".join(f"- {code} - {t['definition']}" for code, t in types.items())


def _int(v):
    try:
        return int(v) if v not in (None, "", "null") else None
    except (ValueError, TypeError):
        return None


def _conf(v):
    v = str(v or "").lower()
    return v if v in _CONF_RANK else ""


# --- candidate pages = ALL prose pages (zero API, no candidate selection) ------
def split_pages(full_markdown):
    """Split full_markdown into [(page_no, text), ...] on the '<!-- page N -->' markers. Text before
    the first marker (rare front matter) is attached to page None and ignored as a candidate."""
    parts = _PAGE_MARKER.split(full_markdown or "")
    pages = []
    # parts = [pre, n1, text1, n2, text2, ...]
    for i in range(1, len(parts), 2):
        pno = int(parts[i])
        txt = parts[i + 1] if i + 1 < len(parts) else ""
        pages.append((pno, txt))
    return pages


def governing_headings(pages):
    """{page_no: heading} — carry the last-seen section heading forward across pages (a section
    spans many pages). Uses the SAME header detector ingest uses (lib.detect_section) so the
    'under:' tag agrees with the section spine. A page with no new header inherits the prior one."""
    heads, current = {}, None
    for pno, txt in pages:
        sec = lib.detect_section(txt)
        if sec:
            current = sec
        heads[pno] = current
    return heads


def prose_pages(pages):
    """Drop drawing/CAD pages (lib.is_drawing_page) and known-boilerplate-only pages; return the
    remaining PROSE pages as candidates. Boilerplate stripping mirrors ingest (gotcha-guarded:
    strip_boilerplate_paragraphs only removes fingerprinted paragraphs, never a whole gotcha page).
    Returns (candidates[(pno,text)], dropped_drawing[pno list])."""
    fingerprints = lib.load_boilerplate_fingerprints()
    candidates, dropped = [], []
    for pno, txt in pages:
        if lib.is_drawing_page(txt):
            dropped.append(pno)
            continue
        kept, _ = lib.strip_boilerplate_paragraphs(txt, fingerprints)
        candidates.append((pno, kept))
    return candidates, dropped


def batch_pages(candidates, headings):
    """Partition candidate pages into <=BATCH_CHAR_BUDGET-char batches, each page rendered with its
    governing-heading tag inline so section_raw is answerable. NEVER truncate a page; if a single
    page exceeds the budget it becomes its own batch. Returns list[str] (one prompt context block)."""
    batches, cur, cur_len = [], [], 0
    for pno, txt in candidates:
        head = headings.get(pno) or "(no section header)"
        block = f"[page {pno} - under: {head}]\n{txt}"
        if cur and cur_len + len(block) > BATCH_CHAR_BUDGET:
            batches.append("\n\n".join(cur))
            cur, cur_len = [], 0
        cur.append(block)
        cur_len += len(block)
    if cur:
        batches.append("\n\n".join(cur))
    return batches


# --- request building (shared by the synchronous + Batches API paths) ---------
def _system_blocks(taxonomy_block):
    """The static system half, behind a cache_control breakpoint so it bills ~0.1x after the first write."""
    return [{
        "type": "text",
        "text": GOTCHA_SYSTEM.format(taxonomy=taxonomy_block),
        "cache_control": {"type": "ephemeral"},
    }]

def _judge_params(taxonomy_block, context):
    """The messages.create kwargs for one batch — identical shape for a live call or a batch request."""
    return dict(
        model=MODEL, max_tokens=MAX_TOKENS_OUT,
        system=_system_blocks(taxonomy_block),
        messages=[{"role": "user", "content": GOTCHA_USER.format(context=context)}],
    )

def _parse_judge_text(text):
    """Strip ```json fences and parse the judge's reply into a list (empty list on any parse failure)."""
    raw = (text or "").strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    try:
        data = json.loads(raw)
        return data if isinstance(data, list) else []
    except json.JSONDecodeError:
        return []


# --- the judge call (one per batch; returns gotchas + token usage) ------------
def call_judge(taxonomy_block, context):
    """One synchronous Claude call over a batch → (list_of_gotcha_dicts, usage). Uses the cached
    system prefix (s3 client/key plumbing) and captures usage so we can report cost + cache hits."""
    import anthropic
    client = anthropic.Anthropic(api_key=extract.API_KEY)
    resp = client.messages.create(**_judge_params(taxonomy_block, context))
    return _parse_judge_text(resp.content[0].text if resp.content else ""), resp.usage


def _int_list(v):
    """Coerce a JSON 'pages' value into a sorted unique list of ints (tolerates a scalar or None)."""
    if v is None:
        return []
    if not isinstance(v, list):
        v = [v]
    out = {p for p in (_int(x) for x in v) if p is not None}
    return sorted(out)


def _new_usage_totals():
    return {"in": 0, "out": 0, "cache_read": 0, "cache_creation": 0, "calls": 0}

def _accumulate_usage(tot, usage):
    """Add one response's usage into the running totals (cache fields default to 0 when caching is off)."""
    tot["in"]  += getattr(usage, "input_tokens", 0) or 0
    tot["out"] += getattr(usage, "output_tokens", 0) or 0
    tot["cache_read"]     += getattr(usage, "cache_read_input_tokens", 0) or 0
    tot["cache_creation"] += getattr(usage, "cache_creation_input_tokens", 0) or 0
    tot["calls"] += 1


def collapse_by_code(raw_gotchas, valid):
    """COLLAPSE grain = (flag_type) for one plan. Merge page lists across batches; the winning row's
    evidence/section/primary_page is the highest-confidence one (ties → the one spanning more pages).
    This is the cost+storage fix: a document-wide requirement is ONE row with a page list, not one/page."""
    by_code = {}
    for g in raw_gotchas:
        if not (isinstance(g, dict) and g.get("code") in valid):
            continue
        code = g["code"]
        conf = _conf(g.get("confidence"))
        pages = _int_list(g.get("pages"))
        primary = _int(g.get("primary_page"))
        if primary is None and pages:
            primary = pages[0]
        # back-compat: an older single-"page" response still contributes its page
        if not pages:
            p1 = _int(g.get("page"))
            if p1 is not None:
                pages = [p1]
                primary = primary or p1
        cand = {
            "code": code, "confidence": conf, "pages": pages, "primary_page": primary,
            "evidence_quote": str(g.get("evidence_quote", g.get("evidence", "")))[:400],
            "rationale": str(g.get("rationale", ""))[:400],
            "section_raw": (str(g.get("section_raw")).strip() or None) if g.get("section_raw") else None,
        }
        prev = by_code.get(code)
        if prev is None:
            by_code[code] = cand
        else:
            merged_pages = sorted(set(prev["pages"]) | set(cand["pages"]))
            better = cand if (_CONF_RANK[conf] > _CONF_RANK[prev["confidence"]]) else prev
            better = dict(better)
            better["pages"] = merged_pages
            by_code[code] = better
    return list(by_code.values())


# --- the VERBATIM GATE: snap the model's quote to an exact span on the cited page ---------------
# The model only LOCATES the evidence (it may paraphrase, over-quote, or point at the wrong page);
# our code GUARANTEES verbatim by slicing the stored span from the actual page text. This is the
# HR12-style gate so non-verbatim evidence can never silently ship (it failed on messy plans without it).
_GATE_DASHES = {"‐", "‑", "‒", "–", "—", "―", "−"}
def _ascii_g(s):
    s = s or ""
    for d in _GATE_DASHES:
        s = s.replace(d, "-")
    return s.replace("‘", "'").replace("’", "'").replace("“", '"').replace("”", '"')

def _gnorm(s):
    """Match-normalize: neutralize OUR converter noise (markdown bold/italic/pipes/<br>) + unicode
    dashes/quotes, collapse whitespace, lowercase — so a faithful copy isn't failed on artifacts while
    any real word/name/number change still breaks the match."""
    return re.sub(r"\s+", " ", re.sub(r"[|*~`_]|<br>", " ", _ascii_g(s).lower())).strip()

GATE_COVERAGE = 0.60   # >=60% of the model's quote-words recovered as ONE verbatim span → auto-accept

def snap_to_page(quote, page_text):
    """Longest contiguous word-run of `quote` that appears verbatim ANYWHERE in page_text, recovered in
    the page's ORIGINAL casing/punctuation. Returns (span, coverage). The span is sliced from the PAGE,
    so it is verbatim by construction; coverage = matched_words / quote_words drives evidence_status."""
    words = _gnorm(quote).split()
    if not words:
        return "", 0.0
    hay, hay_n = _ascii_g(page_text), _gnorm(page_text)
    best_i = best_len = 0
    for i in range(len(words)):
        if words[i] not in hay_n:
            continue
        phrase, k = words[i], i + 1
        while k < len(words) and (phrase + " " + words[k]) in hay_n:
            phrase += " " + words[k]; k += 1
        if (k - i) > best_len:
            best_len, best_i = k - i, i
    if best_len == 0:
        return "", 0.0
    pat = r"[\s|*~`_]*".join(re.escape(w) for w in words[best_i:best_i + best_len])
    m = re.search(pat, hay, re.I)
    span = re.sub(r"\s+", " ", m.group(0)).strip() if m else " ".join(words[best_i:best_i + best_len])
    return span, best_len / len(words)

def _clean_span(s):
    """Strip OUR converter's markdown formatting from a stored span (the words/numbers are the plan's;
    the **bold**/_italic_/~~strike~~/`code`/<br> and table pipes are pymupdf4llm artifacts) so the quote
    reads cleanly in a client doc. Keeps a readable ' | ' between table cells."""
    s = re.sub(r"<br>", " ", s or "")
    s = re.sub(r"[*~`]+", "", s)                                   # bold / italic / strike / code
    s = re.sub(r"(?<![A-Za-z0-9])_+|_+(?![A-Za-z0-9])", "", s)     # markdown underscores (not in-word)
    s = re.sub(r"\s*\|\s*", " | ", s)                             # table cell separators → readable
    return re.sub(r"\s+", " ", s).strip(" |")

def apply_verbatim_gate(deduped, candidates):
    """Set, per gotcha: evidence (the exact page span we STORE), evidence_raw (the model's original
    quote, for audit), and evidence_status:
      verbatim    — snapped span covers >=60% of the model's quote (auto-accept)
      partial     — a real but short span (model over-quoted) → human review
      unverified  — nothing on the page matched the quote (wrong page / fabricated) → human review
      no_evidence — the MODEL itself returned no quote (its own 'I can't substantiate this')
    Page text = exactly what the model was shown (boilerplate-stripped candidate pages)."""
    page_text = {pno: txt for pno, txt in candidates}
    all_text = "\n\n".join(txt for _, txt in candidates)
    for g in deduped:
        raw = (g.get("evidence_quote") or "").strip()
        g["evidence_raw"] = raw
        g["rationale"] = (g.get("rationale") or "").strip()
        if not raw:
            g["evidence"], g["evidence_status"] = "", "no_evidence"
            continue
        span, cov = snap_to_page(raw, page_text.get(g.get("primary_page"), "") or all_text)
        if cov == 0:                                   # the cited page failed — try the whole doc
            span, cov = snap_to_page(raw, all_text)
        if cov >= GATE_COVERAGE:
            g["evidence"], g["evidence_status"] = _clean_span(span), "verbatim"
        elif cov > 0:
            g["evidence"], g["evidence_status"] = _clean_span(span), "partial"
        else:
            g["evidence"], g["evidence_status"] = "", "unverified"
    return deduped


def judge_plan(taxonomy, batches):
    """SYNCHRONOUS path: judge every batch live, union the raw gotchas, then collapse to one row per
    flag_type. Returns (collapsed_rows, usage_totals)."""
    tax_block = _taxonomy_block(taxonomy)
    valid = set(taxonomy)
    raw_all = []
    tot = _new_usage_totals()
    for ctx in batches:
        data, usage = call_judge(tax_block, ctx)
        _accumulate_usage(tot, usage)
        raw_all.extend(data or [])
    return collapse_by_code(raw_all, valid), tot


# --- keyword scan = TELEMETRY ONLY (does NOT select candidate pages) ----------
def _trigger_regexes(taxonomy):
    """Compile per-type trigger regexes, splitting '/'-alternates so each side matches
    ('Phase 1 / Phase 2', '.../ NLEB', '.../ MOA')."""
    out = {}
    for code, t in taxonomy.items():
        pats = []
        for trig in t["triggers"]:
            for side in re.split(r"\s*/\s*", trig):
                side = side.strip()
                if side:
                    pats.append(re.escape(side))
        out[code] = re.compile("|".join(pats), re.I) if pats else re.compile(r"(?!x)x")
    return out


def keyword_telemetry(taxonomy, candidates, deduped):
    """Build the trigger-growth log: per type, which trigger phrases fired on any candidate page, and
    (the valuable signal) which CONFIRMED gotchas had NO trigger fire on their page. Returns a dict +
    a skip_entirely flag (no trigger fired anywhere). PURE telemetry — never filters pages."""
    rx = _trigger_regexes(taxonomy)
    page_text = {pno: txt for pno, txt in candidates}
    fired_any = False
    fired_by_type = {}
    for code, r in rx.items():
        hits = [pno for pno, txt in candidates if r.search(txt or "")]
        if hits:
            fired_any = True
        fired_by_type[code] = hits

    # which confirmed gotchas sit on a page where their OWN trigger did NOT fire (keyword blind spots).
    # Collapsed grain: check the primary page (the strongest-evidence page) for the trigger.
    no_trigger = []
    for g in deduped:
        code = g["code"]
        pno = g.get("primary_page") if g.get("primary_page") is not None else (
            (g.get("pages") or [None])[0])
        txt = page_text.get(pno, "")
        if not rx[code].search(txt or ""):
            no_trigger.append({"code": code, "page": pno, "evidence": g["evidence"][:120]})
    return {"fired_by_type": fired_by_type, "no_trigger_gotchas": no_trigger,
            "skip_entirely": not fired_any}


# --- DB writes (idempotent) --------------------------------------------------
def ensure_schema(conn):
    """Make sure the gotchas table + the plan_metrics rollup columns exist (additive, idempotent)."""
    conn.execute("""CREATE TABLE IF NOT EXISTS gotchas (
        plan_id TEXT, source_file TEXT, section TEXT, flag_type TEXT, family TEXT,
        decision_class TEXT, evidence TEXT, page INTEGER, confidence TEXT)""")
    have = {r[1] for r in conn.execute("PRAGMA table_info(gotchas)")}
    # pages = comma-joined page list (collapsed grain); page = the primary/strongest page (back-compat);
    # page_count = how many pages this one requirement spans (the duplication we used to over-store).
    # rationale = the model's 'why it matters' (interpretation, split out of evidence);
    # evidence_raw = the model's original pre-snap quote (audit); evidence_status = the verbatim-gate verdict
    # (verbatim | partial | unverified | no_evidence). `evidence` now stores the SNAPPED VERBATIM span.
    for col, typ in (("decision_class", "TEXT"), ("pages", "TEXT"), ("page_count", "INTEGER"),
                     ("rationale", "TEXT"), ("evidence_raw", "TEXT"), ("evidence_status", "TEXT")):
        if col not in have:
            conn.execute(f"ALTER TABLE gotchas ADD COLUMN {col} {typ}")
    pm = {r[1] for r in conn.execute("PRAGMA table_info(plan_metrics)")}
    for col, typ in (("gotcha_count", "INTEGER"), ("gotcha_go_no_go_count", "INTEGER"),
                     ("gotcha_pricing_count", "INTEGER"), ("gotcha_burden_tier", "TEXT"),
                     ("has_phasing", "INTEGER"), ("gotcha_extraction_cost", "REAL")):
        if col not in pm:
            conn.execute(f"ALTER TABLE plan_metrics ADD COLUMN {col} {typ}")
    conn.commit()


def reset_clean_slate(conn, plan_ids):
    """Clean slate for the given plans: clear their gotchas rows AND reset the gotcha rollup columns
    so a re-run rebuilds from zero (otherwise counts/tiers go stale, cost double-counts)."""
    for pid in plan_ids:
        conn.execute("DELETE FROM gotchas WHERE plan_id=?", (pid,))
        conn.execute("""UPDATE plan_metrics SET gotcha_count=NULL, gotcha_go_no_go_count=NULL,
                        gotcha_pricing_count=NULL, gotcha_burden_tier=NULL, has_phasing=NULL,
                        gotcha_extraction_cost=NULL WHERE plan_id=?""", (pid,))
    conn.commit()


def write_gotchas(conn, plan_id, source_file, taxonomy, deduped, cost):
    """Write the DEDUPED gotcha set + roll up the plan_metrics columns (per-plan transaction)."""
    conn.execute("DELETE FROM gotchas WHERE plan_id=?", (plan_id,))
    rows = []
    go_no_go = pricing = 0
    has_phasing = 0
    for g in deduped:
        meta = taxonomy[g["code"]]
        dc = meta["decision_class"]
        if dc == "go_no_go":
            go_no_go += 1
        elif dc == "pricing":
            pricing += 1
        if g["code"] == "phasing_staging":
            has_phasing = 1
        pages = g.get("pages") or ([g["primary_page"]] if g.get("primary_page") is not None else [])
        primary = g.get("primary_page") if g.get("primary_page") is not None else (pages[0] if pages else None)
        pages_str = ",".join(str(p) for p in pages)
        rows.append((plan_id, source_file, g["section_raw"], g["code"], meta["family"],
                     dc, g["evidence"], primary, pages_str, len(pages), g["confidence"],
                     g.get("rationale", ""), g.get("evidence_raw", ""), g.get("evidence_status", "")))
    conn.executemany(
        "INSERT INTO gotchas (plan_id, source_file, section, flag_type, family, decision_class, "
        "evidence, page, pages, page_count, confidence, rationale, evidence_raw, evidence_status) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)

    # burden tier from the GO/NO-GO count (the bid-killers); cuts are provisional until all 8 are in.
    n_gng = go_no_go
    tier = "low" if n_gng <= 2 else ("medium" if n_gng <= 5 else "high")
    conn.execute("INSERT OR IGNORE INTO plan_metrics (plan_id) VALUES (?)", (plan_id,))
    conn.execute("""UPDATE plan_metrics SET gotcha_count=?, gotcha_go_no_go_count=?,
                    gotcha_pricing_count=?, gotcha_burden_tier=?, has_phasing=?,
                    gotcha_extraction_cost=? WHERE plan_id=?""",
                 (len(deduped), go_no_go, pricing, tier, has_phasing, round(cost, 6), plan_id))
    conn.commit()
    return {"total": len(deduped), "go_no_go": go_no_go, "pricing": pricing,
            "tier": tier, "has_phasing": has_phasing}


# --- per-plan driver ---------------------------------------------------------
def prep_plan(full_markdown):
    """Page-prep half: split → carry headings → drop drawings → batch. No API. Returns the pieces both
    the synchronous and the Batches API paths need."""
    pages = split_pages(full_markdown)
    headings = governing_headings(pages)
    candidates, dropped = prose_pages(pages)
    batches = batch_pages(candidates, headings)
    return pages, candidates, dropped, batches


def finalize_plan(conn, taxonomy, plan_id, source_file, pages, candidates, dropped,
                  n_batches, deduped, usage, report, batched):
    """Write the deduped gotchas, roll up, print the per-plan line, and append the report record.
    Shared by the synchronous and Batches API paths (only `batched` changes the cost math)."""
    cost = _cost_from_totals(usage, batched=batched)
    deduped = apply_verbatim_gate(deduped, candidates)          # snap quotes → verbatim span + status
    rollup = write_gotchas(conn, plan_id, source_file, taxonomy, deduped, cost)
    telem = keyword_telemetry(taxonomy, candidates, deduped)
    _sc = {}
    for g in deduped:
        _sc[g.get("evidence_status")] = _sc.get(g.get("evidence_status"), 0) + 1
    print(f"    evidence: verbatim={_sc.get('verbatim',0)} partial={_sc.get('partial',0)} "
          f"unverified={_sc.get('unverified',0)} no_evidence={_sc.get('no_evidence',0)}")

    miss_pages = KNOWN_MISSES.get(plan_id, [])
    miss_status = {p: ("DROPPED_AS_DRAWING" if p in dropped else "prose-kept") for p in miss_pages}

    cost_per_page = (cost / len(candidates)) if candidates else 0.0
    print(f"\n  {plan_id}")
    print(f"    pages={len(pages)}  prose={len(candidates)}  dropped_drawing={len(dropped)}  batches={n_batches}")
    print(f"    gotchas={rollup['total']}  (go_no_go={rollup['go_no_go']} pricing={rollup['pricing']})"
          f"  has_phasing={rollup['has_phasing']}")
    print(f"    tokens={usage['in']:,}in/{usage['out']:,}out  cache_read={usage['cache_read']:,}"
          f"  cache_write={usage['cache_creation']:,}  cost=${cost:.4f}  $/prose-page=${cost_per_page:.4f}")
    if miss_pages:
        print(f"    known-miss pages: {miss_status}")
    if telem["skip_entirely"]:
        print(f"    [telemetry] skip_entirely=TRUE (no trigger fired anywhere)")

    report.append({
        "plan_id": plan_id, "n_pages": len(pages), "prose_pages": len(candidates),
        "dropped_drawing": len(dropped), "dropped_drawing_pages": dropped, "batches": n_batches,
        "gotchas": rollup, "tokens_in": usage["in"], "tokens_out": usage["out"],
        "cache_read": usage["cache_read"], "cache_creation": usage["cache_creation"],
        "calls": usage["calls"], "cost": cost, "batched": batched,
        "cost_per_prose_page": round(cost_per_page, 6), "deduped": deduped,
        "miss_status": miss_status, "telemetry": telem,
    })


def process_plan(conn, taxonomy, plan_id, source_file, full_markdown, report):
    """SYNCHRONOUS path: judge one plan live (one call per batch), then write + report."""
    pages, candidates, dropped, batches = prep_plan(full_markdown)
    deduped, usage = judge_plan(taxonomy, batches)
    finalize_plan(conn, taxonomy, plan_id, source_file, pages, candidates, dropped,
                  len(batches), deduped, usage, report, batched=False)


def run_batched(conn, taxonomy, plans, report):
    """BATCHES API path: build ONE Message Batch over every (plan, batch) request, poll to completion,
    then collapse + write per plan. 50% cheaper than the synchronous path; async (most finish < 1h)."""
    import time
    import anthropic
    from anthropic.types.message_create_params import MessageCreateParamsNonStreaming
    from anthropic.types.messages.batch_create_params import Request
    from collections import defaultdict

    client = anthropic.Anthropic(api_key=extract.API_KEY)
    tax_block = _taxonomy_block(taxonomy)
    valid = set(taxonomy)

    # 1. Build all requests up front. The Batches API restricts custom_id to ^[a-zA-Z0-9_-]{1,64}$, so
    #    use a short positional id ("r0", "r1", ...) and map it back to the plan.
    plan_prep, requests, cid_to_plan = {}, [], {}
    for plan_id, source_file, full_markdown in plans:
        pages, candidates, dropped, batches = prep_plan(full_markdown)
        plan_prep[plan_id] = dict(source_file=source_file, pages=pages, candidates=candidates,
                                  dropped=dropped, n_batches=len(batches))
        for ctx in batches:
            cid = f"r{len(requests)}"
            cid_to_plan[cid] = plan_id
            requests.append(Request(custom_id=cid,
                                    params=MessageCreateParamsNonStreaming(**_judge_params(tax_block, ctx))))

    print(f"  submitting {len(requests)} judge requests across {len(plans)} plans to the Batches API "
          f"(50% cost, async)...")
    batch = client.messages.batches.create(requests=requests)
    print(f"  batch id: {batch.id}")

    # 2. Poll until the whole batch ends (most < 1h; max 24h).
    while True:
        b = client.messages.batches.retrieve(batch.id)
        c = b.request_counts
        if b.processing_status == "ended":
            print(f"  batch ended: {c.succeeded} succeeded, {c.errored} errored, {c.canceled} canceled, "
                  f"{c.expired} expired")
            break
        print(f"  status={b.processing_status}  processing={c.processing} succeeded={c.succeeded} "
              f"errored={c.errored}", flush=True)
        time.sleep(30)

    # 3. Group raw gotchas + usage by plan.
    raw_by_plan = defaultdict(list)
    usage_by_plan = defaultdict(_new_usage_totals)
    n_err = 0
    for result in client.messages.batches.results(batch.id):
        plan_id = cid_to_plan.get(result.custom_id)
        if result.result.type == "succeeded":
            msg = result.result.message
            raw_by_plan[plan_id].extend(_parse_judge_text(msg.content[0].text if msg.content else ""))
            _accumulate_usage(usage_by_plan[plan_id], msg.usage)
        else:
            n_err += 1
    if n_err:
        print(f"  ⚠ {n_err} batch requests did not succeed (counted as 0 gotchas for their page range)")

    # 4. Collapse + write each plan (same finalize as the synchronous path; batched=True for the cost math).
    for plan_id, prep in plan_prep.items():
        deduped = collapse_by_code(raw_by_plan.get(plan_id, []), valid)
        usage = usage_by_plan.get(plan_id, _new_usage_totals())
        finalize_plan(conn, taxonomy, plan_id, prep["source_file"], prep["pages"], prep["candidates"],
                      prep["dropped"], prep["n_batches"], deduped, usage, report, batched=True)


def _cost_from_totals(usage, batched=False):
    """Cache-aware $ estimate. Cache WRITES bill 1.25x base input, cache READS 0.1x, uncached input +
    output at base. The Batches API takes 50% off ALL tokens, applied last."""
    in_tok = usage["in"] + usage["cache_creation"] * 1.25 + usage["cache_read"] * 0.10
    cost = (in_tok / 1e6) * PRICE_PER_MTOK_IN + (usage["out"] / 1e6) * PRICE_PER_MTOK_OUT
    if batched:
        cost *= 0.5
    return round(cost, 6)


# --- s4 no-regression diff ---------------------------------------------------
SCHEMA_FIELDS = {"traffic_level", "special_requirement"}   # not gotchas — excluded from the diff


def s4_flags_for(plan_id):
    """The set of gotcha flag_types the OLD s4 pipeline emitted for a plan, read from
    02_outputs/flags.csv (the no-regression benchmark — NOT ground truth)."""
    fcsv = lib.FLAGS_CSV
    out = set()
    if not fcsv.exists():
        return out
    with open(fcsv, newline="") as f:
        for row in csv.DictReader(f):
            if (row.get("plan_id") or "").strip() != plan_id:
                continue
            ft = (row.get("flag_type") or "").strip()
            if ft and ft not in SCHEMA_FIELDS:
                out.add(ft)
    return out


def print_diff(report):
    """Print the s4 vs new diff table (reproduced / dropped / added) per plan."""
    print("\n=== No-regression diff vs flags.csv (s4 = old benchmark, NOT ground truth) ===")
    for r in report:
        pid = r["plan_id"]
        new_types = {g["code"] for g in r["deduped"]}
        old_types = s4_flags_for(pid)
        reproduced = sorted(old_types & new_types)
        dropped = sorted(old_types - new_types)
        added = sorted(new_types - old_types)
        print(f"\n  {pid}")
        print(f"    reproduced ({len(reproduced)}): {reproduced}")
        print(f"    DROPPED    ({len(dropped)}): {dropped}   <- each must be explained")
        print(f"    added      ({len(added)}): {added}")


# --- main --------------------------------------------------------------------
def main():
    only = sys.argv[sys.argv.index("--plan") + 1] if "--plan" in sys.argv else None
    checkpoint = "--checkpoint" in sys.argv
    use_batches = "--batch" in sys.argv   # Message Batches API (50% cost, async) vs synchronous calls

    taxonomy = load_taxonomy()
    assert len(taxonomy) == 20, f"expected 20 active gotcha types, got {len(taxonomy)}"

    conn = sqlite3.connect(DB_PATH)
    ensure_schema(conn)

    # Scope to gotcha-eligible docs: skip drawing-only plan-sets (Build-1 plans.doc_type). A plan_set is
    # all sheets/drawings — judging it produces junk gotchas. proposal/combined/unknown are kept.
    q = ("SELECT plan_id, source_file, full_markdown FROM plans "
         "WHERE convert_status='converted' AND COALESCE(full_markdown,'') <> '' "
         "AND COALESCE(doc_type,'') <> 'plan_set'")
    plans = conn.execute(q).fetchall()
    if checkpoint:
        plans = [p for p in plans if p[0] in CHECKPOINT_PLANS]
    elif only:
        plans = [p for p in plans if p[0] == only]

    mode = "Batches API (50% cost, async)" if use_batches else "synchronous"
    print(f"=== Phase 2a gotcha extraction (judge-all-prose, pool-never-route) ===")
    print(f"    taxonomy: {len(taxonomy)} active types  |  plans to judge: {len(plans)}  |  mode: {mode}")

    reset_clean_slate(conn, [p[0] for p in plans])

    report = []
    if use_batches:
        run_batched(conn, taxonomy, plans, report)
    else:
        for plan_id, source_file, full_markdown in plans:
            process_plan(conn, taxonomy, plan_id, source_file, full_markdown, report)

    # --- the checkpoint report ---
    print_diff(report)

    print("\n=== COST CHECKPOINT (HR12) ===")
    tot_cost = sum(r["cost"] for r in report)
    tot_pages = sum(r["prose_pages"] for r in report)
    tot_in = sum(r["tokens_in"] for r in report)
    tot_cache = sum(r["cache_read"] for r in report)
    for r in report:
        g = r["gotchas"]
        print(f"  {r['plan_id']:42s} prose={r['prose_pages']:3d}  gotchas={g['total']:2d}"
              f"  (gng={g['go_no_go']} pr={g['pricing']})  ${r['cost']:.4f}"
              f"  ${r['cost_per_prose_page']:.4f}/pg")
    print(f"  TOTAL  cost=${tot_cost:.4f}  prose_pages={tot_pages}  tokens_in={tot_in:,}"
          f"  cache_read={tot_cache:,}")
    if tot_pages:
        print(f"  blended $/prose-page = ${tot_cost / tot_pages:.4f}")

    print("\n=== KNOWN-MISS SMOKE TEST ===")
    for r in report:
        if r["miss_status"]:
            print(f"  {r['plan_id']}: {r['miss_status']}")
            miss = KNOWN_MISSES.get(r["plan_id"], [])
            for g in r["deduped"]:
                hit = sorted(set(g.get("pages") or []) & set(miss))
                if hit:
                    print(f"      -> p{hit} {g['code']} [{g['confidence']}]: {g['evidence'][:90]}")

    # write a JSON report artifact for the handoff
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    import datetime
    out = OUT_DIR / f"{datetime.date.today().isoformat()}_gotcha_checkpoint.json"
    out.write_text(json.dumps(report, indent=2, default=str))
    print(f"\n  report artifact -> {out}")

    conn.close()


if __name__ == "__main__":
    main()
