# Spec — capture the milling value AND its native unit (no conversion)

Date: 2026-08-10 · Status: **implemented on the extraction side; payload-assembly edit handed to the
owner, not applied** · Board open item #2

---

## 1. The problem, stated exactly

`milling_sy` is square yards by name (`_sy`), by field description, by the `MILL_SY` code in
`report.py::_QMAP`, by `_UNIT["MILL_SY"] = "SY"`, and by the destination column
`scratch.bid_projects.mill_sy`. **NDDOT measures milling in TONS.** The spec book is explicit:
NDDOT §411.06 Pay Unit `Ton or Square Yard` (`docs/_session/2026-08-10-spec-books-tier1.md`).

On `2026_DUNN-CO-ND_JOB-23388` (md cache `c0e327cf80827ab9`) the bid schedule states:

| pay item | ND item | unit | qty | page |
|---|---|---|---:|---|
| `MILLING PAVEMENT SURFACE` | 411 0100 | TON | 63,092 | p.16 |
| `REMOVAL OF BITUMINOUS SURFACING` | — | TON | 3,915 | p.7 |
| `FULL DEPTH RECLAMATION` | — | SY | 408,216 | p.13 |

The current `milling_sy` description ends *"if the bid schedule measures milling in tons, leave this
field null rather than converting."* That is safe against a wrong number and it is **silent loss of
67,007 tons** on this plan. Silence is the failure shape this project has been bitten by nine times
(HANDOFF §3, §5). This is instance ten of the standing rule: *a failure and a legitimate empty
answer must never share a return value* — and here there are three answers, not two:

1. milling is measured in tons (we have the number, we cannot express it in SY),
2. this plan has no milling item at all,
3. extraction did not produce an answer.

Today all three are `milling_sy = null`.

**Dunn also kills the obvious design.** A single `(value, unit)` pair for the whole bucket cannot
describe Dunn, which is measured in *both* units at once: 408,216 SY of FDR **and** 67,007 TON of
milling/removal. Any "one unit per plan" shape either drops the SY (regressing MN/SD) or drops the
tons (the bug we are fixing). The shape below is therefore **per-unit subtotals**, not one pair.

---

## 2. Non-goals — explicitly out of scope

- **No conversion. No assumed depth.** `bucket_hierarchy.csv` carries an unverified **1.75 Ton/CY**
  that has never been checked against a plan. The spec-book sweep separately turned up an SDDOT
  **1.50 tons/CY** for *salvaged granular material* — a different material, a different state and a
  different provenance. Neither is a milling depth factor and **neither is used here**. Conversion
  waits for a CSI-supplied factor (HANDOFF §7: "conversion is a later layer with a CSI-verified
  factor table").
- **No change to `milling_sy`'s meaning or its description.** MN and SD must not move. That is the
  hard constraint and it is what §6's differential run measures.
- **No DDL.** Storing the tons number in `scratch.bid_projects` needs a `mill_tons` column; that is
  an owner decision, recorded in §5.3, not taken here.

---

## 3. The field shape

Three fields on the extraction record, two asked of the model and one derived in code.

### 3.1 `milling_sy` (num) — UNCHANGED

Square-yard-measured milling and bituminous pavement removal, including FDR. Description untouched,
including the "leave null rather than converting" clause — which is now *correct rather than lossy*,
because the tons have somewhere else to go.

### 3.2 `milling_tons` (num) — NEW, model-answered

> Total quantity of milling / bituminous-surface-removal items that this bid schedule measures in
> TONS, exactly as stated and NOT converted.

Dunn: `63,092 + 3,915 = 67,007`. Null when the schedule has no tons-measured milling item — which is
the MN/SD normal case, and which §3.4 keeps distinguishable from "we did not read it".

### 3.3 `milling_measured_unit` (str) — NEW, model-answered

The unit(s) the schedule actually used for milling, from a closed vocabulary:

| value | meaning |
|---|---|
| `SY` | every milling item is measured in square yards |
| `TON` | every milling item is measured in tons |
| `SY+TON` | both units appear (Dunn) |
| `OTHER` | a milling item is measured in some other unit (CY, LF, LS, STA) |
| `NONE` | **this bid schedule has no milling / bituminous-removal item at all** |
| `null` | **reserved for "extraction produced no answer"** — never for "no such item" |

`NONE` vs `null` is the whole point of the closed vocabulary: it forces the model to *assert*
absence, so absence stops sharing a representation with failure.

### 3.4 `schema.milling_unit_status(record)` (derived, pure, no model call)

Not a stored field — a function over a record, so the status can never drift from the values it
describes. Returns exactly one of:

| status | condition | meaning |
|---|---|---|
| `sy_only` | unit `SY` | `milling_sy` carries the whole quantity. Nothing is missing. |
| `tons_only` | unit `TON` | **CONVERSION_REQUIRED.** `milling_sy` is null *by design*; `milling_tons` carries the number. |
| `sy_and_tons` | unit `SY+TON` | Dunn. Both fields carry a real number; the totals are not addable. |
| `other_unit` | unit `OTHER` | A unit we have no bucket for. Named, not dropped. |
| `not_present` | unit `NONE` and both quantities null | A legitimate empty answer. |
| `unknown` | unit null/absent/unrecognised | Extraction did not answer. **Never** reported as `not_present`. |
| `inconsistent` | the declared unit contradicts the values (e.g. `NONE` with a quantity, `SY` with `milling_tons` set) | The model contradicted itself. Surfaced, not silently resolved in either direction. |

`inconsistent` exists because the alternative — trusting one of the two contradicting signals — is a
fixed-set-of-checks answer to a question the standing rules say must be enumerated by failure mode.

### 3.5 Why not one `(value, unit)` pair, and why not a `milling_measured_qty`

Both were considered and both fail on the very document that motivated the work: Dunn is `SY+TON`
simultaneously, so a single value/unit pair must discard one of the two real numbers. Per-unit
subtotals hold both, and `milling_measured_unit` is what makes the pair *interpretable* (it says
whether a null `milling_tons` means "no tons items" or "we do not know").

---

## 4. How this maps onto what already exists downstream

`scratch.bid_projects` already carries per-bucket unit columns — `mill_unit`, and a global
`unit_source` — written by `pipelines/plan_reader/01_pipeline/bid_projects_record.py:307,312` from
the payload's `quantities` list:

```python
"mill_sy":     _quantity(payload, "MILL"),        # value of the payload row labelled MILL
"mill_unit":   _quantity_unit(payload, "MILL"),   # that row's `unit` string
"unit_source": ("observed" if (payload.get("quantities") or []) else None),
```

A live row confirms the shape: Stearns, `row_source='plan_reader'`, `mill_sy=70263.0`,
`mill_unit='SY'`, `unit_source='observed'`.

**So the "value plus native unit" idea already exists downstream and this spec deliberately does not
invent a second one.** `milling_measured_unit` is the *extraction-side* companion (it can say
`NONE` and `SY+TON`, which a per-row `unit` string cannot); `mill_unit` is the *storage-side*
companion and keeps its exact current semantics. The mapping is:

| extraction | payload `quantities` row | `bid_projects` |
|---|---|---|
| `milling_sy` | `{label: "MILL", unit: "SY"}` | `mill_sy`, `mill_unit='SY'` |
| `milling_tons` | `{label: "MILL_TON", unit: "TON"}` | **nothing today** — see §5.3 |

### 4.1 The label that must NOT be reused, and why

The tons row **must not** be emitted as `label: "MILL"` with `unit: "TON"`. Two consumers key off
that label positionally and neither reads the unit:

- `bid_projects_record.py:307` writes it into the column literally named **`mill_sy`**;
- `apps/api/backend/competitor_predict_live.py:42` maps `"MILL" → "mill_sy"` and feeds it to the
  fitted competitor weights.

Emitting 67,007 tons under `MILL` would put tons into a square-yard column and into a model feature,
with `mill_unit='TON'` sitting beside it as an advisory nobody currently checks. That is a **silent
unit corruption** — the same class of defect as the one being fixed, pointed the other way. A
distinct `MILL_TON` label is inert to both maps: it is displayed and it is not written, which is
loud-by-omission rather than quietly wrong.

**Named finding for the owner:** no consumer of `mill_sy` currently checks `mill_unit`. The unit
columns are recorded but not enforced. Verified two ways: `grep -rn "mill_unit"` across
`apps/ pipelines/ data/ tools/` returns only the writer (`bid_projects_record.py`), its YAML mapping
and its test — no reader; and `competitor_predict_live.py`'s `LABEL_TO_MATERIAL_COL` /
`_MATERIAL_COLS` select the seven quantity columns with no unit column in the query at all.

---

## 5. The payload-assembly edit — SPECIFIED HERE, NOT APPLIED

`apps/api/backend/report.py` is owned by other agents this round. The exact edit is §5.1; the owner
applies it.

### 5.1 `apps/api/backend/report.py::process_pdf`

Immediately after the existing `_QMAP` quantity loop (`report.py:258-266`, the block ending
`field_confidence[label] = _conf(field)`), insert:

```python
    # Milling measured in TONS (NDDOT §411.06 pays milling by the ton). It cannot go in the MILL
    # row: that label is written to the column literally named `mill_sy` (bid_projects_record.py)
    # and to the `mill_sy` model feature (competitor_predict_live.LABEL_TO_MATERIAL_COL), neither of
    # which reads a unit — so tons under `MILL` would be a silent unit corruption. Its own label is
    # inert to both maps: shown to the estimator, never written as square yards, never converted.
    # Spec: docs/_spec/2026-08-10-milling-unit-capture.md.
    mill_tons_field = record.get("milling_tons")
    mill_tons_value = _val(mill_tons_field)
    if mill_tons_value not in (None, "", 0):
        quantities.append({"label": "MILL_TON", "value": mill_tons_value, "unit": "TON"})
        field_confidence["MILL_TON"] = _conf(mill_tons_field)
```

and add one key inside the `rep["identity"]` dict literal (`report.py:275-300`), next to the other
provenance keys:

```python
            # Which unit(s) the bid schedule measured milling in, and whether a conversion is
            # outstanding. Six explicit states incl. `not_present` and `unknown` — a plan with no
            # milling item and a plan we failed to read are NOT the same answer.
            "milling_unit_status": schema.milling_unit_status(record),
```

`schema` is already imported in `report.py:27`. No other file changes are required for the value to
reach the report card: `apps/web/src/components/chat/report-card.tsx:232-238` renders every
`quantities` row generically as `label / value / unit`, so `MILL_TON  67,007  TON` appears with no
frontend change.

### 5.2 What the owner should NOT do

Do not add `"MILL_TON"` to `competitor_predict_live.LABEL_TO_MATERIAL_COL` or to
`bid_projects_record.py`. There is no tons column to receive it (§5.3), and mapping it to `mill_sy`
is exactly the corruption §4.1 exists to prevent.

### 5.3 Deferred, needs a decision (and DDL, which is out of scope here)

Storing the number requires `alter table scratch.bid_projects add column mill_tons double precision`
plus a `mill_tons_unit`-free companion (the existing `mill_unit` already covers the unit for the SY
row). Until then the tons value lives in the extraction record, the payload cache and the report —
and **not** in the database. That is stated so it is a known gap rather than a discovered one.

---

## 6. How this is proved

### 6.1 The mapping is a prompt, so the proof is a differential re-run

Per `03_evaluation/2026-08-10_mapping_regression.py`'s header: a unit test over a prompt asserts
nothing about what the model does with it. Adding two fields to the extraction prompt can perturb
the fields already in it, which is precisely the risk to `milling_sy` on MN/SD.

**Result (2026-08-10, six documents): MN/SD `milling_sy` did not move; Dunn keeps 408,216 SY and
gains 67,007 TON.** Two non-blocking ND movements are declared in
`docs/_session/2026-08-10-milling-unit-capture.md` §3 (Fargo `milling_sy` +14, Dunn
`grading_quantity`). Getting Dunn to 67,007 took four prose iterations; the intermediate 63,092
results and the diagnostic that explained them are recorded in the same report §2.

**Pass condition (blocking):** re-run the `new` arm against `00_input/_md_cache` and diff against the
committed baseline `03_evaluation/outputs/2026-08-10_mapping_regression_new.json`. **Any movement in
`milling_sy` on an MN or SD plan is a regression and blocks the demo.** Dunn (ND) is the case being
changed and is expected to keep `milling_sy = 408,216` *and* gain `milling_tons = 67,007`.

The comparison is against the committed harness baselines, **not** against `_report_payload_cache/`:
those payloads are keyed on PDF content hash with no mapping version in the key, and predate the
2026-08-10 `schema.py` change, so they describe July behaviour.

### 6.2 Scoring — `CONVERSION_REQUIRED` becomes its own category

`docs/_spec/2026-08-10-benchmark-table.md` §2.3 already designed this status; the scorer did not
implement it. `tools/golden/2026-08-10_golden_join.py` scored a key match as `MATCH` whenever any
extracted quantity was non-null, **regardless of whether the units agreed**, and then computed a
variance across two different units.

Implemented rule: when the keys match, both sides carry a quantity, and the normalised units differ,
the row is `CONVERSION_REQUIRED`:

- it is **not** a hit — it is excluded from `matched`, so precision is not inflated;
- it is **not** a miss — it is excluded from the recall denominator, so a known, deliberate design
  gap (no conversion layer) is not reported as an extraction failure;
- it carries **no** `abs_variance` / `pct_variance`, because a variance between TON and SY is not a
  number that means anything;
- it is counted and printed on its own line, so the gap is visible rather than netted away.

Unit normalisation is a small explicit table (`SY`/`SQ YD`/`SQUARE YARD`, `TON`/`TN`/`TONS`,
`CY`/`CU YD`/`CUBIC YARD`, `LF`/`LIN FT`, `EACH`/`EA`). A unit string that normalises to nothing on
either side is treated as **unknown, not as agreement** — `unit_match` is left blank and the row
keeps its previous status rather than being promoted to `CONVERSION_REQUIRED` on a guess.

---

## 7. Open, and deliberately not decided here

1. **The conversion factor itself.** Needs CSI. `1.75 Ton/CY` (unverified, in
   `bucket_hierarchy.csv`) and SDDOT's `1.50 tons/CY` for salvaged granular material are **not**
   milling depth factors and are not interchangeable with each other.
2. **`mill_tons` column in `scratch.bid_projects`** (§5.3) — DDL, owner's call.
3. **Whether `mill_unit` should be enforced rather than merely recorded** (§4.1's named finding).
   Today a consumer reading `mill_sy` cannot tell it was told the unit.
