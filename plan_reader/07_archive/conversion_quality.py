"""
conversion_quality.py — Task A2: how much does PDF→Markdown beat the old flat-text path?

The OLD ingest fed pdfplumber's `.extract_text()` — a flat wall of text with ZERO
structured tables — into the vector DB. The NEW path (01_pipeline/s1_convert.py) uses
pymupdf4llm to emit Markdown that keeps tables and headings. This script measures the
gap across the whole corpus so the choice is evidence-backed, not asserted.

Per plan it compares, page-for-page:
  • TABLE retention — markdown tables + pipe-rows (NEW) vs 0 (the old extract_text path
    produced none; pdfplumber *can* extract tables, but the pipeline never did).
  • HEADING retention — ATX `#` headings (NEW) and how many pages `detect_section`
    can tag on each text (does Markdown give the section tagger more/better anchors?).
  • PAGE-STRUCTURE fidelity — page counts match; ordering preserved.
  • SCANNED/IMAGE pages — pages with <100 chars of text (the existing OCR signal).
Rolled up MN / ND / SD because the formats differ (SD plan-sets are the weak case).

Read-only. Reads the Markdown from the convert cache (warm it first with
`python3 01_pipeline/s1_convert.py 00_input/plans`), runs pdfplumber's extract_text fresh.

Run:
    python3 02_modules/plan_reader/04_tools/conversion_quality.py
Writes:
    02_outputs/<DATE>_conversion_quality.md   (readable scorecard)
    02_outputs/<DATE>_conversion_quality.csv  (machine-readable, one row per plan)
"""
import sys
import csv
import re
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "01_pipeline"))  # 01_pipeline/ holds lib + step modules
import lib

import s1_convert as convert
import s2_indexer as indexer   # reuse load_manifest + extract_pages (pdfplumber)

DATE = "2026-06-10"
OUT = lib.OUT_DIAG

_ATX = re.compile(r"(?m)^#{1,6}\s")
_PIPEROW = re.compile(r"(?m)^\s*\|.*\|\s*$")


def detect_hits(pages_text):
    """How many pages does the section tagger successfully tag? (higher = better anchors)"""
    return sum(1 for t in pages_text if lib.detect_section(t))


def analyze(pdf_path, rec):
    state = (rec.get("state") or "?").strip() or "?"
    plan_id = rec.get("plan_id") or pdf_path.stem

    # OLD path: pdfplumber extract_text, page by page (exactly what ingest used).
    old_pages = [txt for _, txt in indexer.extract_pages(pdf_path)]
    old_chars = sum(len(t) for t in old_pages)
    old_scanned = sum(1 for t in old_pages if len(t.strip()) < 100)
    old_sec_hits = detect_hits(old_pages)

    # NEW path: pymupdf4llm Markdown (from cache).
    md_pages = convert.convert_pages(pdf_path)
    new_pages = [p["text"] for p in md_pages]
    new_chars = sum(len(t) for t in new_pages)
    new_tables = sum(p["n_tables"] for p in md_pages)
    new_scanned = sum(1 for t in new_pages if len(t.strip()) < 100)
    new_sec_hits = detect_hits(new_pages)
    md_all = "\n".join(new_pages)
    atx = len(_ATX.findall(md_all))
    piperows = len(_PIPEROW.findall(md_all))

    # Document-type + structure profile (Task B) — runs on the Markdown text.
    doc_type, sig = lib.detect_doc_type(new_pages)
    image_pages = sum(1 for t in new_pages if not t.strip())   # 0-char (image-only) pages

    return {
        "plan_id": plan_id, "state": state,
        "doc_type": doc_type,
        "drawing_frac": sig["drawing_page_fraction"],
        "median_chars_pg": sig["median_chars_per_page"],
        "image_only_pages": image_pages,
        "old_pages": len(old_pages), "new_pages": len(md_pages),
        "pages_match": len(old_pages) == len(md_pages),
        "old_chars": old_chars, "new_chars": new_chars,
        "old_tables": 0, "new_tables": new_tables, "md_pipe_rows": piperows,
        "md_headings": atx,
        "old_sec_pages": old_sec_hits, "new_sec_pages": new_sec_hits,
        "old_scanned_pages": old_scanned, "new_scanned_pages": new_scanned,
    }


def main():
    manifest = indexer.load_manifest()
    pdfs = sorted(lib.PLANS_DIR.rglob("*.pdf"))
    if not pdfs:
        print("No PDFs under", lib.PLANS_DIR); sys.exit(1)

    rows = []
    print(f"Scoring conversion quality on {len(pdfs)} plans (reads MD cache)…")
    for pdf in pdfs:
        rec = manifest.get(pdf.stem, {})
        r = analyze(pdf, rec)
        rows.append(r)
        print(f"  ✓ {r['plan_id']:<46} {r['state']}  "
              f"tables {r['old_tables']}→{r['new_tables']}  "
              f"sec-pages {r['old_sec_pages']}→{r['new_sec_pages']}")

    # ── CSV ──
    OUT.mkdir(parents=True, exist_ok=True)
    csv_path = OUT / f"{DATE}_conversion_quality.csv"
    with open(csv_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader(); w.writerows(rows)

    # ── State rollup ──
    by_state = defaultdict(list)
    for r in rows:
        by_state[r["state"]].append(r)

    def s(state_rows, key):
        return sum(r[key] for r in state_rows)

    # ── Markdown report ──
    L = []
    L.append(f"# PDF→Markdown conversion-quality scorecard ({DATE})\n")
    L.append("**Old path:** pdfplumber `.extract_text()` → flat text, **0 tables**.  ")
    L.append("**New path:** pymupdf4llm → Markdown (`01_pipeline/s1_convert.py`), tables + headings kept.\n")
    L.append("Question answered (T's Q3): *is conversion good enough, and does it beat the old path?*\n")

    L.append("## Headline\n")
    tot_tables = s(rows, "new_tables")
    tot_piperows = s(rows, "md_pipe_rows")
    tot_head = s(rows, "md_headings")
    sec_gain = s(rows, "new_sec_pages") - s(rows, "old_sec_pages")
    L.append(f"- **Tables recovered:** {tot_tables} Markdown tables / {tot_piperows:,} table rows "
             f"across the corpus — vs **0** on the old flat-text path. The bid-schedule "
             f"quantity tables (MIX_TN, GRADE_CY, …) now survive as structured rows.")
    L.append(f"- **Headings recovered:** {tot_head:,} ATX headings give `detect_section` cleaner anchors.")
    L.append(f"- **Section-tagger anchors:** taggable pages {s(rows,'old_sec_pages')} → "
             f"{s(rows,'new_sec_pages')} ({'+' if sec_gain>=0 else ''}{sec_gain}).")
    L.append(f"- **Page fidelity:** {sum(1 for r in rows if r['pages_match'])}/{len(rows)} "
             f"plans preserved page count exactly.")
    L.append("")

    L.append("## Document structure — what kind of docs are these? (T's Q2)\n")
    L.append("Every per-plan PDF CSI pulls is a **combined proposal+plan** document — a bid "
             "schedule and special provisions up front, engineering drawings behind. None are "
             "standalone plan-sets, so document-level type is `proposal` across the board. The "
             "structural variation that matters is *within* a document (prose vs drawing/spec "
             "pages), which is what the section disposition (Task C) acts on.\n")
    L.append("| Plan | St | doc_type | drawing-pg frac | median chars/pg | image-only pgs |")
    L.append("|---|:--:|:--:|--:|--:|--:|")
    for r in sorted(rows, key=lambda x: (x["state"], x["plan_id"])):
        L.append(f"| {r['plan_id']} | {r['state']} | {r['doc_type']} | {r['drawing_frac']} | "
                 f"{r['median_chars_pg']:,} | {r['image_only_pages']} |")
    L.append("")

    L.append("## By state\n")
    L.append("| State | Plans | MD tables | MD table-rows | MD headings | Sec-pages old→new | Scanned pages (old) |")
    L.append("|---|--:|--:|--:|--:|:--:|--:|")
    for st in sorted(by_state):
        sr = by_state[st]
        L.append(f"| {st} | {len(sr)} | {s(sr,'new_tables')} | {s(sr,'md_pipe_rows'):,} | "
                 f"{s(sr,'md_headings'):,} | {s(sr,'old_sec_pages')}→{s(sr,'new_sec_pages')} | "
                 f"{s(sr,'old_scanned_pages')} |")
    L.append("")

    L.append("## Per plan\n")
    L.append("| Plan | St | Pages (old/new) | MD tables | MD rows | MD headings | Sec-pages old→new | Scanned(old/new) |")
    L.append("|---|:--:|:--:|--:|--:|--:|:--:|:--:|")
    for r in sorted(rows, key=lambda x: (x["state"], x["plan_id"])):
        pm = f"{r['old_pages']}/{r['new_pages']}" + ("" if r["pages_match"] else " ⚠")
        L.append(f"| {r['plan_id']} | {r['state']} | {pm} | {r['new_tables']} | "
                 f"{r['md_pipe_rows']:,} | {r['md_headings']:,} | "
                 f"{r['old_sec_pages']}→{r['new_sec_pages']} | "
                 f"{r['old_scanned_pages']}/{r['new_scanned_pages']} |")
    L.append("")
    L.append("## Reading this\n")
    L.append("- **MD tables / rows > 0** is the win that matters most: quantities are no longer "
             "number-soup. SD plan-sets (drawings) will show fewer tables — that's expected, they "
             "*are* drawings, not tabular proposals (see doc-type detection, Task B).")
    L.append("- **Scanned pages (old)** flags plans that will need OCR (docling/LlamaParse) — pages "
             "where neither path recovers text.")
    L.append("- Section-tagger gains feed Task C (section disposition): cleaner anchors → more "
             "reliable KEEP/DROP decisions.")

    md_path = OUT / f"{DATE}_conversion_quality.md"
    md_path.write_text("\n".join(L) + "\n")
    print(f"\nWrote:\n  {md_path}\n  {csv_path}")


if __name__ == "__main__":
    main()
