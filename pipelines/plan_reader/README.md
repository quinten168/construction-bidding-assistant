# Plan Reader

> ## ⚠️ Fresh clone: two large artifacts are required and NOT in the repo
>
> Both are gitignored as regenerable derived data. Without them the module runs but produces
> degraded or empty results — **it does not error loudly**, so check here first if retrieval
> returns nothing.
>
> | Artifact | Size | Needed for | Recover |
> |---|---|---|---|
> | `06_chroma/` | 1.5 GB | RAG retrieval (`lib.py:52` `CHROMA_DIR`) — `s4_extract_rag.py`, `retriever.py` | Re-run ingest: `s1_convert.py` then `s2_indexer.py` over `00_input/plans/`. Rebuilds from the plan corpus. |
> | `00_input/plans/**` | 4.5 GB | the source corpus the index is built from (205 PDFs) | Not in git — obtain from the team/Box. **Required before `06_chroma` can be rebuilt.** |
>
> Note the dependency order: the corpus is needed to rebuild the index. A clone with neither
> cannot regenerate its way out — you need the plan PDFs first.
>
> Related: `pipelines/ci_model/README.md` documents `ranking_predictions.csv` (94 MB), the
> equivalent artifact on the competitor-intelligence side.

Ingest highway-construction RFP/plan PDFs and turn them into structured, searchable
data: a **whole-document field extractor** for the bid fields the client tracks, and a
**RAG layer** (ChromaDB + MiniLM + Claude) for grounded, cited Q&A over gotchas and
comparables that hide in 100–280 page documents. Owners: Jay + T.

This README is the map. Open it first, then the file you need.

The folders are numbered in workflow order, so you can tell at a glance what does what:

- **`00_input/`** — the corpus + ground truth: the plan PDFs, `plans_manifest.csv` (the processed-tracker), `golden_dataset.csv`.
- **`01_pipeline/`** — the read path. The only thing you run to process a plan: `s1_convert → s2_indexer → s3_extract → s4_extract_rag` (retriever/lib/schema/taxonomy are shared helpers).
- **`02_outputs/`** — the deliverables: `results.csv` (wide) + `flags.csv` (long) + per-run briefs/traces.
- **`03_evaluation/`** — accuracy measurement vs golden. Not part of reading a new PDF.
- **`04_tools/`**, **`05_knowledge/`**, **`06_chroma/`**, **`07_archive/`** — utilities · domain data · vector DB · parked one-time stuff.
- **`run.py`** — one command that chains the whole pipeline on a single PDF and leaves an openable artifact at every step (see *Inspect every step* below).

---

## The pipeline

```
                      00_input/plans/<plan_id>/*.pdf  (+ plans_manifest.csv)
                                   │
                  lib.detect_structure (PAGE SIZE: 8.5x11=proposal, 11x17=maps)
                   proposal / combined → continue ;  plan-set-only → SKIP
                                   │
                      01_pipeline/s1_convert.py  → Markdown (+ readable <plan_id>.md)
                                   │
              ┌────────────────────┴─────────────────────┐
              ▼                                            ▼
   01_pipeline/s2_indexer.py                          01_pipeline/s3_extract.py  (proposal pages)
   Markdown → section TAXONOMY → chunks      identity + bid-schedule quantities + wages
   → embeddings → ChromaDB                   each field {value, confidence, page}
              │                                            │
              ▼                                            │
   01_pipeline/s4_extract_rag.py  ───────────────────────────────────┤
   STRUCTURED retrieval (not prose): traffic_level, phasing │
   + gotchas[] over the 20-type taxonomy {code,evidence,page}│
                                                            ▼
                              one canonical RECORD (01_pipeline/schema.py)
                                   │                        │
                                   ▼                        ▼
        00_input/plans/<id>/<id>.json          02_outputs/results.csv (flattened review view)
        (SOURCE OF TRUTH — the interface)   + 02_outputs/per_plan/<date>_brief.md
                                   │
                                   ▼
              03_evaluation/eval_extraction.py → 02_outputs/scorecards/<date>_extraction_vs_golden.csv
              (auto-score quantities vs golden · human-judged fields side-by-side)
```

`04_tools/` holds off-the-main-path utilities you run occasionally, not to process a plan:
`rebuild_aggregates.py` (rebuild results.csv + flags.csv from the per-PDF JSONs, no Claude),
`boilerplate_scan.py` (cross-plan repetition → `00_input/boilerplate_fingerprints.json` the indexer
consumes), and `retag_sections.py`. One-time analyses (conversion-quality, field-location-map,
suspect-tags) are parked in `07_archive/`.

### Inspect every step (the simplest way in)

```bash
python3 pipelines/plan_reader/run.py inspect <plan.pdf>            # full read, with Claude
python3 pipelines/plan_reader/run.py inspect <plan.pdf> --no-llm   # structure only, no Claude calls
```

One command runs structure-detect → convert → indexer → extract → extract_rag on a single PDF and
leaves a file you can open at each step (a **plan-set-only** PDF is skipped — proposals + hybrids only):

| Step | Open this |
|---|---|
| structure | printed + in the JSON's `document_structure` — `type` (proposal/combined/plan_set) and **which pages the maps live on** (e.g. `127-171`), by page size |
| convert | `00_input/plans/<plan_id>/<plan_id>.md` — the plan as readable Markdown (tables, headings, page markers), colocated with its PDF |
| indexer | `02_outputs/per_plan/<date>_ingest_trace_<plan>.csv` — per page: section, **KEEP/DOWN_WEIGHT/DROP**, chunks kept vs dropped, boilerplate stripped |
| extract (+rag) | **`00_input/plans/<plan_id>/<plan_id>.json`** — the canonical structured record (SOURCE OF TRUTH): every field `{value, confidence, page}`; `gotchas[]` as objects |
| aggregate | `02_outputs/results.csv` — the running review table: one upserted row per plan, flattened from the JSON |
| all | `02_outputs/per_plan/<date>_brief_<plan_id>.md` — one readable brief rendered from the record |

The same artifacts are available per-step: `01_pipeline/s1_convert.py <pdf>` writes the `.md`,
`01_pipeline/s2_indexer.py <pdf> --trace` writes the trace CSV, `01_pipeline/retriever.py "<q>" --save` writes the
retrieved chunks.

### Steps (run in order; everything runs from the repo root with the venv)

| Step | Script | Does |
|---|---|---|
| 0 | `01_pipeline/s1_convert.py` | PDF → structure-preserving **Markdown** via pymupdf4llm (bid-schedule tables + headings survive), with a **pdfplumber fallback** for CAD/drawing pages pymupdf leaves empty. Cached to `00_input/_md_cache/` (machine JSON) **and** written to `00_input/plans/<plan_id>/<plan_id>.md` (readable; `--no-md` to skip). |
| 1 | `01_pipeline/s2_indexer.py` | Markdown → `detect_doc_type` + **section taxonomy** (`05_knowledge/section_taxonomy.csv`: stamp each chunk's `relevance` DECISION/PRICING/BOILERPLATE, skip DROP, down-weight low-value, keep the rest) + **paragraph boilerplate strip** (`00_input/boilerplate_fingerprints.json`) → page-aware chunks → embeddings → ChromaDB. A DROP-section page that still trips a gotcha is **spared** (`lib.page_has_gotcha`). Stamps provenance + `doc_type/section/relevance/disposition/weight` on every chunk. `--reset` rebuilds; `--trace` writes a per-page kept/dropped CSV; `--keep-boilerplate` is the A/B baseline. Idempotent. |
| 2 | `01_pipeline/retriever.py` | Question → retrieve top-k chunks → Claude cited answer (prose). Used standalone for ad-hoc Q&A; `--save` writes the chunks to `.md`; metadata filters `--doc/--state/--section/--relevance/…`. (The structured pipeline uses `extract_rag` instead of prose.) |
| 4a | `01_pipeline/s3_extract.py` | Whole-document extractor for the **proposal** fields (identity + bid-schedule quantities + wages). One Claude call → each field `{value, confidence, page}` (schema-driven). |
| 4b | `01_pipeline/s4_extract_rag.py` | **Structured** retrieval for the mid-doc fields: `traffic_level` (MN code / ND-SD Superpave class), `phasing`, `special_requirements[]`, and a gotcha pass over the **20-type taxonomy** → `gotchas[] {code,evidence,page,confidence}`. Returns values, not prose. |
| — | `01_pipeline/schema.py` | The **canonical output schema** — one field-spec list driving the extraction prompts, the per-PDF JSON, the flattened `results.csv`, and the golden map. Change a field here, not in four places. |
| 3 | `03_evaluation/build_golden.py` | Master-join **pre-fill** of the golden dataset → `02_outputs/golden_prefill.csv` (a human consolidates into the canonical `00_input/golden_dataset.csv`). |
| 5 | `03_evaluation/eval_extraction.py` | Compares the structured record to golden via `schema.GOLDEN_MAP` → **`02_outputs/scorecards/<date>_extraction_vs_golden.csv`** (auto-score quantities/location/wages; human-judged fields like `traffic_level`/`gotchas` shown side-by-side, verdict `review`, to fill golden). `--fresh` re-extracts. |
| 6 | `03_evaluation/rag_report.py` | Runs a fixed diagnostic query battery, saves corpus report + query results + retrieval metrics to `02_outputs/diagnostics/`. |

`01_pipeline/lib.py` is shared config + **the single place every path is defined** (data,
outputs, chroma, `.env`, the repo's `data/reference/`, the `05_knowledge/` home) + the embedding
model/collection. Change a location once, here. `01_pipeline/taxonomy.py`
is the codified gotcha taxonomy (20 types / 5 families, each tagged decision-driver vs
pricing-input). **`05_knowledge/` is the durable, revisable home for all domain knowledge that
drives the code** — the section taxonomy, gotcha taxonomy, and project archetypes are *data*
the pipeline reads, not hard-coded. Read `05_knowledge/KNOWLEDGE.md` (each concept → its source
file → the code that consumes it → how to revise it). Adding a new section/gotcha/archetype is
a row edit + re-run, not a code change.

---

## Output schema — the interface (per-PDF JSON + review CSV)

The Plan Reader emits ONE canonical record per plan (`01_pipeline/schema.py`), surfaced three ways:

- **`00_input/plans/<plan_id>/<plan_id>.json`** — the **source of truth** an LLM or the Competitor module
  consumes. Flat; every scalar is `{value, confidence, page}`; `gotchas` is `[{code, evidence, page,
  confidence}]`; a `document_structure` block reports `type` + where the maps live.
- **`02_outputs/results.csv`** — **WIDE**: one upserted row per plan (clean value columns +
  `citations`/`confidence` + free-text `gotchas`). "What's in this plan, at a glance."
- **`02_outputs/flags.csv`** — **LONG**: one row per flagged item (each taxonomy gotcha + `traffic_level` +
  `phasing` + each `special_requirement`), columns `… section, flag_type, family, evidence, page,
  confidence`. For testing gotcha-by-gotcha with the client and growing the taxonomy. Re-running a plan
  replaces its rows (no dups). `section` = where in the plan the flag came from.

Both CSVs are views of the JSONs — `04_tools/rebuild_aggregates.py` regenerates them from all per-PDF
JSONs with **no Claude calls** (e.g. to backfill `flags.csv` for already-processed plans).

```jsonc
{
  "plan_id": "...", "source_file": "...",
  "document_structure": {"type": "combined", "n_pages": 171, "proposal_ranges": "1-126",
                         "map_ranges": "127-171", "boundary_page": 127},   // where the maps live
  "state":        {"value": "ND", "confidence": "high", "page": 1},
  "hot_mix_tons": {"value": 40877, "confidence": "high", "page": 18},      // proposal: bid schedule
  "traffic_level":{"value": "Superpave FAA 45", "confidence": "high", "page": 131},  // MN code / ND-SD class
  "construction_end": {"value": "2023-10-14", "confidence": "high", "page": 4},
  "gotchas": [{"code": "tight_schedule", "evidence": "...", "page": 4, "confidence": "high"}, ...]
}
```

Fields are sourced by package part: **proposal** (8.5×11) → identity + bid-schedule quantities + dates +
wages (whole-doc extractor, ±10% auto-scored vs golden); **plan-set / maps** (11×17) + special provisions →
traffic_level, phasing, gotchas (structured retrieval). A **plan-set-only** PDF is skipped (no proposal).

**Non-TON bid items are captured raw, not pre-converted, by design (2026-08-10).** `base_tons`/
`shoulder_tons`/`hot_mix_tons` only ever capture TON-measured items. A CY-measured base item, or an
SY-measured item that states its own thickness (e.g. `8" Class 5 ... Surfacing`), goes into a sibling
`items`-type field instead — `base_cy_items` / `shoulder_cy_items` / `mix_sy_depth_items`, each a JSON
array of `{quantity, unit, depth_in, page, note}`. **The extraction prompt asks for zero arithmetic on
these fields** — no multiplying, no summing, no unit conversion — the model only reports numbers it read
directly off the page. A live test caught the model's own pre-computed totals disagreeing with the
arithmetic in its own citation text (a ~13% silent error), so summing and density-converting these items
into the same `base_tons`/`shoulder_tons`/`hot_mix_tons` total is done entirely in code, not the prompt —
`schema.resolve_cy_item`/`resolve_sy_depth_product` plus `apps/api/backend`'s
`material_tons_merge.merge_material_tons()` (that merge module lives in `01_pipeline/` alongside
`schema.py` but is only ever called from the live `apps/api` report path, not from any script in this
README's own steps table). Full writeup: `docs/_spec/2026-08-10-aggregate-mix-tons-conversion.md`.

---

## Source of truth — what to trust, and the join keys

| What | Canonical file | Key | Notes |
|---|---|---|---|
| Plan corpus + provenance | `00_input/plans/plans_manifest.csv` | `plan_id` | One row per plan (outcome, contract_id, year, county, sp_number). Stamped onto every chunk. PDFs are gitignored. |
| Extraction ground truth | `00_input/golden_dataset.csv` | `contract_id` (2025) / manual (2023) | Hand-verified, one row per project. `03_evaluation/eval_extraction.py` scores against this. Dictionary: `00_input/golden_dataset_dictionary.md`. |
| Gotcha taxonomy | `01_pipeline/taxonomy.py` (code) ↔ `05_knowledge/gotcha_taxonomy.csv` (data twin) | `gotcha_type` | 20 types, each tagged decision-driver vs pricing-input. Regenerate the CSV with `taxonomy.py --dump-csv`. Awaiting Alex sign-off. |
| Section taxonomy (two-axis "toss-out") | `05_knowledge/section_taxonomy.csv` | `(doc_type, section)` | `relevance` (DECISION/PRICING/BOILERPLATE — Alex's axis) + `tier` (KEEP/DOWN_WEIGHT/DROP) ingest applies. Gap analysis: `02_outputs/diagnostics/2026-06-10_section_taxonomy_v2.md`; Alex markup: `05_knowledge/_markup/`. |
| Project archetypes | `05_knowledge/project_archetypes.csv` | `archetype` | The 5 archetype choices the extractor offers (built into the prompt by `04_extract.archetype_block`). |
| Boilerplate fingerprints | `00_input/boilerplate_fingerprints.json` | normalized paragraph | Generated by `04_tools/boilerplate_scan.py` (cross-plan repetition, gotcha-guarded). Re-run when the corpus changes. |
| Bid-level master | `../../data/reference/2026-06-03_csi_bid_master.csv` | `Contract_Id` | READ-ONLY. The `contract_id` on each chunk joins back here. |
| Box-folder ↔ outcome crosswalk | `../../data/reference/2026-06-08_crosswalk.csv` | Box folder name | Used by `03_evaluation/build_golden.py`. **⚠ This file is MISSING** — absent from the tree and not gitignored, so `build_golden.py:30` (via `lib.py:33 SOURCE_DATA`) fails. Path corrected here; the file still needs recovering. |

**Generated, not source of truth:** everything in `02_outputs/` and `06_chroma/` is
regenerable — rebuild by re-running the step that wrote it. `02_outputs/` artifacts keep
their `YYYY-MM-DD_` date prefix (they're dated snapshots); the pipeline *code* does not.

---

## Layout

The numbered folders read as the workflow: input → pipeline → outputs → evaluation, then supporting dirs.

```
plan_reader/
├── README.md            ← you are here
├── run.py               ← one-command driver: `run.py inspect <pdf>` (chains the whole pipeline)
├── requirements.txt     ← deps for the whole module (install into the repo-root .venv)
├── .env / .env.example  ← Anthropic key (.env is gitignored; copy the example, single-quote the value)
├── 00_input/            ← the corpus + ground truth: plans/<plan_id>/ (PDF + colocated <plan_id>.{md,json},
│                          all gitignored) · plans_manifest.csv (the processed-tracker) · golden_dataset.csv
│                          · boilerplate_fingerprints.json · _md_cache/ (gitignored)
├── 01_pipeline/         ← THE READ PATH: s1_convert · s2_indexer · s3_extract · s4_extract_rag · retriever
│                          (+ schema.py = the output schema · lib.py = all paths · taxonomy.py)
├── 02_outputs/          ← results.csv + flags.csv (tracked aggregators) + per_plan/ · scorecards/
├── 03_evaluation/       ← accuracy measurement: build_golden · eval_extraction · rag_report
├── 04_tools/            ← occasional utilities: rebuild_aggregates · boilerplate_scan · retag_sections
├── 05_knowledge/        ← DOMAIN KNOWLEDGE (data that drives the code): section_taxonomy.csv,
│                          gotcha_taxonomy.csv, project_archetypes.csv, _markup/, KNOWLEDGE.md
├── 06_chroma/           ← the vector DB (gitignored; rebuild with `indexer --reset`)
└── 07_archive/          ← parked one-time diagnostics + scripts (out of the way, not deleted)
```

`02_outputs/` layout: **`results.csv`** (WIDE — one row per plan) · **`flags.csv`** (LONG — one row per
flagged gotcha/item) · **`per_plan/`** (briefs, ingest traces, retrieved chunks — per-run, gitignored) ·
**`scorecards/`** (extraction scorecard / eval diff + Claude cache).

---

## Setup & run

```bash
# from repo root (01_Summer_2026/), one time:
python3 -m venv .venv
.venv/bin/python -m pip install -r pipelines/plan_reader/requirements.txt
cp pipelines/plan_reader/.env.example pipelines/plan_reader/.env   # then paste your key, keep the quotes

# EASIEST: one PDF → the full structured record + every step's artifact + a readable brief
.venv/bin/python pipelines/plan_reader/run.py inspect \
  "pipelines/plan_reader/00_input/plans/2025_DOUGLAS-CO-MN_SAP-021-600-023_NOBID/9804001.pdf"
.venv/bin/python pipelines/plan_reader/run.py inspect <pdf> --no-llm   # free: structure + convert + index only
```

### Run it manually (step by step)

Each step file runs standalone, so you can inspect one piece at a time. From the repo root
(`01_Summer_2026/`); `P` just shortens the paths.

```bash
cd 01_Summer_2026
P=pipelines/plan_reader

# 1. Convert a PDF → readable Markdown (writes <plan_id>.md next to the PDF; cached).
#    Pass a directory instead of a file to warm the whole corpus' cache.
.venv/bin/python $P/01_pipeline/s1_convert.py "$P/00_input/plans/<plan_id>/<file>.pdf"

# 2. Index into the vector DB (--trace = per-page kept/dropped CSV; --reset rebuilds the whole DB).
#    First run downloads the ~80MB embedding model.
.venv/bin/python $P/01_pipeline/s2_indexer.py "$P/00_input/plans/<plan_id>/<file>.pdf" --trace

# 3. Ad-hoc grounded Q&A over one plan (the RAG retriever — prose answer; --save writes a .md).
.venv/bin/python $P/01_pipeline/retriever.py "What are the prevailing wage requirements?" --doc <plan_id>

# 4. Whole-doc field extraction only (proposal fields → upserts a row into outputs/results.csv).
.venv/bin/python $P/01_pipeline/s3_extract.py "$P/00_input/plans/<plan_id>/<file>.pdf"

# Score extraction vs golden  ·  rebuild the aggregate CSVs from the per-PDF JSONs (no Claude).
.venv/bin/python $P/03_evaluation/eval_extraction.py
.venv/bin/python $P/04_tools/rebuild_aggregates.py
```

> **Note:** `s4_extract_rag` (the mid-doc / gotcha pass) is a library the full `run.py inspect` calls —
> it has no standalone CLI because it needs the indexed chunks *and* the in-progress record. For the
> full structured JSON + `flags.csv`, use **`run.py inspect <pdf>`** (steps 1–4 above are for inspecting
> individual pieces).

Corpus today: **11 plans / 4,338 chunks** (MN ×5 · ND ×3 · SD ×3; 2 client wins, 4 losses, 5 no-bids),
section-taxonomy v2 ON: vs the 4,923 keep-all baseline, 2,454 boilerplate paragraphs stripped + 328
DROP-section chunks removed, 912 chunks down-weighted, and **56 boilerplate pages spared from DROP**
because they carried a real gotcha. Pages by relevance: DECISION 999 · PRICING 453 · BOILERPLATE 713.

---

## Design decisions (and the lessons behind them)

- **Markdown, not flat text** (Phase 2): pymupdf4llm keeps the bid-schedule quantity tables as real Markdown tables (the old pdfplumber `extract_text` smeared them to number-soup) — 1,160 tables / 10k rows recovered corpus-wide, vs 0. Evidence: `02_outputs/2026-06-10_conversion_quality.md`.
- **Hybrid conversion**: pymupdf returns *empty* on pure CAD/drawing pages where pdfplumber still recovers fragmented text (Yankton, a client win, lost 124/144 pages without the fallback). So `00_convert` back-fills empty pages from pdfplumber. Conversion is cached (~1.2s/page on dense plans — convert once).
- **Two-axis section taxonomy (encodes Alex's estimator process)**: every section carries a
  `relevance` (DECISION / PRICING / BOILERPLATE — what *Alex* uses to triage) **and** a `tier`
  (KEEP / DOWN_WEIGHT / DROP — what the vector store does). PRICING stays KEEP (the extractor
  needs it); the relevance *tag* — not a low weight — is what lets `--relevance decision` hide it.
  Splitting `agreement` / `proposal_front_data` out of the old coarse buckets stopped us
  down-weighting Alex's richest decision pages, and let the residual general-conditions / bonds /
  EEO finally be **DROP**-able — with a per-page **gotcha guard** (`lib.page_has_gotcha`) sparing
  any boilerplate page that trips a real trigger. Gap analysis + measured effect:
  `02_outputs/diagnostics/2026-06-10_section_taxonomy_v2.md`.
- **Page-aware chunking** (~350 words, ~50 overlap, sentence boundaries) → every chunk cites an exact page. Trade-off: chunks don't span page boundaries (fine for plans).
- **Embedding bound to the collection** (`lib.get_collection`) → ingest and query can't drift to different models, a classic silent-failure source.
- **Idempotent ingest** via deterministic IDs (`{doc}:p{page}:c{idx}`) + `upsert`.
- **Grounding > fluency**: the query prompt answers from retrieved chunks only, with citations, or says "Not found." Bad retrieval → "not found", never a hallucination.

## Known limitations / next

- **`smart_truncate` drops the mid-document**, so `prevailing_wages` (which sits mid-doc) extracts empty in `01_pipeline/s3_extract.py`. Fix: route that field through RAG retrieval (`01_pipeline/retriever.py`) — `run.py inspect` already does this. Evidence: `02_outputs/diagnostics/2026-06-09_field_location_map.md`.
- **Section tagger is tuned for pdfplumber line structure**, so Markdown's reformatted headers cost ~56 taggable pages corpus-wide (offset by 93 new ATX-heading anchors). Next: teach `detect_section` to read Markdown `#`/`**bold**` headers.
- **Genuinely scanned pages still need OCR** (e.g. Jackson has 19 image-only pages neither converter recovers) — docling/LlamaParse fallback, deferred.
- **Boilerplate fingerprints are corpus-derived** — re-run `04_tools/boilerplate_scan.py` when plans are added (especially new document formats; EJCDC boilerplate only appears in the 4 EJCDC-format plans today).
- **Gotcha taxonomy needs Alex's sign-off** before structured `gotcha_types` extraction is wired.
- MVP ignores addenda (Hard Rule 11). Quantity rows can be mis-attributed for ~146 date+county key conflicts in the master — cross-check the crosswalk before trusting quantities.
