# RAG Evaluation — Findings (2026-06-09)

What the RAG pipeline is good at, where it breaks, and what to change. Interprets the
three saved artifacts in this folder (now persisted — they used to only print to the terminal):

- `2026-06-09_rag_corpus_report.md` — what's in the vector DB (for chunking decisions)
- `2026-06-09_rag_query_results.md` — per-query retrieved chunks + grounded answers
- `2026-06-09_rag_retrieval_metrics.csv` — one row per query (distances, docs/sections hit)

Reproduce: `.venv/bin/python 02_modules/plan_reader/rag/scripts/2026-06-09_05_rag_report.py`
(`--no-llm` for a free retrieval-only run).

**Corpus under test: 11 plans → 3,744 chunks / ~2,200 pages** (grown from 5 plans / 1,416 chunks).
MiniLM embeddings, cosine distance.

---

## Headline: RAG is great for *prose*, still poor for *CAD sheets*

10-question diagnostic battery (8 with a known answer, 2 controls). Distance rule of thumb:
**<0.45 strong · 0.45–0.65 moderate · >0.70 weak/absent.**

| Question | Top dist | Answer | Verdict |
|---|--:|---|---|
| Prevailing / Davis-Bacon wages | **0.356** | full, correct | ✅ strong |
| Total HMA mix tonnage | **0.309** | answered (was "not found" at 5 plans) | ✅ **improved with corpus size** |
| Earthwork excavation CY | 0.366 | "not found" (close chunks, no clean total) | ⚠️ inconsistent |
| Phasing / staging | 0.411 | **"not found"** | ❌ miss |
| Dewatering / groundwater | 0.424 | correct | ✅ strong |
| Seasonal / NLEB / whooping crane | 0.464 | answered (now finds Yankton + 08MQ content) | ✅ improved |
| Box culvert in scope? | 0.481 | correct | ✅ good |
| Historic bridge / 4(f) / MOA | 0.494 | correct | ✅ good |
| High-pressure gas line / utility | 0.606 | **"not found"** | ❌ miss |
| Marketing budget (control — absent) | 0.708 | **"not found"** ✓ | ✅ control passed |

**Two things the larger corpus taught us:**
1. **Corpus size helps semantic retrieval.** Mix tonnage and NLEB went from miss → answered just
   by adding plans — more chunks means a better nearest-neighbour exists. So some "RAG can't do
   this" conclusions from the 5-plan run were really "not enough data yet."
2. **But the CAD-sheet misses are structural, not data-starved.** Phasing and the gas line still
   miss at 11 plans, for the same reason as before ⬇.

---

## Why phasing + the gas line still miss: "number-soup" chunks

Both are real gotchas in `SAP 032`, and the whole-doc extractor *found* them. RAG misses them
because the relevant plan/profile sheets are pure coordinate strings:

> `28+00 29+00 30+00 31+00 32+00 33+00 34+00 35+00 36+00 37+00 …` (stationing, no prose)

These embed with nothing semantic to match, so a query for "gas line" or "phasing" can't land on
them — even restricted to the right document. **This is the one structural limitation to design
around**, not tune away.

## Chunking signals (from the corpus report)

- Degenerate chunk sizes persist: a ~22k-char max chunk (number-soup page) and 2-word min chunks.
  → drop/down-weight low-text-density chunks (high digit-to-letter ratio).
- The heuristic section tagger carries section state forward and **over-labels** (e.g. one header
  propagates across many pages). Treat section tags as a soft hint for citations/filtering, not truth.
- The corpus is now MN-heavy by chunk count (Watonwan's 615-page plan alone = 1,053 chunks). Fine
  for retrieval, but be aware when reading aggregate section stats.

---

## What to change (recommendations) — unchanged in direction, firmer in evidence

1. **Hybrid extraction, by field type:**
   - **Whole-doc / bid-schedule parse** (`extraction_mvp.py`) for tabular quantities + booleans.
     RAG quantity retrieval is *inconsistent* (tonnage worked, earthwork CY didn't) — don't depend on it.
   - **RAG retrieval** for narrative fields: prevailing wages + prose gotchas (environmental,
     dewatering, historic/MOA, seasonal). These are reliably strong.
2. **Always filter single-plan extraction by `doc_id`** so cross-doc retrieval doesn't dilute.
3. **Drop/down-weight low-text-density chunks** — removes the number-soup poisoning CAD-sheet retrieval.
4. **CAD-sheet gotchas (gas line, phasing labels) need a non-embedding path** — keyword/regex on
   plan-sheet text, or a vision pass. Semantic search alone won't find a 4-word note in a coordinate grid.

---

## Bottom line

The RAG pipeline is a **validated, grounded Q&A layer**: reliable on prose, honest about absence
(the control correctly returns "not found"), and it *improves as the corpus grows*. It is not a
quantity extractor and not a CAD-sheet reader. Used for narrative gotchas + prevailing wages — its
job in the hybrid design — it's a real asset; the whole-doc extractor stays the path for schedule
quantities. That split is the extraction strategy for the MVP.
