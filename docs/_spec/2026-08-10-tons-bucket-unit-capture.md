# Spec — surface a tons-bucket item the schedule measured in some other unit (no conversion)

Date: 2026-08-10 · Status: **proposed + implemented in the same pass; conversion explicitly out of
scope** · Board open item, CSI live test on plan **9786015** (CSAH 2 / Maryland Ave, Murray Co MN)

Precedent this deliberately copies rather than reinvents:
[`docs/_spec/2026-08-10-milling-unit-capture.md`](2026-08-10-milling-unit-capture.md).

---

## 1. The problem, stated exactly

`hot_mix_tons`, `base_tons` and `shoulder_tons` are **tons by name, by description and by
destination column** (`scratch.bid_projects.mix_tn` / `base_tn` / `shldr_tn`). When the bid schedule
measures one of those materials in some other unit, the extraction has nowhere to put it, so it
returns a **bare null**.

CSI hit this on plan **9786015**: the base is stated in **CUBIC YARDS**, so `base_tons` came back
null and the report was indistinguishable from a plan with no aggregate base at all.

Three different answers currently share one representation:

1. the material is there and the schedule measures it in a unit this field cannot hold,
2. this bid schedule has no such item,
3. extraction did not produce an answer.

That is the standing rule — *a failure and a legitimate empty answer must never share a return
value* — and this is its **eleventh** instance in this repo (milling was the tenth).

**This is the same defect as the milling one, pointed at three more fields.** It therefore gets the
same shape and the same vocabulary. A second, differently-named mechanism for the same idea would be
worse than the bug.

---

## 2. Non-goals — explicitly out of scope

- **NO CONVERSION. No assumed depth, no assumed density, no multiplication anywhere.** CY→TON and
  SY→TON are task 2b, which is spec-only and awaiting Alex's sign-off on a factor table. The
  unverified `1.75 Ton/CY` in `bucket_hierarchy.csv` and SDDOT's `1.50 tons/CY` for *salvaged
  granular material* are neither interchangeable nor applicable, and neither is used here.
- **No change to what `hot_mix_tons` / `base_tons` / `shoulder_tons` mean.** They stay tons-only.
  Every plan whose buckets are already tons-measured must not move — that is what §6 measures.
- **No aggregate-surfacing ruling.** `quantity_crosswalk.py::CSI_OPEN_QUESTIONS_2026_08_07` is still
  open with CSI (`AGGREGATE SURFACING CLASS 1/2/5/SPECIAL`, riprap, crushing/stockpile). Nothing
  here assumes an answer; the new fields report what the schedule *says*, never what a bucket
  *should* be.
- **No DDL.** Storing an unconverted quantity in `scratch.bid_projects` would need new columns. Not
  taken here; recorded in §5.3 as a known gap.

---

## 3. The field shape

Two model-answered fields per bucket, plus one derived function in code. Buckets:
`hot_mix` (`hot_mix_tons`), `base` (`base_tons`), `shoulder` (`shoulder_tons`).

### 3.1 `hot_mix_tons` / `base_tons` / `shoulder_tons` — UNCHANGED

Still "total TONS", still null when the schedule measures the material in something else. That
clause is now *correct rather than lossy*, because the item has somewhere else to go.

### 3.2 `{bucket}_measured_unit` (str) — NEW, model-answered

Directly parallel to `milling_measured_unit`. Closed vocabulary, and the whole point of it being
closed is that it forces the model to **assert** absence so absence stops sharing a representation
with failure:

| value | meaning |
|---|---|
| `TON` | every item in this bucket is measured in tons |
| `TON+OTHER` | some items are in tons, at least one is in another unit |
| `OTHER` | every item in this bucket is measured in a non-ton unit (CY, SY, LF, STA, MILE, LS) |
| `NONE` | **this bid schedule has no item in this bucket at all** |
| `null` | **reserved for "extraction produced no answer"** — never for "no such item" |

Milling's vocabulary is `SY / TON / SY+TON / OTHER / NONE / null` because its field unit is SY and
tons is the one known alternative. These three fields have exactly one native unit (TON) and several
possible alternatives, so the token set collapses to the four above — same construction, same
`NONE`-vs-`null` contract.

### 3.3 `{bucket}_unconverted` (str) — NEW, model-answered

One line per bucket item **whose unit is not tons**, verbatim from the schedule:

```
DESCRIPTION | QUANTITY | UNIT
```

9786015 base: `AGGREGATE BASE CLASS 5 | 2485 | CY`. Null when there are no such items.
Never summed, never converted.

**Why a per-item line and not milling's scalar subtotal.** Milling had exactly two candidate units,
so `milling_sy` + `milling_tons` was a *complete* per-unit decomposition. These buckets are not:
measured on the 8-plan item-level golden corpus (`tools/golden/2026-08-10_golden_rows.csv`,
categorised with `quantity_crosswalk.spec_category`), a single plan routinely carries a single
bucket in two or more units at once —

| bucket | unit combinations seen within one plan |
|---|---|
| `base` | `TON+CY`, `TON+SY` |
| `hma` | `TON+SY`, `TON+GAL`, `TON+EACH`, `TON+GAL+SY+SF` |
| `surfacing` (shoulder) | `CY+SY`, `TON+LF` |

A single scalar "off-unit subtotal" would therefore add cubic yards to square yards — *reproducing
the exact conflation this fix exists to prevent*, one layer further in. Per-unit subtotal fields
would mean four or five new numeric fields per bucket. The item line carries the item, its value
**and** its unit without summing anything, which is precisely what has to be recorded.

### 3.4 `schema.bucket_unit_status(record, field)` (derived, pure, no model call)

Not a stored field — a function over a record, so the status can never drift from the values it
describes. It never converts and never infers a quantity. Returns exactly one of:

| status | condition | meaning |
|---|---|---|
| `tons_only` | unit `TON`, a tons value, nothing unconverted | The field carries the whole quantity. Nothing is missing. |
| `unconverted_only` | unit `OTHER` | **CONVERSION_REQUIRED.** The tons field is null *by design*; the items are named in `{bucket}_unconverted`. **This is 9786015's base.** |
| `tons_and_unconverted` | unit `TON+OTHER` | Both real. The two are **not addable**. |
| `not_present` | unit `NONE`, and neither a tons value nor an unconverted line | A legitimate empty answer. |
| `unknown` | unit null / absent / outside the vocabulary | Extraction did not answer. **Never** reported as `not_present`. |
| `inconsistent` | the declared unit contradicts the values (`NONE` with a quantity; `TON` with unconverted lines; `OTHER` with a tons value) | The model contradicted itself. Surfaced, not silently resolved in either direction. |

`inconsistent` exists for the same reason it does in `milling_unit_status`: trusting one of two
contradicting signals is a fixed-set-of-checks answer to a question that must be enumerated by
failure mode.

**Why this is a second function and not a generalisation of `milling_unit_status`.**
`milling_unit_status` decides between two *numeric* fields in two different units; this one decides
between one numeric field and a *text list*. Folding them into one parameterised function would mean
editing the milling path, which is proven and shipped, to gain nothing. Both functions are listed
side by side in `schema.py` with the shared vocabulary (`not_present` / `unknown` / `inconsistent`)
spelled identically so a reader sees one idea, not two.

---

## 4. How this reaches the report — the carry-through registry, not new plumbing

`apps/api/backend/payload_carry.py` already exists precisely for this: its docstring names "a
captured raw milling value + unit" as an expected future entry, and it is a **registry** so adding a
field is one tuple entry rather than an edit in four files.

The three `{bucket}_unconverted` fields are appended to `CARRIED_FIELDS`. Each therefore contributes
**two** keys to `payload["identity"]`:

- the value itself, and
- `{bucket}_unconverted_status` ∈ `detected` / `none_found` / `extraction_failed`,

and `payload_carry.render_value()` guarantees the rendered cell is **never blank** — an
`extraction_failed` renders as a loud "⚠️ Not captured", never as "no base".

`apps/api/backend/report.py` additionally puts the three derived statuses on `identity`, next to the
existing `milling_unit_status`:

```python
"hot_mix_unit_status":  schema.bucket_unit_status(record, "hot_mix_tons"),
"base_unit_status":     schema.bucket_unit_status(record, "base_tons"),
"shoulder_unit_status": schema.bucket_unit_status(record, "shoulder_tons"),
```

### 4.1 What must NOT happen — the label lesson, restated

The unconverted quantity **must not** be emitted as a `quantities` row under the labels `MIX`,
`BASE` or `SHLDR`. `bid_projects_record.py` writes those labels straight into the columns literally
named `mix_tn` / `base_tn` / `shldr_tn`, and `apps/api/backend/competitor_predict_live.py`'s
`LABEL_TO_MATERIAL_COL` feeds them to the fitted competitor weights. **Neither reads a unit.**
2,485 CY arriving in a column named `base_tn` would be a silent unit corruption — the same defect
class as the one being fixed, pointed the other way.

The value is a per-item text list, so it structurally cannot become a numeric `quantities` row. It
travels on `identity` only: displayed to the estimator, never written as tons, never converted.
That is loud-by-omission rather than quietly wrong.

---

## 5. Deferred, and named so it is a known gap rather than a discovered one

1. **The conversion itself (task 2b).** Needs a CSI-verified factor table with Alex's sign-off.
   Nothing in this change multiplies anything.
2. **Database columns.** Until DDL exists, an unconverted quantity reaches the extraction record,
   the payload cache and the report — and **not** `scratch.bid_projects`.
3. **The aggregate-surfacing / riprap / crushing rulings** stay open
   (`CSI_OPEN_QUESTIONS_2026_08_07`). Not assumed here.

---

## 6. How this is proved

### 6.1 The mapping is a prompt, so the proof is a run over the real document

A unit test over a prompt asserts nothing about what the model does with it
(`03_evaluation/2026-08-10_mapping_regression.py` header). The blocking proofs are:

- **Red before green on 9786015.** The same document, the same extractor, the two arms:
  the old field set returns `base_tons = null` and nothing else — the CY base is invisible. The new
  field set must return `base_measured_unit`/`base_unconverted` naming the CY item, and
  `bucket_unit_status(record, "base_tons") == "unconverted_only"`.
- **No-regression.** Re-run the `new` arm over `00_input/_md_cache` and diff against the committed
  baseline `03_evaluation/outputs/2026-08-10_mapping_regression_new.json`. **Any movement in
  `hot_mix_tons` / `base_tons` / `shoulder_tons` on a plan whose bucket is tons-measured is a
  regression and blocks the demo.**

The comparison is against the committed harness baseline, **not** `_report_payload_cache/`: those
payloads are keyed on PDF content hash with no mapping version in the key and predate the 2026-08-10
schema changes.

### 6.2 The status function is proved exhaustively, not by sampling

`01_pipeline/test_tons_bucket_unit_capture.py` walks every combination of declared unit × tons value
× unconverted list and asserts that **"found but unconvertible", "genuinely absent" and "extraction
failed" are three distinct return values** — the rule this whole change is an instance of. A test
that only proves a plan with no base at all returns null proves nothing and is explicitly not
what is asserted.
