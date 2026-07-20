#!/usr/bin/env python3
"""
08_doc_type_flags.py  —  BUILD 1: document-type identifier + error/coverage flags.

WHY: an EMPTY proposal is a real extraction MISS; an empty plan_set is EXPECTED (its schedule lives
on the drawing sheets, not in prose). Without a doc_type the coverage gate can't tell those apart and
either false-alarms on plan-sets or stays silent on real misses. This tool populates:

  plans.doc_type           proposal | plan_set | combined | unknown   (page-size structure detection,
                           lib.detect_structure on the PDF; markdown fallback lib.detect_doc_type)
  plan_metrics.schedule_status
        extracted          quantities were parsed
        no_schedule_found  proposal/combined with NO quantities → a real miss (the error flag)
        no_clean_table     (reserved — Build 2 sets this when it finds a schedule REGION but the table
                            won't parse, i.e. image/mangled, distinct from 'absent')
        not_applicable     plan_set (no prose schedule expected)
  plan_metrics.quantity_review   1 = a proposal/combined plan that is missing quantities → needs eyes

No API. Idempotent. Sole DB writer while it runs.

Run:
    cd 01_Summer_2026
    python3 pipelines/plan_reader/04_tools/08_doc_type_flags.py
"""
import re
import sys
import sqlite3
from pathlib import Path
from collections import Counter

TOOLS_DIR   = Path(__file__).resolve().parent
MODULE_ROOT = TOOLS_DIR.parent
sys.path.insert(0, str(MODULE_ROOT / "01_pipeline"))
import lib                                  # detect_structure / detect_doc_type / page markers

DB_PATH = MODULE_ROOT / "csi_v2.db"
_PAGE_MARKER = re.compile(r"<!--\s*page\s+(\d+)\s*-->", re.I)


def ensure_schema(conn):
    """Additive, idempotent — add the two flag columns to plan_metrics if missing."""
    have = {r[1] for r in conn.execute("PRAGMA table_info(plan_metrics)")}
    for col, typ in (("schedule_status", "TEXT"), ("quantity_review", "INTEGER")):
        if col not in have:
            conn.execute(f"ALTER TABLE plan_metrics ADD COLUMN {col} {typ}")
    conn.commit()


def md_pages(full_markdown):
    """Split converted markdown into per-page texts (for the no-PDF content fallback)."""
    parts = _PAGE_MARKER.split(full_markdown or "")
    return [parts[i + 1] if i + 1 < len(parts) else "" for i in range(1, len(parts), 2)]


def doc_type_for(pdf_path, full_markdown):
    """Page-size structure detection from the PDF (most reliable); fall back to content-based
    detection on the markdown when the PDF is missing. Returns proposal|plan_set|combined|unknown."""
    if pdf_path and Path(pdf_path).exists():
        try:
            return lib.detect_structure(pdf_path).get("type", "unknown")
        except Exception:
            pass
    pages = md_pages(full_markdown)
    if pages:
        try:
            dt, _ = lib.detect_doc_type(pages)
            # detect_doc_type may return 'contract_forms'/'addendum' — collapse to proposal for the
            # size-based scheme (a special-provisions-only book is still proposal-SHAPED; the empty
            # schedule then shows up as schedule_status='no_schedule_found', which is the real signal).
            return "plan_set" if dt == "plan_set" else ("unknown" if dt == "addendum" else "proposal")
        except Exception:
            pass
    return "unknown"


def main():
    conn = sqlite3.connect(DB_PATH)
    ensure_schema(conn)

    rows = conn.execute(
        "SELECT plan_id, source_pdf_path, full_markdown FROM plans").fetchall()
    dt_ct = Counter()
    print("=== detecting doc_type (page-size structure) ===")
    for plan_id, pdf, md in rows:
        dt = doc_type_for(pdf, md)
        conn.execute("UPDATE plans SET doc_type=? WHERE plan_id=?", (dt, plan_id))
        dt_ct[dt] += 1
    conn.commit()

    # --- set the flags: join doc_type + has_quantity (one UPDATE, no per-row python) ---
    conn.execute("""
        UPDATE plan_metrics SET
          schedule_status = CASE
            WHEN (SELECT doc_type FROM plans p WHERE p.plan_id = plan_metrics.plan_id) = 'plan_set'
                 THEN 'not_applicable'
            WHEN COALESCE(has_quantity, 0) = 1 THEN 'extracted'
            ELSE 'no_schedule_found' END,
          quantity_review = CASE
            WHEN (SELECT doc_type FROM plans p WHERE p.plan_id = plan_metrics.plan_id) = 'plan_set'
                 THEN 0
            WHEN COALESCE(has_quantity, 0) = 0 THEN 1
            ELSE 0 END
    """)
    conn.commit()

    # --- coverage report ---
    print(f"\ndoc_type distribution: {dict(dt_ct)}")
    print("\nschedule_status:")
    for st, n in conn.execute(
            "SELECT COALESCE(schedule_status,'(none)'), COUNT(*) FROM plan_metrics GROUP BY 1 ORDER BY 2 DESC"):
        print(f"  {st:18s} {n}")
    qr = conn.execute("SELECT COUNT(*) FROM plan_metrics WHERE quantity_review=1").fetchone()[0]
    total = conn.execute("SELECT COUNT(*) FROM plan_metrics").fetchone()[0]
    print(f"\n>>> quantity_review = 1 (proposals/combined MISSING quantities — the real misses): {qr}/{total}")
    print("    plan_sets with no quantities are correctly NOT flagged (schedule on the sheets).")

    # surface the flagged proposals by doc_type so we can see what Build 2 must recover
    print("\nflagged (quantity_review=1) by doc_type:")
    for dt, n in conn.execute("""
        SELECT p.doc_type, COUNT(*) FROM plan_metrics m JOIN plans p ON p.plan_id=m.plan_id
        WHERE m.quantity_review=1 GROUP BY p.doc_type ORDER BY 2 DESC"""):
        print(f"  {str(dt):10s} {n}")
    conn.close()


if __name__ == "__main__":
    main()
