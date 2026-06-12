"""
flag_suspect_tags.py — surface SUSPECT section tags / retrievals for human review.

The eval scores field *extraction* (vs golden) and section *recall* ("no-section-found rate"), but
nothing scored section-tag *precision* — so a confident-but-WRONG tag (e.g. a proposal cover page
mis-labeled `special_provisions` because it *references* the special provisions) slipped through.
This read-only script flags candidates a human then confirms into the ledger
(`data/section_tag_ledger.csv`).

Three heuristics (NO Claude calls — chunk metadata + PDF re-read + retrieval only):
  1. cross_ref_false_positive — a short line matches a section keyword AND a cross-ref cue
     ("...SEE ATTACHED", "...REFER TO..."): it points to a section, it isn't one.
  2. weak_retrieval — an info-type probe's top hit has distance > 0.65: the field is probably not
     really there (or it's SD drawing-soup), so whatever section it landed on is unreliable.
  3. single_page_section — a section that spans exactly one page is usually a stray match
     (legitimately-short sections like title_index / proposal_front are excluded).

Writes 02_outputs/2026-06-09_suspect_tags.csv with the SAME columns as the ledger (+ blank verdict /
correct_section) so confirmed rows paste straight in.

Run:
    .venv/bin/python 02_modules/plan_reader/04_tools/flag_suspect_tags.py
"""
import sys
import csv
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).resolve().parent))               # this dir (04_tools/) for sibling imports
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "01_pipeline"))  # 01_pipeline/ holds lib + step modules
import lib

import s2_indexer as ingest_mod
import retriever as query_mod
import location_map as location_mod   # sibling tool, reuse INFO_TYPES

OUT = lib.OUT_DIAG
PLANS_DIR = lib.PLANS_DIR
DATE = "2026-06-09"
WEAK_DIST = 0.65
# Sections that are legitimately one page — don't flag these as single_page_section.
SHORT_OK = {"title_index", "proposal_front", "unknown"}
LEDGER_COLS = ["plan", "page", "info_type", "tagged_section", "correct_section",
               "error_type", "distance", "verdict", "notes"]


def pdf_for(doc_id):
    d = PLANS_DIR / doc_id
    return next(d.glob("*.pdf"), None) if d.is_dir() else next(PLANS_DIR.rglob(f"{doc_id}.pdf"), None)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    col = lib.get_collection()
    meta = col.get(include=["metadatas"])["metadatas"]
    doc_ids = sorted({m["doc_id"] for m in meta})

    # page -> current assigned section, and section -> pages, per doc (from metadata).
    page_tag = defaultdict(dict)                       # doc -> {page: section}
    sec_pages = defaultdict(lambda: defaultdict(set))  # doc -> section -> {pages}
    for m in meta:
        d, pg = m["doc_id"], m.get("page", 0)
        page_tag[d][pg] = m.get("section", "unknown")
        sec_pages[d][m.get("section", "unknown")].add(pg)

    rows = []
    counts = defaultdict(int)

    # ── Heuristic 1: cross-reference lines that name a section ────────────────
    for d in doc_ids:
        pdf = pdf_for(d)
        if pdf is None:
            print(f"   ! {d}: PDF not found; skipping cross-ref scan")
            continue
        for page_no, text in ingest_mod.extract_pages(pdf):
            for raw in text.splitlines():
                s = raw.strip()
                if not s or len(s) > 60:
                    continue
                up = s.upper()
                if not lib._CROSSREF_CUE.search(up):
                    continue
                for name, pat in lib._SECTION_COMPILED:
                    if pat.search(up):
                        rows.append(dict(plan=d, page=page_no, info_type="",
                                         tagged_section=page_tag[d].get(page_no, "?"),
                                         correct_section="", error_type="cross_ref_false_positive",
                                         distance="", verdict="",
                                         notes=f"line references '{name}': \"{s[:70]}\""))
                        counts["cross_ref_false_positive"] += 1
                        break

    # ── Heuristic 2: weak-retrieval probes ───────────────────────────────────
    for info, q in location_mod.INFO_TYPES:
        for d in doc_ids:
            hits = query_mod.retrieve(col, q, 1, where={"doc_id": d})
            if not hits:
                continue
            h = hits[0]
            if h["distance"] > WEAK_DIST:
                rows.append(dict(plan=d, page=h["meta"]["page"], info_type=info,
                                 tagged_section=h["meta"].get("section", "?"), correct_section="",
                                 error_type="weak_retrieval", distance=round(h["distance"], 3),
                                 verdict="", notes=f"top hit dist {h['distance']:.3f} > {WEAK_DIST} — field likely absent/unreliable"))
                counts["weak_retrieval"] += 1

    # ── Heuristic 3: single-page sections ────────────────────────────────────
    for d in doc_ids:
        for sec, pages in sec_pages[d].items():
            if sec in SHORT_OK or len(pages) != 1:
                continue
            rows.append(dict(plan=d, page=min(pages), info_type="", tagged_section=sec,
                             correct_section="", error_type="single_page_section", distance="",
                             verdict="", notes="section spans exactly one page — possible stray match"))
            counts["single_page_section"] += 1

    out_csv = OUT / f"{DATE}_suspect_tags.csv"
    with open(out_csv, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=LEDGER_COLS)
        w.writeheader()
        w.writerows(rows)

    print(f"\n✓ wrote {out_csv.name}  ({len(rows)} suspects)")
    for k in ("cross_ref_false_positive", "weak_retrieval", "single_page_section"):
        print(f"   {k:26} {counts[k]}")
    print("\nNext: triage these, then paste confirmed rows into "
          "03_evaluation/2026-06-09_section_tag_ledger.csv with a verdict + correct_section.")


if __name__ == "__main__":
    main()
