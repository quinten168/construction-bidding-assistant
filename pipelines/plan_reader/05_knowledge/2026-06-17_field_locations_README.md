# Field-Location Intelligence — Precedence Rules (2026-06-17)

> Companion to `2026-06-17_field_locations.csv` and the `location_intelligence` DB table.
> Built empirically by scanning `plans.full_markdown` across the **100 converted plans** (READ-ONLY),
> tagging every field-label occurrence with the SECTION TYPE governing it, and grounding the material
> counts against the parsed `materials` table. Reproduce: `04_tools/_scan_field_locations.py` →
> `04_tools/10_load_location_intelligence.py`.

---

## The point of this layer

A number CSI cares about (say "17,432 t of hot mix") appears in **several places** in one plan: the
priced bid schedule, the title-sheet quantity summary, special-provisions prose, typical-section
callouts. They are not all equal. Extraction needs a **precedence rule** — which occurrence is *law*,
which is a *decoy*. This map answers that per field, grounded in where each label actually lands across
the corpus.

`location_intelligence` is one table with a `target_kind` discriminator:
- `WHERE target_kind = 'gotcha'` → gotcha locations (free, from the `gotchas` table).
- `WHERE target_kind IN ('material','numeric','spec')` → the field-location detail (this exercise).

`is_authoritative = 1` + `precedence_rank = 1` mark the law; higher ranks are decoys ordered by prevalence.

---

## The precedence RULES (which source is law, per field)

### Materials → **bid_schedule** is law
`MIX_TN · GRADE_CY · BASE_TN · SHLDR_TN · MILL_SY · CRUSH_TN · STOCK_TN`

The authoritative quantity is the **priced line item in the bid schedule** — that is the number CSI
actually bids against. Grounded empirically in the parsed `materials` table (every parsed line came out
of `base_bid`/`alternate_*`), so these counts are real, not regex guesses:

| field | authoritative n_docs (bid schedule, parsed) | loudest decoy section |
|---|--:|---|
| MIX_TN   | 47 | special_provisions (52) |
| BASE_TN  | 26 | special_provisions (35) |
| GRADE_CY | 25 | special_provisions (41) |
| SHLDR_TN | 23 | special_provisions (41) |
| STOCK_TN | 19 | special_provisions (36) |
| MILL_SY  | 17 | special_provisions (15) |
| CRUSH_TN |  9 | special_provisions (22) |

**Decoys to ignore:** the same material words recur loudly in `special_provisions` (measurement-and-
payment prose, material-source clauses), `typical_sections`, and the title-sheet summary. They carry the
*word* but not the *priced quantity*. Never sum a tonnage from prose — only from the bid-schedule table.

> **CRUSH_TN / STOCK_TN caveat:** these two parse as priced buckets in almost no plans (CRUSH 0,
> STOCK 1 in the `materials` table) — they are genuinely rare pay items. Their bid_schedule `n_docs`
> here come from the prose-label scan, so treat them as *presence signals*, not quantity-confirmed.
> Flagged LOW where applicable.

### Project stationing → **title sheet** is law
`project_stationing` (BEGIN/END PROJECT … STA 10+80 … STA 589+11)

Authoritative source = the **title sheet** — which appears under two DOT heading conventions, so BOTH
are marked authoritative (rank 1): `proposal_front_data` (MN front-data block) and `title_index`
(ND/SD "TITLE SHEET / ESTIMATED QUANTITIES" sheet). Same physical sheet, two names.

- **Decoy (loud):** `special_provisions` (n=15) — calendar-day-count and work-restriction clauses
  quote stations ("SD 44 Sta 0+12 to Sta 7+50 Calendar Day Count"). These are *constraints on a
  segment*, not the project's begin/end. `traffic_staging` (n=9) quotes stations for phasing limits —
  also a decoy.
- **LOW SAMPLE:** the title-sheet begin/end pair is quiet (n=3–4 docs) — the BEGIN/END PROJECT label is
  terse and the title sheet often sits in pre-section front matter (`unknown`). Treat as a *targeted*
  retrieval, not a high-frequency pattern.

### Project length → **title sheet** is law
`project_length` (PROJECT LENGTH: 10.953 MILES)

Authoritative = the title-sheet **"PROJECT LENGTH: X.XXX MILE"** line (`proposal_front_data` n=3,
`title_index` n=2).

- **Decoy (loudest):** bare `X.XXX MILES` in prose recurs in 32+ docs (`unknown`/front matter) and 19
  in `special_provisions` (sampling-location, mobilization clauses: "throughout the project length").
  Only the labeled title-sheet line is the real length; a bare mileage number anywhere else is noise.
- **LOW SAMPLE** on `title_index` (n=2) — flag.

### Traffic level → **title-sheet DESIGN DATA block** is law
`traffic_level` (DESIGN DATA / TRAFFIC / ESAL block + the SP mixture callout e.g. "SP 12.5 (2,B)")

Authoritative = the **DESIGN DATA / design-traffic block on the title sheet** (`title_index` n=3,
`proposal_front_data` n=1).

- **Decoy:** the **SP mixture-level callout** (`SP 12.5 (2,B)`, `TYPE SP …`) is printed in the
  **bid-schedule item description** (n=8) and in `special_provisions` (n=19). That callout encodes the
  mixture level (useful!), but the *design traffic / ESAL / ADT* — the number that drives aggregate
  quality and competitor cost — is the DESIGN DATA block. Use the SP callout as a *corroborating*
  signal, not the primary design-traffic source.
- **LOW SAMPLE** — flag; design-data blocks are terse and frequently in unheaded front matter.

---

## Per-state notes

| field | MN | ND | SD |
|---|---|---|---|
| **materials** | bid_schedule (MN has the richest priced schedules; 67 of the bid_schedule sections) | bid_schedule, but ND county plans bury it inside `contract_front` EJCDC front matter | bid_schedule; SD plan-sets are drawing-heavy so the schedule is sparser |
| **stationing / length** | MN `proposal_front_data` front-data block | ND `title_index` title sheet | SD `title_index` |
| **traffic level** | MN prints SP mixture levels heavily in special provisions + bid items | ND/SD lean on the DESIGN DATA block | — |

General pattern (consistent with the 2026-06-09 field-location map): **MN** plans are the most
section-clean (each field in a predictable section); **ND** county plans push everything through
`contract_front` (EJCDC/county front matter); **SD** plan-sets are drawings with few prose headers, so
section attribution is weakest there.

---

## How the extractor should use this

1. **Target the authoritative section, don't scan the whole doc.** For each field, retrieve/parse the
   `WHERE is_authoritative=1` section first:
   - materials → parse the **bid-schedule table** (already done by `05_parse_bid_schedule`);
   - stationing / length / traffic → retrieve the **title sheet** (`proposal_front_data` OR
     `title_index`) and run the labeled-line extraction there.
2. **Treat lower-rank sections as decoys.** A material tonnage found in `special_provisions` prose, or a
   bare mileage in front matter, must NOT override the authoritative source. Use them only to
   *corroborate* (or to recover a field the authoritative section is missing — then drop confidence).
3. **Honor the LOW SAMPLE flags.** stationing/length/traffic are quiet on the title sheet (n=1–4). The
   extractor should retrieve them with a tight label query, expect misses on drawing-only SD plans, and
   measure the hit rate before trusting automation (HR12).
4. **The SP mixture callout (`SP 12.5 (2,B)`) is a bonus signal** for mixture level, distinct from the
   DESIGN DATA design-traffic number — capture both, label them separately.

---

## Provenance / regenerate

- Scan: `04_tools/_scan_field_locations.py` (READ-ONLY; scans `plans.full_markdown`, grounds materials
  against the `materials` table) → `05_knowledge/2026-06-17_field_locations.csv`.
- Load: `04_tools/10_load_location_intelligence.py` (CREATE TABLE + idempotent DELETE/insert; unions the
  free gotcha rows from `gotchas` + the field rows from the CSV) → `location_intelligence` table.
- Section vocabulary matches `05_knowledge/2026-06-17_section_intelligence.csv` (`section_type` keys).
- **Limitation:** the markdown bid-schedule TABLE often lacks a nearby classifiable heading, so the
  prose-label scan undercounts materials in `bid_schedule` — that is why the loader overrides the
  authoritative material count with the parsed `materials`-table doc count (the empirical truth).
