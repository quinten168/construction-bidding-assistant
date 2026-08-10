# Spec — Extraction Benchmark Table (`scratch.extraction_benchmark`)

**2026-08-10. Phase B of P0 #1. STATUS: AWAITING OWNER REVIEW — no DDL has been applied.**

Nothing in §5 has been run. The connection was used **read-only** (`read_only=True` on every
session) to shape the join against the real schema. No write, no DDL, no touch to
`scratch.bid_projects` or `scratch.bid_results`.

Inventory and evidence: `docs/_session/2026-08-10-golden-dataset-inventory.md`.

---

## 1. What this has to answer

> For a given plan, did we extract the quantities the bid schedule actually states — and where
> we did not, was it a wrong number or a missed item?

Every accuracy claim in Wednesday's presentation should come out of this table.

---

## 2. What the read-only shaping found — three facts that change the design

### 2.1 The year spreadsheets are already loaded, but only 2024–2025

`scratch.bid_projects` (1,589 rows, `source_batch = 'bid_year_and_job_id_fix_2026-08-01'`)
**is** the year spreadsheets, carrying `mix_tons / grading_yards / base_tons / shldr_tons /
mill_sy / crush_tons / stock_tons`.

`bid_year`: 2023 → **1 row**, 2024 → 630, 2025 → 957. `bid_date` range 2023-04-18 to 2025-08-28,
with only **11 rows before 2023-09-01**.

**The `2023 Spreadsheet.xlsx` — 585 rows, 486 with at least one bucket quantity — is not
loaded.** That is the single cheapest expansion of the golden set available: ~486 project
lettings of CSI-stated bucket truth, already in a parsed-friendly format, one loader away.
It also explains the poor overlap below: 6 of the 8 machine-readable bid schedules are 2023
projects, and 4 of them find no `bid_projects` row at all.

### 2.2 `dot_project_id` ↔ `source_project_id` is not a usable join today

Matching all 114 distinct `plans.dot_project_id` values against `bid_projects.source_project_id`
(punctuation-normalised, `LIKE` both directions) returns **2 matches out of 114**. It is a
coverage problem (2023 missing) compounded by a format problem (`SAP-007-616-035` vs
`SAP 007-616-035`) and 323 of 1,588 `source_project_id` values being NULL.

**The benchmark therefore must not depend on that join.** It carries its own explicit
`plan_id` ↔ `project_natural_key` resolution and records which method resolved it.

### 2.3 CSI's spreadsheet quantities are UNIT-CONVERTED; the bid schedule's are not

This is the finding that most shapes the table. Watonwan `SAP 083-090-007`, three sources:

| bucket | golden bid schedule (rtv-csv) | our `plan_metrics` | CSI `bid_projects` |
|---|---|---|---|
| grading | `2106.507 EXCAVATION - COMMON` **19,042 CY** | **19,042** | **19,042** |
| base | `2211.507 AGGREGATE BASE CLASS 5` **5,724 CY** | NULL | **8,068 TON** |
| mix | `2360.504 ... (2,B) 3"` **23,197 SY** + `2360.509` 86 + 69 TON | NULL | **3,983 TON** |

Grading agrees exactly three ways. Base and mix do not — and **not because anyone is wrong.**
The plan states base in **CY** and most of the mix in **SY**; CSI's estimator converted to TON.
Our pipeline's `csi_bucket` is unit-guarded, so it drops the item rather than convert, and
emits NULL.

> **Scoring CSI's converted 8,068 TON against our NULL as an "extraction miss" would be wrong.**
> It is a missing conversion layer, not a missing extraction. The table must separate those, or
> the presentation will report a recall failure that is really a known, deliberate design gap
> (HANDOFF §7: "no unit conversion in the mapping layer; conversion is a later layer with a
> CSI-verified factor table").

Hence `unit_match` and the `CONVERSION_REQUIRED` comparison status in §5.

---

## 3. Grain and sources

**One fact table at item grain**, plus a view that rolls up to bucket grain. Bucket-level golden
sources (the year spreadsheets) land in the same table with `golden_grain = 'bucket'` and a NULL
`spec_item_number`, so precision/recall/variance are computed once, not twice.

| tier | golden source | grain | n | states |
|---|---|---|---|---|
| 1 | `rtv-csv-for-Bid Item List*` | item | 8 files / 772 rows | MN |
| 1 | `Bid Items.xlsx` | item | 8 files | SD, ND, MN |
| 1 | `Proposal_NDOT_*` | item | 10 files | NE |
| 2 | `*QUANITIES.pdf` | item | 33 files (30 with a text layer) | MN 18, ND 12, SD 3 |
| 3 | year spreadsheets → `bid_projects` | bucket | ~2,120 rows w/ quantities | all |

Tier 1 is the trustworthy set (26 schedules, zero parsing risk). Tier 2 requires PDF extraction
and carries the image-only and mojibake hazards. Tier 3 is CSI-stated and unit-converted.

`is_golden` marks tier 1–2 rows that a human has confirmed transcribe the source document
faithfully. **It is not "we have a golden file" — it is "a human checked this row."** It stays
`false` on load; §6 is the promotion rule.

---

## 4. Join design

### 4.1 Plan resolution (`plan_id` ↔ golden source), in strict precedence order

| rank | method | key | `plan_match_method` |
|---|---|---|---|
| 1 | state project number, punctuation-normalised | `SAP 018-603-024` → `SAP018603024` | `state_project_number` |
| 2 | corpus folder name → explicit hand-verified map | see `tools/golden/2026-08-10_golden_join.py` | `explicit_map` |
| 3 | `{state}_{county}_{bid_date}` (the board's settled fallback) | | `state_county_date` |
| — | none of the above | | `unresolved` |

Rank 2 is currently the *only* method that resolves all five overlapping plans, because of §2.2.
It is explicit rather than fuzzy on purpose: a wrong plan match silently corrupts every number
downstream and would look exactly like an extraction error.

**No fuzzy name matching, at any rank.** If nothing resolves, the row loads with
`plan_match_method = 'unresolved'` and `comparison_status = 'PLAN_UNRESOLVED'` — it is never
dropped, because a silently dropped row is indistinguishable from a plan we scored perfectly.

### 4.2 Item resolution, in precedence order

| rank | method | `item_match_method` |
|---|---|---|
| 1 | state spec item number, base form (`2104.503`, suffix stripped) | `spec_item_number` |
| 2 | full extended form (`2104.503/00315`) where both sides carry it | `spec_item_extended` |
| 3 | normalised description + unit | `description_unit` |
| — | golden row with no counterpart | `unmatched` |

⚠️ **Rank 1 is blocked on a defect, and the benchmark must not hide it.**
`materials.bid_item_no` holds the spec number on some plans (Crow Wing: `2104.504`) and a bare
line number on others (Blue Earth: `1, 2, 3`). Only **331 of 6,385** rows corpus-wide match
`dddd.ddd`. The loader classifies each plan's key column first and writes
`comparison_status = 'KEY_UNUSABLE'` for line-numbered plans — it does **not** attempt the join
and report 0% recall, which would read as an extraction failure when it is a schema failure.

This is the concrete, measured argument for P0 #3's spec-item-number path.

### 4.3 Alternates and superseded revisions — two ways to silently double-count

Both were discovered in Phase A and both must be represented, not filtered away:

- `is_alternate` — mutually exclusive scope (`Alternate A` / `Alternate B`, or an `A`-prefixed
  line namespace). **Excluded from the base-bid roll-up, retained as rows.** Present in ND/SD
  bid schedules; absent from all 8 MN machine-readable files.
- `scope_label` — the raw band header (`Base Bid - Participating`, `BASE BID – SECTION 2`,
  `Alternate A - Asphalt with Geogrid`). Additive *sections* and exclusive *alternates* are
  distinguishable **only** by this text, so it is stored verbatim rather than reduced to a flag.
- `source_revision` — for NDDOT proposals, the `Rev:` stamp. Job 22484's three identical
  64,750 TON rows are one item on three revisions of proposal sheet `5 of 11`. The rule is
  *keep only the highest `Rev:` per `Page N of M`*; superseded rows load with
  `comparison_status = 'SUPERSEDED_REVISION'` so the dedup is auditable rather than invisible.

---

## 5. DDL — **PROPOSED, NOT APPLIED**

```sql
-- ==========================================================================
-- PROPOSED. DO NOT RUN WITHOUT OWNER APPROVAL.
-- Target: Supabase, schema `scratch`. Additive only -- creates new objects,
-- alters nothing existing, and never writes to bid_projects / bid_results.
-- ==========================================================================

CREATE TABLE IF NOT EXISTS scratch.extraction_benchmark (
    benchmark_id        bigserial PRIMARY KEY,

    -- ---- what we are scoring -------------------------------------------
    plan_id             text NOT NULL,     -- csi_v2.plans.plan_id
    project_natural_key text,              -- scratch.bid_projects, NULL if unresolved
    plan_match_method   text NOT NULL
        CHECK (plan_match_method IN ('state_project_number','explicit_map',
                                     'state_county_date','unresolved')),

    -- ---- the golden side ------------------------------------------------
    golden_source_class text NOT NULL
        CHECK (golden_source_class IN ('rtv_bid_item_list','bid_items_xlsx',
                                       'proposal_ndot','quanities_pdf',
                                       'year_spreadsheet')),
    golden_source_file  text NOT NULL,     -- path relative to the corpus mirror root
    golden_grain        text NOT NULL CHECK (golden_grain IN ('item','bucket')),
    golden_tier         smallint NOT NULL CHECK (golden_tier BETWEEN 1 AND 3),

    spec_item_number    text,              -- '2104.503'; NULL at bucket grain
    spec_item_extended  text,              -- '2104.503/00315' where stated
    spec_scheme         text               -- 'mndot_2xxx','mndot_econstruction',
                                           -- 'nddot_spec_code','nedot_dotted',
                                           -- 'freeform','none'
        CHECK (spec_scheme IN ('mndot_2xxx','mndot_econstruction','nddot_spec_code',
                               'nedot_dotted','sddot','freeform','none')),
    golden_description  text,
    golden_unit         text,
    golden_quantity     double precision,  -- NULL means the source stated none
    scope_label         text,              -- verbatim band header
    is_alternate        boolean NOT NULL DEFAULT false,
    source_revision     text,              -- NDDOT 'Rev:' stamp
    source_line         text,

    -- ---- the extracted side ---------------------------------------------
    csi_bucket          text,              -- hot_mix_tons, base_tons, ...
    csi_category        text,
    extracted_description text,
    extracted_unit      text,
    extracted_quantity  double precision,  -- NULL is NOT zero. See CHECK below.
    item_match_method   text
        CHECK (item_match_method IN ('spec_item_number','spec_item_extended',
                                     'description_unit','unmatched')),

    -- ---- the score -------------------------------------------------------
    comparison_status   text NOT NULL
        CHECK (comparison_status IN (
            'MATCH',                  -- both sides present, both quantified
            'MATCH_NULL_QUANTITY',    -- keys matched, extracted qty is NULL (lump sum)
            'CONVERSION_REQUIRED',    -- keys matched, units differ -- see 2.3
            'MISSED_BY_EXTRACTION',   -- golden row, nothing extracted
            'EXTRA_NOT_IN_GOLDEN',    -- extracted row absent from golden
            'SUPERSEDED_REVISION',    -- superseded NDDOT Rev: page
            'KEY_UNUSABLE',           -- plan's bid_item_no is line-numbered
            'PLAN_UNRESOLVED',        -- golden file matched no plan
            'GOLDEN_UNPARSEABLE'      -- image-only / mojibake source
        )),
    unit_match          boolean,
    abs_variance        double precision,  -- only when comparison_status='MATCH'
    pct_variance        double precision,

    -- ---- provenance (required by the board) ------------------------------
    is_golden           boolean NOT NULL DEFAULT false,
    verified_at         timestamptz,
    verified_by         text,
    verification_note   text,

    loaded_at           timestamptz NOT NULL DEFAULT now(),
    loader_version      text NOT NULL,

    -- A variance may exist only for a real numeric comparison. This is the
    -- failure/empty rule expressed as a constraint: a NULL extracted quantity
    -- can never masquerade as a measured zero-variance match.
    CONSTRAINT variance_only_on_match CHECK (
        (comparison_status = 'MATCH' AND abs_variance IS NOT NULL)
        OR (comparison_status <> 'MATCH' AND abs_variance IS NULL)
    ),
    CONSTRAINT match_requires_quantities CHECK (
        comparison_status <> 'MATCH'
        OR (golden_quantity IS NOT NULL AND extracted_quantity IS NOT NULL)
    ),
    CONSTRAINT verified_fields_together CHECK (
        (is_golden = false)
        OR (verified_at IS NOT NULL AND verified_by IS NOT NULL)
    ),
    CONSTRAINT item_grain_has_number CHECK (
        golden_grain <> 'bucket' OR spec_item_number IS NULL
    )
);

CREATE UNIQUE INDEX IF NOT EXISTS extraction_benchmark_natural_uq
    ON scratch.extraction_benchmark (
        plan_id, golden_source_file,
        coalesce(spec_item_extended, spec_item_number, ''),
        coalesce(csi_bucket, ''), coalesce(scope_label, ''),
        coalesce(source_revision, ''), coalesce(source_line, '')
    );

CREATE INDEX IF NOT EXISTS extraction_benchmark_plan_idx
    ON scratch.extraction_benchmark (plan_id);
CREATE INDEX IF NOT EXISTS extraction_benchmark_status_idx
    ON scratch.extraction_benchmark (comparison_status);
CREATE INDEX IF NOT EXISTS extraction_benchmark_bucket_idx
    ON scratch.extraction_benchmark (csi_bucket);

COMMENT ON COLUMN scratch.extraction_benchmark.is_golden IS
    'A HUMAN confirmed this row transcribes the source document faithfully. '
    'Not "a golden file exists". Defaults false; see the promotion rule in the spec.';
COMMENT ON COLUMN scratch.extraction_benchmark.extracted_quantity IS
    'NULL means nothing was extracted. It is never a zero. Guarded by variance_only_on_match.';
COMMENT ON COLUMN scratch.extraction_benchmark.comparison_status IS
    'CONVERSION_REQUIRED is a known design gap (no unit conversion layer), NOT an '
    'extraction miss. Excluded from the recall denominator in the scorecard view.';

-- --------------------------------------------------------------------------
-- Per-bucket scorecard. Alternates and superseded revisions are excluded from
-- the base-bid roll-up; CONVERSION_REQUIRED is reported separately so a known
-- design gap is never presented as an extraction failure.
-- --------------------------------------------------------------------------
CREATE OR REPLACE VIEW scratch.extraction_benchmark_scorecard AS
SELECT
    csi_bucket,
    count(*) FILTER (WHERE comparison_status <> 'EXTRA_NOT_IN_GOLDEN')  AS golden_items,
    count(*) FILTER (WHERE comparison_status IN ('MATCH','MATCH_NULL_QUANTITY')) AS matched_items,
    count(*) FILTER (WHERE comparison_status = 'MISSED_BY_EXTRACTION')  AS missed_items,
    count(*) FILTER (WHERE comparison_status = 'EXTRA_NOT_IN_GOLDEN')   AS extra_items,
    count(*) FILTER (WHERE comparison_status = 'CONVERSION_REQUIRED')   AS conversion_gap_items,
    round((count(*) FILTER (WHERE comparison_status IN ('MATCH','MATCH_NULL_QUANTITY')))::numeric
        / nullif(count(*) FILTER (WHERE comparison_status IN
            ('MATCH','MATCH_NULL_QUANTITY','MISSED_BY_EXTRACTION')), 0), 4) AS recall,
    round((count(*) FILTER (WHERE comparison_status IN ('MATCH','MATCH_NULL_QUANTITY')))::numeric
        / nullif(count(*) FILTER (WHERE comparison_status IN
            ('MATCH','MATCH_NULL_QUANTITY','EXTRA_NOT_IN_GOLDEN')), 0), 4) AS precision,
    sum(golden_quantity) FILTER (WHERE comparison_status = 'MATCH')      AS golden_total,
    sum(abs_variance)                                                    AS abs_variance_total,
    round(sum(abs_variance)::numeric
        / nullif(sum(golden_quantity) FILTER (WHERE comparison_status = 'MATCH'), 0) * 100, 4)
                                                                         AS pct_variance
FROM scratch.extraction_benchmark
WHERE is_alternate = false
  AND comparison_status <> 'SUPERSEDED_REVISION'
GROUP BY csi_bucket;

GRANT SELECT ON scratch.extraction_benchmark            TO csi_reader;
GRANT SELECT ON scratch.extraction_benchmark_scorecard  TO csi_reader;
```

### Rollback

```sql
DROP VIEW  IF EXISTS scratch.extraction_benchmark_scorecard;
DROP TABLE IF EXISTS scratch.extraction_benchmark;
```
Additive only — nothing existing is altered, so rollback is a clean drop.

---

## 6. `is_golden` promotion rule

`is_golden = false` on load, always. A row is promoted only when a human has compared it to the
source document and set all three fields in one statement:

```sql
UPDATE scratch.extraction_benchmark
   SET is_golden = true, verified_at = now(), verified_by = :who, verification_note = :note
 WHERE benchmark_id = ANY(:ids);
```

`verified_fields_together` makes a promotion without provenance impossible. Tier 3 (year
spreadsheet) rows are **never** promoted: they are CSI's converted working numbers, not a
transcription of a source document, and marking them golden would make §2.3's conversion gap
unfalsifiable.

---

## 7. What is already built and runnable locally

| path | status |
|---|---|
| `tools/golden/2026-08-10_golden_parse.py` | ✅ runs; 8/8 files, 3 schema variants, 772 rows, 0 failures |
| `tools/golden/2026-08-10_golden_join.py` | ✅ runs; emits the comparison at the statuses above |
| `tools/golden/2026-08-10_golden_rows.csv` | ✅ 772 golden item rows |
| `tools/golden/2026-08-10_golden_comparison.csv` | ✅ 88 comparison rows |

Current local output, which is what the table would hold for the Tier-1 MN subset:

```
plan                                          gold  extr  match   prec  recall
2023_CROW-WING-CO-MN_SAP-018-603-024_NOBID      45    46     45  0.978   1.000
2025_WATONWAN-CO-MN_WATLINE-TRAIL_NOBID         42    13     13  1.000   0.310
pooled                                          87    59     58  0.983   0.667

bucket             items  golden_total  abs_variance    err%
base_tons              1         5,849             0   0.00%
grading_quantity       2        34,918             0   0.00%
hot_mix_tons           1         4,732             0   0.00%
shoulder_tons          2           478             0   0.00%
```

Both scripts exit non-zero when a file set or keyword matches zero rows, so an empty run fails
loudly instead of passing quietly.

**Not yet built** (deliberately — these follow approval of §5): parsers for `Bid Items.xlsx`
(Class A2) and `Proposal_NDOT_*` (Class A3), the `2023 Spreadsheet.xlsx` loader, the
QUANITIES-PDF extractor, and the writer that inserts into the table.

---

## 8. Decisions needed from the owner

1. **Approve or amend the DDL in §5**, then say explicitly that it may be applied. Nothing runs
   until then.
2. **§2.3 — is `CONVERSION_REQUIRED` the right call?** It keeps a known design gap out of the
   recall number. The alternative is scoring it as a miss, which makes recall look worse than
   the extractor deserves. This changes the headline accuracy figure either way.
3. **Load `2023 Spreadsheet.xlsx` into `bid_projects`?** ~486 lettings with quantities, and it
   is where 6 of the 8 machine-readable bid schedules live. It is also a **write to
   `bid_projects`**, which I am not doing without being asked.
4. **Table name and schema** — `scratch.extraction_benchmark` assumed.
5. **`verified_by` format** — free text, or restricted to a known set of initials?
