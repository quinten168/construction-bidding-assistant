# Session report — 2026-08-10 · ND milling: capture the value AND its unit, do not convert

Spec: `docs/_spec/2026-08-10-milling-unit-capture.md`. Board open item #2.

**Headline: Dunn's 67,007 tons of milling are preserved and reported in tons. `milling_sy` did not
move on any MN or SD plan. No conversion was performed and no depth factor was assumed.**

---

## 1. The field shape

Three fields, two asked of the model and one derived in code. Per-unit subtotals rather than one
`(value, unit)` pair, because **Dunn is measured in both units at once** — 408,216 SY of FDR *and*
67,007 TON of milling/removal — so any single-pair shape must throw one of the two real numbers away.

| field | kind | meaning |
|---|---|---|
| `milling_sy` | num, **unchanged** | the square-yard lines (incl. FDR). MN/SD behaviour untouched. |
| `milling_tons` | num, **new** | the TON-measured milling and bituminous-removal lines, exactly as stated, **unconverted**. |
| `milling_measured_unit` | str, **new** | closed vocabulary: `SY` · `TON` · `SY+TON` · `OTHER` · `NONE` · null |
| `schema.milling_unit_status(record)` | derived, pure | one of `sy_only` · `tons_only` · `sy_and_tons` · `other_unit` · `not_present` · `unknown` · `inconsistent` |

`NONE` versus null is the whole design. The model must **assert** that a schedule has no milling
item; null is reserved for "extraction produced no answer". That makes the three states the standing
rule demands — *milling measured in tons* / *no milling on this plan* / *extraction failed* —
distinguishable instead of all being `milling_sy = null`. `inconsistent` covers the model
contradicting itself (unit `NONE` with a quantity, unit `SY` with tons) rather than silently
believing one side.

Verified on the six statuses directly (`schema.milling_unit_status` over synthesised cells) and end
to end on the six-plan corpus run below, where three distinct statuses came back for real:
`sy_and_tons` (Dunn), `sy_only` (four plans), `not_present` (the SD plan).

## 2. Dunn — 67,007 tons preserved, in tons

`c0e327cf80827ab9`, ND Job 23388, run through the real extractor against `00_input/_md_cache`:

```
milling_sy            = 408,216      (FULL DEPTH RECLAMATION, SY, p.13 — unchanged)
milling_tons          =  67,007      (63,092 MILLING PAVEMENT SURFACE p.16
                                      + 3,915 REMOVAL OF BITUMINOUS SURFACING p.7)
milling_measured_unit = "SY+TON"
milling_unit_status   = "sy_and_tons"
```

67,007 is exactly the number the session doc says was being dropped silently. No conversion was
applied in either direction; the two totals are not addable and nothing in the code adds them.

**The three-revision trap was handled.** `REMOVAL OF BITUMINOUS SURFACING | TON | 3,915` is printed
on pages 7, 8 and 9 — the superseded-revision duplication the golden agent found. It is counted
**once**. A diagnostic run that asked the model to itemise confirmed it excluded pages 8 and 9 by
name as earlier revisions of the same proposal page.

**Getting to 67,007 took four prose iterations and the intermediate results are worth recording**,
because three of them looked like success and were not:

| iteration | `milling_tons` on Dunn |
|---|---|
| first draft ("sum only the items whose unit is TON", item names listed) | 63,092 — the 3,915 removal line silently omitted |
| + `grading_quantity` clause amended to say tons removals go to `milling_tons` rather than "leave it out of every total" | 63,092 |
| + "any pay item named in the milling_sy definition belongs here when its unit is TON" | 63,092 |
| + "there is typically MORE THAN ONE such line, pages apart — scan the whole schedule; answering with only the largest single line is wrong" | **67,007** |

The diagnostic that unstuck it: the same field description **in isolation** returned 67,007 on the
first try, while the same description inside the full 18-field prompt returned 63,092. The field
definition was never the problem — attention across a crowded prompt was. That is the same lesson as
the harness-vs-live-path finding in `2026-08-10-mapping-rulings-and-corpus.md` §2, one level in:
**testing a field description on its own can pass while the shipped prompt fails.**

## 3. The no-regression run

Harness: `03_evaluation/2026-08-10_mapping_regression.py --arm new`, against `00_input/_md_cache`,
diffed against the committed baseline `outputs/2026-08-10_mapping_regression_new.json`. **Not**
against `_report_payload_cache/` — those payloads are keyed on PDF content hash with no mapping
version in the key and predate the 2026-08-10 schema change, so they describe July behaviour.

Six documents, chosen deliberately rather than by `--limit`'s alphabetical accident (a new `--only`
flag was added for this; a hash it cannot find is a fatal setup error, not a quietly smaller run):

| doc | plan | state | `milling_sy` baseline → now | `milling_tons` | status |
|---|---|---|---|---|---|
| `f19c9df671fd2fd7` | 9813645 Stearns | **MN** | 140,430 → **140,430** | null | `sy_only` |
| `9ff5dc83b09d4079` | Crow Wing SAP 018-603-024 | **MN** | 15,067 → **15,067** | null | `sy_only` |
| `3929bfb697838f3c` | 25-1076 | **SD** | null → **null** | null | `not_present` |
| `47bcf6b258b8547c` | (ND, milling bid in SY — control) | ND | 116,362 → **116,362** | null | `sy_only` |
| `c0e327cf80827ab9` | Dunn Job 23388 | ND | 408,216 → **408,216** | **67,007** | `sy_and_tons` |
| `609a8b856ceed52a` | 8416165 Fargo PR-23-E1 | ND | 193,507 → **193,521** | null | `sy_only` |

**MN/SD movement: none. The blocking condition is not met and this is demo-eligible on that test.**
The SD plan returning `not_present` rather than null is itself the new behaviour working: "this
schedule has no milling item" is now an answer instead of an absence.

Two movements to declare, both on ND plans and neither blocking:

1. **Fargo `milling_sy` 193,507 → 193,521 (+14, 0.007%).** The baseline is the correct figure — the
   five SY milling lines on pages 45–48 sum to exactly 193,507 and there is no 14 SY line anywhere in
   the document. This is a model arithmetic slip, **but it is stable, not noise**: two repeat runs of
   the identical final prompt both returned 193,521, so it is attributable to the prose change rather
   than to sampling. Small, on an ND plan, and reported rather than rounded away.
2. **Dunn `grading_quantity` 34,338 → 44,035.** `grading_quantity`'s prose was amended (its old
   clause "leave it out of every total" directly contradicted the new field). This number is
   unstable across runs on this document — 32,890 / 43,035 / 44,035 / 44,455 across four runs — so
   Dunn grading is noisy independent of this change, and I am not claiming either value is right.

The state of every document was determined from its own text, not assumed: Fargo (`609a8b85`) reads
as **ND** — "State of North Dakota", Cass County, `fargobidopenings.com` — and is not an MN plan
despite the MnDOT-style eight-digit plan id.

Evidence committed: `03_evaluation/outputs/2026-08-10_mapping_regression_new_milling_subset.json`
(the six-document `new` arm with the final prose, carrying an `extras` block per document with
`milling_tons` / `milling_measured_unit` / `milling_unit_status`).

**Not run: the other 11 documents.** This is a six-document subset, not the full 17-document arm.
The four never-milling MN documents and the remaining ND ones were not re-run, so this is evidence
about the plans listed above and not about the whole corpus.

## 4. `CONVERSION_REQUIRED` scoring

`tools/golden/2026-08-10_golden_join.py` previously scored a key match as `MATCH` whenever any
extracted quantity was non-null **regardless of whether the units agreed**, then computed a variance
across two different units. It now has the category `docs/_spec/2026-08-10-benchmark-table.md` §2.3
already designed:

- keys match, both sides quantified, **normalised units differ** → `CONVERSION_REQUIRED`;
- **not a hit**: out of `matched`, so precision is not inflated;
- **not a miss**: out of the recall denominator *and* the precision denominator, so a deliberate
  design gap (there is no conversion layer, by decision) is never presented as an extraction failure;
- **no variance** is computed — TON minus SY is not a number that means anything;
- counted and printed in its own `conv` column with an explanatory line, so it can't be netted away.

Unit comparison is tri-state. `norm_unit()` returns `None` for anything outside an explicit alias
table, and `None` never compares equal to anything **including another `None`** — two unrecognised
strings must not read as "the units agree". A row with an unknown unit on either side keeps its
previous status and gets a blank `unit_match`; it is never promoted to `CONVERSION_REQUIRED` on a
guess. Two new columns, `extracted_unit` and `unit_match`, are written to the comparison CSV.

**Current run: `conversion_required = 0`, and pooled recall 0.667 / precision 0.983 are unchanged.**
That is the honest result — today's golden set is MN-only, both sides read the same MN bid schedules,
and MN units agree. The category is built for the ND/SD golden files (`Bid Items.xlsx`,
`Proposal_NDOT_*`) that are not parsed yet, and for the tier-3 comparison against CSI's
unit-converted spreadsheet quantities.

**A zero from a new code path is not evidence the path works**, so the branch is covered by
`tools/golden/2026-08-10_test_conversion_required.py` — a **coverage** test, not a unit test: it
walks every distinct unit string in the golden CSV (32) and in `materials` (1,891) rather than
strings I remembered to write down. It passes, and **it caught a real defect on its first run**:
`S.Y.` on a real `milling_sy` corpus row normalised to unknown, because periods were only stripped
from the end. Every unit on a `milling_sy` row now normalises (`SY` 40 rows, `SQ YD` 12, `S Y` 8,
`SqYd` 5, `Square Yard` 2, `SQYD` 2, `S.Y.` 1 — all → `SY`, 3.02M SY total).

## 5. The payload-assembly edit — for the owner to apply, NOT applied

`apps/api/backend/report.py` is owned by other agents this round. Exact text in the spec, §5.1.
Summary and the reason it is shaped this way:

- Append a **`MILL_TON`** row to `quantities` when `record["milling_tons"]` has a value:
  `{"label": "MILL_TON", "value": ..., "unit": "TON"}`, plus its `field_confidence` entry.
- Add `"milling_unit_status": schema.milling_unit_status(record)` to `rep["identity"]`.
  `schema` is already imported at `report.py:27`. No frontend change is needed —
  `report-card.tsx:232-238` renders every quantities row generically, so `MILL_TON 67,007 TON`
  appears as-is.

**The label must not be `MILL`.** Two consumers key off that label positionally and neither reads the
unit: `bid_projects_record.py:307` writes it into the column literally named **`mill_sy`**, and
`competitor_predict_live.py:42` maps `"MILL" → "mill_sy"` and feeds it to the fitted competitor
weights. Emitting tons under `MILL` would put tons into a square-yard column and a model feature —
the same defect class as the one being fixed, pointing the other way.

**Named finding, two verification methods.** No consumer of `mill_sy` checks `mill_unit` today. (1)
`grep -rn "mill_unit"` across `apps/ pipelines/ data/ tools/` returns only the writer
(`bid_projects_record.py`), its YAML mapping and its test — no reader. (2)
`competitor_predict_live.py`'s `_MATERIAL_COLS` / `LABEL_TO_MATERIAL_COL` select the seven quantity
columns and no unit column appears in the query at all. The unit columns are recorded, not enforced.

**Known gap, stated so it is not discovered later:** with this edit the tons value reaches the
extraction record, the payload cache and the report, but **not the database** — `bid_projects` has no
`mill_tons` column and adding one is DDL, which is out of scope. `mill_unit` stays `'SY'` for the SY
row, exactly as today.

## 6. What I did not do

- No conversion, no depth factor. `bucket_hierarchy.csv`'s unverified 1.75 Ton/CY and SDDOT's 1.50
  tons/CY for salvaged granular material are a different material, state and provenance; neither is
  used and neither is recorded as usable.
- No DDL, no writes to `bid_projects` / `bid_results`, no `publish_to_supabase`, no bulk republish.
  The only database access this session was a **read-only** SQLite open of `csi_v2.db`.
- Did not touch `report.py`, `final_report.py`, `report-card.tsx`, `apps/web/src/app/api/report/**`,
  `s4_extract_rag.py`, `pipelines/ci_model/`, or `road_midpoint.py`.
- Did not start the item-number layer, Chroma hosting, or cache demotion.
- Nothing pushed.

Test state: `pytest pipelines/plan_reader/01_pipeline` — 55 passed before the change and 55 passed
after (the 6 chromadb-dependent tests error identically both ways; `chromadb` is not installed in
this sandbox, a pre-existing environment gap).
