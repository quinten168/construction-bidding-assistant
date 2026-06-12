"""
retriever.py  —  STEP 2: ask a question, get a cited answer.

    question -> embed -> retrieve top-k nearest chunks -> Claude synthesizes -> answer

Run:
    .venv/bin/python 02_modules/plan_reader/01_pipeline/retriever.py "Are there phasing or staging requirements?"
    ... "What are the prevailing wage requirements?" --doc 2025_JACKSON-CO-MN_SAP-032-629-048_NOBID  # restrict to one plan
    ... "What is the total mix tonnage?" -k 8                                        # retrieve more chunks
    ... "Are there phasing requirements?" --doc <plan_id> --save                     # also write the retrieved chunks + answer to a .md

INSPECTABILITY (2026-06-11): --save writes 02_outputs/<date>_retrieved_<slug>.md — the exact
chunks that were retrieved (source/page/section/distance + full text) and, unless --no-llm,
Claude's grounded answer beneath them. Open it to SEE what the model was handed before it
answered.

Two ideas to learn:
  • RETRIEVAL is just nearest-neighbour search in embedding space. We print the
    chunks we retrieved so you can SEE what the model was given (transparency =
    debuggability — if the answer is wrong, look here first).
  • GROUNDING: the prompt forces Claude to answer ONLY from the retrieved chunks
    and to CITE source+page, or say "Not found in the retrieved sections." This is
    the core anti-hallucination discipline of RAG. Garbage retrieval -> the model
    says "not found" instead of inventing — which is the correct behaviour.
"""
import sys
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lib

MODEL = "claude-sonnet-4-6"   # matches s3_extract.py for consistency
ENV_PATH = lib.ENV_PATH   # .../02_modules/plan_reader/.env


def load_api_key():
    """Reuse the project's env convention: a single-quoted key in `env`, or the
    ANTHROPIC_API_KEY environment variable."""
    import os
    key = os.environ.get("ANTHROPIC_API_KEY")
    if key:
        return key
    return ENV_PATH.read_text().split("'")[1]


def retrieve(collection, question, k, where=None):
    """Nearest-k chunks for the question. `where` is an optional metadata filter
    (e.g. {"doc_id": "SAP 032-629-048 Plan"} or {"state": "MN"})."""
    res = collection.query(
        query_texts=[question],
        n_results=k,
        where=where or None,
    )
    # Chroma returns parallel lists; zip them into tidy dicts.
    hits = []
    for doc, meta, dist in zip(res["documents"][0], res["metadatas"][0], res["distances"][0]):
        hits.append({"text": doc, "meta": meta, "distance": dist})
    return hits


def build_context(hits) -> str:
    """Format retrieved chunks for the prompt, each labeled with a citation tag."""
    blocks = []
    for i, h in enumerate(hits, 1):
        m = h["meta"]
        tag = f'[{i}] {m["source_file"]} p.{m["page"]} ({m.get("section", "?")})'
        blocks.append(f"{tag}\n{h['text']}")
    return "\n\n---\n\n".join(blocks)


SYNTH_PROMPT = """You are helping a highway-construction estimator review a bid plan.
Answer the QUESTION using ONLY the retrieved plan excerpts below. Rules:
- If the answer is present, state it concisely and cite the excerpt tag(s) like [2] and the page.
- If the excerpts do not contain the answer, reply exactly: "Not found in the retrieved sections."
- Do not use outside knowledge or guess.

QUESTION: {question}

RETRIEVED EXCERPTS:
{context}
"""


def synthesize(question: str, context: str) -> str:
    import anthropic
    client = anthropic.Anthropic(api_key=load_api_key())
    msg = client.messages.create(
        model=MODEL,
        max_tokens=600,
        messages=[{"role": "user",
                   "content": SYNTH_PROMPT.format(question=question, context=context)}],
    )
    return msg.content[0].text


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("question")
    ap.add_argument("-k", type=int, default=5, help="how many chunks to retrieve")
    ap.add_argument("--doc", default=None, help="restrict to one doc_id (plan_id, e.g. 2023_DUNN-CO-ND_CP-13_WON)")
    ap.add_argument("--state", default=None, help="restrict to one state (MN/ND/SD)")
    ap.add_argument("--section", default=None,
                    help="restrict to one section (e.g. traffic_staging, prevailing_wage, bid_schedule)")
    ap.add_argument("--relevance", default=None, choices=["DECISION", "PRICING", "BOILERPLATE",
                    "decision", "pricing", "boilerplate"],
                    help="restrict to one relevance class (DECISION/PRICING/BOILERPLATE — Alex's axis). "
                         "Use --relevance decision to see only bid/no-bid-relevant chunks.")
    ap.add_argument("--outcome", default=None, help="restrict to one outcome (bid_won/bid_lost/no_bid)")
    ap.add_argument("--year", default=None, help="restrict to one bid year (e.g. 2023)")
    ap.add_argument("--county", default=None, help="restrict to one county (e.g. Dunn)")
    ap.add_argument("--no-llm", action="store_true", help="show retrieval only, skip Claude")
    ap.add_argument("--save", action="store_true",
                    help="also write retrieved chunks (+ grounded answer) to 02_outputs/<date>_retrieved_<slug>.md")
    args = ap.parse_args()

    # Build a metadata filter. Multiple keys are AND-ed; Chroma wants explicit $and.
    relevance = args.relevance.upper() if args.relevance else None
    filters = {"doc_id": args.doc, "state": args.state, "section": args.section,
               "relevance": relevance,
               "outcome": args.outcome, "year": args.year, "county": args.county}
    clauses = [{k: v} for k, v in filters.items() if v]
    where = clauses[0] if len(clauses) == 1 else ({"$and": clauses} if clauses else None)

    col = lib.get_collection()
    hits = retrieve(col, args.question, args.k, where)

    print(f"\nQ: {args.question}")
    print(f"\n── Retrieved {len(hits)} chunks "
          f"(distance = cosine, lower = closer) ─────────────────────")
    for i, h in enumerate(hits, 1):
        m = h["meta"]
        preview = h["text"][:130].replace("\n", " ")
        print(f"  [{i}] {m['source_file']} p.{m['page']}  [{m.get('section','?')}]  (dist {h['distance']:.3f})")
        print(f"      {preview}…")

    answer = None
    if not args.no_llm:
        answer = synthesize(args.question, build_context(hits))
        print("\n── Claude's grounded answer ───────────────────────────────────────")
        print(answer)

    if args.save:
        save_retrieval(args.question, hits, answer, args.doc)


def save_retrieval(question, hits, answer, doc):
    """Write the retrieved chunks (+ grounded answer, if any) to an openable .md so the
    user can SEE exactly what the model was handed. The full chunk text is included (not the
    130-char preview shown in the terminal)."""
    import datetime
    import re
    slug = re.sub(r"[^a-z0-9]+", "-", (doc or question).lower()).strip("-")[:50] or "query"
    lib.OUT_PER_PLAN.mkdir(parents=True, exist_ok=True)
    out = lib.OUT_PER_PLAN / f"{datetime.date.today().isoformat()}_retrieved_{slug}.md"
    parts = [f"# Retrieval for: {question}\n"]
    if doc:
        parts.append(f"_restricted to doc: {doc}_\n")
    parts.append(f"\n## Retrieved {len(hits)} chunks (cosine distance — lower = closer)\n")
    for i, h in enumerate(hits, 1):
        m = h["meta"]
        parts.append(f"\n### [{i}] {m['source_file']} · p.{m['page']} · "
                     f"{m.get('section', '?')} · dist {h['distance']:.3f}\n")
        parts.append(f"> doc_type={m.get('doc_type','?')} · relevance={m.get('relevance','?')} "
                     f"· disposition={m.get('disposition','?')}\n\n")
        parts.append(h["text"].strip() + "\n")
    if answer is not None:
        parts.append("\n## Claude's grounded answer\n\n" + answer + "\n")
    out.write_text("".join(parts))
    print(f"\n  ↳ saved retrieval: {out}")


if __name__ == "__main__":
    main()
