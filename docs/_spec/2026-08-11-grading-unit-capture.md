# Spec — `grading_quantity` gains the same off-unit capture the other buckets have

Date: 2026-08-11 · Branch `2026-08-10-mapping-honesty` (PR #104) · Status: **written before the
code, then implemented in the same pass**

This is the **twelfth** instance of this repo's standing rule — *a failure and a legitimate empty
answer must never share a return value* — and the **third** instance of the same off-unit shape.
It is deliberately a copy of the two that shipped the day before, not a new mechanism:

- `docs/_spec/2026-08-10-milling-unit-capture.md` (tenth instance) — `milling_sy` / `milling_tons` /
  `milling_measured_unit` + `schema.milling_unit_status()`.
- `docs/_spec/2026-08-10-tons-bucket-unit-capture.md` (eleventh) — `hot_mix_tons` / `base_tons` /
  `shoulder_tons` each gaining `*_measured_unit` + `*_unconverted` + `schema.bucket_unit_status()`.

---

## 1. Why this is needed, and why it is not a prose change

Alex's returned `.docx` assigns **`Clean Rock` → `grading_yards`** (the six-box pick, decoded from
the checkbox XML; `docs/_session/2026-08-11-alex-conformance-encoding.md` §2, ruling #24).

The shipped `grading_quantity` prose already names Clean Rock. It fires **0 / 13** measured runs,
and the model says exactly why, in its own stated reason
(`docs/_session/2026-08-11-alex-conformance-behavior.md` §4.2):

> "CLEAN ROCK (Item 045) is listed under grading definition but is measured in TON not CY so not
> counted here."

That is a **self-contradiction inside one field description**. `grading_quantity` says

> "Also count 'SALVAGE AND REUSE EXISTING AGGREGATE' and 'CLEAN ROCK'."

and, two sentences later,

> "When a removal is measured in square yards or tons, do NOT convert it and do NOT count it here."

Dunn's Clean Rock is `| CLEAN ROCK | TON | 758 |`. The model obeyed the second clause. The contrast
that proves the diagnosis: **`SALVAGE AND REUSE EXISTING AGGREGATE` fires 3/3** — on White Shield
that plan prices it in **CY**, so no clause conflicts. *The two unassigned picks differ only in the
unit the state happened to use.*

**Deleting the second clause is not an option.** It exists because no verified SY→CY or TON→CY
factor exists (depth is stated on 0 of 41 corpus removal rows). Counting a TON item into a CY total
is the exact conflation this project spent a day proving closed.

So honouring Alex requires the **third** structural answer, not a wording tweak: `grading_quantity`
must be able to say *"this item is grading, here it is, here is its unit, and here is why it is not
in the total"* — which is precisely what `base_unconverted` / `hot_mix_unconverted` /
`shoulder_unconverted` already do for their buckets. A field addition is not a prose change, hence
this spec.

## 2. What is added

Two model-answered fields and one derived status. **Nothing is converted anywhere.**

| field | type | role |
|---|---|---|
| `grading_measured_unit` | str | closed vocabulary: `CY` · `CY+OTHER` · `OTHER` · `NONE` |
| `grading_unconverted` | str | every grading pay item whose unit is NOT CY, one per line, `DESCRIPTION \| QUANTITY \| UNIT`, verbatim |
| `grading_unit_status` | derived | one of the six statuses below. No model call. |

```
GRADING_UNIT_TOKENS  = ("CY", "CY+OTHER", "OTHER", "NONE")

GRADING_UNIT_STATUSES = (
    "cy_only",              # unit CY — grading_quantity carries the whole quantity
    "unconverted_only",     # unit OTHER — the total is null BY DESIGN; the items are named
    "cy_and_unconverted",   # unit CY+OTHER — both real; the two are NOT addable
    "not_present",          # the model asserted there is no grading item. A legitimate empty answer.
    "unknown",              # no answer at all — extraction failure. NEVER reported as not_present.
    "inconsistent",         # the declared unit contradicts the values. Surfaced, not resolved.
)
```

### 2.1 Why the token spellings are what they are

The two shipped precedents already differ in their *first* token, and they differ **for the same
reason this one does**: the token names the bucket's NATIVE unit.

- milling is SY-native → `sy_only`, `sy_and_tons`
- the tons buckets are TON-native → `tons_only`, `tons_and_unconverted`
- grading is CY-native → **`cy_only`, `cy_and_unconverted`**

The four tokens that carry no unit in their name — `unconverted_only`, `not_present`, `unknown`,
`inconsistent` — are spelled **byte-identically** to the tons-bucket vocabulary, on purpose. It is
one idea, not three. Same for the closed unit vocabulary: `NONE` is the answer for "there is no such
item", and `null` is never used for that.

### 2.2 Why a fourth entry in `TONS_BUCKETS` was rejected

`schema.TONS_BUCKETS` and `bucket_unit_status()` hard-code `TON` / `TON+OTHER` as the in-unit
tokens. Adding grading there would either (a) force a CY bucket to answer `TON`, which is a lie the
closed vocabulary would then propagate into `bid_projects.grade_cy`, or (b) require
`bucket_unit_status` to become unit-parameterised — an edit to the **proven, shipped, measured**
tons path to gain nothing.

The same argument the tons spec itself makes about not generalising `milling_unit_status` applies
verbatim one layer out. `grading_unit_status()` is therefore a third small pure function beside the
other two, and `TONS_BUCKETS` keeps meaning exactly what its name says.

## 3. Carry-through

`grading_unconverted` is registered in `apps/api/backend/payload_carry.py::CARRIED_FIELDS` — one
tuple entry, per that module's own docstring ("Adding one is a tuple entry here, not an edit in four
files"), plus one `_LABELS` entry:

```
"grading_unconverted": "Grading not counted (unit is not cubic yards)"
```

That gives it the same three-valued presence (`detected` / `none_found` / `extraction_failed`) every
other carried field has, on both the PDF-drop path (`report.py`) and the corpus path
(`final_report.py::_payload_from_plan_id`), with no further edits.

`report.py` emits `grading_unit_status` alongside the existing `milling_unit_status` and the three
`*_unit_status` keys.

**Frontend: deliberately untouched.** `apps/web/src/lib/gap-status.ts` still holds
`BUCKET_UNIT_CELL = undefined` (the shape-dependent half, held open per
`docs/_spec/2026-08-10-frontend-gap-rendering.md` §5), and both parity tests skip on that rather
than passing vacuously. A grading cell lands when that half lands — adding a py-only status token
cannot break the parity test, which asserts TS→py.

## 4. What this does NOT do

1. **No conversion.** No TON→CY or SY→CY factor, constant, or dormant code path. That is PR #105's
   engine, flag-off, and explicitly not this pass. `bucket_hierarchy.csv`'s 1.75 Ton/CY is
   unverified and SDDOT's 1.50 tons/CY is salvaged granular material — a different material and a
   different state. Neither is used.
2. **It does not move the removal rule.** SY/TON-measured *bituminous* removal still reports in
   `milling_sy` / `milling_tons`, exactly as before. `grading_unconverted` picks up what has
   nowhere else to go — Clean Rock (TON), concrete removal in SY, subgrade preparation (SY).
3. **It does not touch `crushing_tons` / `stockpile_tons`**, which CSI has still not ruled on.

## 5. How it is proved

Same as its two predecessors — the mapping is a prompt, so a unit test proves nothing about it:

- **Coverage test**, red before green: `01_pipeline/test_grading_unit_capture.py` asserts the six
  statuses are six distinct values, that a found-but-unconvertible item can never render as
  `not_present`, and that `CLEAN ROCK` is a real priced corpus row (Dunn p13, 758 TON) rather than a
  fixture.
- **Behavioural measurement**, N=10 on Dunn Job 23388 through the live-path input chain
  (`build_input`), reported in `docs/_session/2026-08-11-conformance-fixes.md`. A ruling that still
  does not fire is reported as still not firing.
- **Differential harness** `03_evaluation/2026-08-10_mapping_regression.py --arm new`, diffed
  against the committed baseline. `grading_quantity` moving **up** is already an EXPLAINED direction
  (rulings #10/#11); the topsoil family lands under the same entry.
