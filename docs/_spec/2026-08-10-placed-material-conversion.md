# Spec — SY/CY → tons conversion for PLACED materials

Date: **2026-08-10** · Status: **SPEC ONLY. NOTHING BUILT. Awaiting Alex's signature on §3 and the
owner's decision on §9.** · Board task 2b

Author's scope note: no code was written for this. No `.py` file in this repo contains a
multiplication introduced by this task. Every number below was computed in a throwaway shell, and
the working is shown so it can be re-derived without trusting me.

Sits **on top of** `docs/_spec/2026-08-10-tons-bucket-unit-capture.md` (task 2a, already built and
shipped in `pipelines/plan_reader/01_pipeline/schema.py`). This layer never replaces that one. See §5.

---

## 1. The finding that motivates it, and the half-truth in the current text

`schema.py:110-118` (`grading_quantity`) says:

> "When a removal is measured in square yards or tons, do NOT convert it and do NOT count it here —
> **no verified depth or density factor exists.**"

That clause is **correct for removals and wrong as a general statement about placed materials**, and
it is currently the only reason the system refuses every conversion.

For a placed material, both missing pieces are on the page:

- **Depth is stated in the pay-item description itself.** MnDOT writes
  `2.0" Depth Type SP 9.5 Wearing Course Mixture (2,B) (P) (CSAH 2)`. The depth is not inferred, not
  looked up, not assumed — it is part of the contractual item name.
- **Density is a published, industry-standard factor**, not a guess about this plan.

The refusal is costing real quantity. On plan **9786015** — the plan CSI itself raised — the entire
asphalt and base scope is measured in SY and CY, so `hot_mix_tons` and `base_tons` are both null
today while the plan carries **1,901 tons of mix and 3,852 tons of base**.

### 1.1 What is NOT claimed here

The removal case is not being reopened. Note the measured fact in §6.3: **depth is stated on 21 of
79 milling rows** in the corpus, so "removals have no depth" is itself not quite true either. The
reason removals stay unconverted is different and stronger, and it is **CSI's ruling**, not a
missing factor — see §7.

---

## 2. The oracle: plan 9786015, and it is rare

CSI supplied hand-computed tonnages for this plan. That makes it the only **validated arithmetic
oracle** on this project — everywhere else we have CSI *bucket totals*, which conflate extraction
error with conversion error. Here we have the input lines, the factor claim and the answer.

**Source, verified.** `9786015.pdf` at
`…/CSI ELP 2026/2025 Bid year (9.1.24-8.31.25) - CURRENT/12 - AUGUST/Plans Proposals/08.07.25 MURRAY
CO MN, FULDA PROJ 254021 (CSAH 2) INFRASTRUCTURE IMPS/` on the local iCloud mirror (Box reads time
out; see `TASKS.md`). Already converted in `pipelines/plan_reader/00_input/_md_cache/` as
`a3171c2187e8af85.json`, 466 pages. Bid schedule = **EJCDC C-410 Bid Form, Article 3.01.A**, pdf
pages **25–28**. Project: *CSAH 2 Infrastructure Improvements, City of Fulda, Murray County,
Minnesota, July 14, 2025*.

**The real lines, transcribed from md-cache page 27** (not invented):

| Item | Description **exactly as printed** | Unit | Qty |
|---:|---|---|---:|
| 40 | `8" Class 5 Alley & Shouldering Aggregate Surfacing (CV) (P)` | SY | 38 |
| 41 | `Class 5 Aggregate Base (CV) (P)` | CY | 2,485 |
| 42 | `12" Cement Stabilized Subgrade (CV) (P)` | SY | 1,566 |
| 43 | `Cement Powder based on 5%` | TON | 40 |
| 44 | `2.0" Depth Type SP 9.5 Wearing Course Mixture (2,B) (P) (CSAH 2)` | SY | 5,368 |
| 45 | `3.0" Depth Type SP 12.5 Non Wearing Course Mixture (2,B) (P) (CSAH 2)` | SY | 5,368 |
| 46 | `1.5" Depth Type SP 9.5 Wearing Course Mixture (2,B) (P) (MARYLAND AVE)` | SY | 1,703 |
| 47 | `2.5" Depth Type SP 12.5 Wearing Course Mixture (2,B) (P) (MARYLAND AVE)` | SY | 1,703 |

And two lines from page 26 that matter to §7:

| Item | Description | Unit | Qty |
|---:|---|---|---:|
| 5 | `Mill Bituminous Surface (2.0") (CSAH 2)` | SY | 8,731 |
| 7 | `Remove Bituminous Pavement` | SY | 7,097 |

Item 5 is the sharpest single fact in this document: **a removal with a stated depth.** Depth
availability is therefore *not* what separates convert from don't-convert. §3.2 and §7 turn on this.

---

## 3. The proposed factor table — Alex's decision, not mine

This is a **proposal for signature**. Nothing in it originates from CSI, and until Alex signs it the
flag in §9 stays off.

### 3.1 The table

| # | Material class | Factor | Direction | Source / provenance |
|---:|---|---|---|---|
| F1 | **Bituminous mixture** (MN `Type SP …`, ND `Superpave`, SD `Asphalt Concrete`), placed | **113 lb per SY per inch of compacted depth** | SY + depth → ton | Industry-standard compacted HMA unit weight. **Provenance: proposed by the owner for this task; not traced to a state spec book.** Alex to confirm. |
| F2 | **Class 5 aggregate base**, purchased and placed | **3,100 lb/CY = 1.55 ton/CY** | CY → ton | Same. **Provenance: proposed by the owner; not traced to a state spec book.** Alex to confirm. |
| F3 | **Shoulder aggregate** (Class 5 family) | SY × stated depth ÷ 36 → CY, then **F2** | SY + depth → ton | Derived: F3 is not an independent factor, it is a geometry step feeding F2. |

**F3 is deliberately not a fourth number.** Writing `86.11 lb/SY-in` as its own row would create a
second, silently-drifting statement of F2 (113 × 36 = 4,068 lb/CY is F1's equivalent; 3,100 ÷ 36 =
86.11 lb/SY-in is F2's). One number per material, and the geometry is a step, not a factor.

### 3.2 What is deliberately absent from this table

- **No milling / RAP factor.** Not proposed, not derived, not defaulted. §7.
- **No factor for removal in any unit.** §7.
- **No factor for `Cement Stabilized Subgrade`** — CSI ruled it do-not-count, and it is the item on
  this very plan that would be convertible on a depth test (`12"`, 1,566 SY) and must not be.
- **No "Class 5-like" or "aggregate, general" catch-all.** §4.3.
- **No `Aggregate Surfacing Class 1 / 2 / Special`.** §8.
- **No loose-vs-compacted (CV/LV) distinction.** Every 9786015 aggregate line is stamped `(CV)`
  (compacted volume), which is what F2's density assumes. **An `(LV)` line is a different
  measurement basis and this table does not cover it** — it must fall through to §5's surfaced
  output with reason `lv_basis_not_blessed`. Named because MN publishes `2211.507 Aggregate Base
  (CV)/(LV)` as two real pay items and the corpus contains `Haul Full Depth Reclamation (LV)`
  (see `2026-08-10-spec-books-tier1.md` C2).

---

## 4. The rule

### 4.1 The gate, stated once

> **Convert a line only when BOTH hold: (a) its material class is in the blessed table of §3.1, AND
> (b) the geometry the factor needs is available from the line itself.** Otherwise surface the raw
> value and unit with a machine-readable reason. **Never guess. Never drop. Never round the input.**

"(b)" is deliberately not spelled "a depth is available", because the requirement differs per factor:

| Factor | Needs | Available from |
|---|---|---|
| F1 (SY → ton) | density **and** depth | depth parsed from the item description |
| F2 (CY → ton) | density only | nothing — CY is already a volume |
| F3 (SY → ton) | density **and** depth | depth parsed from the item description |

**F2 is the reason the gate is not "depth or nothing".** `Class 5 Aggregate Base (CV) (P) | 2485 |
CY` carries no depth and needs none. A depth-availability gate would refuse the single largest
tonnage on the oracle plan.

### 4.2 Where the depth comes from, and what happens without one

**Source: the pay-item description string, and nowhere else.** Not a typical section, not a plan
sheet, not a default. Three printed forms appear in the corpus and all three are the same fact:

| form | corpus example |
|---|---|
| leading `N.N" Depth` | `2.0" Depth Type SP 9.5 Wearing Course Mixture (2,B) (P) (CSAH 2)` |
| trailing `N" Thick` / `N" THICKNESS` | `Type SP 12.5 Wearing Course Mixture (3,C) 2" Thick`, `TYPE SP 9.5 WEARING COURSE MIXTURE (2,B) 3" THICKNESS` |
| leading `N"` with no keyword | `8" Class 5 Alley & Shouldering Aggregate Surfacing (CV) (P)`, `Superpave FAA 43 - 4"` |

**No depth ⇒ no conversion, ever.** The line is surfaced through §5 with reason
`depth_not_stated`. It is not defaulted to 2", not inferred from a sibling line on the same plan,
not inferred from the course type, and not carried over from the previous plan. A default depth is
the single cheapest way to reintroduce the 605× Dunn failure with a plausible-looking number
attached, and it is forbidden.

**Two depths on one line ⇒ no conversion.** If more than one inch-measurement parses out of a
description, the line is surfaced with reason `depth_ambiguous`. Do not take the first, the largest
or the last. (Anticipated shape: `Mill Bituminous Surface (2.0") … 1.5" Depth …` on a combined
line.)

### 4.3 The blessed-table gate

**How a class gets in:** Alex names the material and the factor, in writing, and the row is added
with his name and the date in a `blessed_by` / `blessed_on` column. Nothing else admits a class —
not a spec book, not a plausible analogy, not a factor found in this repo.

**What happens to a class that is not in it:** it is **surfaced, never converted**, with reason
`class_not_blessed`, carrying its description, quantity and unit verbatim. It counts as neither a
hit nor a miss (§10.2). It is visible to the estimator as *"we read this, we cannot express it in
tons"* — which is exactly the state task 2a already produces today for every off-unit line, and is
strictly better than what preceded it (a bare null).

**Why an unblessed class must never fall back to a "similar" factor.** Four reasons, in descending
order of how much money they cost:

1. **Similar-looking aggregates are physically different products.** MnDOT §3138.1
   (`2026-08-10-spec-books-tier1.md` Q5) puts Aggregate Surfacing, Aggregate Base and Shoulder Base
   Aggregate on **one shared class table** — a "Class 5" is a Class 5 by name across all three — yet
   Surfacing must additionally be 100% passing 3/4", may contain no glass, and needs PI 5–12.
   *"Class 5 Aggregate Surfacing" and "Class 5 Aggregate Base" are physically different products
   under the same class number.* Name similarity is affirmatively **not** evidence of density
   similarity in this domain.
2. **A wrong conversion is invisible; a refusal is loud.** A refusal surfaces as
   `unconverted_only` with the raw line printed. A wrong factor produces a number in the right
   order of magnitude, in the right column, with no signal. Every one of the eleven silent-failure
   instances on this project's standing list has that shape.
3. **The fallback would have no owner.** A blessed row is a factor Alex signed. A fallback row is a
   factor nobody signed that CSI will read as though he had.
4. **It converts an honest gap into a false coverage number.** §10.2 depends on unconvertible lines
   being counted separately; a fallback moves them into `matched` and inflates recall with numbers
   nobody verified.

### 4.4 Precedence — the rulings sit ABOVE conversion

Evaluation order, and it is not negotiable:

```
1. CSI exclusion rulings        (do-not-count → the line leaves the pipeline entirely)
2. CSI bucket rulings           (which bucket, e.g. FDR's quantity stays in milling_sy)
3. task 2a capture              (found-but-off-unit → *_unconverted, *_measured_unit)
4. THIS LAYER                   (blessed class + geometry → a tons value, ADDED ALONGSIDE)
```

A ruling can veto a conversion. **A conversion can never veto, move or re-bucket a ruling.** §7 is
the concrete case.

---

## 5. Shape: a layer on top of task 2a, never a replacement for it

Task 2a is built and shipped. `schema.py` now carries, per tons bucket:

| bucket | unit token field | per-item list field |
|---|---|---|
| `hot_mix_tons` | `hot_mix_measured_unit` | `hot_mix_unconverted` |
| `base_tons` | `base_measured_unit` | `base_unconverted` |
| `shoulder_tons` | `shoulder_measured_unit` | `shoulder_unconverted` |

plus `schema.bucket_unit_status(record, field)` returning one of `tons_only` /
`unconverted_only` / `tons_and_unconverted` / `not_present` / `unknown` / `inconsistent`.

**`*_unconverted` is already exactly the input this layer needs**: one line per item, as printed, in
the form `DESCRIPTION | QUANTITY | UNIT`. The description carries the depth; the unit carries the
direction. No new extraction field and no new model call is required for the conversion itself.

### 5.1 Three invariants

1. **`*_unconverted` is never emptied, rewritten or trimmed by this layer.** A line that converts
   successfully stays in the list, verbatim. The raw evidence and the derived number coexist. This
   is what makes a conversion auditable and what makes it reversible if Alex changes a factor.
2. **`hot_mix_tons` / `base_tons` / `shoulder_tons` are NOT written by this layer.** Those fields
   mean *"tons the bid schedule stated"*. A converted value is a different kind of number and gets
   its own field (§6). Writing into them would make a stated value and a derived value
   indistinguishable downstream — the exact defect §6 exists to prevent, and the exact mistake the
   `MILL` / `MILL_TON` label decision avoided in `2026-08-10-milling-unit-capture.md` §4.1.
3. **`bucket_unit_status()` is not modified and its return values do not change.** A plan with a
   fully-converted base bucket is still `unconverted_only` — because the *schedule* still measured
   it in CY. The conversion is an addition to what we can say, not a change to what the schedule
   said. If a downstream consumer wants "is there a number now?", it reads §6's fields.

**Consequence, stated plainly so it is a known gap and not a discovered one:** with the flag off
(§9's default), behaviour is byte-identical to today. With it on, nothing that exists today changes
value; new fields appear beside the old ones.

---

## 6. Provenance — a converted number and a stated number must never look alike

### 6.1 The required shape (proposed; not built)

Per bucket, three derived values and a per-line record. Names are proposals.

| name | type | meaning |
|---|---|---|
| `<bucket>_converted_tons` | num | sum of the lines this layer could convert. **Null, never 0, when nothing converted** — a legitimate zero and a failure must not share a value. |
| `<bucket>_converted_lines` | list | one record per line the layer *attempted*, converted or not (§6.2) |
| `<bucket>_conversion_status` | str | closed vocabulary, §6.3 |

### 6.2 The per-line record — what CSI must be able to see

Every attempted line carries, whether or not it converted:

```
description        # verbatim, as printed on the bid schedule
quantity, unit     # verbatim, as stated
depth_in           # the parsed depth, or null
depth_source       # the exact substring the depth was parsed from, e.g. '2.0" Depth'
material_class     # the blessed-table row matched, or null
factor_id          # F1 / F2 / F3, or null
factor_value       # e.g. '113 lb/SY/in' — the literal factor, not a reference to it
factor_blessed_by  # 'Alex <surname>' + date, or null
tons               # the derived value, or null
reason             # null when converted; otherwise ONE of the closed set below
```

`factor_value` is carried on the row **as a literal**, not as a pointer into the table, so a report
printed today still explains itself after the table is edited. `reason` is non-null exactly when
`tons` is null — never both, never neither.

**Closed `reason` vocabulary:** `class_not_blessed` · `depth_not_stated` · `depth_ambiguous` ·
`lv_basis_not_blessed` · `unit_not_convertible` · `ruling_excluded` · `ruling_bucketed_elsewhere` ·
`flag_off`.

### 6.3 `<bucket>_conversion_status`

| status | meaning |
|---|---|
| `not_applicable` | bucket was `tons_only` or `not_present` — nothing to convert, and that is a real answer |
| `all_converted` | every off-unit line converted |
| `partly_converted` | some converted, some carry a reason. **The bucket total is INCOMPLETE and must be labelled so on screen.** |
| `none_converted` | off-unit lines exist, none was convertible. Every one carries a reason. |
| `disabled` | the flag is off (§9). Distinct from `none_converted` on purpose: "we did not try" is not "we tried and could not". |
| `unknown` | upstream `bucket_unit_status` was `unknown` or `inconsistent` — this layer does not run on an input it cannot trust, and says so |

### 6.4 In the report

Non-negotiable for the UI, whoever builds it:

- A converted number is **never** printed bare. It carries a visible marker and the factor, e.g.
  `1,901 t (converted · 113 lb/SY/in)`.
- `partly_converted` renders as visibly incomplete. Per `TASKS.md` P0 4a: *if the UI has no branch
  for a gap state it must render visibly wrong, not blank.*
- The per-line records are reachable from the number. CSI's question will be *"where did 1,901
  come from?"* and the answer is four lines of arithmetic they can check by hand — as they did.

---

## 7. Interaction with `milling_sy` — the rulings sit above this layer

**CSI ruled (2026-08-07, ruling #9) that FULL DEPTH RECLAMATION is base *work* whose quantity stays
in `milling_sy`, in square yards.** Rulings #5 and #6 put `REMOVE BITUMINOUS PAVEMENT` and
`REMOVAL OF BITUMINOUS SURFACING` in `milling_sy` too. **This layer must not touch any of it.**

The temptation is concrete and it is on the oracle plan: item 5 is
`Mill Bituminous Surface (2.0") (CSAH 2) | 8,731 | SY` — a stated depth, a bituminous material, a
square-yard quantity. Under a naive "has depth + is bituminous ⇒ convert" rule it converts to
~986 tons and silently undoes a client ruling.

**Three independent reasons it must not, any one of which is sufficient:**

1. **The ruling.** CSI decided the bucket and the unit. A derived layer does not overrule a client
   decision. `bucket_hierarchy.csv` records `milling_sy` as `unit=SY, in_total_tons=0` — it is not
   a tonnage bucket at all, so there is nowhere for a converted ton to legitimately land.
2. **F1 is the wrong factor even if conversion were allowed.** F1 is *compacted, placed* HMA.
   Milled material is *removed and loose*; RAP bulks up. Applying a placed-density factor to a
   removal over-reports by whatever the loose/compacted ratio is, and nobody here has measured it.
3. **The contractual unit is SY, in two states independently.** MnDOT 2232.4: *"measure pavement
   milling by the AREA of each type of surface removed."* SDDOT 332.4: not field-measured at all —
   *plan quantity is the basis of payment*. `2026-08-10-spec-books-tier1.md` Q3.

**Mechanically:** the blessed table (§3.1) contains no milling or removal class, so
`class_not_blessed` fires and the line surfaces unchanged. The protection is structural, not a
special case bolted on — which is the point of §4.3's gate being class-based rather than
depth-based. **`milling_sy` and `milling_tons` are out of scope of this spec entirely and their
values must be bit-identical before and after.** That is a blocking test in §10.1.

---

## 8. The open aggregate-surfacing bucket — noted, NOT resolved

`AGGREGATE SURFACING CLASS 1 / 2 / 5 / SPECIAL` currently lands in `shoulder_tons` on a keyword
guess. `schema.py:119-123` says so out loud: *"still counted here, pending a CSI ruling."*
`docs/_spec/2026-08-10-live-mapping-rulings.md` "Open" #4 records it as unresolved.

**This spec does not resolve it and must not.** Three notes so it is not accidentally resolved by
someone implementing §3:

1. **Two corrections to the framing on the board.** (a) The constant
   `quantity_crosswalk.py::CSI_OPEN_QUESTIONS_2026_08_07` literally contains only
   `["riprap classification", "crushing/stockpile exclusion"]` — the aggregate-surfacing question is
   recorded in the live-mapping spec, **not** in that constant. (b) The board's "67,000 T" does not
   reproduce against the current store: `csi_v2.db` at `crosswalk_version=2` shows **18 rows,
   33,771 TON** of `AGGREGATE SURFACING` in `shoulder_tons` (bucket total 57,173 T over 24 rows).
   Both figures are stated; I did not reconcile them, and the discrepancy does not affect this spec.
2. **Every one of those 18 rows is already in TON.** The open question is *which bucket*, which is a
   ruling. It is not a conversion, and this layer never runs on them.
3. **F2 must not be quietly extended to Aggregate Surfacing.** §4.3's reason 1 is exactly this case:
   MnDOT puts Surfacing and Base on one class table and then specifies them differently. If Alex
   wants Aggregate Surfacing converted he blesses it as its own row with its own factor.

---

## 9. Gating — "not ready in time" must be the automatic safe state

Owner's decision, recorded: this ships behind a flag that is **OFF unless two gates pass**.

### 9.1 The two gates

| gate | passes when |
|---|---|
| **G1 — blessed** | The factor table carries a non-empty `blessed_by` + `blessed_on` for **every** row it intends to use. Alex, in writing. |
| **G2 — reproduces** | The §10.1 acceptance test passes on plan 9786015: all three CSI numbers reproduce within tolerance. |

### 9.2 The design that makes "off" automatic

The failure mode being designed against is *"Wednesday arrives, Alex has not signed, and the flag is
still on because nobody remembered to turn it off."* Three properties, and the first is the one that
matters:

1. **The gates are computed, not configured.** The flag is not a boolean somebody sets. It is
   `enabled = G1 and G2 and operator_opt_in`, evaluated at import. G1 reads the table's own
   `blessed_by` column; G2 reads the acceptance test's recorded result. **Forgetting to sign leaves
   an empty `blessed_by`, which is `False`, which is off.** Inaction is safe; only three
   deliberate positive acts turn it on.
2. **`operator_opt_in` defaults absent-is-off.** Env var unset ⇒ off. Set to anything other than an
   explicit truthy token ⇒ off, with a loud log line, not a silent fallback. (`TASKS.md` M2 records
   the general form of this trap: *absent-means-current is one sign flip from re-creating the bug.*)
3. **Off is a state, not a silence.** With the flag off, `<bucket>_conversion_status` is `disabled`
   — never `none_converted`, never null, never absent. Anyone reading a report can tell "the layer
   was switched off" from "the layer ran and nothing was convertible". Twelfth application of the
   standing rule.
4. **Off changes no existing value.** §5.1. So the demo path with the flag off is the demo path as
   it is today, with one extra explanatory status string.

### 9.3 Recommendation

**Ship with `operator_opt_in` unset for the Aug 12 presentation**, even if G1 and G2 both pass.
`hot_mix_tons` on 9786015 moving from null to 1,901 is a *visible* number change on a plan CSI knows
by hand; it belongs in a conversation with Alex, not on a slide he sees for the first time. Compare
`TASKS.md` P1 #20 — the same lesson already learned about Stearns `milling_sy` doubling by design.

---

## 10. Acceptance test — CSI's own numbers on plan 9786015

### 10.1 The three targets, and the arithmetic, shown

**Mix — F1, 113 lb/SY per inch, ÷ 2000 lb/ton:**

| Item | Qty (SY) | Depth (in) | `SY × in × 113 ÷ 2000` | Computed | CSI | Δ |
|---:|---:|---:|---|---:|---:|---:|
| 44 | 5,368 | 2.0 | `5368 × 2.0 × 113 ÷ 2000` | **606.5840** | 606.58 | +0.0040 |
| 45 | 5,368 | 3.0 | `5368 × 3.0 × 113 ÷ 2000` | **909.8760** | 909.86 | **+0.0160** |
| 46 | 1,703 | 1.5 | `1703 × 1.5 × 113 ÷ 2000` | **144.3292** | 144.33 | −0.0008 |
| 47 | 1,703 | 2.5 | `1703 × 2.5 × 113 ÷ 2000` | **240.5488** | 240.55 | −0.0012 |
| | | | **total** | **1,901.3380** | **1,901.34** | **−0.0020** |

**All four reproduce, and the one apparent discrepancy is CSI's, not the factor's.** Item 45 is the
only Δ above rounding. It is explained without adjusting anything: **CSI's own four per-item figures
sum to 1,901.32, but CSI's stated total is 1,901.34** — which is exactly the unrounded computation.
So 909.86 is a rounding/transcription artifact in CSI's per-item column, and CSI's *total* confirms
that the true item-45 value is 909.876. No factor was touched to make this fit; had the factor been
wrong the total would have been wrong too, and it is right to 0.0002%.

For completeness, the factor that *would* reproduce a literal 909.86 on item 45 is
`909.86 × 2000 ÷ (5368 × 3) = 112.998 lb/SY-in` — i.e. 113 to five significant figures. There is no
alternative factor hypothesis here; there is a rounded printout.

**Base — F2, 3,100 lb/CY:**

```
2,485 CY × 3,100 lb/CY ÷ 2,000 lb/ton = 2,485 × 1.55 = 3,851.75 t
```
CSI: **3,851.75**. Δ = **0.00**. Exact.

**Shoulder — F3 geometry then F2:**

```
38 SY × 8 in ÷ 36 in/yd = 8.444444 CY
8.444444 CY × 1.55 ton/CY        = 13.088889 t  →  13.09
```
CSI: **13.09**. Δ = **−0.0011**, i.e. CSI rounded to 2 dp. Exact to the stated precision.

**Verdict: all three reproduce from the proposed factors.** No factor was adjusted.

### 10.2 The test, as a gate

**Blocking pass conditions.** All must hold, on `a3171c2187e8af85` (plan 9786015):

| # | Condition | Tolerance |
|---:|---|---|
| A1 | four per-item mix tons, in schedule order | ±0.02 t per item |
| A2 | mix bucket total = 1,901.34 | ±0.02 t |
| A3 | base = 3,851.75 | exact to 2 dp |
| A4 | shoulder = 13.09 | ±0.01 t |
| A5 | `Mill Bituminous Surface (2.0") (CSAH 2)` produces **no** tons and carries `class_not_blessed` | — |
| A6 | `12" Cement Stabilized Subgrade (CV) (P)` produces **no** tons | — |
| A7 | `milling_sy` and `milling_tons` are **bit-identical** to the flag-off run on all 17 `_md_cache` plans | exact |
| A8 | with the flag off, every quantity field on all 17 plans is bit-identical to today's committed baseline | exact |

Per-item tolerance is ±0.02 rather than ±0.005 **because of the item-45 artifact**: CSI's printed
per-item figures are not internally consistent to the cent, and a tighter tolerance would fail on
CSI's rounding rather than on our arithmetic. A2 is checked against CSI's *total*, which is the
internally consistent figure.

**A7 and A8 are the regression gates and they are the ones that will actually catch a mistake.**
A1–A4 prove the factors; A7–A8 prove this layer is additive.

**CSI's historical figure for this job is 1,850 t against a computed 1,901.34 t — a 2.8% gap.** That
is a real, expected disagreement between *plan quantity* and *what CSI carried in its own
spreadsheet*, and it is **not** an acceptance criterion. It is precisely what `TASKS.md` P1 #16's
three-way golden column exists to explain. Do not tune a factor toward 1,850.

### 10.3 Scoring — reuse the existing category

`CONVERSION_REQUIRED` already exists in `tools/golden/2026-08-10_golden_join.py` (built for D1): out
of `matched`, out of **both** denominators, no variance computed. A line this layer converts moves
from `CONVERSION_REQUIRED` into the normal scored population and **acquires a variance**. A line it
declines stays `CONVERSION_REQUIRED`. No new category, and the count of `CONVERSION_REQUIRED` rows
becomes the honest measure of what the blessed table still does not cover.

**The headline moves, and the movement must be declared.** Recall is currently 0.667 with converted
tonnage excluded from the denominator. Turning this on adds rows to the scored population, so the
number will change. Report before-and-after, both labelled.

---

## 11. Corpus evidence — measured, not asserted

Method: `pipelines/plan_reader/csi_v2.db` (167 MB, iCloud symlink), table `materials`, filtered
`crosswalk_version = 2` — 6,385 rows, **66 distinct plans**. Depth detected with
`(\d+(\.\d+)?)\s*("|”|INCH(ES)?)`, case-insensitive, over `raw_description`.

**Noise filter, and it is load-bearing.** 175 rows carry a quantity above 10⁹ and are plan-sheet
legend text parsed as bid items (e.g. a scale bar, a scope-of-work callout). All measurements below
exclude rows with `len(description) > 90` **or** `quantity > 10⁸`. Unfiltered, the whole-corpus
"quantity-weighted" rate is meaningless — it reported 0.1%, driven entirely by a `3.38e13` row whose
"quantity" is an AIP project number. Reported so the filter is a stated decision, not a hidden one.

### 11.1 Depth availability — the headline is that it is not the binding constraint

| Category | Clean rows | In TON already (no conversion needed) | In SY/CY (conversion candidates) | Of those, depth stated |
|---|---:|---:|---:|---|
| `hma` | 177 | 71 | 19 | **15 / 19 = 78.9%** |
| `base` | 94 | 41 | 33 | 6 / 33 = 18.2% |
| `surfacing` | 38 | 24 | 4 | 1 / 4 = 25.0% |

Those headline rates **understate the real availability badly**, and the raw lines say why.

**`hma`, SY: the 4 without a depth are not placed mix at all.** They are
`Remove and Dispose of Bituminous Pavement` (a removal), `FULL DEPTH BITUMINOUS RECLAMATION` (FDR),
`BITUMINOUS SEAL COAT` (a seal coat, MN 2356 / ND §420 — not mix), and
`BITUMINOUS BASE PATCH SPECIAL`. The first three are **mis-categorised into `hma` by the bare
`BITUMINOUS` keyword** — the same defect family as `2026-08-10-spec-books-tier1.md` C5. They are
reported here as a finding, not fixed (the crosswalk is not this task's file).

> **Excluding those three: depth is stated on 15 of 16 genuine placed-mix SY rows = 93.8%.**
> The one genuine miss is `BITUMINOUS BASE PATCH SPECIAL | 2,500 | SY`, which correctly surfaces
> with `depth_not_stated`.

**`base`, CY: depth availability is irrelevant.** 17 of the 33 candidates are CY, and F2 needs no
depth. Of the remaining 16 SY rows, **11 are `FULL DEPTH RECLAMATION`** — which ruling #9 excludes
from this layer entirely (§7). Two more are salvage/relay (`REMOVE AND RELAY SALVAGED BASE COURSE`,
`Remove And Relay Blended Base Course`) — removals, not purchased material. The genuinely
placed-base SY rows are `STABILIZED BASE COURSE - 6" DEPTH` and `- 8" DEPTH` (both depth-stated) and
`CEMENT STABILIZED BASE COURSE` (no depth), none of which is in the blessed table anyway.

> **Correctly scoped — placed base only, after removing FDR and salvage — the CY rows need no depth
> and every remaining depth-relevant SY row but one states it.**

**`surfacing`, 4 candidates:** three CY (no depth needed), one SY
(`8" Class 5 Alley & Shouldering Aggregate Surfacing (CV) (P)` — depth stated). **4/4 convertible on
geometry**, though only the Class 5 rows are class-blessed.

### 11.2 How much of the corpus this layer even touches

**Most of the corpus already states tons.** `hma` 71/177 TON, `base` 41/94, `surfacing` 24/38. This
layer is a **minority-case fix with a large per-plan effect**, not a corpus-wide re-computation. On
9786015 the effect is total: every asphalt and base line is off-unit, so the two buckets go from
null to 1,901 t and 3,852 t.

### 11.3 The removal comparison, and the correction it forces

**21 of 79 clean `milling` rows state a depth (26.6%)** — `MILL BITUMINOUS SURFACE (2.0")`,
`Mill Bituminous Surfacing 1.5" (P)` (168,834 SY), `MILL BITUMINOUS SURFACE (4.0")`, and so on.

**So `schema.py`'s "no verified depth … exists" is not literally true for milling either.** The
correct statement — and the one this spec relies on — is:

> Depth is often available on removals. **Conversion is refused on removals because CSI ruled the
> bucket and the unit (§7), and because no removal *density* factor has been verified.** Those are
> two separate reasons and neither is "the depth is unknown."

This spec does not edit that text (`schema.py` is another agent's file this round). Flagged as a
wording correction for whoever owns it next: the sentence is currently right by accident.

---

## 12. Why the two other factors in this repo are NOT interchangeable with §3.1

Both exist, both are tempting, and **neither may be substituted for F1/F2/F3 or "harmonised" with
them.** This section exists so that a future reader who finds three ton-per-CY numbers in one repo
does not average them.

| | **F2 (this spec)** | `bucket_hierarchy.csv` **1.75 Ton/CY** | SDDOT §270.4 **1.50 tons/CY** |
|---|---|---|---|
| Material | **Class 5 aggregate base**, purchased and placed | **Removed pavement/base** — demolition debris | **Salvaged granular material**, in a stockpile |
| Direction of work | placed | removed | salvaged and stockpiled |
| State | MN (and the MN/ND/SD Class 5 family, pending §3.1) | ND (a Dunn plan sheet) | **SD only** |
| Provenance | proposed by the owner; **awaiting Alex** | **unverified** — a plan-sheet number, never checked against a plan | **published state spec**, SD pdf p.153, citable |
| Where it belongs | `hot_mix_tons` / `base_tons` / `shoulder_tons` | `removal_tons`, a bucket that **exists in the CSV and is implemented nowhere** | SD salvaged-material measurement, under 5,000 tons |
| In this spec | **is the spec** | **not used** | **not used** |

**Why the differences are load-bearing and not pedantic:**

1. **Placed ≠ removed.** F2's 3,100 lb/CY is *compacted in place* — the `(CV)` stamp on every
   9786015 aggregate line is that basis stated contractually. 1.75 Ton/CY = 3,500 lb/CY describes
   *broken-out debris*. They cannot both be right about the same cubic yard, and they are not
   describing the same cubic yard. A 13% error applied to the wrong bucket, with no signal.
2. **Different state, different material, different measurement point.** SDDOT's 1.50 is *salvaged
   granular material measured in a stockpile*, capped at 5,000 tons, in SD. Applying it to a
   Minnesota purchased-Class-5 line is three substitutions at once, each individually wrong.
3. **Different provenance means different authority.** SDDOT's 1.50 is citable to a page. The 1.75
   is a number somebody typed. F1/F2 will be a factor Alex signed. Merging a citable factor, an
   unsourced factor and a client-signed factor into one table destroys the only property that makes
   any of them usable — knowing who is accountable for the number.
4. **`milling-unit-capture` §2 and §7.1, and `spec-books-tier1` "Two facts", already ruled on
   exactly this** and used the same words: *different material, different state, different
   provenance. Do not substitute one for the other.* This is the third document to say it. If a
   fourth is needed, something has gone wrong upstream of the documents.

**If a removal conversion is ever wanted, it is a separate blessed row with its own signature**, not
an extension of F2 and not a promotion of the 1.75.

---

## 13. Open, and deliberately not decided here

1. **The factors themselves.** F1 and F2 have no external citation in this repo. They reproduce
   CSI's numbers to five significant figures, which is strong evidence they are the factors CSI
   *used* — it is not evidence they are the factors CSI *endorses going forward*. G1 needs Alex.
2. **`(LV)` loose-volume lines.** §3.2. No factor proposed.
3. **Which states F1 covers.** The 113 lb/SY-in reproduces on an MN `Type SP` plan. Whether it
   applies unchanged to ND `Superpave FAA 43` and SD `Asphalt Concrete` is **untested** — the corpus
   has ND SY rows (`Superpave FAA 43 - 3" / 4" / 5"`) but no CSI oracle behind them. Recommend F1
   be blessed **per state or explicitly as all-three**, and that the table carry a `states` column
   so a silent cross-state application is impossible.
4. **Aggregate Surfacing's bucket.** §8. Untouched.
5. **Whether converted tons reach `scratch.bid_projects`.** Storing them needs new columns and
   therefore DDL, which is out of scope. Until then a converted value reaches the report and **not**
   the database — same known gap shape as `milling-unit-capture` §5.3.
6. **The `hma` mis-categorisations found in §11.1** (`BITUMINOUS SEAL COAT`, `Remove and Dispose of
   Bituminous Pavement`, `FULL DEPTH BITUMINOUS RECLAMATION` all landing in `hma`). Reported, not
   fixed; `quantity_crosswalk.py` is not this task's file.
7. **`schema.py`'s "no verified depth or density factor exists" wording.** §11.3. Correct conclusion,
   wrong stated reason. Flagged for that file's owner.
