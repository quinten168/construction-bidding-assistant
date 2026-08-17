# Plan Reader — Domain Knowledge

This folder is the **single, durable home** for the domain knowledge that *drives the
pipeline's code*: which document sections matter, what counts as a "gotcha," and how a
project is archetyped. It exists because that knowledge was previously scattered and
partly hard-coded (in `01_pipeline/taxonomy.py`, an old `05_knowledge/section_taxonomy.csv`, and a
prompt string inside `s3_extract.py`).

> **Principle: domain knowledge is *data*, code is the *engine*.**
> When a new plan reveals a new section, gotcha, or archetype, you **add a row to a file
> here and re-run** — you do not edit code. This keeps the (growing) lists safe, reviewable,
> and answerable: every "why does the pipeline treat X this way?" is one lookup in this folder.

The lists **will grow** as we ingest more plans and proposals, and as the client (Alex)
validates them. That's expected — these files are meant to be revised.

---

## What lives here

| File | What it is | Source of truth for | Consumed by | Revision process |
|---|---|---|---|---|
| `section_taxonomy.csv` | The **two-axis section map**: per `(doc_type, section)` a `relevance` (DECISION / PRICING / BOILERPLATE — Alex's axis) and a `tier` (KEEP / DOWN_WEIGHT / DROP — what the vector store does). | How ingest treats each section, and how chunks are tagged for decision-vs-pricing retrieval. | `01_pipeline/lib.py` (`load_disposition`, `disposition_for`, `relevance_for`) → `s2_indexer.py`, `retriever.py --relevance`, `run.py`. | Edit a row (or add one for a new section). New section label also needs a regex in `lib.SECTION_PATTERNS`. Re-ingest with `--reset`. |
| `gotcha_taxonomy.csv` | The **20 gotcha types** × {family, relevance (decision_driver / pricing_input), definition, triggers, examples, provenance}. Data twin of `01_pipeline/taxonomy.py`. | Human-reviewable gotcha list (the one Alex marks up). | `01_pipeline/taxonomy.py` is the *code* source; this CSV mirrors it (regenerate with `python 01_pipeline/taxonomy.py --dump-csv`). Triggers feed the gotcha guard in `lib.page_has_gotcha` + `04_tools/boilerplate_scan.py`. | Edit `01_pipeline/taxonomy.py` (the code source), then `--dump-csv` to refresh this file. (Or mark up `_markup/` for Alex, then promote his calls into `taxonomy.py`.) |
| `project_archetypes.csv` | The **5 project archetypes** + definitions. | The archetype choices offered to the extractor. | `01_pipeline/s3_extract.py` (`archetype_block()` builds the prompt from this — no longer hard-coded). | Add/edit a row; re-run `s3_extract.py`. |
| `_markup/` | **Client sign-off CSVs** — editable copies for Alex to mark `agree (Y/N)` + notes. Not read by code. | Capturing Alex's validation before we promote it into the source-of-truth files. | Humans. | Hand to Alex; fold his answers back into `section_taxonomy.csv` / `taxonomy.py`. |

---

## The two axes (why `section_taxonomy.csv` has both `relevance` and `tier`)

These come from measuring our pipeline against **Alex's actual estimator process**. Alex
sorts every part of a plan/proposal into three buckets:

- **DECISION** — drives the bid/no-bid call: the bid form (quantity overview), the agreement
  (substantial-completion date), the proposal front-matter (location / work type / length /
  completion), plan notes (gotchas, phasing), and project-specific special provisions
  (MnDOT 1804 prosecution of work).
- **PRICING** — needed to *price* the work but not to *decide*: prevailing wage
  ("crucial for pricing… won't influence our decision"), geotech, typical sections, and
  *most* special provisions.
- **BOILERPLATE** — standard language he's "seen many times": general/supplementary
  conditions, bonds, EEO / federal-aid required provisions.

`relevance` is **Alex's axis** (the client-facing one, what a future bid/no-bid agent filters
on). `tier` is the **mechanical** axis — what ingest does in the vector store. They're related
but distinct: a PRICING section is still `KEEP` (the extractor needs it) — the `relevance` tag,
not a low weight, is what lets a decision-only query hide it. Only BOILERPLATE is `DROP`/
`DOWN_WEIGHT`, and a DROP page that still trips a gotcha trigger is spared at ingest
(`lib.page_has_gotcha`) — we never delete a decision gotcha.

---

## Status

- Section taxonomy v2 and the gotcha relevance split are **proposals pending Alex's sign-off**.
  `material_source` is explicitly flagged for him (traffic level to quarry capability is arguably
  a decision/fit question, not pure pricing).
- The supporting markup, gap analysis, and CSI review documents behind these proposals are not in
  this repository. They are covered in the knowledge transfer document.
