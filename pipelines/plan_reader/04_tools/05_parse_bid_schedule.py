#!/usr/bin/env python3
"""
05_parse_bid_schedule.py  —  PHASE 1: deterministic bid-schedule parser (Part A).

For every converted plan in csi_v2.db, parse the bid SCHEDULE out of `full_markdown` and write
ONE PARSE, TWO OUTPUTS:
  • materials (LONG)      — one row per bid-schedule line item (audit trail: traces every bucket
                            total back to the source line + page).
  • plan_metrics (WIDE)   — the 7 material buckets (GROUP BY csi_bucket) + bid_item_count +
                            n_spec_categories + scope flags, rolled up from the same parse.

The parser is the VALIDATED logic from the 2026-06-15 feasibility test (produced Dunn = 39 items),
ported here as production code. The key idea is the PRICE-COLUMN DISCRIMINATOR: a real bid *schedule*
is a pricing form (it has a UNIT PRICE / SUBTOTAL / EXTENDED column); engineer's-estimate quantity
tabulations ("BASIS OF ESTIMATE") share QUANTITY/UNIT but carry no price. Requiring a price column is
what drops Dunn from a polluted 104 rows to the correct 39. The description -> csi_bucket / spec_category
mapping is the single canonical crosswalk in 05_knowledge/quantity_crosswalk.py.

This is PART A only — deterministic, NO Claude calls. The LLM fallback (Part B) is added separately,
only after this part's checkpoint passes, and only for plans where this parse finds nothing.

Idempotent: a plan's materials rows are deleted before re-insert; plan_metrics is upserted.

Run:
    cd 01_Summer_2026
    python3 pipelines/plan_reader/04_tools/05_parse_bid_schedule.py            # all plans
    python3 pipelines/plan_reader/04_tools/05_parse_bid_schedule.py --plan 2023_DUNN-CO-ND_CP-13_WON
"""
import os
import re
import sys
import json
import sqlite3
from pathlib import Path

# Reuse module paths + the canonical crosswalk (read-only imports; nothing in 01_pipeline is modified).
TOOLS_DIR    = Path(__file__).resolve().parent
MODULE_ROOT  = TOOLS_DIR.parent                                  # .../plan_reader
PIPELINE_DIR = MODULE_ROOT / "01_pipeline"
KNOWLEDGE_DIR = MODULE_ROOT / "05_knowledge"
sys.path.insert(0, str(PIPELINE_DIR))
sys.path.insert(0, str(KNOWLEDGE_DIR))
import lib                             # noqa: E402  — for ENV_PATH (the API key location)
import quantity_crosswalk as xwalk     # noqa: E402  — the single source of truth for the mapping

# --- paths -------------------------------------------------------------------
DB_PATH   = MODULE_ROOT / "csi_v2.db"
PLANS_DIR = MODULE_ROOT / "00_input" / "plans"                   # for the v1 JSON delta cross-check

# --- LLM fallback config (Part B only — Part A makes NO API calls) ------------
# Same client/key/model conventions as 01_pipeline/s3_extract.py (reused, not modified).
MODEL = "claude-sonnet-4-6"
# Sonnet 4.6 list price per MILLION tokens — used only to turn measured token counts into a $ estimate
# for the cost report. If the rate is stale, the TOKEN counts (the real signal) are still reported.
PRICE_PER_MTOK_IN  = 3.0
PRICE_PER_MTOK_OUT = 15.0
# Targeting the fallback: send ONLY likely bid-schedule pages, never the whole document.
FALLBACK_PAGE_BUDGET = 60_000     # max chars of page text sent to the LLM per plan
FALLBACK_PER_PAGE_CAP = 25_000    # truncate any single huge (pooled CAD) page before adding it
FALLBACK_MAX_API_PLANS = 60       # raised 2026-06-17 for the full corpus sweep (~46 plans, ~$5); revert to 5 after

# The plan_metrics columns Part A owns. We upsert ONLY these so Phase 1.5/2 columns (work_type,
# size_*, has_phasing, messiness_score, gotcha_*) are never clobbered by a re-run.
METRICS_OWNED = (xwalk.CSI_BUCKETS + [
    "box_culvert", "prevailing_wages", "has_quantity", "bid_item_count",
    "n_spec_categories", "has_structures_work", "parse_method", "unmapped_items", "extraction_cost",
])

# --- low-level table-cell helpers (ported from the feasibility parser) --------
def _clean(cell):
    """Strip pymupdf4llm Markdown artifacts (~~strikethrough~~, <br>, bold **) from a table cell."""
    return cell.replace("~~", "").replace("<br>", " ").replace("**", "").strip()


def _split(line):
    """Split one Markdown table row '| a | b |' into cleaned cells, or None if it isn't a table row."""
    s = line.strip()
    if not s.startswith("|"):
        return None
    return [_clean(p) for p in s.strip("|").split("|")]


def _is_separator(cells):
    """True for the '|---|---|' divider row under a Markdown header."""
    return all(c == "" or set(c) <= set("-: ") for c in cells)


def _num(s):
    """Parse a quantity cell to a float, tolerating commas/units; None if there's no number."""
    s = re.sub(r"[^\d.]", "", (s or "").replace(",", ""))
    try:
        return float(s) if s not in ("", ".") else None
    except ValueError:
        return None


TOTAL_RE = re.compile(r"TOTAL OF (ALL|ALTERNATE)|GRAND TOTAL|TOTAL BASE BID", re.I)
ALT_RE   = re.compile(r"ALTERNATE\s+([A-Z])\b", re.I)
LUMP_UNITS = {"LSUM", "LS", "LUMP SUM", "LUMP"}


def _is_header(cells):
    """Bid-schedule PRICING-form header signature: QUANTITY + a description col + a unit col +
    a PRICE/SUBTOTAL/EXTENDED col. The price column is the discriminator that separates the biddable
    schedule from engineer's-estimate quantity tabulations. Covers the MN/ND/SD layouts."""
    u = [c.upper() for c in cells]
    has_qty   = any("QUANTITY" in c for c in u)
    has_desc  = any(("DESCRIPTION" in c) or c in ("ITEM", "ITEM #") for c in u)
    has_unit  = any(c in ("UNIT", "UNITS") for c in u)
    # Price-column discriminator. Besides PRICE/SUBTOTAL/EXTENDED, the SD DOT proposal form labels its
    # priced columns "UNIT COST" + "ITEM TOTAL" (and some MN/ND forms use "AMOUNT"/"COST") — all are the
    # priced-bid signal that separates the biddable schedule from an engineer's-estimate tabulation.
    PRICE_TERMS = ("PRICE", "SUBTOTAL", "EXTENDED", "UNIT COST", "ITEM TOTAL", "AMOUNT")
    has_price = any(any(t in c for t in PRICE_TERMS) for c in u)
    return has_qty and has_desc and has_unit and has_price and len(cells) >= 4


def _colmap(cells):
    """Map header cell names -> field indices (each DOT orders the columns differently)."""
    u = [c.upper() for c in cells]

    def find(pred, default=None):
        for i, c in enumerate(u):
            if pred(c):
                return i
        return default

    qty_i  = find(lambda c: "QUANTITY" in c)
    unit_i = find(lambda c: c in ("UNIT", "UNITS"))
    desc_i = find(lambda c: "DESCRIPTION" in c)
    if desc_i is None:                                   # MnDOT uses a bare 'Item' column
        desc_i = find(lambda c: c == "ITEM")
    code_i = find(lambda c: "MAT NO" in c or c == "ITEM #" or c == "SPEC")
    line_i = find(lambda c: c in ("NO.", "BID ITEM", "LINE", "NO"))
    if line_i is None:
        line_i = 0
    return {"line": line_i, "code": code_i, "desc": desc_i, "unit": unit_i, "qty": qty_i}


# --- the parse (header-anchored; tracks the page each item sits on) -----------
_PAGE_MARKER = re.compile(r"<!-- page (\d+) -->")


def _page_for_each_line(lines):
    """Return a list[int|None] giving the page number in effect at each line, by carrying forward the
    most recent '<!-- page N -->' marker. Lets every materials row record its source page."""
    pages, current = [], None
    for ln in lines:
        m = _PAGE_MARKER.search(ln)
        if m:
            current = int(m.group(1))
        pages.append(current)
    return pages


def parse_bid_items(full_markdown):
    """Find every bid-schedule header row, map its columns, and consume item rows until the matching
    TOTAL row / next header / +200 lines — tolerating page-break gaps so continuation tables (e.g.
    Dunn items 26-37) are captured. Returns a list of dicts with the line fields + page + mapping."""
    lines = full_markdown.splitlines()
    n = len(lines)
    page_at = _page_for_each_line(lines)

    # Locate every header row first; we consume rows between a header and its TOTAL/next-header.
    headers = []
    for i, ln in enumerate(lines):
        cells = _split(ln)
        if cells and _is_header(cells):
            headers.append((i, _colmap(cells)))
    header_idx = {i for i, _ in headers}

    items, seen = [], set()
    for hi, cmap in headers:
        # Section label: a bid schedule may have ALTERNATE blocks — look back a few lines for the marker.
        section = "base_bid"
        for k in range(hi, max(0, hi - 8), -1):
            m = ALT_RE.search(_clean(lines[k]))
            if m:
                section = f"alternate_{m.group(1).upper()}"
                break

        # Find where this schedule block ends: the TOTAL row, the next header, or a +200-line cap.
        end = n
        for j in range(hi + 1, min(n, hi + 200)):
            if TOTAL_RE.search(_clean(lines[j])) or j in header_idx:
                end = j
                break

        # Walk the item rows.
        for j in range(hi + 1, end):
            cells = _split(lines[j])
            if not cells or _is_separator(cells) or _is_header(cells):
                continue
            if TOTAL_RE.search(" ".join(cells)):
                continue
            need = max(cmap["desc"] or 0, cmap["unit"] or 0, cmap["qty"] or 0)
            if len(cells) <= need:
                continue
            desc = cells[cmap["desc"]] if cmap["desc"] is not None else ""
            if not desc or len(desc) < 2 or "DESCRIPTION" in desc.upper():
                continue
            unit = cells[cmap["unit"]] if cmap["unit"] is not None else ""
            qty  = cells[cmap["qty"]] if cmap["qty"] is not None else ""
            code = cells[cmap["code"]] if cmap["code"] is not None and cmap["code"] < len(cells) else ""
            line_raw = cells[cmap["line"]] if cmap["line"] < len(cells) else ""
            ln_digits = re.sub(r"\D", "", line_raw)
            ln_int = int(ln_digits) if ln_digits else None
            is_lump = unit.upper() in LUMP_UNITS

            # De-dup: the same (section, line, description) can recur across a page-break repeat.
            key = (section, ln_int, desc.upper()[:40])
            if key in seen:
                continue
            seen.add(key)

            bucket, cat = xwalk.map_line(desc, unit)
            items.append({
                "bid_item_no": str(ln_int) if ln_int is not None else (code or ""),
                "raw_description": desc,
                "unit": unit,
                "quantity": (None if is_lump else _num(qty)),
                "section": section,
                "page": page_at[j],
                "csi_bucket": bucket,
                "spec_category": cat,
            })
    return items


# --- rollup: the 7 buckets + complexity signals from the same parse -----------
BOX_CULVERT_RE = re.compile(r"BOX CULVERT|\bRCBC\b|PRECAST CONCRETE BOX", re.I)
WAGE_RE        = re.compile(r"DAVIS[- ]BACON|PREVAILING WAGE|WAGE DETERMINATION", re.I)


def rollup_metrics(items, full_markdown):
    """Roll the parsed line items up into the plan_metrics columns Part A owns. The 7 bucket totals are
    a GROUP BY csi_bucket sum, so each total traces back to its source line(s)."""
    buckets = {b: 0.0 for b in xwalk.CSI_BUCKETS}
    for it in items:
        if it["csi_bucket"] and it["quantity"]:
            buckets[it["csi_bucket"]] += it["quantity"]
    # Store a clean None for an empty bucket (rather than 0) so "not present" is distinguishable.
    bucket_vals = {b: (round(v, 2) if v else None) for b, v in buckets.items()}

    cats = {it["spec_category"] for it in items}
    cats.discard("other")                                # 'other' isn't a real spec category

    # box_culvert: scan both the line items and the markdown (the culvert may be a plan note, not a line).
    has_box = any(BOX_CULVERT_RE.search(it["raw_description"]) for it in items) or \
              bool(BOX_CULVERT_RE.search(full_markdown))
    # prevailing_wages: deterministic keyword presence (the wage section, not the bid schedule).
    has_wage = bool(WAGE_RE.search(full_markdown))

    # unmapped_items: descriptions the crosswalk couldn't categorize — the growth backlog + fallback input.
    unmapped = sorted({it["raw_description"] for it in items if it["spec_category"] == "other"})

    return {
        **bucket_vals,
        "box_culvert": 1 if has_box else 0,
        "prevailing_wages": 1 if has_wage else 0,
        "has_quantity": 1 if any(v for v in bucket_vals.values()) else 0,
        "bid_item_count": len(items),
        "n_spec_categories": len(cats),
        "has_structures_work": 1 if "structures" in cats else 0,
        "parse_method": "deterministic",
        "unmapped_items": json.dumps(unmapped),
        "extraction_cost": 0.0,                          # deterministic parse costs nothing
    }


# --- DB writes (idempotent) --------------------------------------------------
def write_materials(conn, plan_id, source_file, items, parse_method, confidence):
    """Replace this plan's materials rows with the freshly parsed set (idempotent per plan). The
    parse_method/confidence are stamped per row so a fallback-recovered line is distinguishable from a
    deterministically-parsed one ('deterministic'/'high' vs 'llm_fallback'/'medium')."""
    conn.execute("DELETE FROM materials WHERE plan_id = ?", (plan_id,))
    conn.executemany(
        "INSERT INTO materials (plan_id, source_file, section, bid_item_no, raw_description, "
        "csi_bucket, spec_category, quantity, unit, page, confidence, parse_method) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [(plan_id, source_file, it["section"], it["bid_item_no"], it["raw_description"],
          it["csi_bucket"], it["spec_category"], it["quantity"], it["unit"], it["page"],
          confidence, parse_method) for it in items],
    )
    conn.commit()


def ensure_metrics_stub(conn, plan_id):
    """Make sure a plan has a plan_metrics row WITHOUT overwriting anything — used for plans Part A
    can't parse, so a prior LLM-fallback result is never clobbered by a later deterministic re-run."""
    conn.execute("INSERT OR IGNORE INTO plan_metrics (plan_id) VALUES (?)", (plan_id,))
    conn.commit()


def upsert_metrics(conn, plan_id, metrics):
    """Insert/update the plan_metrics row, writing ONLY Part A's owned columns (ON CONFLICT keeps any
    Phase 1.5/2 columns intact)."""
    cols = ["plan_id"] + METRICS_OWNED
    placeholders = ", ".join("?" for _ in cols)
    updates = ", ".join(f"{c} = excluded.{c}" for c in METRICS_OWNED)
    conn.execute(
        f"INSERT INTO plan_metrics ({', '.join(cols)}) VALUES ({placeholders}) "
        f"ON CONFLICT(plan_id) DO UPDATE SET {updates}",
        [plan_id] + [metrics[c] for c in METRICS_OWNED],
    )
    conn.commit()


# --- validation helpers ------------------------------------------------------
def v1_s3_value(plan_id, field):
    """Read the existing v1 s3 value for a field from the colocated per-plan JSON (for the <5% delta
    cross-check). Returns None if no JSON / no value."""
    p = PLANS_DIR / plan_id / f"{plan_id}.json"
    if not p.exists():
        return None
    rec = json.load(open(p))
    v = rec.get(field)
    return v.get("value") if isinstance(v, dict) else v


# --- PART B: LLM fallback (only for plans where the deterministic parse found nothing) ---------------
import anthropic     # noqa: E402  — imported here so Part A stays import-light + obviously API-free

_KW_RE       = re.compile(r"SCHEDULE OF PRICES|BID SCHEDULE|STATEMENT OF ESTIMATED QUANTITIES|"
                          r"ESTIMATED QUANTITIES|SCHEDULE OF ITEMS|PROPOSAL FORM", re.I)
_SPECCODE_RE = re.compile(r"\b\d{4}\.\d{2,3}\b")   # DOT pay-item codes (2360.504, 2106.507) — schedule signal

FALLBACK_PROMPT = """You are reading pages from a highway-construction bid plan. These pages should
contain the BID SCHEDULE (a.k.a. Schedule of Prices / Statement of Estimated Quantities) — the table
of every pay item with its quantity and unit. The automatic table parser failed on these pages
(scanned / CAD-drawn / merged cells), so read them carefully and recover the line items.

Return ONLY a JSON array, one object per bid-schedule pay item, no other text:
[{{"bid_item_no": "<item number or code, or null>", "description": "<the item description>",
  "unit": "<UNIT, e.g. TON/SY/CY/LF/EA/LSUM>", "quantity": <number or null for lump-sum>}}]

Rules:
- Include ONLY real bid-schedule pay items. Do NOT include wage tables, spec text, or notes.
- quantity: a plain number, no commas/units; null for lump-sum items.
- If these pages contain no recognizable bid schedule, return [].

Pages:
---
{pages}
---"""


def is_plan_set_only(conn, plan_id):
    """True if the plan has NO real prose sections — only the pooled '(plan sheets / drawings)' (and/or
    '(intro)') section. These are the plan-set-only PDFs awaiting their proposal PDF from Box; their bid
    schedule isn't present, so we must NOT spend an API call on spurious keyword hits in the drawings."""
    real = conn.execute(
        "SELECT COUNT(*) FROM sections WHERE plan_id=? AND raw_heading NOT IN "
        "('(plan sheets / drawings)', '(intro)')", (plan_id,)).fetchone()[0]
    return real == 0


def select_schedule_pages(full_markdown):
    """Pick the pages most likely to hold the bid schedule and return them as one string (page markers
    kept so the LLM can cite). Score each page by schedule keywords + density of DOT pay-item codes;
    take the highest-scoring pages within a char budget (truncating any one huge pooled CAD page).
    Returns (pages_text, page_numbers)."""
    parts = _PAGE_MARKER.split(full_markdown)
    scored = []
    for i in range(1, len(parts), 2):
        pno = int(parts[i])
        txt = parts[i + 1] if i + 1 < len(parts) else ""
        score = (2 if _KW_RE.search(txt) else 0) + len(_SPECCODE_RE.findall(txt))
        if score > 0:
            scored.append((score, pno, txt[:FALLBACK_PER_PAGE_CAP]))
    scored.sort(key=lambda x: -x[0])                      # strongest schedule signal first

    chosen, total = [], 0
    for score, pno, txt in scored:
        if chosen and total + len(txt) > FALLBACK_PAGE_BUDGET:
            continue
        chosen.append((pno, txt))
        total += len(txt)
    chosen.sort(key=lambda x: x[0])                       # back into reading order
    pages_text = "\n\n".join(f"<!-- page {pno} -->\n{txt}" for pno, txt in chosen)
    return pages_text, [pno for pno, _ in chosen]


def call_llm_for_items(pages_text):
    """One Claude call over the targeted schedule pages → (list_of_item_dicts, usage). usage carries the
    measured input/output token counts so the caller can log cost."""
    api_key = os.environ.get("ANTHROPIC_API_KEY") or lib.ENV_PATH.read_text().split("'")[1]
    client = anthropic.Anthropic(api_key=api_key)
    resp = client.messages.create(
        model=MODEL, max_tokens=4096,
        messages=[{"role": "user", "content": FALLBACK_PROMPT.format(pages=pages_text)}],
    )
    raw = resp.content[0].text.strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    try:
        items = json.loads(raw)
        items = items if isinstance(items, list) else []
    except json.JSONDecodeError:
        items = []
    return items, resp.usage


def llm_items_to_materials(raw_items, schedule_pages):
    """Turn the LLM's [{bid_item_no, description, unit, quantity}] into the same materials-row shape the
    deterministic parser produces, running the SAME crosswalk. page = the first schedule page sent (we
    don't get per-item pages back from the fallback)."""
    page = schedule_pages[0] if schedule_pages else None
    out = []
    for it in raw_items:
        desc = str(it.get("description") or "").strip()
        if not desc:
            continue
        unit = str(it.get("unit") or "").strip()
        qty = it.get("quantity")
        try:
            qty = float(qty) if qty not in (None, "", "null") else None
        except (ValueError, TypeError):
            qty = None
        bucket, cat = xwalk.map_line(desc, unit)
        out.append({
            "bid_item_no": str(it.get("bid_item_no") or "").strip(),
            "raw_description": desc, "unit": unit, "quantity": qty,
            "section": "base_bid", "page": page, "csi_bucket": bucket, "spec_category": cat,
        })
    return out


def usd_cost(usage):
    """Convert a usage object's token counts to an approximate USD cost (Sonnet 4.6 list price)."""
    cin = (usage.input_tokens / 1e6) * PRICE_PER_MTOK_IN
    cout = (usage.output_tokens / 1e6) * PRICE_PER_MTOK_OUT
    return round(cin + cout, 4)


def run_fallback(conn, no_schedule_plans):
    """Run the LLM fallback over the plans the deterministic parse missed. Skips plan-set-only plans
    (awaiting their proposal PDF — no API spend). STOPS after FALLBACK_MAX_API_PLANS plans that actually
    call the API, so cost is reviewed before doing more. Returns a list of cost records to report."""
    print("\n=== Part B: LLM fallback (targeted, measured) ===")
    cost_log, api_calls = [], 0
    for plan_id, source_file, full_markdown in no_schedule_plans:
        # Don't spend on plan-set-only plans — their bid schedule isn't in the PDF at all.
        if is_plan_set_only(conn, plan_id):
            conn.execute("UPDATE plan_metrics SET parse_method='awaiting_proposal_pdf' WHERE plan_id=?",
                         (plan_id,))
            conn.commit()
            print(f"  · {plan_id:42s} plan-set only — awaiting proposal PDF (no API call)")
            continue

        if api_calls >= FALLBACK_MAX_API_PLANS:
            print(f"  ⏸ {plan_id:42s} HELD — hit the {FALLBACK_MAX_API_PLANS}-plan cost checkpoint "
                  f"(re-run with --continue after reviewing cost)")
            continue

        pages_text, page_nums = select_schedule_pages(full_markdown or "")
        if not pages_text:
            conn.execute("UPDATE plan_metrics SET parse_method='no_schedule_found' WHERE plan_id=?",
                         (plan_id,))
            conn.commit()
            print(f"  · {plan_id:42s} no schedule pages located (no API call)")
            continue

        # The actual paid call.
        raw_items, usage = call_llm_for_items(pages_text)
        api_calls += 1
        cost = usd_cost(usage)
        items = llm_items_to_materials(raw_items, page_nums)

        write_materials(conn, plan_id, source_file, items, "llm_fallback", "medium")
        metrics = rollup_metrics(items, full_markdown or "")
        metrics["parse_method"] = "llm_fallback"
        metrics["extraction_cost"] = cost
        upsert_metrics(conn, plan_id, metrics)

        cost_log.append({"plan_id": plan_id, "pages": len(page_nums), "items": len(items),
                         "in": usage.input_tokens, "out": usage.output_tokens, "cost": cost})
        print(f"  ✓ {plan_id:42s} pages={len(page_nums)} items={len(items):3d}  "
              f"tokens={usage.input_tokens:,}in/{usage.output_tokens:,}out  ${cost:.4f}")
    return cost_log, api_calls


# --- main --------------------------------------------------------------------
def main():
    only = None
    if "--plan" in sys.argv:
        only = sys.argv[sys.argv.index("--plan") + 1]
    do_fallback = "--fallback" in sys.argv          # opt-in: a plain run is always API-free

    conn = sqlite3.connect(DB_PATH)
    q = ("SELECT plan_id, source_file, full_markdown FROM plans "
         "WHERE convert_status='converted' AND COALESCE(full_markdown,'') <> ''")
    plans = conn.execute(q).fetchall()
    if only:
        plans = [p for p in plans if p[0] == only]

    parsed, no_schedule, counts = [], [], []
    print("=== Part A: deterministic bid-schedule parse ===")
    for plan_id, source_file, full_markdown in plans:
        items = parse_bid_items(full_markdown or "")
        if items:
            # Deterministic hit: write its rows (idempotent) + roll up the metrics.
            write_materials(conn, plan_id, source_file, items, "deterministic", "high")
            metrics = rollup_metrics(items, full_markdown or "")
            upsert_metrics(conn, plan_id, metrics)
            parsed.append(plan_id)
            counts.append(len(items))
            print(f"  ✓ {plan_id:42s} items={len(items):3d}  buckets="
                  f"{ {b: metrics[b] for b in xwalk.CSI_BUCKETS if metrics[b]} }")
        else:
            # No deterministic schedule — leave any prior fallback result intact (just ensure a row
            # exists), and queue it for Part B. NEVER overwrite here, or a plain re-run wipes fallback.
            ensure_metrics_stub(conn, plan_id)
            no_schedule.append((plan_id, source_file, full_markdown))
            print(f"  – {plan_id:42s} no deterministic schedule (Part B / LLM-fallback target)")

    # -- Verification (Part A checkpoint) --
    print("\n-- Part A checkpoint --")
    # 1. Dunn ground truth = 39 items.
    dunn = conn.execute("SELECT COUNT(*) FROM materials WHERE plan_id='2023_DUNN-CO-ND_CP-13_WON'").fetchone()[0]
    print(f"  Dunn item count: {dunn}  (expect 39)  {'PASS' if dunn == 39 else 'FAIL'}")

    # 2. <5% delta vs v1 s3 on hot_mix_tons + milling_sy for the clean prose plans that have a v1 JSON.
    print("  Bucket delta vs v1 s3 (clean plans with a JSON):")
    for plan_id in parsed:
        for field in ("hot_mix_tons", "milling_sy"):
            mine = conn.execute(f"SELECT {field} FROM plan_metrics WHERE plan_id=?", (plan_id,)).fetchone()[0]
            old = v1_s3_value(plan_id, field)
            if old and mine:
                delta = (mine - old) / old * 100
                flag = "ok" if abs(delta) < 5 else "OVER 5%"
                print(f"    {plan_id:42s} {field:13s} mine={mine:>10,.0f} s3={old:>10,.0f} ({delta:+.1f}% {flag})")

    # 3. bid_item_count resolution.
    if counts:
        print(f"  bid_item_count resolution: min={min(counts)} max={max(counts)} "
              f"(n_mat_types historically caps at 6)")
    print(f"  parsed: {len(parsed)}  | no-schedule (fallback targets): {len(no_schedule)}")
    for pid, _, _ in no_schedule:
        print(f"    - {pid}")

    # -- Part B: LLM fallback (only when explicitly requested) --
    if do_fallback:
        cost_log, api_calls = run_fallback(conn, no_schedule)
        print("\n-- Cost checkpoint (first fallback batch) --")
        if cost_log:
            tot = sum(r["cost"] for r in cost_log)
            for r in cost_log:
                print(f"    {r['plan_id']:42s} ${r['cost']:.4f}  ({r['in']:,}in/{r['out']:,}out, {r['items']} items)")
            avg = tot / len(cost_log)
            print(f"  API plans: {api_calls}  total ${tot:.4f}  avg ${avg:.4f}/plan")
            print(f"  Projection @ ${avg:.4f}/plan: 11-plan corpus ≈ ${avg*11:.2f}; "
                  f"100-plan corpus ≈ ${avg*100:.2f}  (Sonnet 4.6 @ ${PRICE_PER_MTOK_IN}/${PRICE_PER_MTOK_OUT} per MTok)")
            print("  >>> REVIEW COST before processing any held plans (re-run handles the rest). <<<")
        else:
            print("  No paid fallback calls were made (all targets were plan-set-only / no schedule).")
    else:
        print("\n  (LLM fallback NOT run — pass --fallback to process the no-schedule plans.)")

    conn.close()


if __name__ == "__main__":
    main()
