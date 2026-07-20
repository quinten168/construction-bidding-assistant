# Section Taxonomy v2 — encoding Alex's estimator process

**Date:** 2026-06-10 · **For:** Alex (estimator) review · **Status:** proposal pending sign-off

We compared how the Plan Reader treats document sections against **Alex's actual process** for
reviewing plan sets + proposals. This doc is (1) the gap we found, (2) the new two-axis taxonomy
that fixes it, and (3) the measured effect on the pipeline. The taxonomy itself is editable —
the markup sheet is `knowledge/_markup/2026-06-10_section_taxonomy_markup.csv`; the live source of
truth the code reads is `knowledge/section_taxonomy.csv`.

---

## 1. The gap

Alex sorts every part of a plan into three buckets by **purpose**:

- **DECISION** — drives the bid/no-bid call (bid form, agreement/schedule, proposal front page,
  plan notes, project-specific special provisions / phasing).
- **PRICING** — needed to *price* the work but not to *decide* (prevailing wage, geotech, typical
  sections, *most* special provisions).
- **BOILERPLATE** — standard language "seen many times" (general/supplementary conditions, bonds,
  EEO / federal-aid required provisions).

Our pipeline had **only one axis** — a vector-store tier (KEEP / DOWN_WEIGHT / DROP) derived from
*boilerplate repetition*. That's orthogonal to Alex's purpose axis, and it produced three concrete
mismatches:

| # | Mismatch | Why it's wrong |
|---|---|---|
| 1 | We **down-weighted** the **proposal front page** and the **Agreement** | Alex calls the front page his richest decision source and the Agreement's substantial-completion date "a key piece of information." Our coarse labels (`proposal_front`, `contract_front`) pooled those gold pages with blank covers / bonds / EEO boilerplate. |
| 2 | We protected **prevailing wage** as a top decision gotcha | Alex: "crucial for *pricing*… won't influence our *decision*." It's a pricing input, not a decision driver. One tier couldn't say "keep for the extractor, hide from the decision agent." |
| 3 | Coarse labels couldn't carry Alex's split | He skips "*most* Special Provisions" but zeroes in on the phasing parts (MnDOT 1804 prosecution of work); and `contract_front` lumped the decision-critical Agreement with general-conditions/bonds/EEO boilerplate. |

---

## 2. The new two-axis taxonomy

Every section now carries **two** labels:

- **`relevance`** — Alex's axis: `DECISION` / `PRICING` / `BOILERPLATE`. (The client-facing one;
  a future bid/no-bid agent filters on it.)
- **`tier`** — what the vector store does: `KEEP` / `DOWN_WEIGHT` / `DROP`. (Mechanical.)

They're related but distinct: a PRICING section is still `KEEP` (the extractor needs it) — the
`relevance` *tag*, not a low weight, is what lets a decision-only query hide it. To make Alex's
split detectable, we **split eight high-value sections** out of the old coarse buckets:

| New section | Split out of | Relevance | Tier |
|---|---|:--:|:--:|
| `agreement` | contract_front | DECISION | KEEP |
| `proposal_front_data` | proposal_front | DECISION | KEEP |
| `prosecution_of_work` (MnDOT 1804 phasing) | special_provisions | DECISION | KEEP |
| `general_conditions` (Standard + Supplementary) | contract_front | BOILERPLATE | **DROP** |
| `bonds_forms` | contract_front | BOILERPLATE | **DROP** |
| `eeo_federal` | contract_front | BOILERPLATE | **DROP** |
| `geotechnical` | specifications | PRICING | KEEP |
| `typical_sections` | specifications | PRICING | KEEP |

**The payoff:** the old `contract_front` could only ever be `DOWN_WEIGHT` (never `DROP`) because
the Agreement + ~33 protected gotcha paragraphs hid inside it. Now that the Agreement and the
wage/DBE/LD gotchas are detected *separately*, the residual general-conditions / bonds / EEO
become genuinely **droppable** — while a per-page **gotcha guard** still spares any boilerplate
page that trips a real trigger. `proposal_front_data` is detected by content markers **and by
position** (the first ~2-3 proposal pages), so it's state-agnostic — not just MnDOT.

`proposal_front_data` also fixes mismatch #1 directly; the `relevance` tag fixes #2 (prevailing
wage = PRICING, kept for the extractor, hidden from `--relevance decision`); the `agreement` /
`prosecution_of_work` splits fix #3.

---

## 3. Measured effect (11-plan corpus)

**Pages by relevance** (section assignment, carry-forward + position rule):

| Relevance | Pages | Top sections |
|---|--:|---|
| DECISION | 999 | general_notes (295), traffic_staging (284), agreement (174), bid_schedule (167), proposal_front_data (60) |
| PRICING | 453 | special_provisions (225), prevailing_wage (147), specifications (46), geotechnical (35) |
| BOILERPLATE | 713 | title_index (220), general_conditions (201), contract_front (183), eeo_federal (62), bonds_forms (47) |

**Chunk count A/B** (`01_ingest.py --reset` vs `--keep-boilerplate`):

| Configuration | Chunks |
|---|--:|
| Keep-all baseline (`--keep-boilerplate`) | 4,923 |
| Phase-2 (paragraph strip + old DOWN_WEIGHT only) | 4,666 |
| **v2 disposition ON** | **4,338** |

v2 removes **585 chunks vs keep-all** (~12%): 328 from the new DROP sections + 2,454 boilerplate
paragraphs stripped — while **sparing 56 boilerplate pages** that carried a real gotcha (Watonwan
22, Walsh 7, Dunn 5, …). The "tier, don't delete a gotcha" invariant held.

**No retrieval regression** (cosine distance, lower = closer; target < 0.45 for the key fields):

| Query | Top hit | Distance |
|---|---|--:|
| Prevailing wage requirements | `prevailing_wage` p.197 | 0.392 |
| Total mix asphalt tonnage | `bid_schedule` / `special_provisions` | 0.285 |
| Box culvert present | `proposal_front_data` (08MQ) | 0.456 |
| Phasing / staging | `traffic_staging` | 0.555 |

Note the #3 prevailing-wage hit is an `eeo_federal` page that was **spared from DROP** by the
gotcha guard — the safety net is visible in retrieval.

**Decision-vs-pricing routing works.** A query for "prevailing wage davis bacon rates":
- *unfiltered* → top hits are `eeo_federal` + `prevailing_wage` (PRICING/BOILERPLATE).
- *`--relevance decision`* → those vanish entirely; only `agreement`, `proposal_front_data`,
  `traffic_staging` remain. The bid/no-bid agent can now read decision content without wage noise.

---

## 4. For Alex to confirm (open questions)

1. **`material_source` / traffic level** — we tentatively tagged it a *pricing input*, but whether
   a job needs a quarry is arguably a *capability/fit* (decision) question. Your call.
2. **EEO / federal-aid provisions → DROP from the RAG store?** DBE goals live here; the full-doc
   extractor still captures them for pricing, but we drop them from decision retrieval. OK?
3. **"Most" special provisions = pricing, project-specific = decision** — we auto-split the MnDOT
   1804 prosecution-of-work part as DECISION and leave the rest as PRICING. Does that match how you
   actually triage special provisions?

Mark up `knowledge/_markup/2026-06-10_section_taxonomy_markup.csv` (one row per section,
`agree_Y_N` + notes) and we'll fold your answers into the live taxonomy.
