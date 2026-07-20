# NOTES_FOR_LATER — Phase 1+ observations parked during Phase 0

Things noticed while building the Phase 0 bulk-convert + section-split pipeline. **Not built** — the
Phase 0 scope is convert → schema → load → split. These are for the bid-schedule parser (Phase 1),
classification (1.5), gotchas (2), and Jay's section normalization (Track B).

## Bid-schedule parsing (Phase 1)
- **Watonwan SP-8303-48 is a multi-project package (619 pp).** Its sheets carry TWO S.P. numbers —
  `S.P. 8303-48 (TH 15/TH 30)` and `S.P. 8304-123 (TH 15/TH 60)` — so it likely has **more than one
  bid schedule**. The parser should not assume one schedule per plan; key line items to the right S.P.
- Bid-schedule sections surfaced in the split as headings like `BID SCHEDULE`, `ARTICLE 13—BASIS OF
  BID`, `5.02 UNIT PRICE BID`, `PREPARATION AND DELIVERY OF PROPOSAL`. Use `sections.raw_heading`
  (once Jay normalizes `section_type='bid_schedule'`) to locate the table, or fall back to scanning
  `full_markdown` for the price-column discriminator (the plan's verified Dunn=39-items approach).

## Plans that still need their proposal PDF from Box (Phase 1 LLM-fallback / re-pull)
- **Yankton (WON), Jackson, Hand/08MQ are plan-set-ONLY** PDFs — all pages are 11×17 drawings, no
  proposal prose. They split to a single `(plan sheets / drawings)` section and have **no bid-schedule
  text to parse**. Conversion "succeeded" by char count only because the pdfplumber fallback recovered
  CAD label text. Before extraction, pull the matching **proposal** PDF from Box (per the crosswalk).
- Consider replacing the Phase 0 `MIN_MARKDOWN_CHARS` char threshold with a **proposal-content** check
  (`lib.detect_doc_type` / has_bid_schedule / has_procurement_front) so "needs proposal PDF" is flagged
  truthfully rather than passing on raw character count.

## Section normalization (Jay, Track B)
- **`header_text` over-admits non-headings** (deferred from the 2026-06-15 density fix — out of scope
  for that surgical change). Short uppercase lines that aren't section headings still pass as
  `raw_heading`: phone numbers, timestamps (`05/08/2024 15:49:36 UTC`), `(CORPORATE SEAL)`, and other
  form-field boilerplate. Tighten `header_text` (or filter at normalization) to reject these — e.g.
  drop lines that are mostly digits/punctuation, match a date/time pattern, or are parenthetical seals.
- **`ARTICLE n` headings appear in two dash styles** — hyphen (`ARTICLE 1 - BID RECIPIENT`) and em-dash
  (`ARTICLE 1—DEFINITIONS AND TERMINOLOGY`). Fold both when normalizing.
- MnDOT letter-sized **title-block lines bleed through as headings** on Watonwan (e.g. the `S.P. …`
  lines, `REVISED 06/30/22`). These are sheet metadata, not real sections — candidates for a
  `section_type` like `plan_sheet_titleblock` or a drop rule.
- The `(plan sheets / drawings)` and `(intro)` synthetic headings mark pooled/leading content — Jay can
  treat them as their own `section_type`s.

## Next-up feature — metrics-belief review of the Sweet Spot layer (added 2026-06-16, T request)
- **Question to settle:** do we actually believe `work_type` / `size_tier` and the headline
  "small jobs within a type = higher margin" finding — and is the deferred `messiness_score` worth building?
- **Why it's parked separately:** these metrics are *descriptive segmentation*, not predictors. The
  win/margin model is explicitly **AUC ≈ 0.51 (no signal)** — whether CSI wins a bid it placed is driven by
  **price**, not job type/size (see `02_modules/sweet_spot/scripts/2026-06-04_00_METHODOLOGY.md §5c` and
  `2026-06-04_sweetspot_findings.md`). `work_type` is a near-definitional label; `size_tier`'s margin pattern
  is back-tested on the training book (not held out) but matches CSI's own words; `messiness` is unbuilt
  (reserved columns, used in zero shipped code).
- **Where to do it:** the **Sweet Spot / dashboard layer** (`02_modules/sweet_spot/`, dashboard pages 5 & 8),
  NOT the Plan Reader. Phase 2 (gotchas) consumes none of these, so this is **not a Phase 2 blocker**.

> **Note on the `02_modules/sweet_spot/` paths above:** these are **historical**, from the
> pre-restructure layout. They are deliberately left un-repathed — `sweet_spot` has **no current
> home in this repo** (`git ls-files | grep -c sweet_spot` → 0) and its destination is still an open
> decision, so there is nothing correct to point them at yet. The same historical path also appears
> in executable code at `04_tools/06_derive_classification.py:37`, where it will fail at runtime.
- **Suggested scope when picked up:** (1) a held-out / temporal validation of the size→margin pattern rather
  than fit-and-observe on the same data; (2) state-relative size cuts (a single national cut means different
  percentiles in ND vs SD); (3) decide whether to build `messiness_score` at all, or keep shipping the inputs
  and let CSI weight them.

## Doc-type detection (Phase 5)
- Page-SIZE structure (`lib.detect_structure`, 11×17 vs 8.5×11) was by far the most reliable
  drawing-vs-prose signal in Phase 0 — much better than the text-density `lib.is_drawing_page`, which
  missed letter-sized CAD sheets. Phase 5's semantic doc-type detection should keep page-size as a
  strong feature even though Mochen flagged "page size is hacky" (it's a signal, not the only one).

## Bid-schedule crosswalk growth (Phase 1 → ongoing) — `05_knowledge/quantity_crosswalk.py`
- **⚠ MEASURED REGRESSION (2026-06-16):** the `ASPHALT CONCRETE PAVEMENT` gap is not cosmetic — a v1-vs-v2
  diff showed **v2 dropped Brookings' entire hot-mix tonnage (v1 had 17,432 t; v2 = none)**, which is why
  Brookings mis-classified as `work_type='Other'` instead of a paving type. v1's s3 semantic extractor caught
  it; the v2 deterministic/fallback parser didn't. **Priority fix** — add the SD `ASPHALT CONCRETE PAVEMENT`
  (and similar) keyword to `SPEC_MAP` → `hot_mix`, re-run `05_parse_bid_schedule.py` (free), and re-diff vs v1.
- The `unmapped_items` backlog (in `plan_metrics`) is the growth queue. Real variants the SPEC_MAP
  currently misses, worth adding (pure re-run, no API): `ASPHALT CONCRETE PAVEMENT` (SD phrasing) → hma;
  `EXCAVATION - COMMON` (MnDOT word order vs the map's "COMMON EXCAVATION") → grading; tack-coat lines
  (`SS-1h`, `CSS-1h`, `ASPHALT FOR TACK`) → a tack category (not a bucket). Add keyword rows
  most-specific-first and re-run `05_parse_bid_schedule.py` (deterministic plans only; free).
- Some `unmapped_items` are parse NOISE on deterministic plans (e.g. a stray "Application No.:" header
  row captured on Walsh). They don't affect the buckets (which reconcile at 0.0%) but a row-filter
  pass on `parse_bid_items` would tidy the long table.
- **Canonical cross-state spec_category** stays deferred (Phase 2 parking lot). Raw `spec_category` is
  stored on every `materials` row, so canonicalization is a pure recompute over stored rows — no re-parse.

## LLM fallback hardening (Phase 1)
- **Watonwan SP-8303 returned 0 items** — the fallback output hit `max_tokens=4096` and the JSON
  truncated. It's the 619-pp multi-project package (two S.P. numbers). Fixes: raise `max_tokens`, tighten
  `select_schedule_pages` targeting, or split the call per S.P. number. ~$0.13 to retry — held pending T.
- Fallback page targeting uses keyword + DOT-spec-code density with a 60k-char budget and 25k per-page
  cap. It correctly found WATLINE's inline schedule on p2 (no "BID SCHEDULE" keyword, but dense spec
  codes). Watch the per-page cap on plans whose schedule is a single huge pooled CAD page (Douglas).
