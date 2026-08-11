# PR #102 validation — `fix/aggregate-mix-tons-conversion`

**Date:** 2026-08-10 · **Branch validated:** `origin/fix/aggregate-mix-tons-conversion` @ `c029c86`
(checked out as `pr102-validate` in an isolated worktree; **nothing merged, nothing pushed, no PR
comment, no edit to `schema.py` / `report.py` / `s3_extract.py` / the golden**).

**Verdict, one line: adopt as base, with three named gaps — the conversion is correct, deterministic
and code-only, but it is not the thing that fixes prose-classification drift, it emits a converted
number that no consumer can distinguish from a stated one, and it collides on key names with 2a.**

Everything below is measured. Harnesses added by this validation (new files, not edits):

| file | what it does |
|---|---|
| `pipelines/plan_reader/03_evaluation/2026-08-10_pr102_stability.py` | repeat live extraction + per-item bucket-assignment stability; `--repeat-math` for code determinism |
| `pipelines/plan_reader/03_evaluation/2026-08-10_pr102_truncation_probe.py` | 2048 vs 6000 token-cap behaviour, `stop_reason` recorded |
| `pipelines/plan_reader/03_evaluation/2026-08-10_pr102_status_probe.py` | the derived-status/merge behaviour on two-units-at-once and unconvertible items (no network) |
| `pipelines/plan_reader/03_evaluation/2026-08-10_pr102_corpus_sweep.py` | one extraction per cached plan — coverage, not stability |

Raw run records: `/tmp/pr102_runs.json` (Murray ×6), `/tmp/pr102_stearns.json` (×6),
`/tmp/pr102_crow.json` (×6), `/tmp/pr102_sweep.json` (corpus).
Corpus source: the primary checkout's `00_input/_md_cache` (read-only; a worktree gets no copy of
that untracked cache). No PDF re-conversion, no Chroma write, no DB access.

---

## 1. Correctness — all three numbers reproduce, with the arithmetic in code

`python 2026-08-10_pr102_stability.py --repeat-math 1000`, on plan **9786015** (Murray Co MN,
CSAH 2 / Maryland Ave, md hash `a3171c2187e8af85`):

```
merge_material_tons() x1000: 1 distinct result(s) -> DETERMINISTIC
  full precision: {'base_tons': 3851.75, 'shoulder_tons': 13.08888888888889, 'hot_mix_tons': 1901.338}
  base_tons      code=3851.75  expected=3851.75  MATCH
  shoulder_tons  code=13.09    expected=13.09    MATCH
  hot_mix_tons   code=1901.34  expected=1901.34  MATCH

  chain (code, not by hand):
    base   : 2485.0 CY x 1.55
    shldr  : 8.444444444444445 CY x 1.55      # 38 SY x 8 in / 36
    mix    : [10736.0, 16104.0, 2554.5, 4257.5] sum = 33652.0 SY-in x 0.0565
```

Every multiplication and every sum is performed by `schema.resolve_cy_item` /
`schema.resolve_sy_depth_product` and `material_tons_merge.merge_material_tons`. Nothing was
computed by hand or read out of a doc — the numbers above are the functions' return values.

The four Type SP lines are the ones from the bid schedule (page 27, items 44–47): 5,368 SY @2.0",
5,368 SY @3.0", 1,703 SY @1.5", 1,703 SY @2.5". They are resolved **individually** and only then
summed — `[10736.0, 16104.0, 2554.5, 4257.5]` — which is exactly the "must not be summed with each
other before conversion" requirement.

**Code math is deterministic:** 1,000 repeated calls on a fixed record produced **1 distinct
result**. It is a pure function of the record with no I/O, no clock, no dict-ordering dependence —
and the run confirms it rather than asserting it.

**End-to-end (model → code) it also reproduces**: all 6 live extractions of 9786015 returned
`{'base_tons': 3851.75, 'shoulder_tons': 13.08888888888889, 'hot_mix_tons': 1901.338}`.

---

## 2. THE KEY QUESTION — does it reduce the non-determinism?

### Where the bucketing decision lives: **still the model.**

`material_tons_merge.py` does **arithmetic only**. It never sees a description. Read the call chain:

- `schema.py`'s three new fields (`base_cy_items`, `shoulder_cy_items`, `mix_sy_depth_items`) are
  **prose field descriptions** — longer and far more specific than the seven originals, but still
  prose the model interprets. The base/shoulder split is decided by sentences like *"Do NOT list
  'AGGREGATE SHOULDERING' or 'AGGREGATE SURFACING CLASS 1 / 2 / 5 / SPECIAL' items here … those
  belong exclusively in `shoulder_cy_items`"*.
- `material_tons_merge.merge_material_tons(record)` reads `record["base_cy_items"]` etc. and calls
  `resolve_cy_item` / `resolve_sy_depth_product`, which key **only** on `item["unit"]`
  (`"CY"` / `"SY"`) and `item["depth_in"]`. The `note` (the pay-item name) and `page` are carried
  but never read by any decision.
- Nothing anywhere keys on the item description or on a spec item number.

**So: the model decides which bucket an item belongs to; code decides only how many tons that item
is worth.** #102 moves the *arithmetic* out of the model — which is a real and well-evidenced win,
the PR documents a live ~13% silent multiply error it removes — but the *classification* is exactly
as model-driven as before. It does not address the drift class we measured (Stearns `MILL`
140,430↔70,263, Crow Wing `GRADE` 7,707↔15,876, 9809481 `GRADE` 45↔12,159): those are all
`milling_sy` / `grading_quantity`, seven-prose-sentence scalars that **#102 does not touch at all**
(`git diff main...origin/fix/aggregate-mix-tons-conversion -- pipelines/plan_reader/01_pipeline/schema.py`
shows insertions only; no existing quantity description is modified).

**How an unrecognised description is handled:** it is not handled, because code never sees one. The
only code-level "unrecognised" branch is on the **unit token**: `resolve_cy_item` returns `None` for
anything that is not `CY`, or `SY`-with-a-positive-`depth_in`. That `None` is then folded into the
status as `sy_no_depth_present` — see the defects in §3.

### Measured: per-item bucket assignment across repeated runs

Six live extractions per plan, `temperature=0`, `max_tokens=6000`, same document text the live path
builds. **Per-item** assignment, not just bucket totals:

**Plan 9786015 (Murray) — 6/6 runs OK, 0 errors**

| item (qty, unit, depth) | plan line | bucket, per run | verdict |
|---|---|---|---|
| 2485.0 CY, depth None | 41 Class 5 Aggregate Base (CV)(P) | `base_cy_items` ×6 | STABLE |
| 38.0 SY, depth 8.0 | 40 8" Class 5 Alley & Shouldering Aggregate Surfacing | `shoulder_cy_items` ×6 | STABLE |
| 5368.0 SY, depth 2.0 | 44 Type SP 9.5 Wearing (CSAH 2) | `mix_sy_depth_items` ×6 | STABLE |
| 5368.0 SY, depth 3.0 | 45 Type SP 12.5 Non-Wearing (CSAH 2) | `mix_sy_depth_items` ×6 | STABLE |
| 1703.0 SY, depth 1.5 | 46 Type SP 9.5 Wearing (Maryland Ave) | `mix_sy_depth_items` ×6 | STABLE |
| 1703.0 SY, depth 2.5 | 47 Type SP 12.5 Wearing (Maryland Ave) | `mix_sy_depth_items` ×6 | STABLE |

**36 of 36 item-level bucket assignments identical** (6 items × 6 runs). Item counts per bucket:
`base_cy_items [1,1,1,1,1,1]`, `shoulder_cy_items [1,1,1,1,1,1]`, `mix_sy_depth_items
[4,4,4,4,4,4]` — all distinct=1. Derived statuses stable (`base=cy_only`,
`shoulder=sy_converted_only`, `mix=sy_converted_only` ×6). Merged totals distinct=1 on all three
buckets. Untouched scalars also stable: `grading_quantity` 2,495 ×6, `milling_sy` 15,828 ×6.

**Plan 9813645 (Stearns) — 6/6 OK.** `milling_sy` = **70,263 on all six runs** (distinct=1); every
new items field returned `[]` (an asserted empty list, count 0, not null) on all six; merged
base/shoulder/mix = 270 / 460 / 14,480 ×6.

**Crow Wing SAP 018-603-024 — 6/6 OK.** `grading_quantity` = **15,876 on all six runs**
(distinct=1); items fields `[]` ×6; merged 5,849 / 478 / 4,732 ×6.

### What this does and does not prove

- **Arithmetic determinism: proven** (1,000 code repeats, 1 result).
- **Classification stability on these three plans, this session: 18/18 runs stable, 36/36 item
  assignments stable, and zero drift in the two fields that drifted tonight.** That is real
  evidence, and it is the strongest single result in this validation.
- **It is NOT proof that the drift is fixed**, and #102 does not claim to fix it. I could not
  reproduce the Stearns/Crow Wing drift *at all* in 12 consecutive runs, which means the drift is
  episodic across sessions/prompt-versions rather than run-to-run within a session — so a
  6-run-stable result is not evidence that a mechanism which *can* drift no longer does. The
  mechanism (prose → model classification) is unchanged by #102, so the correct statement is:
  **#102 removes one non-determinism source (model arithmetic) and leaves the other (model
  classification) exactly where it was.** Anyone citing this PR as "the fix for the mapping drift"
  would be citing it for something it does not do.

---

## 3. Scope — capture-all

**Does it capture every material item with nothing dropped? No.** It captures the CY/SY-with-depth
items of **3 of the 7 live buckets** and drops several real shapes. Concretely:

### 3.1 It DOES handle one bucket carrying two units at once — the value, at least

`2026-08-10_pr102_status_probe.py` (pure, no network):

| case | `base_unit_status` | merged `base_tons` |
|---|---|---|
| TON only (500) | `tons_only` | 500.0 |
| **TON 500 + CY 100** | **`cy_only`** | **655.0** ← correct value, wrong label |
| **TON 500 + SY 360 @6"** | **`sy_converted_only`** | **593.0** ← correct value, wrong label |
| CY 100 + SY 360 @6" (no tons) | `mixed` | 248.0 |
| CY 100 + SY 999 **no depth** | `sy_no_depth_present` | **155.0 — the 999 SY is silently excluded** |
| GAL 4200 only | **`sy_no_depth_present`** (wrong name) | **None** |
| items field null, tons 500 | `unknown` | 500.0 |

The four separate SY mix lines on 9786015 are held as four entries and converted individually
(§1) — the "must not be summed before conversion" requirement is met.

### 3.2 Where it falls short — named gaps

1. **`_aggregate_unit_status` ignores the native TON value whenever the items list is non-empty.**
   `schema.py`'s `_aggregate_unit_status` computes `has_tons` and then never uses it once
   `items` is truthy. So a bucket that is genuinely TON+CY reports `cy_only` while its value is a
   *blend* of a stated tonnage and a converted one. There is no `tons_and_converted` state in
   `AGGREGATE_UNIT_STATUSES`. **2a's vocabulary has exactly this state (`tons_and_unconverted`) and
   #102's does not** — a straight regression against the case the golden says is routine.
2. **`sy_no_depth_present` is both a mask and a misnomer.** One unconvertible item makes the whole
   bucket report `sy_no_depth_present` even when other items converted fine (row 5 above: value 155
   is a *partial* total, and no status says "partial"). And a `GAL`/`EACH`/`LF` item — a unit that
   has nothing to do with depth — also reports `sy_no_depth_present`.
3. **The excluded quantity is not carried anywhere.** `report.py:323` writes
   `field_confidence[cy_field] = _conf(record.get(cy_field))`, and `_conf` (`report.py:104-112`)
   returns **only** `{confidence, page, reason}` — it drops the value. The raw items list therefore
   never reaches the payload. The 999 SY in row 5 exists only inside the model's prose `reason`
   string. This is the same silent-drop shape #102 exists to fix, one layer in.
4. **A failure and a legitimate empty answer share a return value in `merge_material_tons`.**
   Row 6: a plan with a real base item measured in GAL returns `base_tons = None` — identical to a
   plan with no base at all. `_combine` returns `None` when "both components are absent", and an
   all-unconvertible items list produces `cy_total = None` via `_sum_items`, which the docstring
   describes as intended. The status field is the only thing that separates the two, and per gap 2
   it labels the GAL case wrongly. **Judged by the repo's own standing rule, this is a defect.**
5. **Only 3 of 7 buckets are covered.** `_QMAP` (`report.py:38-40`) has seven: `hot_mix_tons`,
   `grading_quantity`, `base_tons`, `shoulder_tons`, `milling_sy`, `crushing_tons`,
   `stockpile_tons`. #102 adds item capture for base/shoulder/mix. `milling` has its own separate
   mechanism (`milling_tons` / `milling_measured_unit`, untouched, correctly so).
   **`crushing_tons` and `stockpile_tons` are TON-named with no off-unit capture at all**, and
   `grading_quantity` is CY-named with no SY-with-depth capture. The golden's `surfacing CY+SY`
   shape has no live bucket of its own; it lands in base/shoulder by CSI ruling, so it is covered
   only to the extent the prose splits it correctly.
6. **Only two units are convertible: `CY` and `SY`-with-a-stated-depth.** The golden's measured
   `hma = TON+GAL` and `TON+EACH` cases produce nothing — the field descriptions ask only for CY/SY
   items, so a GAL item is never even listed, and if it were, gap 2/4 applies.
7. **No per-value provenance — a converted number is indistinguishable from a stated one.**
   See §4.3; this is its own finding.

### 3.3 Corpus coverage, measured (`2026-08-10_pr102_corpus_sweep.py`, one run per plan, n=18)

Every plan in the primary checkout's `_md_cache`, run once through #102's path:

- **8 of 18 plans have at least one item #102 converts** (`187bbb4f`, `22a6c16c`, `2b2438a4`,
  `2c83fa4e`, `6c906b58`, `823d011b`, `a3171c21`, `d3c6880e`). This is the majority-relevant path,
  not an edge case — consistent with the frontend agent's 9-of-14 payload count.
- Largest single effect: `d3c6880e` (Emmons ND) — **5** CY base items → `base_tons = 9,374.4`,
  previously null. `2c83fa4e` (Burleigh ND) 2 items → 4,325.0. `6c906b58` (Douglas MN) converts
  base **and** shoulder (2,945.0 / 1,550.0).
- **A live instance of gap 2, on a real plan:** `823d011b34af0e82` returns
  `mix_unit_status = 'sy_no_depth_present'` with **4** items in `mix_sy_depth_items` and a merged
  `hot_mix_tons = 4,892.9`. That number is a *partial* total — at least one of the four items was
  silently excluded — and nothing in the payload says so, nor carries the excluded quantity. This is
  the exact defect predicted by the synthetic probe, occurring in the demo corpus.
- **Token overflow is corpus-wide, not one plan.** Output tokens under #102 exceeded the old 2,048
  default on **3 of 18** plans (`c0e327cf` Dunn 2,260 · `a3171c21` Murray 2,176 · `d3c6880e` Emmons
  2,145), with `823d011b` at 1,998 and four more in the 1,800s. Before the cap was raised those
  three extractions would have returned a full record of null cells. Max observed 2,260 vs the new
  6,000 cap.
- Statuses across the 18: `tons_only` and `not_present` dominate the untouched buckets, `cy_only`
  ×8, `sy_converted_only` ×3, `sy_no_depth_present` ×1, `mixed` ×0, `unknown` ×0, `inconsistent` ×0.
  No extraction errored (18/18 OK).

---

## 4. Interaction

### 4.1 Composition with 2a (`2026-08-10-mapping-honesty`) — **they overlap and contradict; they do not compose as-is**

| | 2a | #102 |
|---|---|---|
| new extract fields | 6: `{hot_mix,base,shoulder}_measured_unit` + `_unconverted` | 3: `base_cy_items`, `shoulder_cy_items`, `mix_sy_depth_items` |
| item shape | one string, `DESCRIPTION \| QUANTITY \| UNIT` per line | JSON array of `{quantity, unit, depth_in, page, note}` |
| conversion | **none, by design** | 1.55 t/CY, 0.0565 t/SY-in |
| status fn | `schema.bucket_unit_status(record, field)` | `schema.{base,shoulder,mix}_unit_status(record)` |
| status vocabulary | `tons_only` · `unconverted_only` · `tons_and_unconverted` · `not_present` · `unknown` · `inconsistent` | `tons_only` · `cy_only` · `sy_converted_only` · `mixed` · `sy_no_depth_present` · `not_present` · `unknown` · `inconsistent` |

**Overlap:** both ask the model for the *same* off-unit items, in two different shapes, in the same
prompt. Applied together the model is asked to enumerate item 41 twice. That is 9 new fields on one
extraction call.

**Contradiction — the key-name trap, confirmed in code on both branches:**

- #102, `apps/api/backend/report.py:346-348`, literal keys:
  `"base_unit_status"`, `"shoulder_unit_status"`, `"mix_unit_status"`.
- 2a, `report.py`, computed: `f"{bucket.rsplit('_', 1)[0]}_unit_status"` over
  `schema.TONS_BUCKETS` = `{hot_mix_tons, base_tons, shoulder_tons}` → evaluated:
  `hot_mix_unit_status`, `base_unit_status`, `shoulder_unit_status`.

So **`base_unit_status` and `shoulder_unit_status` are emitted by BOTH branches with different,
partly-disjoint vocabularies**, and the third key differs by name (`mix_unit_status` vs
`hot_mix_unit_status`). The coordinator's report is confirmed exactly. Consequences:

- A consumer written against 2a reading a #102 payload gets `hot_mix_unit_status → undefined` and
  renders a perfectly-captured mix bucket as "Not captured".
- Worse and quieter: it gets `base_unit_status = "cy_only"` — a token 2a's vocabulary does not
  contain — so any `switch`/lookup falls through to its default. Same wrong render, but this one
  reads as a valid key with a valid-looking value.

**Exact key names #102 puts on the payload** (from the code, not the spec):
`identity.base_unit_status`, `identity.shoulder_unit_status`, `identity.mix_unit_status`, plus
`field_confidence` entries keyed `"base_cy_items"`, `"shoulder_cy_items"`, `"mix_sy_depth_items"`
(confidence/page/reason only — no value; §3.2 gap 3).

**Also a textual merge conflict**, both files: both branches replace the same
`data = call_json(prompt) or {}` line in `s3_extract.py::extract_fields`, and both insert into the
same `identity` dict immediately after `"milling_unit_status"` in `report.py`.

**They are not mutually exclusive in principle** — 2a is "say what the schedule measured, convert
nothing"; #102 is "convert it". Our own 2b spec explicitly designs #102's job as *a layer on top of
2a* (§5, "never a replacement for it"). But as written they are two implementations of the capture
step, and only one capture step can exist.

### 4.2 Token-cap truncation — **mitigated, not fixed; the failure/empty collapse is untouched**

`2026-08-10_pr102_truncation_probe.py`, plan 9786015:

```
run0 @max_tokens=2048 -> stop_reason='max_tokens', output_tokens=2048, why='truncated_at_max_tokens'
run1 @max_tokens=2048 -> stop_reason='max_tokens', output_tokens=2048, why='truncated_at_max_tokens'

# the SHIPPED code path on #102's branch, same response:
  WARNING: JSON parse failed (Unterminated string starting at: line 171 column 15 (char 5688)).
call_json returned: None
merge: {'base_tons': None, 'shoulder_tons': None, 'hot_mix_tons': None}
new statuses: unknown unknown unknown      milling_unit_status: unknown
sample scalars: {'milling_sy': None, 'grading_quantity': None, 'county': None, 'hot_mix_tons': None}
```

- **What #102 fixes:** the cap. `extract_fields` now passes `max_tokens=6000` (an inline literal at
  `s3_extract.py`; the regression harness got the same change). Measured real usage on 9786015
  under #102: **2,100 / 2,124 / 2,174 / 2,145 / 2,156 / 2,104 output tokens** — all six above the
  old 2,048 default. The truncation was real and the raise is necessary. Headroom at 6,000 is ~2.8×,
  and Stearns/Crow Wing ran 1,678–1,917.
- **What #102 does NOT fix:** `call_json` still returns `None` for both truncation and malformed
  JSON, never inspects `resp.stop_reason`, and `extract_fields` still does `or {}`. The log line
  above says "JSON parse failed (Unterminated string…)" for what was actually a complete, correct
  answer that ran out of room. A truncated extraction then produces a **full record of clean null
  cells** — `county=None`, `milling_sy=None` — i.e. a total extraction failure presented as a plan
  that states nothing. **#102 is directly exposed to this** (it adds three fields to the same call)
  and leaves it in place.
- **Does it worsen it?** Marginally, yes, in one respect: three array fields make the response
  length depend on how many qualifying items a plan has, so the response size is now data-dependent
  rather than roughly fixed by field count. A plan with 20 off-unit items is a bigger response than
  anything measured here, and the failure mode when it overflows is still "the plan says nothing".
- **2a is strictly better here, in one narrow way**: it does inspect `stop_reason` and names the
  cause in the log (`"response was CUT OFF at the max_tokens cap"`), and puts the budget in a named
  constant `EXTRACT_MAX_TOKENS = 6000` rather than an inline literal. It also does not fix the
  shared return value — and says so explicitly in the comment.
- **Partial credit where due:** for the three *new* fields specifically, #102 does keep the
  distinction alive one level down — `_coerce_items` returns `None` for a non-list (→ status
  `unknown`) and `[]` for a model-asserted empty (→ `not_present`/`tons_only`). That is the right
  discipline, correctly implemented. It just cannot save a record whose whole JSON never parsed.

### 4.3 The provenance gap — a converted number and a stated number look identical

Checked specifically, and it holds. Nothing in #102 marks a value as converted **at the value**:

- `report.py:289-297`: `quantities.append({"label": label, "value": _effective(src), "unit": _UNIT[dst]})`.
  `_effective` returns the merged number; the appended dict has no provenance key, no factor, no
  flag. For 9786015 this is `{"label": "BASE", "value": 3851.75, "unit": "t"}` — byte-identical in
  shape to a plan that stated 3,851.75 tons on its bid schedule.
- The accompanying `field_confidence[label] = _conf(field)` reads the **native** cell — which on
  9786015 is absent. Confirmed: `schema.cell(None, "", None)` → `_conf` →
  `{'confidence': '', 'page': None, 'reason': None}`. **So a fully-derived 3,851.75 t renders with
  blank confidence and no page citation**, while the actual evidence (`confidence: high, page: 27`)
  sits under a *different* key, `field_confidence["base_cy_items"]`, that no quantity row points to.
- `bid_projects_record.py` reads `payload["quantities"]` verbatim, so the DB row gets the derived
  number with no marker either. `competitor_predict_live.py`'s `_MATERIAL_COLS` then scores it as
  if stated.
- The only conversion signal anywhere is the bucket-level `identity.{base,shoulder,mix}_unit_status`
  — which (a) is not attached to the value, (b) mislabels the TON+CY blend as `cy_only` (§3.2 gap 1),
  and (c) never carries the factor. The constants `1.55` / `0.0565` appear **nowhere in the
  payload**; they exist only as module constants, so a report printed today cannot explain itself
  after the factor changes.
- #102's own spec has no provenance section — §8 "Explicitly out of scope" does not mention it,
  so this is an unrecorded gap, not a deferred one.

The coordinator's read is correct, and I would put it more strongly: this is the **same defect
class**, pointed the other way, and it is worse than the one it replaces because a converted number
carries a factor assumption a stated number does not.

---

## 5. Verdict

### **Adopt as base — with three named gaps that must be closed before it is called done.**

Why adopt: the conversion is right, it is code-only, it reproduces all three of CSI's numbers to the
cent, its arithmetic is deterministic under 1,000 repeats, its item-level classification was stable
across 18 live runs on three plans, it correctly refuses to sum the four SY mix lines before
converting, its `None`-vs-`[]` discipline on the new fields is the correct one, and it removes a
measured ~13% model-arithmetic error. It is also the only one of the two branches that actually
produces a tonnage; 2a deliberately produces none. Nothing about it is architecturally wrong — every
gap below is additive.

**Named gap 1 — provenance.** Every converted value must be distinguishable from a stated one at the
value, carrying the literal factor and the lines it came from. Our 2b spec §6 already specifies the
shape (`<bucket>_converted_tons` / `_converted_lines` / `_conversion_status`, `factor_value` carried
as a literal). #102 has none of it, including in its spec. **This is the blocking one** — it is the
repo's own standing-rule violation, and CSI's first question will be "where did 1,901 come from?".

**Named gap 2 — key-name and vocabulary reconciliation with 2a.** `base_unit_status` /
`shoulder_unit_status` are emitted by both with incompatible vocabularies; `mix_unit_status` vs
`hot_mix_unit_status` differ by name. Pick one name set and one closed vocabulary before either
lands, and make sure the chosen vocabulary retains a **both-units** state (2a's
`tons_and_unconverted`) — #102 has no such state and silently mislabels the blend as `cy_only`.

**Named gap 3 — the two internal collapses.** (a) `merge_material_tons` returns `None` both for "no
base on this plan" and for "a base item we could not convert"; (b) the raw items list never reaches
the payload, because `_conf` drops the value, so an excluded quantity is unrecoverable. Both are the
failure-vs-empty rule, inside the change that exists to enforce it.

Not blocking but should be recorded: the truncation/parse conflation in `call_json` is untouched
(adopt 2a's `stop_reason` naming and its `EXTRACT_MAX_TOKENS` constant when integrating), and
coverage is 3 of 7 buckets with only CY and SY-with-depth convertible.

**And explicitly:** do not describe #102 as reducing the mapping drift. It does not touch the seven
prose scalars where the drift was measured, and its own bucketing is still model-driven prose.

### Which spec survives

**`docs/_spec/2026-08-10-placed-material-conversion.md` (ours, on `2026-08-10-mapping-honesty`)
survives as the design of record. `docs/_spec/2026-08-10-aggregate-mix-tons-conversion.md` (#102's)
should be marked superseded** and reduced to what it uniquely holds: the implementation notes and
the three-bug evidence trail (model arithmetic wrong ~13%, mix reusing the `/36` formula, the
2,048-token overflow), which are genuinely valuable and are not in ours.

Reasons, in order:

1. **They agree on the physics, so this is not a technical dispute.** #102's `MIX_TON_PER_SY_INCH =
   0.0565` is exactly ours: 113 lb/SY-in ÷ 2000. `AGGREGATE_TON_PER_CY = 1.55` is identical. Both
   reproduce 3,851.75 / 13.09 / 1,901.34. Two independent derivations landing on the same constants
   is a reason to keep **one** document, not two.
2. **Ours specifies what #102's gap 1 is missing** — provenance on every converted number (§6),
   a closed `reason` vocabulary, the factor carried as a literal, the `partly_converted` state, and
   a flag whose default-off makes "not ready" the automatic safe state (§9). #102's spec has no
   equivalent to any of these.
3. **Ours is explicit that this layer sits on top of 2a and never overwrites the stated-tons
   fields** (§5.1 invariant 2) — which is precisely the distinction #102's implementation lost.
4. **#102's spec is a PR writeup, ours is a design.** #102's §8/§9 are scoped to what that PR did;
   ours holds the factor-blessing gate, the corpus evidence (§11), and the acceptance test (§10).

This repo already carries four competing material-mapping artifacts and that is named in HANDOFF.md
§2 as the root cause of most of its confusion. **Do not leave a fifth**: one spec, one status-key
vocabulary, one capture shape.
