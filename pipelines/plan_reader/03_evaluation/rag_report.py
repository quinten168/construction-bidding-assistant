"""
rag_report.py  —  RUN the RAG and SAVE the results so they can be reviewed/tuned.

The earlier query script printed answers to the terminal only — nothing was saved, so
every run evaporated. This script runs a fixed DIAGNOSTIC QUERY BATTERY against the
ingested corpus and writes three artifacts to 02_outputs/:

  1. <date>_rag_corpus_report.md   — what's in the vector DB (chunks/doc, section mix,
                                     chunk-size stats). This is what you read to decide
                                     whether the CHUNKING strategy needs to change.
  2. <date>_rag_query_results.md   — per query: the retrieved chunks (page, section,
                                     distance, preview) + the grounded cited answer.
  3. <date>_rag_retrieval_metrics.csv — one row per query: top/mean distance, #docs hit,
                                     sections hit, whether the answer was "not found".
                                     Sort this to see which queries retrieve weakly.

The query battery is DIAGNOSTIC: most questions have a known answer (from the two cached
extractions) so you can judge whether retrieval found the right chunk. Two are deliberate
controls — an absent topic that SHOULD return "not found", and prevailing wages (which the
smart_truncate extractor misses) to test whether RAG recovers it.

Run (costs ~1 Claude call per query unless --no-llm):
    .venv/bin/python pipelines/plan_reader/03_evaluation/rag_report.py
    ... --no-llm        # retrieval only, no API cost (still saves corpus + metrics)
    ... -k 6            # retrieve more chunks per query
"""
import sys
import csv
import argparse
import datetime
from pathlib import Path
from collections import Counter, defaultdict

sys.path.insert(0, str(Path(__file__).resolve().parent / ".." / "01_pipeline"))  # 01_pipeline/ holds lib + step modules
import lib

# Reuse the query script's retrieval + synthesis so we don't duplicate logic.
import retriever as query_mod

OUT = lib.OUT_DIAG
DATE = datetime.date.today().isoformat()

# ── The diagnostic query battery ──────────────────────────────────────────────
# Each: (question, why_we_ask). "why" is printed in the report so a reviewer
# knows what a good answer looks like.
QUERIES = [
    ("What are the prevailing wage or Davis-Bacon wage requirements?",
     "CONTROL: smart_truncate drops this mid-doc field (extractor scores 0%). "
     "Does RAG recover it? If yes, that's the case for RAG-based extraction."),
    ("Are there construction phasing or staging requirements?",
     "Known gotcha in SAP 032 (two-phase construction)."),
    ("Is there a box culvert in the project scope?",
     "Both plans have BOX=X — retrieval should hit culvert pay items / notes."),
    ("Is dewatering or groundwater control required?",
     "Known gotcha in 08MQ (box culvert dewatering, groundwater elev 1442)."),
    ("Are there historic bridge, Section 4(f), or MOA cultural resource requirements?",
     "Known gotcha in 08MQ (NRHP-eligible historic bridge, MOA)."),
    ("Is there a high pressure gas line or utility conflict in the project area?",
     "Known gotcha in SAP 032 (Enterprise Products high-pressure gas line)."),
    ("Are there seasonal work restrictions for endangered species like the NLEB or whooping crane?",
     "Known gotcha in 08MQ (NLEB Apr15-Oct31, whooping crane stoppage)."),
    ("What is the total tonnage of hot mix asphalt (HMA / mix)?",
     "Quantity retrieval — should hit the bid schedule / estimated quantities."),
    ("What earthwork or grading excavation quantity in cubic yards is required?",
     "Quantity retrieval — grade_cy; tests bid-schedule retrieval."),
    ("What is the marketing budget and social media advertising plan for this project?",
     "CONTROL: absent topic. Correct behaviour = 'Not found in the retrieved sections.'"),
]


def corpus_report(col):
    """Pull every chunk's metadata and summarize the collection for chunking decisions."""
    data = col.get(include=["metadatas", "documents"])
    metas, docs = data["metadatas"], data["documents"]
    n = len(metas)

    by_doc = Counter(m["doc_id"] for m in metas)
    by_section = Counter(m.get("section", "unknown") for m in metas)
    sec_by_doc = defaultdict(Counter)
    for m in metas:
        sec_by_doc[m["doc_id"]][m.get("section", "unknown")] += 1

    sizes = sorted(len(d.split()) for d in docs)           # words per chunk
    char_sizes = sorted(m.get("n_chars", 0) for m in metas)

    def pct(arr, p):
        return arr[min(len(arr) - 1, int(len(arr) * p))] if arr else 0

    lines = [f"# RAG Corpus Report — {DATE}", "",
             f"Vector DB: `{lib.CHROMA_DIR}`  ·  collection `{lib.COLLECTION}`  ·  "
             f"embedding `{lib.EMBED_MODEL}` (384-dim, cosine)", "",
             f"**{n:,} chunks** across **{len(by_doc)} documents**.", "",
             "## Chunks per document", "",
             "| Document | Chunks |", "|---|--:|"]
    for d, c in by_doc.most_common():
        lines.append(f"| {d} | {c} |")

    lines += ["", "## Section tag distribution (heuristic tagger)", "",
              "Soft signal only — used for citations + optional `--section` filtering. "
              "A high `unknown` share means the header patterns miss that DOT's format.", "",
              "| Section | Chunks | Share |", "|---|--:|--:|"]
    for s, c in by_section.most_common():
        lines.append(f"| {s} | {c} | {100*c/n:.0f}% |")

    lines += ["", "## Chunk size distribution (words per chunk)", "",
              f"Target is ~350 words / ~50 overlap (set in `lib.chunk_text`).", "",
              "| Stat | Words | Chars |", "|---|--:|--:|",
              f"| min | {sizes[0]} | {char_sizes[0]:,} |",
              f"| p25 | {pct(sizes,.25)} | {pct(char_sizes,.25):,} |",
              f"| median | {pct(sizes,.5)} | {pct(char_sizes,.5):,} |",
              f"| p75 | {pct(sizes,.75)} | {pct(char_sizes,.75):,} |",
              f"| max | {sizes[-1]} | {char_sizes[-1]:,} |",
              "", "### Section mix per document", ""]
    for d in by_doc:
        top = ", ".join(f"{s} {c}" for s, c in sec_by_doc[d].most_common(4))
        lines.append(f"- **{d}** — {top}")

    return "\n".join(lines) + "\n"


def run_queries(col, k, use_llm):
    """Run the battery; return (markdown_report, metrics_rows)."""
    md = [f"# RAG Query Results — {DATE}", "",
          f"Retrieved top-{k} chunks per query (cosine distance, lower = closer). "
          f"{'Grounded Claude answer included.' if use_llm else 'Retrieval only (--no-llm).'}", "",
          "Distance rule of thumb (from prior runs): **<0.45 strong · 0.45–0.65 moderate · "
          ">0.7 weak/likely-absent**.", ""]
    metrics = []

    for q, why in QUERIES:
        hits = query_mod.retrieve(col, q, k)
        dists = [h["distance"] for h in hits]
        docs_hit = sorted({h["meta"]["doc_id"] for h in hits})
        secs_hit = sorted({h["meta"].get("section", "?") for h in hits})

        md += [f"## Q: {q}", "", f"*Why we ask:* {why}", "",
               "| # | Document | Page | Section | Distance | Preview |",
               "|--:|---|--:|---|--:|---|"]
        for i, h in enumerate(hits, 1):
            m = h["meta"]
            prev = h["text"][:90].replace("\n", " ").replace("|", "\\|")
            md.append(f"| {i} | {m['doc_id']} | {m['page']} | {m.get('section','?')} | "
                      f"{h['distance']:.3f} | {prev}… |")
        md.append("")

        answer = ""
        if use_llm:
            answer = query_mod.synthesize(q, query_mod.build_context(hits))
            md += ["**Grounded answer:**", "", f"> {answer.strip()}", "", "---", ""]
        else:
            md += ["---", ""]

        not_found = "not found" in answer.lower()
        metrics.append({
            "question": q,
            "top_distance": round(dists[0], 3) if dists else "",
            "mean_distance": round(sum(dists) / len(dists), 3) if dists else "",
            "worst_distance": round(dists[-1], 3) if dists else "",
            "docs_hit": "; ".join(docs_hit),
            "n_docs_hit": len(docs_hit),
            "sections_hit": "; ".join(secs_hit),
            "answer_not_found": not_found if use_llm else "",
            "answer": answer.strip().replace("\n", " ") if use_llm else "",
        })

    return "\n".join(md) + "\n", metrics


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-k", type=int, default=5)
    ap.add_argument("--no-llm", action="store_true", help="retrieval only, no Claude calls")
    args = ap.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    col = lib.get_collection()

    # 1. Corpus composition
    corpus_md = corpus_report(col)
    (OUT / f"{DATE}_rag_corpus_report.md").write_text(corpus_md)
    print(f"✓ wrote {DATE}_rag_corpus_report.md")

    # 2 + 3. Query battery
    query_md, metrics = run_queries(col, args.k, use_llm=not args.no_llm)
    (OUT / f"{DATE}_rag_query_results.md").write_text(query_md)
    print(f"✓ wrote {DATE}_rag_query_results.md ({len(metrics)} queries)")

    cols = ["question", "top_distance", "mean_distance", "worst_distance",
            "n_docs_hit", "docs_hit", "sections_hit", "answer_not_found", "answer"]
    with open(OUT / f"{DATE}_rag_retrieval_metrics.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(metrics)
    print(f"✓ wrote {DATE}_rag_retrieval_metrics.csv")
    print(f"\nAll artifacts in: {OUT}")


if __name__ == "__main__":
    main()
