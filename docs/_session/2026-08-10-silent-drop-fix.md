# Session report — task 2a, the silent drop on the tons buckets

Date: 2026-08-10 · Branch `2026-08-10-mapping-honesty` · Commit `0bd858d`
Spec: [`docs/_spec/2026-08-10-tons-bucket-unit-capture.md`](../_spec/2026-08-10-tons-bucket-unit-capture.md)

**Scope held:** nothing in this change multiplies anything. Conversion is task 2b and is untouched.

---

## 1. What the defect actually was — bigger than the board records

The board records plan **9786015** (CSAH 2 / Maryland Ave, Fulda, Murray Co MN) as a **base**
problem: base is 2,485 CY, `base_tons` is tons, so the number was dropped.

Re-running the real document through the live path's own extractor shows the plan was dropping
**all three tons buckets**, not one:

| field | old arm | what the schedule actually states |
|---|---|---|
| `hot_mix_tons` | `null` | four Type SP mixture lines, **14,142 SY** total, measured in SQUARE YARDS |
| `base_tons` | `null` | `Class 5 Aggregate Base (CV) (P)` — **2,485 CY** (page 27) |
| `shoulder_tons` | `null` | `8" Class 5 Alley & Shouldering Aggregate Surfacing (CV) (P)` — **38 SY** |

Three bare nulls, and nothing anywhere in the record saying those items exist. A plan with a full
paving section read exactly like a plan with no paving in it. That is the standing rule —
*a failure and a legitimate empty answer must never share a return value* — **eleventh instance**
(milling was the tenth, earlier tonight).

---

## 2. The field shape, and how it matches the milling precedent

Deliberately the **same shape and the same vocabulary** as
`docs/_spec/2026-08-10-milling-unit-capture.md`, because a second differently-named mechanism for
one idea would be worse than the bug.

| milling (tenth instance) | tons buckets (eleventh instance) |
|---|---|
| `milling_sy` — unchanged, SY only | `hot_mix_tons` / `base_tons` / `shoulder_tons` — unchanged, TON only |
| `milling_measured_unit` — closed vocab `SY`/`TON`/`SY+TON`/`OTHER`/`NONE`/`null` | `{bucket}_measured_unit` — closed vocab `TON`/`TON+OTHER`/`OTHER`/`NONE`/`null` |
| `milling_tons` — the off-unit quantity, verbatim, unconverted | `{bucket}_unconverted` — the off-unit **items**, verbatim, unconverted, unsummed |
| `schema.milling_unit_status()` — derived, 7 states | `schema.bucket_unit_status(record, field)` — derived, 6 states |
| `NONE` asserts absence; `null` reserved for extraction failure | identical contract |
| `inconsistent` when the declared unit contradicts the values | identical |
| carried to the report without a `MILL` label, because `MILL` writes into `mill_sy` | carried on `identity` only, never as a `MIX`/`BASE`/`SHLDR` quantities row, for the same reason |

**The one deliberate divergence, and why.** Milling's off-unit capture is a *scalar subtotal*
(`milling_tons`) because milling has exactly two candidate units, so two numeric fields are a
complete decomposition. These three buckets are not decomposable that way. Measured on the
item-level golden corpus (`tools/golden/2026-08-10_golden_rows.csv`, 772 rows over 8 plans,
categorised with `quantity_crosswalk.spec_category`), **a single plan routinely carries a single
bucket in two units at once**:

| bucket | unit combinations seen within one plan |
|---|---|
| `base` | `TON+CY`, `TON+SY` |
| `hma` | `TON+SY`, `TON+GAL`, `TON+EACH`, `TON+GAL+SY+SF` |
| `surfacing` (shoulder) | `CY+SY`, `TON+LF` |

A single "off-unit subtotal" scalar would therefore **add cubic yards to square yards** — the same
conflation this fix exists to prevent, one layer further in. Per-unit subtotal fields would mean
four or five new numeric fields per bucket. The per-item line
(`DESCRIPTION | QUANTITY | UNIT`) carries the item, its value **and** its unit without summing
anything, which is exactly what task 2a asks be recorded. 9786015 immediately exercises this: its
hot mix is four separate SY lines that must not be added together.

`bucket_unit_status` is a second function rather than a generalisation of `milling_unit_status`
because milling decides between two *numeric* fields and this decides between a numeric field and a
*text list*; folding them would mean editing the proven, shipped milling path to gain nothing. The
shared half of the vocabulary (`not_present` / `unknown` / `inconsistent`) is spelled identically on
purpose.

### Carry-through — the registry claim, tested

`apps/api/backend/payload_carry.py`'s docstring predicted this exact entry ("a captured raw milling
value + unit"). Adding the three fields **was one tuple entry each**: `report.py` picks up the value
and a three-valued `_status` automatically, and `final_report.py` (which this task does not own)
needed **no edit at all** — it already iterates `CARRIED_FIELDS` at three call sites
(`:538`, `:702`, `:823`). Verified by running the registry end to end, not by reading it.

`report.py` additionally puts the three derived statuses on `identity`, next to the existing
`milling_unit_status`:

```
"hot_mix_unit_status" / "base_unit_status" / "shoulder_unit_status"
```

Three distinguishable states are now guaranteed by construction:
**found-but-unconvertible = `unconverted_only`**, **genuinely absent = `not_present`**,
**extraction failed = `unknown`**.

---

## 3. The 9786015 result — red before green, on the real document

The mapping is a prompt, so the proof is a differential re-run of the same document through the same
extractor at `temperature=0`, not a unit test. Runner:
`pipelines/plan_reader/03_evaluation/2026-08-10_tons_unit_capture_run.py`.
Corpus: the local iCloud mirror (Box reads time out); the 466-page PDF was converted into
`00_input/_md_cache/a3171c2187e8af85.json` — the bid schedule line is on **page 27**:

```
|41|Class 5 Aggregate Base (CV) (P)|CY|2,485|
```

**RED** (`outputs/2026-08-10_tons_unit_capture_9786015_old.json`) — the shipped field set:

```
base_tons = null      capture = null      base status = unknown
hot_mix_tons = null   shoulder_tons = null   both also unknown
```

**GREEN** (`outputs/2026-08-10_tons_unit_capture_9786015_new.json`):

```
base_tons            = null            (correct — the schedule states no tons)
base_measured_unit   = "OTHER"
base_unconverted     = "Class 5 Aggregate Base (CV) (P) | 2485 | CY"
base_unit_status     = "unconverted_only"

hot_mix_unconverted  = 4 lines, 5368 SY + 5368 SY + 1703 SY + 1703 SY, each named separately
shoulder_unconverted = "8\" Class 5 Alley & Shouldering Aggregate Surfacing (CV) (P) | 38 | SY"
```

The item, its value, its unit and the reason it was not counted — for all three buckets. **No
multiplication anywhere in the change.**

The seven quantity totals are **byte-identical between the two arms** on this document
(`grading_quantity = 2495`, `milling_sy = 15828`, the rest null), which is asserted as a test: adding
six fields to a prompt can perturb the fields already in it, and on this document it did not.

---

### 3.1 No-regression sweep — the guarded fields did not move, and this is not a one-plan bug

`--sweep` over all 18 cached plans on the new arm, diffed against the committed baseline
`03_evaluation/outputs/2026-08-10_mapping_regression_new.json`
(`outputs/2026-08-10_tons_unit_capture_sweep.json`, 0 ERROR):

**`hot_mix_tons` / `base_tons` / `shoulder_tons` moved on ZERO of the 17 baseline documents.** That
is the blocking pass condition and it passed. (Five other movements, none in a guarded field, are in
§6.)

The sweep also shows the defect is corpus-wide, not one plan:

| bucket | `tons_only` | `unconverted_only` | `tons_and_unconverted` | `not_present` | `inconsistent` |
|---|---:|---:|---:|---:|---:|
| `hot_mix_tons` | 10 | 3 | 0 | 2 | 3 |
| `base_tons` | 4 | **6** | **1** | 7 | 0 |
| `shoulder_tons` | 3 | 2 | 0 | 13 | 0 |

**7 of 18 plans were dropping their aggregate base silently** — every one a real, named item:
`AGGREGATE BASE (CV) CL 6 | 749 | CU YD`, `Aggregate Base Class 5 | 1900 | CY`,
`Aggregate Base Course Cl 5 | 2700 | CY`, `Salvaged Base Course | 1050 | CY` (alongside 1,070 TON on
the same plan), and one airport plan with five separate C.Y. lines. Before this change every one of
those was a bare null.

The three `hot_mix` `inconsistent` results are the design working, not noise: two are
`measured_unit = TON` with no tonnage and nothing unconverted — the model contradicted itself, and
that is surfaced rather than silently resolved toward either reading.

## 4. The coverage test, and its red-before-green proof

`pipelines/plan_reader/01_pipeline/test_tons_bucket_unit_capture.py` — **16 tests, all passing.**

It is a coverage test, not a unit test: the headline assertions run against the **committed
artifacts of the real extraction run above**, so the suite needs no API call but is asserting on
evidence, not on a mock. A test that passes on a plan with no base at all proves nothing and is
explicitly not what is asserted; the assertion is on a plan whose base **exists and is CY-measured**.

- `test_9786015_cy_base_used_to_be_a_bare_null_the_red_half` — the before state, committed.
- `test_9786015_cy_base_is_now_surfaced_with_its_value_its_unit_and_a_reason` — `2485`, `CY`,
  `AGGREGATE BASE` and `unconverted_only` must all survive; and `base_tons`/`shoulder_tons`/
  `hot_mix_tons` must all still be null, i.e. nothing was converted.
- `test_9786015_hot_mix_and_shoulder_were_dropped_the_same_way_and_are_now_surfaced_too`.
- `test_red_and_green_are_the_same_document_and_the_same_seven_totals` — the perturbation guard.
- `test_found_but_unconvertible_absent_and_failed_are_three_distinct_values` — the standing rule,
  asserted directly, per bucket.
- `test_every_declared_unit_maps_to_a_status_and_contradictions_are_surfaced` — exhaustive over
  vocabulary × tons-present × unconverted-present (16 combinations per bucket), and it asserts that
  every token in the closed vocabulary is reachable.
- plus: a null unit is never read as absence; both cell-shaped and flat records accepted; asking it
  about `milling_sy` raises rather than returning a plausible-looking status; `0` tons is not a
  quantity.

**Red proof (code half).** Running the same test file against `git show HEAD:…/schema.py` fails at
**collection**:

```
E   AttributeError: module 'schema' has no attribute 'TONS_BUCKETS'
!!!! Interrupted: 1 error during collection !!!!
```

**Red proof (behaviour half).** The committed old-arm artifact — three bare nulls and status
`unknown` on the real document.

**No regressions:** `apps/api`'s pytest suite run on `.venv` shows only the two pre-existing
failures (`test_midpoint_bridge` — rough edge 6's MnDOT flake; `test_candidate_pool_consistency` —
missing `pyarrow`). Nothing new.

---

## 5. 🔴 A defect this change tripped, named and only half-fixed

**`s3_extract.call_json` cannot tell a response cut off at the token cap from a malformed one.**

Adding six schema fields pushed the whole-doc extraction to **exactly 2,048 output tokens** on
9786015 — `stop_reason == "max_tokens"`, verified against the API, `output_tokens == 2048`. The
answer was complete and correct up to the cut. `call_json` caught the `JSONDecodeError`, printed
"JSON parse failed", and returned `None`; `extract_fields` then does `data = call_json(prompt) or {}`
and produces **a whole record of clean null cells** — indistinguishable from a plan that states
nothing. That is the standing rule again, sitting in the extraction call itself, and it has been
latent (`payload_carry.py:56-59` already declares the same hole from the RAG side).

**Fixed here:** the whole-doc budget is now `EXTRACT_MAX_TOKENS = 6000`, sized to the field count and
commented to be raised when fields are added, and the warning now names truncation as truncation.

**NOT fixed here, deliberately:** `call_json` still returns `None` for both causes. Changing its
contract touches four callers including the live RAG path, the night before a demo, and this task is
"do not add features while cleaning". **Recommend it as a board item.** Note the sizing is a real
constraint, not a one-off: **every field added to `EXTRACT_FIELDS` costs output tokens**, and the
failure mode when the budget is exceeded is a silently empty plan.

---

## 5.1 NO CONVERSION ARITHMETIC WAS WRITTEN — explicit confirmation

**I wrote no conversion arithmetic of any kind.** No multiplication of a SY or CY quantity into
tons, no factor constant, no lb/SY, no ton/CY, nothing behind a flag, a disabled branch, a commented
block or a TODO stub. Nothing was written and then removed, so there is nothing dormant to find.

Verified by grepping every added line of the diff for `*`, `factor`, `1.75`, `1.50`, `lb/`, `/ 27`,
`density`, `depth`: the only hits are (a) prose comments that say conversion is **not** done here and
name the factors that are **not** used, (b) `*_unconverted` appearing inside comment text, (c) a
`glob("*.json")` in the runner, and (d) `**{...}` dict-unpacking in `report.py`'s identity literal.

`{bucket}_unconverted` carries the **raw stated value and the raw stated unit, verbatim and
unsummed** — `Class 5 Aggregate Base (CV) (P) | 2485 | CY`, not a normalised or pre-scaled number,
and the four SY hot-mix lines on 9786015 are kept as four separate lines precisely so nothing is
pre-aggregated. A later conversion layer (ours or PR **#102** `fix/aggregate-mix-tons-conversion`)
gets the untouched plan number. `docs/_spec/2026-08-10-placed-material-conversion.md` was not
implemented in any part.

`pipelines/plan_reader/00_input/golden_dataset.csv` was **not touched** (`git status` clean for it).

## 6. Things that contradict, or are not on, the board

0. 🔴 **Stearns `milling_sy` does NOT reproduce at 140,430 today — it comes back 70,263.**
   Board P1 #20 says "Tell CSI that Stearns `milling_sy` is now 140,430, not 70,263" (ruling #9, FDR
   included), and the merge note repeats it. On `f19c9df671fd2fd7` (plan `9813645`, `COUNTY OF
   STEARNS`, CP 073-123-025) the document states `FULL DEPTH RECLAMATION 70167 SY` and three
   `MILL BITUMINOUS SURFACE` lines summing to 70,263 SY — 140,430 together. Live extraction returns
   **70,263**: the FDR is not being counted.
   **This is not caused by this change.** Verified two ways, five runs, none returning 140,430:
   (i) my runner's `old` arm — the shipped field set with none of the six new fields — twice, and its
   `new` arm twice, all 70,263; (ii) the baseline harness's own `2026-08-10_mapping_regression
   .run_one(..., "new")`, unmodified, once: 70,263. Either the committed baseline captured a
   non-reproducing run, or something moved since. **Do not repeat the 140,430 number to CSI until
   someone re-derives it.** Milling is not this task's file to fix.
1. **The board calls 9786015 a base problem. It is a three-bucket problem.** Hot mix (14,142 SY over
   four lines) and shouldering (38 SY) were being dropped by the same mechanism. Board item 2a and
   D1 should say all three.
2. **`base_tons = null` on this plan was never a mapping miss.** The recall number in P0 #1
   ("recall 0.667, the failure mode is recall not accuracy") counts cases like this as extraction
   failures. They are not — the item was read, and the unit was the blocker. This is exactly the D1
   `CONVERSION_REQUIRED` argument, now with a live, non-MN-golden example: the golden set is MN-only
   and reported `conversion_required = 0`, while a real MN plan CSI actually tested has **three**
   buckets in that state. Whoever closes D1 should re-check that zero.
3. **Every existing cached payload will now render three loud "⚠️ Not captured" rows** (hot mix /
   base / shoulder "not counted"), because those payloads predate the fields — the same behaviour
   phasing already has, and the honest reading, but it is three more rows on ten stale payloads.
   `python tools/2026-08-10_rewarm_demo_cache.py --check` lists them; a re-warm clears it. **If a
   stale plan is on Wednesday's demo path, this is visible on stage.**
4. **`payload_carry.render_value()` collapses newlines to spaces**, so a multi-line
   `*_unconverted` renders as `A | 1 | CY B | 2 | SY` in the §① snapshot. The raw value is intact on
   `identity`; only the rendered cell is ambiguous. Left alone — `render_value` is shared with
   phasing and this task does not own a rendering change.
5. **The aggregate-surfacing / riprap / crushing rulings stay open**
   (`quantity_crosswalk.py::CSI_OPEN_QUESTIONS_2026_08_07`). Nothing here assumes an answer: the new
   fields report what the schedule *says*, never what a bucket *should* be.
6. **Not attempted (needs DDL, owner's call):** there is no column in `scratch.bid_projects` for an
   unconverted quantity. The item reaches the extraction record, the payload cache and the report —
   **not** the database. Same gap milling's `mill_tons` has.
7. **9786015 is not in the golden set.** The 8 item-level golden folders include a *different*
   Murray project (`25051 Murray County (CSAH 42, 47, CR 67)`). Verified two ways: the folder list
   from `2026-08-10_golden_rows.csv` contains no `08.07.25 MURRAY … FULDA` row, and a full-text
   search of `00_input/_md_cache` for `FULDA` returned nothing before this session converted the
   PDF. So this plan is new corpus, not a re-scoring of an existing golden row.
