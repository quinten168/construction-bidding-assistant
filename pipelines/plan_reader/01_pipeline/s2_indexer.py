"""
s2_indexer.py  —  STEP 1: turn plan PDFs into searchable vectors.

    PDF  ->  Markdown (convert)  ->  drop/down-weight boilerplate  ->  chunks  ->  ChromaDB

Run (from the repo root):
    python3 pipelines/plan_reader/01_pipeline/s2_indexer.py pipelines/plan_reader/00_input/plans
    python3 .../01_pipeline/s2_indexer.py pipelines/plan_reader/00_input/plans --reset            # drop & rebuild
    python3 .../01_pipeline/s2_indexer.py pipelines/plan_reader/00_input/plans --keep-boilerplate # A/B: ingest everything
    python3 .../01_pipeline/s2_indexer.py <one.pdf> --trace                                    # also write a per-page kept/dropped CSV
    python3 .../01_pipeline/s2_indexer.py "pipelines/plan_reader/00_input/plans/2023_DUNN-CO-ND_CP-13_WON/2023_DUNN-CO-ND_CP-13.pdf"

INSPECTABILITY (2026-06-11): --trace writes 02_outputs/<date>_ingest_trace_<stem>.csv — one row
per page showing section, doc_type, the KEEP/DOWN_WEIGHT/DROP action, chunks kept vs dropped,
boilerplate paragraphs stripped, and whether a gotcha spared a DROP page. Open it to see
exactly which parts of a long plan were skipped vs preserved.

The corpus folder is searched recursively (rglob), so passing 00_input/plans/ picks up
every 00_input/plans/<plan_id>/x.pdf. doc_id and provenance (state/outcome/contract_id/
year/county/sp_number) come from plans_manifest.csv, keyed by PDF stem.

The front-end (Phase 2): instead of feeding pdfplumber's flat text straight in, we
  1. CONVERT each PDF to structure-preserving Markdown (convert; tables + headings kept),
  2. DETECT the document type (lib.detect_doc_type) and stamp it on every chunk,
  3. apply the SECTION TAXONOMY (knowledge/section_taxonomy.csv): stamp each chunk's
     `relevance` (DECISION/PRICING/BOILERPLATE — Alex's axis), skip DROP boilerplate,
     mark DOWN_WEIGHT prose, keep everything else — so the vector DB isn't diluted by the
     repetitive standard-spec / forms pages that drown out project-specific content. A page
     in a DROP section that still carries a gotcha is spared (kept, de-prioritized).
Pass --keep-boilerplate to ingest everything (the A/B baseline for measuring the win).

Design choices worth learning:
  • PAGE-AWARE chunking: we chunk within each page, so every chunk carries an exact
    `page` number ("the gotcha is on p.47"). (A chunk never spans a page boundary.)
  • DETERMINISTIC IDs ("{doc}:p{page}:c{idx}") + upsert => re-ingesting the same PDF
    REPLACES its chunks instead of duplicating them. Safe to re-run.
  • Embedding is done BY ChromaDB (the model is bound to the collection in lib.py).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # 01_pipeline/ on path → `import lib`/`import convert` work
import lib

import csv
import pdfplumber

# The PDF→Markdown converter (Step 0). Same dir (01_pipeline/), so a plain import works now that
# the digit prefixes are gone (was lib.load_step("s1_convert.py")).
import s1_convert as convert

# The plan corpus manifest is the source of truth for per-plan provenance
# (plan_id, state, outcome, contract_id, year, county, sp_number). We stamp each
# chunk with these so doc_ids are human-readable and the query filters work.
MANIFEST = lib.MANIFEST

# Manifest columns we copy onto every chunk's metadata.
MANIFEST_FIELDS = ("plan_id", "state", "outcome", "contract_id", "year", "county", "sp_number")


def load_manifest():
    """Return {pdf_stem: {plan_id, state, outcome, contract_id, year, county, sp_number}}
    from the plan manifest, or {} if it's missing. We key on the stem of the manifest's
    primary_pdf/source_file so the lookup matches the PDF we're ingesting (pdf.stem)."""
    if not MANIFEST.exists():
        print(f"  (no manifest at {MANIFEST}; chunk metadata will be sparse)")
        return {}
    out = {}
    for row in csv.DictReader(open(MANIFEST)):
        rec = {f: (row.get(f) or "").strip() for f in MANIFEST_FIELDS}
        for col in ("source_file", "primary_pdf"):
            fn = (row.get(col) or "").strip()
            if fn:
                out[Path(fn).stem] = rec
    return out


def extract_pages(pdf_path: Path):
    """Yield (page_number, text) for each page. Page numbers are 1-based."""
    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages, start=1):
            yield i, (page.extract_text() or "")


# Tier -> retrieval weight stamped on each chunk. DOWN_WEIGHT chunks stay searchable
# but a future re-ranker can de-prioritize them; DROP chunks are never stored.
_TIER_WEIGHT = {"KEEP": 1.0, "DOWN_WEIGHT": 0.3}


def ingest_pdf(pdf_path: Path, collection, rec=None, keep_boilerplate=False, disp_table=None, trace=None):
    """Convert one PDF to Markdown, drop/down-weight boilerplate, chunk, and upsert.
    Returns a stats dict {added, dropped, downweighted, doc_type, pages}. `rec` is the
    manifest record (plan_id, state, …) stamped onto every chunk.

    If `trace` is a list, append one row PER PAGE describing what ingest did with it
    (section, tier, chunks kept/dropped, boilerplate stripped, gotcha-spared) — the
    openable "what got kept vs tossed, and why" artifact (see main()'s --trace)."""
    rec = rec or {}
    doc_id = rec.get("plan_id") or pdf_path.stem        # human-readable doc key
    prov = {f: rec.get(f, "") for f in ("state", "outcome", "contract_id", "year", "county", "sp_number")}
    disp_table = lib.load_disposition() if disp_table is None else disp_table

    # STEP 0: PDF -> structure-preserving Markdown (cached on disk; tables/headings kept).
    md_pages = convert.convert_pages(pdf_path)
    total_text = sum(len(p["text"]) for p in md_pages)
    if total_text < 100:
        print(f"  ⚠️  {pdf_path.name}: <100 chars converted — likely image-only/scanned "
              f"(needs OCR: docling/LlamaParse). Skipping.")
        return {"added": 0, "dropped": 0, "downweighted": 0, "doc_type": "?", "pages": len(md_pages)}

    # STEP 2: one document-type label for the whole PDF, stamped on every chunk.
    doc_type, _ = lib.detect_doc_type([p["text"] for p in md_pages])

    fingerprints = set() if keep_boilerplate else lib.load_boilerplate_fingerprints()
    ids, docs, metas = [], [], []
    dropped = downweighted = boiler_paras = spared = 0
    # Section per page: header detection w/ carry-forward + the proposal front-matter position
    # rule, computed once here so ingest and demo can't drift (lib.page_sections).
    sections = lib.page_sections([p["text"] for p in md_pages], doc_type)

    for pg, current_section in zip(md_pages, sections):
        page_no, text = pg["page"], pg["text"]
        # STEP 3a: paragraph-level toss-out — strip cross-plan boilerplate (gotcha-safe).
        text, n_boiler = lib.strip_boilerplate_paragraphs(text, fingerprints)
        boiler_paras += n_boiler
        # STEP 3b: section-level disposition — what do we do with this section's content?
        tier = lib.disposition_for(current_section, doc_type, disp_table)
        # Gotcha guard: never DROP a page that still carries a decision gotcha. Downgrade the
        # DROP to DOWN_WEIGHT (kept, de-prioritized) so the "tier, don't delete a gotcha"
        # invariant holds even inside a boilerplate section.
        spared_this_page = False
        if tier == "DROP" and not keep_boilerplate and lib.page_has_gotcha(text):
            tier = "DOWN_WEIGHT"
            spared += 1
            spared_this_page = True
        relevance = lib.relevance_for(current_section, doc_type)
        page_chunks = lib.chunk_text(text)
        page_dropped = tier == "DROP" and not keep_boilerplate
        if trace is not None:
            trace.append({
                "doc_id": doc_id,
                "page": page_no,
                "section": current_section,
                "doc_type": doc_type,
                "relevance": relevance,
                "tier": tier,
                "action": "DROP" if page_dropped else ("DOWN_WEIGHT" if tier == "DOWN_WEIGHT" else "KEEP"),
                "chunks_kept": 0 if page_dropped else len(page_chunks),
                "chunks_dropped": len(page_chunks) if page_dropped else 0,
                "boiler_paras_stripped": n_boiler,
                "gotcha_spared": int(spared_this_page),
                "is_drawing": int(lib.is_drawing_page(text)),
                "n_chars": len(text),
            })
        if page_dropped:
            dropped += len(page_chunks)
            continue
        if tier == "DOWN_WEIGHT":
            downweighted += len(page_chunks)
        for c_idx, chunk in enumerate(page_chunks):
            ids.append(f"{doc_id}:p{page_no}:c{c_idx}")
            docs.append(chunk)
            metas.append({
                "source_file": pdf_path.name,
                "doc_id": doc_id,
                "doc_type": doc_type,
                "page": page_no,
                "section": current_section,
                "relevance": relevance,          # DECISION / PRICING / BOILERPLATE (Alex's axis)
                "disposition": tier,
                "weight": _TIER_WEIGHT.get(tier, 1.0),
                "is_drawing": lib.is_drawing_page(text),
                "n_chars": len(chunk),
                **prov,
            })

    if not ids:
        print(f"  ⚠️  {pdf_path.name}: no chunks produced (all dropped?).")
        return {"added": 0, "dropped": dropped, "downweighted": 0, "spared": spared,
                "boiler_paras": boiler_paras, "doc_type": doc_type, "pages": len(md_pages)}

    # upsert (not add) => idempotent. Chroma embeds each `document` with MiniLM here.
    collection.upsert(ids=ids, documents=docs, metadatas=metas)
    bp_note = f", stripped {boiler_paras} boilerplate paras" if boiler_paras else ""
    drop_note = f", dropped {dropped} DROP-section chunks" if dropped else ""
    dw_note = f", down-weighted {downweighted}" if downweighted else ""
    spared_note = f", spared {spared} gotcha pages from DROP" if spared else ""
    print(f"  ✓ {pdf_path.name} [{doc_type}]: {len(ids)} chunks across {len(md_pages)} pages"
          f"{dw_note}{drop_note}{spared_note}{bp_note}")
    return {"added": len(ids), "dropped": dropped, "downweighted": downweighted, "spared": spared,
            "boiler_paras": boiler_paras, "doc_type": doc_type, "pages": len(md_pages)}


def collect_pdfs(args):
    paths = []
    for a in args:
        p = Path(a)
        if p.is_dir():
            # rglob: the corpus is nested one level (plans/<plan_id>/x.pdf).
            paths.extend(sorted(p.rglob("*.pdf")))
        elif p.suffix.lower() == ".pdf":
            paths.append(p)
        else:
            print(f"  (skipping non-pdf: {a})")
    return paths


def main():
    flags = {"--reset", "--keep-boilerplate", "--trace"}
    args = [a for a in sys.argv[1:] if a not in flags]
    reset = "--reset" in sys.argv[1:]
    keep_boilerplate = "--keep-boilerplate" in sys.argv[1:]
    do_trace = "--trace" in sys.argv[1:]
    if not args:
        print(__doc__)
        sys.exit(1)

    pdfs = collect_pdfs(args)
    if not pdfs:
        print("No PDFs found.")
        sys.exit(1)

    print(f"Loading collection '{lib.COLLECTION}' (first run downloads the "
          f"{lib.EMBED_MODEL} model, ~80MB)…")
    if reset:
        # doc_ids changed (now plan_id, not pdf stem), so old stem-keyed chunks
        # would linger as orphans. --reset drops the whole collection first.
        import chromadb
        client = chromadb.PersistentClient(path=str(lib.CHROMA_DIR))
        try:
            client.delete_collection(lib.COLLECTION)
            print(f"  --reset: dropped existing collection '{lib.COLLECTION}'.")
        except Exception:
            pass
    col = lib.get_collection()
    before = col.count()

    manifest = load_manifest()
    disp_table = lib.load_disposition()
    mode = "KEEP-ALL (boilerplate included)" if keep_boilerplate else \
           f"disposition ON ({len(disp_table)} section rules)"
    print(f"Ingesting {len(pdfs)} PDF(s) — {mode}:")
    total = dropped = downweighted = boiler = spared = 0
    trace = [] if do_trace else None
    for pdf in pdfs:
        st = ingest_pdf(pdf, col, rec=manifest.get(pdf.stem),
                        keep_boilerplate=keep_boilerplate, disp_table=disp_table, trace=trace)
        total += st["added"]; dropped += st["dropped"]; downweighted += st["downweighted"]
        boiler += st.get("boiler_paras", 0); spared += st.get("spared", 0)

    if do_trace and trace:
        import datetime
        stem = lib.plan_id_for(pdfs[0].stem) if len(pdfs) == 1 else "corpus"
        lib.OUT_PER_PLAN.mkdir(parents=True, exist_ok=True)
        trace_path = lib.OUT_PER_PLAN / f"{datetime.date.today().isoformat()}_ingest_trace_{stem}.csv"
        cols = ["doc_id", "page", "section", "doc_type", "relevance", "tier", "action",
                "chunks_kept", "chunks_dropped", "boiler_paras_stripped", "gotcha_spared",
                "is_drawing", "n_chars"]
        with open(trace_path, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=cols)
            w.writeheader()
            w.writerows(trace)
        print(f"\n  ↳ per-page ingest trace ({len(trace)} pages): {trace_path}")

    after = col.count()
    print(f"\nDone. Added/updated {total} chunks this run "
          f"(down-weighted {downweighted}, dropped {dropped} DROP-section chunks, "
          f"spared {spared} gotcha pages from DROP, "
          f"stripped {boiler} boilerplate paragraphs). "
          f"Collection now holds {after} chunks (was {before}).")
    print(f"DB on disk: {lib.CHROMA_DIR}")


if __name__ == "__main__":
    main()
