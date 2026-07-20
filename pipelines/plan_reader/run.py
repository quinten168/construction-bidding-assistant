"""
run.py — the Plan Reader's one-command driver: "drop in one PDF, inspect every step."

    python3 pipelines/plan_reader/run.py inspect <plan.pdf>
    python3 pipelines/plan_reader/run.py inspect <plan.pdf> --no-llm     # structure only, no Claude calls

Runs the whole read path on a SINGLE plan PDF, assembles one canonical structured record
(01_pipeline/schema.py), and leaves an OPENABLE artifact at every step:

    01_pipeline/convert      ->  00_input/plans/<plan_id>/<plan_id>.md    (readable Markdown: tables + headings)
    01_pipeline/indexer      ->  02_outputs/per_plan/<date>_ingest_trace_<plan>.csv  (per page: KEEP/DOWN_WEIGHT/DROP)
                       ->  chunks upserted into ChromaDB (so the RAG step is live)
    01_pipeline/extract      ->  whole-doc fields (identity + bid-schedule quantities), each {value,conf,page}
    01_pipeline/extract_rag  ->  mid-doc fields (traffic_level, construction dates, phasing) + gotchas[],
                          retrieved + STRUCTURED (not prose)

…combined into the interface artifacts:

    00_input/plans/<plan_id>/<plan_id>.json   ← the SOURCE OF TRUTH (per-field value/confidence/page)
    02_outputs/results.csv                   ← flattened review view, one upserted row per plan
    02_outputs/per_plan/<date>_brief_<plan_id>.md   ← human-readable brief (rendered from the record)

This is a demo of the automated read, not a verified extraction. (Was tools/demo_brief.py.)
"""
import sys
import csv
import datetime
from pathlib import Path
from collections import defaultdict

# 01_pipeline/ holds lib + the read-path step modules; one insert and every plain import below resolves.
sys.path.insert(0, str(Path(__file__).resolve().parent / "01_pipeline"))
import lib
import schema
import s1_convert as convert
import s2_indexer as indexer
import s3_extract as extract
import s4_extract_rag as extract_rag
import retriever
import taxonomy

DATE = datetime.date.today().isoformat()
OUT = lib.OUT_PER_PLAN

# Trace columns — kept in sync with 01_pipeline/s2_indexer.py's --trace CSV so the two artifacts match.
TRACE_COLS = ["doc_id", "page", "section", "doc_type", "relevance", "tier", "action",
              "chunks_kept", "chunks_dropped", "boiler_paras_stripped", "gotcha_spared",
              "is_drawing", "n_chars"]


def write_trace(trace, stem):
    """Write the per-page ingest trace CSV (same shape 01_pipeline/s2_indexer.py --trace produces)."""
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"{DATE}_ingest_trace_{stem}.csv"
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=TRACE_COLS)
        w.writeheader()
        w.writerows(trace)
    return path


def main():
    argv = sys.argv[1:]
    if argv and argv[0] == "inspect":          # `run.py inspect <pdf>` — verb is optional
        argv = argv[1:]
    no_llm = "--no-llm" in argv
    args = [a for a in argv if not a.startswith("--")]
    if not args:
        print(__doc__); sys.exit(1)
    pdf = Path(args[0])
    if not pdf.exists():
        print("PDF not found:", pdf); sys.exit(1)

    # Page-size doc structure FIRST: a bid package is a proposal (8.5x11) + a plan set / maps (11x17).
    # We handle proposals + hybrids; a plan-set-only PDF (all tabloid) has no bid schedule/dates/wages —
    # skip it entirely for now (proposals only).
    structure = lib.detect_structure(pdf)
    if structure["type"] == "plan_set":
        print(f"  ⏭  {pdf.name} is a PLAN-SET-only document "
              f"({structure['n_pages']} tabloid/map pages, no proposal) — skipping "
              f"(proposals + hybrids only for now).")
        return
    print(f"  document structure: {structure['type']} · {structure['n_pages']} pages · "
          f"maps on {structure['map_ranges'] or 'none'}")

    manifest = indexer.load_manifest()
    rec = manifest.get(pdf.stem, {})
    plan_id = rec.get("plan_id") or pdf.stem
    artifacts = []   # (label, path) — printed at the end so the user knows what to open

    print(f"[1/4] Converting {pdf.name} to Markdown…")
    md_pages = convert.convert_pages(pdf)
    md_path = convert.write_markdown(pdf, md_pages)             # ← openable .md
    artifacts.append(("Readable Markdown", md_path))
    n_tables = sum(p["n_tables"] for p in md_pages)
    md_chars = sum(len(p["text"]) for p in md_pages)
    doc_type, sig = lib.detect_doc_type([p["text"] for p in md_pages])

    # Section walk via the shared lib.page_sections (header carry-forward + proposal front-matter
    # position rule) so the brief matches exactly how ingest sectioned the doc.
    disp_table = lib.load_disposition()
    sections = lib.page_sections([p["text"] for p in md_pages], doc_type)
    sec_pages = defaultdict(lambda: {"pages": 0, "tier": "KEEP", "relevance": "DECISION"})
    for sec in sections:
        sec_pages[sec]["pages"] += 1
        sec_pages[sec]["tier"] = lib.disposition_for(sec, doc_type, disp_table)
        sec_pages[sec]["relevance"] = lib.relevance_for(sec, doc_type)

    print(f"[2/4] Ingesting into ChromaDB (so RAG answers are live)…")
    col = lib.get_collection()
    trace = []
    stats = indexer.ingest_pdf(pdf, col, rec=rec, disp_table=disp_table, trace=trace)
    trace_path = write_trace(trace, plan_id)                    # ← openable per-page kept/dropped CSV
    artifacts.append(("Per-page ingest trace", trace_path))

    # ── Schema-driven structured extraction → one canonical record (the JSON source of truth) ──
    record = schema.blank_record(plan_id, pdf.name, DATE)
    # store the readable summary (ranges), not the raw per-page lists
    record["document_structure"] = {k: structure[k] for k in
                                    ("type", "n_pages", "proposal_ranges", "map_ranges", "boundary_page")}
    if not no_llm:
        print(f"[3/4] Whole-doc extraction (identity + bid-schedule quantities, proposal pages)…")
        # Feed only the PROPOSAL (letter-size) pages — cleaner quantities, no map-page noise.
        prop_set = set(structure["proposal_pages"])
        proposal_md = convert.pages_to_markdown([p for p in md_pages if p["page"] in prop_set])
        truncated = extract.smart_truncate(proposal_md, extract.MAX_CHARS)
        extract.fill_extract_fields(record, truncated)
        print(f"[4/4] Structured RAG (traffic level → map pages, dates, phasing, gotchas)…")
        extract_rag.fill_rag_fields(record, col, plan_id, map_pages=structure["map_pages"])
        json_path = lib.write_json(pdf, record)            # ← per-PDF JSON, the interface contract
        artifacts.append(("Structured extraction (JSON — source of truth)", json_path))
        lib.mark_processed(plan_id, DATE)                  # ← manifest = live 'what's processed' tracker
    else:
        print("[3/4] --no-llm: skipping Claude extraction + RAG (record stays empty).")

    meta = {"outcome": rec.get("outcome", ""), "pages": len(md_pages), "n_chunks": stats["added"]}
    # (1) WIDE aggregate — one upserted row per plan.
    lib.upsert_csv(lib.RESULTS_CSV, "plan_id", schema.flatten_row(record, meta), schema.CSV_COLUMNS)
    artifacts.append(("Results aggregator — wide, one row/plan", lib.RESULTS_CSV))
    # (2) LONG aggregate — one row per flagged gotcha/item (for client review + taxonomy work).
    if not no_llm:
        page_section = lib.page_section_map(col, plan_id)
        gotcha_family = {c: t["family"] for c, t in taxonomy.GOTCHA_TYPES.items()}
        flags = schema.flag_rows(record, meta, page_section, gotcha_family)
        lib.replace_rows(lib.FLAGS_CSV, "plan_id", plan_id, flags, schema.FLAG_COLUMNS)
        artifacts.append((f"Flags aggregator — long, {len(flags)} flag rows this plan", lib.FLAGS_CSV))

    # ── Build the human-readable brief (rendered from the same record) ──
    L = [f"# Bid Brief — {plan_id}\n",
         f"*Generated by the Plan Reader pipeline from a single PDF "
         f"(`{pdf.name}`). This is a demo of the automated read, not a verified extraction.*\n",
         "## 1. Document\n",
         "| Field | Value |", "|---|---|",
         f"| Plan | {plan_id} |",
         f"| State | {rec.get('state','?')} |",
         f"| Outcome | {rec.get('outcome','?')} |",
         f"| Contract ID | {rec.get('contract_id','—')} |",
         f"| Package type | **{structure['type']}** (by page size: proposal=8.5×11, maps=11×17) |",
         f"| Pages | {structure['n_pages']} |",
         f"| Proposal pages | {structure['proposal_ranges'] or '—'} |",
         f"| **Maps / plan-set on pages** | **{structure['map_ranges'] or 'none'}** |", ""]

    L += ["## 2. Conversion & preprocessing\n",
          f"- **Converted to Markdown:** {len(md_pages)} pages, **{n_tables} tables recovered**, "
          f"{md_chars:,} chars (the bid-schedule quantities survive as real tables — not number-soup).",
          f"- **Chunks stored:** {stats['added']}  ·  down-weighted: {stats['downweighted']}  ·  "
          f"**dropped as boilerplate: {stats['dropped']}**.",
          "",
          "**Section disposition (what we kept vs skipped, and why):** "
          "*Relevance is Alex's axis — DECISION drives bid/no-bid, PRICING is needed only to "
          "price the work, BOILERPLATE is standard contract language. Tier is what the vector "
          "store does with it.*\n",
          "| Section | Relevance | Pages | Tier |", "|---|:--:|--:|:--:|"]
    for sec, d in sorted(sec_pages.items(), key=lambda kv: -kv[1]["pages"]):
        L.append(f"| {sec} | {d['relevance']} | {d['pages']} | {d['tier']} |")
    L.append("")

    L.append("## 3. Extracted fields  *(value · confidence · page)*\n")
    if no_llm:
        L.append("*(skipped — ran with --no-llm)*\n")
    else:
        L += ["| Field | Value | Conf | Page |", "|---|---|:--:|--:|"]
        for f in schema.SCALAR_FIELDS:
            c = record[f["name"]]
            val = "—" if c["value"] in (None, "") else str(c["value"]).replace("\n", " ")
            L.append(f"| {f['name']} | {val} | {c['confidence'] or '—'} | {c['page'] or '—'} |")
        L.append("")
        sr = record["special_requirements"]
        if sr:
            L.append("**Special requirements:**\n")
            for x in sr:
                L.append(f"- {x['text']}" + (f"  *(p.{x['page']})*" if x.get("page") else ""))
            L.append("")

    if not no_llm:
        g = record["gotchas"]
        L.append("## 4. Gotchas  *(taxonomy-coded, with cited evidence)*\n")
        if g:
            L += ["| Code | Evidence | Page | Conf |", "|---|---|--:|:--:|"]
            for x in g:
                ev = str(x.get("evidence", "")).replace("\n", " ")[:160]
                L.append(f"| `{x['code']}` | {ev} | {x.get('page') or '—'} | {x.get('confidence') or '—'} |")
        else:
            L.append("*(none detected)*")
        L.append("")

    L.append("## Caveats\n")
    L.append("- Automated first-pass read — values are **not human-verified**.")
    L.append("- Quantities are read from the bid-schedule table; cross-check the table on the "
             "cited page before relying on a number.")
    L.append(f"- Doc-type heuristic signals: {sig}")

    OUT.mkdir(parents=True, exist_ok=True)
    out_path = OUT / f"{DATE}_brief_{plan_id}.md"
    out_path.write_text("\n".join(L) + "\n")
    artifacts.append(("Combined brief", out_path))

    print("\n── Artifacts you can open ─────────────────────────────────────────")
    for label, path in artifacts:
        print(f"  • {label}: {path}")


if __name__ == "__main__":
    main()
