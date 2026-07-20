#!/usr/bin/env python3
"""
09_schedule_detect.py  —  bid-schedule PRESENCE detector (no extraction, no approximation, free).

Answers one question per plan: is there a real bid-item TABLE in this PDF, and on which pages? — so the
empty-quantity plans can be triaged BY HAND. This is NOT doc_type (that's plans.doc_type) and NOT
work_type (paving vs structural) — it is purely table presence + a jump-to page list for manual review.

Writes to plan_metrics:
  schedule_signal   both | table_only | heading_only | none
        both         a Jay schedule HEADING + a real pay-item TABLE found  (strongest)
        table_only   a pay-item table found, no clear heading
        heading_only a schedule heading mentioned, but NO table in this PDF (likely the table is a
                     SEPARATE plan-set/file → re-pull or doc-type check)
        none         neither → wrong-doc / special-provisions-only
  schedule_pages    comma-joined candidate pages (heading pages + table pages) to verify by hand

Detection avoids distractor tables (Gallons-of-Fuel, Materials-Control, gradation, wage, mix-design)
and requires a quantity >= 1 (so fuel ratios like 0.17 don't count). Page pointers are CANDIDATES to
verify, not guarantees. No API. Idempotent. Sole DB writer while it runs.

Run:
    cd 01_Summer_2026
    python3 pipelines/plan_reader/04_tools/09_schedule_detect.py
"""
import re
import sqlite3
from pathlib import Path
from collections import Counter

MODULE_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = MODULE_ROOT / "csi_v2.db"

def strip_md(s): return re.sub(r"[~*`]+|<br>", " ", s or "")

SCHED = re.compile(r"schedule of prices|proposal schedule of items|statement of estimated quantit|"
                   r"\bbid schedule\b|\bbid form\b|section 00300|bid tabulation|unit price bid|schedule of items", re.I)
DISTRACT = re.compile(r"gallons of fuel|fuel per unit|materials control|gradation|wage rate|wage decision|"
                      r"prevailing wage|mix design|concrete grade|qc.?qa|testing rate|verification testing|truck rental", re.I)
UNIT = re.compile(r"^(TONS?|SY|SQ ?YDS?|CY|CU ?YDS?|LF|LIN ?FT|EACH|EA|LS|LUMP ?SUM|GAL(LON)?S?|ACRES?|"
                  r"HOURS?|HR|MILES?|CWT|LBS?|RDSTA|STA|FEET|FT|UNIT|SF)$", re.I)
NUM = re.compile(r"^\$?[\d,]+(\.\d+)?$")


def payitem_rows(txt):
    """Rows that look like a REAL bid item: a unit cell + a quantity >= 1. 0 if the page is a distractor."""
    if DISTRACT.search(strip_md(txt)[:400]):
        return 0
    n = 0
    for ln in txt.splitlines():
        if "|" not in ln:
            continue
        cells = [c.strip() for c in strip_md(ln).split("|")]
        if not any(UNIT.fullmatch(c) for c in cells):
            continue
        if any(NUM.fullmatch(c) and float(c.replace(",", "").replace("$", "") or 0) >= 1 for c in cells):
            n += 1
    return n


def detect(md):
    parts = re.split(r"<!--\s*page\s+(\d+)\s*-->", md or "")
    pages = [(int(parts[i]), parts[i+1] if i+1 < len(parts) else "") for i in range(1, len(parts), 2)]
    head_pg = [pno for pno, txt in pages
               if SCHED.search(strip_md(txt)) and not DISTRACT.search(strip_md(txt)[:200])]
    tbl_pg = [pno for pno, txt in pages if payitem_rows(txt) >= 3]
    if head_pg and tbl_pg:   sig = "both"
    elif tbl_pg:             sig = "table_only"
    elif head_pg:            sig = "heading_only"
    else:                    sig = "none"
    pages_str = ",".join(str(p) for p in sorted(set(head_pg[:5] + tbl_pg[:8])))
    return sig, pages_str


def ensure_schema(conn):
    have = {r[1] for r in conn.execute("PRAGMA table_info(plan_metrics)")}
    for col, typ in (("schedule_signal", "TEXT"), ("schedule_pages", "TEXT")):
        if col not in have:
            conn.execute(f"ALTER TABLE plan_metrics ADD COLUMN {col} {typ}")
    conn.commit()


def main():
    conn = sqlite3.connect(DB_PATH)
    ensure_schema(conn)
    rows = conn.execute(
        "SELECT plan_id, full_markdown FROM plans WHERE COALESCE(full_markdown,'') <> ''").fetchall()
    sig_ct = Counter()
    for plan_id, md in rows:
        sig, pages = detect(md)
        sig_ct[sig] += 1
        conn.execute("INSERT OR IGNORE INTO plan_metrics (plan_id) VALUES (?)", (plan_id,))
        conn.execute("UPDATE plan_metrics SET schedule_signal=?, schedule_pages=? WHERE plan_id=?",
                     (sig, pages, plan_id))
    conn.commit()

    print(f"schedule_signal across {len(rows)} converted plans: {dict(sig_ct)}")
    print("\nThe triage of the empty-quantity plans (quantity_review=1):")
    for sig, n in conn.execute("""
        SELECT COALESCE(m.schedule_signal,'(none)'), COUNT(*) FROM plan_metrics m
        WHERE m.quantity_review=1 GROUP BY 1 ORDER BY 2 DESC"""):
        tag = {"both": "has table+heading -> verify by hand",
               "table_only": "has table -> verify",
               "heading_only": "NO table in PDF -> re-pull / doc-type",
               "none": "no schedule -> wrong-doc / special-provisions"}.get(sig, "")
        print(f"  {sig:14s} {n:3d}   {tag}")
    print("\nWork the list:  SELECT plan_id, schedule_signal, schedule_pages FROM plan_metrics "
          "WHERE quantity_review=1 ORDER BY schedule_signal;")
    conn.close()


if __name__ == "__main__":
    main()
