# Spec — silently-dropped CY/SY aggregate & mix quantities, merged into base/shoulder/mix tons

Date: 2026-08-10 · Status: **implemented and verified against a live extraction**

---

## 1. The problem, stated exactly

`base_tons`/`shoulder_tons`/`hot_mix_tons` only ever captured bid-schedule line items denominated
in TON. A CY-measured base item, or an SY-measured aggregate/mix item that states its own
thickness in inches, was extracted for nothing — no field, no `field_confidence` entry, no
citation — and silently dropped from every downstream total.

Caught on `MN_MURRAY_CO_FULDA_2025-08-07` (payload cache
`pipelines/plan_reader/00_input/_report_payload_cache/a3171c2187e8af85.json`, plan_id `9786015`):
the report showed only 2 of 5 real materials. Two concrete items exposed the gap:

| item | description | unit | qty | fate before this fix |
|---|---|---|---|---|
| 41 | Class 5 Aggregate Base (CV)(P) | CY | 2,485 | dropped — `base_tons` only accepts TON |
| 40 | 8" Class 5 Alley & Shouldering Aggregate Surfacing (CV)(P) | SY | 38 | dropped — `shoulder_tons` only accepts TON |
| 44–47 | Type SP Wearing/Non-Wearing Course Mixture, various stated depths | SY | 5,368 / 5,368 / 1,703 / 1,703 | dropped — `hot_mix_tons` only accepts TON |

This is a correction to that extraction gap, not a new source of model bias — these are real
material quantities the bid schedule states, that the pipeline previously extracted nothing for.

---

## 2. The fix, in one sentence

Capture each qualifying item's own stated numbers (quantity, and thickness if SY), do **zero**
arithmetic in the extraction prompt, and let code sum and density-convert every item into the
same `base_tons`/`shoulder_tons`/`hot_mix_tons` total the native TON extraction already
represents — so the report and the DB row are always the same number (see §6).

---

## 3. A real bug caught mid-implementation: the model's own arithmetic was wrong

The first version of this fix asked the model to pre-compute a single CY (or SY·inch) total per
bucket — the same shape as the existing `milling_tons` field's "sum these stated numbers"
instruction. A live extraction test on the Murray plan caught the returned **value** disagreeing
with the arithmetic spelled out in the model's own **reason** text:

- `mix_sy_depth_product`: reason text correctly computed `10,736 + 16,104 + 2,554.5 + 4,257.5 =
  33,652` (and even said "wait, recalculating..." mid-sentence) — but the returned `value` was
  **38,167**, a ~13% error with no relationship to the correct sum.
- `base_cy`: reason text said `2,485 + 8.44 = 2,493.44` — the returned `value` was **2,496.06**.

Two-term addition of already-stated numbers (`milling_tons`'s design) is reliable — verified
correct twice in testing (`8,731 + 7,097 = 15,828`, exact, both before and after this change). A
4-item multiply-then-sum, and even a 1-multiply-1-add case, was not. **Multiplication, not just
multi-item complexity, is the unreliable operation here**, even at `temperature=0`.

**Fix**: redesigned `base_cy`/`shoulder_cy`/`mix_sy_depth_product` from pre-summed `num` scalars
into raw per-item `items`-type array fields (`base_cy_items`, `shoulder_cy_items`,
`mix_sy_depth_items` — `schema.py:111,141,178`). Each item is `{quantity, unit, depth_in, page,
note}`, holding only numbers read directly off the page. **The model never multiplies, sums, or
converts anything for these fields** — every arithmetic step moved into
`material_tons_merge.py`, auditable, testable Python. Re-verified live on the same Murray plan
after the redesign: `base_tons=3,851.75`, `shoulder_tons=13.09`, `hot_mix_tons=1,901.34`, every one
matching an independent manual calculation exactly, and `grading_quantity`/`milling_sy` unchanged
at `2,495`/`15,828` (no prompt-perturbation regression on the pre-existing fields).

This also meant dropping the originally-planned `base_measured_unit`/`shoulder_measured_unit`/
`mix_measured_unit` fields entirely — with a real items list to inspect, the unit-status
classification is fully code-derivable (`schema.py:441` `_aggregate_unit_status`) and doesn't need
a separate, redundantly-model-asserted summary field that could itself drift from the items list.

### 3.1 A second bug, same session: mix wrongly reused the CY-conversion formula

`material_tons_merge.py`'s first cut called the same per-item resolver
(`schema.resolve_cy_item`, `CY = SY * inches / 36`) for all three buckets, including mix. Mix has
**no CY intermediate** — its formula is `SY * inches * MIX_TON_PER_SY_INCH` directly. Reusing the
base/shoulder resolver silently divided every mix product by 36 before the density multiplication,
undercounting mix tons **36x** (`52.8` instead of the correct `1,901.3` on the Murray plan — caught
by comparing against an independent manual calculation, not by any test that would have passed
either way). Fixed by adding a distinct `schema.resolve_sy_depth_product` (`schema.py:421`, no
`/36`) and threading the correct resolver through both `material_tons_merge._sum_items` and
`schema.mix_unit_status` explicitly — `_sum_items` takes `resolver` as a required, never-defaulted
parameter (`material_tons_merge.py:53`) specifically so this class of mix-up can't happen silently
again.

### 3.2 A third bug, same session: the extraction call ran out of response budget

Adding three array-shaped fields to the whole-doc extraction prompt pushed a real response past
`call_json`'s default `max_tokens=2048`, truncating the model's JSON mid-object and failing to
parse — confirmed live on the Murray plan before the fix. Raised to `max_tokens=6000` in
`extract_fields()` (`s3_extract.py:222`), which leaves real headroom for a document with several
qualifying items across all three new fields plus every existing field's own citation text.

---

## 4. The item shape and the two resolvers

```
{"quantity": <number>, "unit": "CY" | "SY", "depth_in": <number or null>, "page": <int>, "note": <str>}
```

- `schema.resolve_cy_item(item)` (`schema.py:397`) — base/shoulder only. `unit == "CY"` returns
  `quantity` directly; `unit == "SY"` with a positive `depth_in` returns `quantity * depth_in / 36`
  (pure geometry — area × depth = volume, no assumed density); anything else (SY with no usable
  depth, an unrecognised unit) returns `None` — a real item, just not convertible without guessing.
- `schema.resolve_sy_depth_product(item)` (`schema.py:421`) — mix only. `unit == "SY"` with a
  positive `depth_in` returns `quantity * depth_in` (no `/36` — mix's density constant already
  operates on the raw SY·inch product); anything else returns `None`.

Both are pure and shared between `material_tons_merge.py` (the sum) and `schema.py`'s status
functions (the classification), so the two can never disagree about what a given item resolves to.

**Depth-sourcing rule, unchanged from the original scope**: only ever use a thickness printed in
that exact item's own description. Never borrow one from a different item, never assume one. An SY
item with no stated depth anywhere in its own text resolves to `None` and is named
(`sy_no_depth_present`, §5), never silently excluded without a trace.

**Base/shoulder mutual exclusivity**: item 40 ("... Shouldering Aggregate Surfacing") is,
by name, ambiguous between the two buckets, and an early live test showed the model listing it in
*both* `base_cy_items` and `shoulder_cy_items` — double-counting it. Both field descriptions
(`schema.py:141,178`) now explicitly cross-reference each other and state every qualifying item
belongs in exactly one of the two, mirroring `base_tons`/`shoulder_tons`'s existing split
(`GRAVEL SURFACING`/`TRAFFIC SERVICE AGGREGATE` → base; `AGGREGATE SURFACING CLASS ...` → shoulder).

---

## 5. Unit status (derived, code-only, no model-asserted summary field)

`schema.base_unit_status()` / `shoulder_unit_status()` / `mix_unit_status()` (`schema.py:482-496`)
classify a bucket purely from `(native_tons_field, items_list)` — no separate `*_measured_unit`
field to trust or drift out of sync:

| status | condition |
|---|---|
| `tons_only` | items list is empty (`[]`) and the native tons field has a real value |
| `cy_only` | every convertible item resolved via direct CY read |
| `sy_converted_only` | every convertible item resolved via SY-with-depth conversion |
| `mixed` | both a direct CY read and an SY-converted item are present |
| `sy_no_depth_present` | at least one item is SY with no usable stated depth — seen, not convertible |
| `not_present` | items list is empty and the native tons field also has no value |
| `unknown` | the items field itself is `null` — extraction produced no answer at all |
| `inconsistent` | a non-empty items list that classifies as neither of the above (garbled response) |

`unknown` is never reported as `not_present`: a model returning `null` (no answer) and a model
asserting `[]` (a real "nothing here") are different claims and stay distinguishable, same standing
rule as `milling_unit_status` (`docs/_spec/2026-08-10-milling-unit-capture.md`).

---

## 6. The merge, and why report/DB agreement is guaranteed by construction

`material_tons_merge.merge_material_tons(record)` (`material_tons_merge.py:84`) returns
`{"base_tons": ..., "shoulder_tons": ..., "hot_mix_tons": ...}` — native TON value plus the summed,
density-multiplied items total, or `None` if both are absent (never a bare `0` standing in for
"we don't know").

`apps/api/backend/report.py::process_pdf` calls this **once** (`report.py:272`), before both the
archetype classification (`qrow`, which used to read `base_tons`/`shoulder_tons` raw and now reads
the merged value via an `_effective()` helper, `report.py:275`) and the displayed `quantities` list
(`report.py:322` area) — and `bid_projects_record.py` reads whatever ends up under the `"BASE"`/
`"SHLDR"`/`"MIX"` labels in `payload["quantities"]` verbatim, with zero changes needed there. One
computation, three consumers (archetype, report, DB row) — they cannot disagree, because nothing
computes this number twice. This matters beyond tidiness: a report and a stored value disagreeing
over the same project is the specific failure class CLAUDE.md's invariant #1 documents as the
reason the old CI subprocess was removed entirely.

**Confirmed concretely**: before this fix, the Murray plan's rendered report already said
"Work Type: Reconstruct / Rebuild" while the underlying JSON payload's `archetype` field said
`"Grading/Earthwork"` — the two disagreed because the archetype was computed from `base_tons=null`
(dropped) while a human reading the report saw the real bid schedule. `_archetype()`
(`apps/api/backend/project_registry.py:48-63`) requires `paving` (mix ≥ 1,000 tons or ≥15% share)
**and** `GRADE_CY ≥ 500` for "Reconstruct/Rebuild". Post-fix, `hot_mix_tons` merges to `1,901.34`
(≥ the 1,000-ton paving threshold) and `grading_quantity` stays `2,495` (≥ 500) — `archetype` now
computes to `"Reconstruct/Rebuild"`, matching what the report already displayed. This fix closes
that disagreement at its root rather than patching either side to match the other.

**Idempotent by construction**: `merge_material_tons` is a pure function of the extraction record.
It never reads `scratch.bid_projects`, so calling it twice on the same record always yields the
same three numbers — no accumulation risk from re-running the pipeline on an already-processed plan.

---

## 7. Constant provenance

`AGGREGATE_TON_PER_CY = 1.55` and `MIX_TON_PER_SY_INCH = 0.0565` (`material_tons_merge.py:48,50`)
are CSI-supplied (MnDOT reference conversion table), confirmed 2026-08-10 — a different, more
authoritative source than `bucket_hierarchy.csv`'s `1.75 Ton/CY`, which every existing reference to
it flags as unverified and never checked against a plan (`schema.py`'s `milling_tons` comment,
`docs/_spec/2026-08-10-milling-unit-capture.md:44-49,269-271`). Both are fixed, MnDOT-sourced
numbers, not a configurable per-state/per-material lookup table — explicitly deferred if this ever
needs to expand past MnDOT projects.

---

## 8. Explicitly out of scope

- No CY→TON (or SY→TON) conversion is attempted anywhere the depth isn't stated on that exact
  line item — an SY item with no stated depth stays unconverted, named via `sy_no_depth_present`,
  never guessed.
- No new `scratch.bid_projects` columns — the merged value replaces what's already written to
  `base_tons`/`shldr_tons`/`mix_tons`; nothing new is added.
- `bid_projects_writer.py` (the actual Postgres writer) was not relocated into `pipelines/` — it
  already lives in `apps/api/backend/` and is called from `report.py:437`; only the *value* being
  written changed, not where the write happens.
- `milling_sy`/`milling_tons` were not touched — confirmed correct and out of scope for this fix.

## 9. Downstream consequences — check, don't assume

- `apps/api/backend/competitor_predict_live.py`'s `_MATERIAL_COLS`/`LABEL_TO_MATERIAL_COL` read
  `base_tons`/`shldr_tons`/`mix_tons` directly as live model features. Any plan whose total moves
  from null/low to a real number changes that plan's scored features immediately — re-validate
  Precision@5 (rough edge #10's baseline, 0.282) once this is live against real traffic, rather than
  assuming an improvement. **Not done in this pass** — this sandbox has no `SUPABASE_TEAM_DB_URL`
  configured (same gap as CLAUDE.md rough edge 7), so no live-DB or model-scoring validation was
  possible here; the verification in this doc is extraction-layer and arithmetic-layer only.
- A project's `archetype` can shift as a direct, intended consequence (§6) — this itself feeds the
  candidate-pool "same_type" signal (rough edge #10). Expected, not a regression, but worth
  watching in aggregate once this runs against more of the live corpus.
