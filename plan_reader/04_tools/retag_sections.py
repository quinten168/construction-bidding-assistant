"""
retag_sections.py — re-apply section tags after a detect_section change.

When `lib.SECTION_PATTERNS` / `detect_section` changes (e.g. the v2 ND `contract_front`
patterns), existing chunks keep their OLD `section` metadata. This re-tags every chunk
WITHOUT re-embedding: it re-extracts each plan's page text from the PDF, recomputes the
carry-forward section per page exactly as ingest does, then `collection.update`s the `section`
field on each chunk (text + vectors untouched).

We must re-read the PDFs (not the stored chunk text): detect_section keys on short header
LINES, and chunk text is sentence-packed with the line structure lost — so reconstructing
from chunks would mis-detect headers.

Run:
    .venv/bin/python 02_modules/plan_reader/04_tools/retag_sections.py
"""
import sys
from pathlib import Path
from collections import Counter

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "01_pipeline"))  # 01_pipeline/ holds lib + step modules
import lib

# Reuse the ingest step's extract_pages (same text the original tagging saw).
import s2_indexer as ingest_mod

PLANS_DIR = lib.PLANS_DIR


def page_sections_for(pdf_path: Path):
    """Replicate ingest_pdf's carry-forward: {page_no: section} for one PDF."""
    current = "unknown"
    out = {}
    for page_no, text in ingest_mod.extract_pages(pdf_path):
        sec = lib.detect_section(text)
        if sec:
            current = sec
        out[page_no] = current
    return out


def main():
    col = lib.get_collection()
    meta = col.get(include=["metadatas"])["metadatas"]
    doc_ids = sorted({m["doc_id"] for m in meta})

    before = Counter(m.get("section", "?") for m in meta)
    total_changed = 0

    for doc_id in doc_ids:
        # doc_id is the plan_id (= the folder name), so the PDF is plans/<doc_id>/*.pdf.
        # (The file itself may be named anything, e.g. 9804001.pdf or "00 Prosoal.pdf".)
        pdf = next((PLANS_DIR / doc_id).glob("*.pdf"), None) if (PLANS_DIR / doc_id).is_dir() \
            else next(PLANS_DIR.rglob(f"{doc_id}.pdf"), None)   # fallback: doc_id == stem
        if pdf is None:
            print(f"   ! {doc_id}: PDF not found under plans/; skipping (keeps old tags)")
            continue
        page_sec = page_sections_for(pdf)
        got = col.get(where={"doc_id": doc_id}, include=["metadatas"])
        ids, metas = got["ids"], got["metadatas"]
        changed = 0
        for m in metas:
            new = page_sec.get(m["page"], m.get("section"))
            if new != m.get("section"):
                changed += 1
            m["section"] = new
        col.update(ids=ids, metadatas=metas)
        total_changed += changed
        print(f"   ✓ {doc_id:42} {len(ids)} chunks, {changed} re-tagged")

    after = Counter(m.get("section", "?")
                    for m in col.get(include=["metadatas"])["metadatas"])
    print(f"\nRe-tagged {total_changed} chunks (no re-embedding).")
    print(f"{'section':20} {'before':>7} {'after':>7}")
    for s in sorted(set(before) | set(after)):
        print(f"{s:20} {before.get(s,0):>7} {after.get(s,0):>7}")


if __name__ == "__main__":
    main()
