# State spec books — Tier 1 findings

Date: **2026-08-10** · Scope: **Tier 1 only** (targeted extraction of MEASUREMENT / BASIS OF PAYMENT
for the pay-item families that land in our buckets). Tier 2 — full indexing of ~3,000 pages into
Chroma — is **BACKLOG, not attempted**. See §9.

Sources (all three already in `pipelines/plan_reader/05_knowledge/`):

| State | File | PDF pages |
|---|---|---|
| MN | `2026-08-08-2025 MnDOT Standard Specifications for Construction-38774551-v3.pdf` | 1,081 |
| ND | `2026-08-08-2025 NDDOT Standard Specifications for Road and Bridge Construction.pdf` | 521 |
| SD | `2026-08-08-2025-sddot-specbook-final.pdf` | 596 |

Deliverable table: **`pipelines/plan_reader/05_knowledge/2026-08-10-spec_item_lookup.csv`** —
68 rows (MN 28 · ND 20 · SD 20). Every row carries a PDF page number.

Method: `pdftotext -layout` to text, page-indexed by form-feed, then targeted retrieval of the
`METHOD OF MEASUREMENT` / `BASIS OF PAYMENT` clause and its pay-item schedule for each family.
**Page numbers in the CSV are PDF pages** (what you type into a viewer's page box); the book's own
printed page number is in a separate `printed_page` column because the three books disagree on
offset (MN is −15, ND is −17, SD is 0).

**Every contradiction below was verified by actually running `quantity_crosswalk.map_line_v2()`
on the state's real item name, not by reading the keyword list.** Where a claim is inference from
the spec's structure rather than its words, it says so.

---

## The six questions

### Q1 — The state-naming crosswalk for hot mix

| State | Section | Pay item as the state writes it | Unit |
|---|---|---|---|
| MN | 2360 *Plant Mixed Asphalt Pavement* | `2360.509 Type SP__ __ Course Mixture (traffic, binder)` | ton |
| MN | 2360 | `2360.504 Type SP__ __ Course Mixture` | **square yard** |
| MN | 2360 | `2360.509 Type SP__ Bituminous Mixture for Specified Purpose` | ton |
| MN | 2360 | `2360.509 Type SP__ Bituminous Mixture Production` | ton (FOB Dept trucks) |
| ND | 430 *Hot Mix Asphalt (HMA)* | `Superpave, FAA __` | Ton |
| ND | 430 | `RAP Superpave, FAA __` | Ton |
| ND | 430 | `Patching` | Ton |
| SD | 320 *Asphalt Concrete, General* (+321/322/324/325/326) | `Asphalt Concrete` (Class D/E/G/Q/S/HR) | Ton |
| SD | 324 | `Asphalt Concrete Composite` | Ton |

The load-bearing fact for the Dunn bug: **NDDOT's section is *titled* "HOT MIX ASPHALT (HMA)" but
the word "HMA" never appears in a pay item.** The pay item is `Superpave, FAA __`
(ND pdf p.239, printed 222). A prompt asking for "Total tons of hot mix asphalt (HMA)" is asking
for a string that is not on an ND bid schedule. Same shape in SD: 320.1 says the section covers
"all types of hot mixed asphalt pavements", and the pay item is `Asphalt Concrete`.

MN is the one state where the word "Bituminous" appears in some hot-mix item names but **not** in
the most common one — `Type SP 12.5 Wearing Course Mixture (3,C)` contains neither "BITUMINOUS" nor
"HMA". It is matched today only by the `TYPE SP` keyword.

`quantity_crosswalk.py` already handles all three vocabularies (`SUPERPAVE`, `TYPE SP`,
`ASPHALT CONCRETE`) — **verified by running it.** The gap is in the *live* path's prose field
descriptions (`01_pipeline/schema.py`), which is where the 605× under-report happened. That file is
out of scope for this task per the working rules; the vocabulary it needs is the table above.

### Q2 — Full Depth Reclamation: does the spec agree with CSI?

**Yes, on both counts, in two states independently.**

*Category — the spec puts FDR under BASE, not removal:*
- **MN**: §2215 *Reclamation* sits in the book's **Base Construction** division (TOC, MN pdf p.9),
  between `2212 Drainable Aggregate Base` and `2221 Shoulder Base Aggregate`. The removals section,
  `2104 Removing Pavement and Miscellaneous Structures`, is in the **Grading** division (MN pdf p.8).
- **SD**: §280 *Full Depth Reclamation (FDR)* sits inside **PART B GRANULAR BASES AND SURFACING**
  (SD pdf p.148–155). **PART C ASPHALT CONSTRUCTION** does not begin until SD pdf p.156.

*Unit — the spec measures FDR in square yards, explicitly:*
- MN 2215.4 (pdf p.190): *"Measure the Full depth reclamation by the square yard."* Pay items
  `2215.504 Full Depth Reclamation` and `2215.504 Stabilized Full Depth Reclamation`, square yard
  (pdf p.191).
- SD 280.4 (pdf p.155): *"FDR will be measured to the nearest square yard. Plans quantity will be
  the basis of payment."*

So CSI's ruling — *base work whose quantity stays in `milling_sy`* — is exactly what both books say.
The unit is not a compromise; it is the contractual unit.

**ND does not have an FDR pay item.** Two verification methods, both named:
(1) the book's own section list (ND pdf p.9) runs `302 Aggregate Base and Surface Course` →
`401 Prime, Tack, or Fog Coat` → `411 Milling Pavement Surface` → `420 Bituminous Seal Coat`, with
no reclamation section anywhere in the 200/300/400 series;
(2) a case-insensitive full-text search of the extracted book for `full depth reclamation` returns
**0 hits** (the same search returns 10 in MN and 2 in SD). The only ND hit for "reclaim" is
`153.01 RECLAIMER`, an *equipment* specification, and pit-restoration language in §106.

Related: MN's `2215.509 Aggregate Base` (ton) is the **additional imported aggregate** placed with
the reclamation. It carries the identical item *name* as `2211.509 Aggregate Base`. Item name alone
cannot tell you which section a line came from.

### Q3 — Does ND measure milling in tons?

**Yes, and the book says so in the pay-item table itself.**

> ND §411.06 BASIS OF PAYMENT (pdf p.210, printed 193)
> `Milling Pavement Surface` — Pay Unit: **`Ton or Square Yard`**

§411.05 deliberately does **not** fix a unit: *"The Engineer will measure, as specified in Section
109.01, Measurement of Quantities"* — the unit is whatever the contract's bid schedule says. That
is a spec that permits both, not one that prefers SY. Section number: **411**. Item name:
`Milling Pavement Surface` (matched today by the `MILLING PAVEMENT` keyword).

Contrast: MN 2232.4 is unambiguous — *"measure pavement milling by the AREA of each type of surface
removed"*, pay items `2232.504 Mill Bituminous Surface (__")` / `Mill Concrete Surface (__")`,
square yard only. SD 332 is square yard only *and* is not field-measured at all — 332.4 says
**"will not be measured. Plans quantity will be used."**

### Q4 — Do ND and SD use MnDOT's 2xxx numbering?

**No. Three different schemes. A spec-item lookup must be keyed per state.**

| | MN | ND | SD |
|---|---|---|---|
| scheme | 4-digit section + 3-digit pay-item suffix | 3-digit section + 2-digit subsection | 3-digit section + subsection letter |
| hot mix | `2360.509` | `430.06` | `320.5 B` |
| aggregate base | `2211.509` | `302.06` | `260.5` |
| milling | `2232.504` | `411.06` | `332.5 B` |
| excavation | `2106.507` | `203.06` | `120.5 A.1` |
| removals | `2104.504` | `202.06` | `110.5` |

Worse than "different numbers": **only MnDOT has a pay-item number at all.** The `.504/.507/.509`
suffix *encodes the unit* (`.504` = square yard, `.507` = cubic yard, `.509` = ton, `.503` = linear
foot, `.506` = gallon, `.508` = pound, `.502` = each, `.501` = lump sum, `.518` = square foot —
read off the MN schedules across pdf pp.158, 168, 174, 183, 191, 195, 282, 283, 329). ND and SD
publish a **name → pay unit table** with no item number; the number in the CSV's `item_number`
column for ND/SD is the *basis-of-payment clause*, which is the closest stable identifier the books
offer.

Practical consequence: `SPEC_MAP` contains the numeric keywords `2211`, `2112`, `2118`, `2360`.
Those can only ever fire on a Minnesota plan. They are inert on 35.8% of CSI's bidding (ND) and on
every SD plan.

### Q5 — Aggregate Surfacing Class 1/5/Special and Aggregate Base CL 5/6/13

**MN — the class number tells you nothing; the section number tells you everything.** §3138.1
(pdf p.859) states its scope in one sentence: *"This Specification lists the quality requirements
for Aggregates used for 2118 Aggregate Surfacing, 2211 Aggregate Base, and 2221 Shoulder Base
Aggregate."* One class table (Classes 1–6, Table 3138.2-1) serves all three. A "Class 5" is a
Class 5 whether it is going under the mainline or on the shoulder. What separates them:

| item | section | division in the book | our bucket |
|---|---|---|---|
| `Aggregate Surfacing, Class __` | 2118 | Grading | `shoulder_tons` |
| `Aggregate Base Class __` | 2211 | Base Construction | `base_tons` |
| `Shoulder Base Aggregate Class __` | 2221 | Base Construction | `shoulder_tons` |

Class-specific facts worth knowing: only Classes 5 and 6 carry a **minimum crushing requirement**
(25% / 30%) — Classes 1–4 have none. Surfacing aggregate (3138.2D) additionally must be 100%
passing 3/4 inch *regardless of the class specified*, may not contain glass, and needs PI 5–12.
So "Class 5 Aggregate Surfacing" and "Class 5 Aggregate Base" are physically different products
under the same class number.

**ND — same conclusion, different table.** Classes are 2, 3, 3M, 4, 5, 7, 8, 13 (Table 816-01,
ND pdf p.434). `Aggregate Base Course Cl__` and `Aggregate Surface Course Cl__` are both §302 and
both `Ton or Cubic Yard` (pdf p.205) — the only discriminator is the word **Base** vs **Surface**
in the item name. Cl 13 is the common ND base class; Cl 5 is what Traffic Service Aggregate must
meet (§302.03).

**SD — the item name is the discriminator and it is *not* a class number.** §882 Table 1
(pdf p.531) gives separate gradation columns for `Subbase`, `Gravel Cushion`, `Base Course`,
`Base Course` and `Gravel Cushion` in their *limestone ledge rock* variants, `Gravel Surfacing`,
`Pit Run` and `Granular Bridge End Backfill`. Gravel Surfacing is genuinely a different material — PI **4–12**
where Base Course is **0–6**, and 100% passing 3/4 inch. All are paid per ton under §260.5.

I found **no "Special" class** in any of the three books. Two verification methods, both named:
(1) full-text search for `Class Special` / `Cl Special` / `Special Class` across all three extracted
books returned nothing in an aggregate context; (2) the three class tables themselves (MN Table
3138.2-1 pdf p.860, ND Table 816-01 pdf p.434, SD §882 Table 1 pdf p.531) enumerate their classes
exhaustively and none includes a "Special". If "Aggregate Surfacing Special" appears in our corpus
it is a **plan-specific special provision**, not a standard-spec class — which means the spec books
cannot resolve it and the plan set has to.

### Q6 — PG binder, tack, prime: is counting binder tons a double count?

**Yes for mass in all three states — but only ND and SD actually expose the trap, and they expose
it differently.**

The mix ton always includes the binder. All three books say so in their measurement clause:

- MN 2360.5 (pdf p.321): *"The Contract Unit Price for asphalt mixture used in each course includes
  the cost of constructing the asphalt surfacing and **providing and incorporating asphalt binder,
  mineral filler, and hydrated lime**."* And 2360.4: *"The Engineer will not make deductions for the
  asphalt Materials."*
- ND 430.05A (pdf p.239): *"...the tonnage of bituminous mix used in the accepted pavement and will
  **make no deduction for the weight of asphalt cement** used in the mixture."*
- SD 320.4B (pdf p.168): *"The mixture of mineral aggregate, asphalt binder, and hydrated lime...
  will be weighed after mixing. **No deduction will be made for the weight of the asphalt binder**
  or hydrated lime."*

Where they differ is whether the binder is *also* a separate ton item:

| State | separate binder pay item? | unit | double-count risk |
|---|---|---|---|
| MN | **No** — 2360's schedule lists mixture items only | — | none |
| MN tack / prime | yes (`2357.506` / `2358.506`) | **gallon** | none — cannot enter a TON bucket |
| ND | **Yes** — `__ Asphalt Cement` | **Ton** or Gallon | **real** |
| ND tack / prime | yes (`Tack Coat` / `Prime Coat`, §401.06) | **gallon** | none |
| SD | **Yes** — `Asphalt Binder` (320.5 A) and `Hydrated Lime` (320.5 E) | **Ton** | **real** |
| SD tack / prime / fog / flush | yes — item is named simply `Asphalt` (330.5 A) | **Ton** | **real** |

SD is the sharpest case: §330 measures prime, tack, fog seal and flush seal asphalt **by the ton**,
under a pay item literally called `Asphalt`. That is a ton of asphalt that is not mix.

Current behaviour, verified by running the crosswalk on the real names:

```
'PG 58-28 Asphalt Cement'  TON -> bucket=None  cat=other  (untracked_category)
'Asphalt Binder'           TON -> bucket=None  cat=other  (never_matched)
'Hydrated Lime'            TON -> bucket=None  cat=other  (never_matched)
'Asphalt'                  TON -> bucket=None  cat=other  (never_matched)
```

All four correctly stay out of `hot_mix_tons`. **Three of the four do so by accident** — nothing in
`SPEC_MAP` names them; they fall through to `other` with `never_matched`, which is the crosswalk's
signal for *"we failed to read this"*, not *"we deliberately excluded it"*. That is the exact
failure/empty-answer collapse the working rules forbid. Only ND's Asphalt Cement is handled on
purpose, by the deliberate `("ASPHALT CEMENT", "other")` rule at the top of `SPEC_MAP`.

**The one item where the answer flips: SD `Asphalt Concrete Composite` (324.5, pdf p.192).** Its
basis of payment explicitly bundles *"mineral aggregate, asphalt binder, asphalt for tack SS-1h or
CSS-1h, asphalt for flush seal, sand for flush seal, and when required asphalt for prime MC-70,
blotting sand for prime, hydrated lime"* into the one ton price. On a composite job a separate
binder line **should not exist**; if one appears it is either a different scope or a bid-schedule
error worth flagging to an estimator.

`bucket_hierarchy.csv` already says `hot_mix_tons` = *"placed hot mix only; tack/prime/binder
excluded"*. The spec books confirm that is the right policy in all three states.

---

## Contradictions with our current keyword mapping

All verified by running `quantity_crosswalk.map_line_v2()` on the state's own item name.
`quantity_crosswalk.py` was **not modified** — this section is a report, per the task's scope.

### C1 — ND `Aggregate Surface Course Cl 13` lands in `base_tons`, not `shoulder_tons`

```
'Aggregate Surface Course Cl 13'  TON -> bucket=base_tons  cat=base
```
`AGGREGATE SURFACING` (the surfacing keyword) does not match `Aggregate Surface Course`, and
`CL 13` → base fires first. **ND surfacing tonnage is currently counted as base tonnage.** Spec
basis: §302.06, ND pdf p.205 — the two are distinct pay items.

### C2 — `Haul Full Depth Reclamation (LV)` puts CUBIC YARDS into `milling_sy`

```
'Haul Full Depth Reclamation (LV)'  CY -> bucket=milling_sy  cat=base
```
The FDR ruling's `bucket_override` deliberately ignores the unit (that is what makes the SY case
work), but it also fires on MN's `2215.507 Haul Full Depth Reclamation (LV)`, which is a **cubic
yard haul item**, not reclaimed area. `unit_matches_bucket` goes False and flags it, but the
quantity still sums into an SY total. Spec basis: MN 2215.5 schedule, pdf p.191.

### C3 — SD `Subbase` and `Gravel Cushion` match nothing at all

```
'Subbase'        TON -> bucket=None  cat=other  gap=never_matched
'Gravel Cushion' TON -> bucket=None  cat=other  gap=never_matched
```
Both are §260.5 pay items, per ton, and Gravel Cushion is SD's standard granular layer under
asphalt (§882 Table 1 gives it its own gradation column). Neither word appears in `SPEC_MAP`.
**Real SD base tonnage counted nowhere, reported as a reader failure.** Spec basis: SD pdf p.151
(payment) and p.531 (material).

### C4 — MN `Mill Concrete Surface` matches nothing

```
'Mill Concrete Surface (2")'  SY -> bucket=None  cat=other  gap=never_matched
```
`MILL BITUMINOUS`, `MILLING ASPHALT` and `COLD MILLING` all miss it, and the bare `MILLING` keyword
needs the *-ing* form. It is a real MnDOT pay item — `2232.504`, square yard, same section and same
payment clause as `Mill Bituminous Surface` (MN pdf p.195).

### C5 — `Sawing Bituminous Pavement` is categorised as hot mix

```
'Sawing Bituminous Pavement'  LF -> bucket=None  cat=mixed  spec=hma
```
`BITUMINOUS` → hma fires before `SAWING` → milling ever gets a chance, so the `SAWING` keyword is
**dead for the item it was written for**. It is a linear-foot item so no quantity moves, but the
category is wrong twice: it is neither hot mix nor milling — it is `2104.503`, a removals item
(MN pdf p.158). Note `2104.5`: if the contract has no sawing pay item, the cost is folded into other
items, so a missing sawing line is not a missing scope.

### C6 — ND `Patching` matches nothing — and it is the item the Dunn bug returned

```
'Patching'  TON -> bucket=None  cat=other  gap=never_matched
```
`Patching` is a real §430.06 pay item, Ton (ND pdf p.239). This is the line the live path returned
200 tons from while missing the 121,221-ton Superpave line. MN's analogue,
`2231.509 Bituminous Patching Mixture`, *does* match (via `BITUMINOUS`) and lands in `hot_mix_tons` —
so the same work is bucketed inconsistently across states.

### C7 — ND `Remove & Salvage Base & Surfacing` (Ton) matches nothing

```
'Remove & Salvage Base & Surfacing'  TON -> bucket=None  cat=other  gap=never_matched
```
§202.06, ND pdf p.156. A removal bid **in tons** — precisely the `removal_tons` row that
`bucket_hierarchy.csv` describes and that no bucket rule implements. It is reported as a reader
failure rather than as a known unbucketed category.

### C8 — MnDOT's own item numbers encode the unit, and we ignore that

`.504` = square yard, `.507` = cubic yard, `.509` = ton (and `.501` LS, `.502` EA, `.503` LF,
`.506` gal, `.508` lb, `.518` SF). `SPEC_MAP` uses bare section numbers (`2211`, `2112`, `2118`,
`2360`) as keywords and throws the suffix away. A single MN item number is a category **and** a unit
in four characters — the most reliable signal available on an MN plan, currently unused.

### C9 — the numeric keywords are Minnesota-only

`2211`, `2112`, `2118`, `2360` cannot fire on an ND or SD plan (Q4). Half the corpus by bidding
volume gets no benefit from them.

### C10 — dead duplicate: `ASPHALT CEMENT` appears twice in `SPEC_MAP`

Line 39 maps it to `other` (correct — it is a binder, Q6); line 80 maps it to `hma`. First match
wins, so line 80 is unreachable. Verified: `'PG 58-28 Asphalt Cement'` returns `other`. Harmless
today, but it is a keyword that *says* the opposite of what the code does, sitting in the hot-mix
block where someone reordering the list would trip on it.

### C11 — `('base','CY')` and `('hma','SY')` have no bucket, and both are standard pay items

`2211.507 Aggregate Base (CV)/(LV)`, `2118.507`, `2221.507` (all cubic yard) and `2360.504` Type SP
Course Mixture (square yard) are all real MnDOT items with real bid quantities. Each returns
`bucket=None, gap=no_bucket_for_unit`. That is the *honest* answer — but on a plan bid in CV, the
`base_tons` total will read zero and look like a plan with no base.

### C12 — SD's `Select Subgrade Topping` is grading by keyword, imported material by spec

```
'Select Subgrade Topping'  CY -> bucket=grading_quantity  cat=grading
```
`SUBGRADE` → grading fires. §120.5 C (SD pdf p.137) defines it as work *"over and above that
normally required for embankment construction"* — i.e. imported granular material, closer to
MN's `Select Granular Embankment`. Probably right in a CY bucket; flagged because CSI has already
ruled `CEMENT STABILIZED SUBGRADE` **excluded**, and these two share a keyword.

### C13 — spec agreements worth recording (not contradictions)

- CSI's `TRAFFIC SERVICE AGGREGATE` → base: **spec agrees.** ND §302.03 defines it as 816 Class 5
  or §817, and its pay item is in the Aggregate Base and Surface Course section (pdf p.205).
  *Caveat:* §302.05 measures it **in the stockpile**, not as placed roadway material, and material
  picked up and reused is not measured at all.
- CSI's `GRAVEL SURFACING` → base: verified to reach `base_tons`.
- CSI's FDR ruling: **spec agrees on both category and unit** (Q2).

### C14 — one place where the spec disagrees with a CSI ruling

CSI ruled `REMOVE BITUMINOUS PAVEMENT` and `REMOVAL OF BITUMINOUS SURFACING` → **mill**. MnDOT puts
those under `2104 Removing Pavement and Miscellaneous Structures`, in the **Grading** division —
structurally separate from `2232 Mill Pavement Surface` in the **Base Construction** division. The
work is also different: 2104.5 pays for removing, hauling and *disposing*, and 2104.4A explicitly
refuses to classify thickness; 2232 pays for milling a stated depth and lets the contractor keep
the millings. This is a legitimate business ruling that overrides the spec — recorded here so it is
visible as a deliberate divergence rather than an unexamined one.

---

## Two facts the books gave us that we did not ask for

**A published SY↔CY conversion factor, from SDDOT.** §270.4 (SD pdf p.153): salvaged material under
5,000 tons *"may be measured in a stockpile and converted to tons using a factor of **1.50 tons per
cubic yard**"*, and material stockpiled for future use is measured that way unconditionally. This
is a real, citable, state-published factor for salvaged granular/asphalt material. It is **not** the
same thing as the unverified `1.75 Ton/CY` in `bucket_hierarchy.csv`, which is a Dunn plan-sheet
number for removed pavement — different material, different state, different provenance. Do not
substitute one for the other; do record that a citable factor now exists for one specific case.

**SD has no embankment pay item, by design.** §120.5 B (SD pdf p.137): *"Embankment will not be paid
for directly but will be subsidiary work pertaining to the several classes of excavation."* An SD
plan with no embankment line is **correct**, not under-read. Any coverage metric that treats a
missing embankment line as a gap will be permanently wrong on every SD plan.

Also worth flagging for anyone reading plan quantities as contractual: **SD 332.4 and SD 280.4 both
say the quantity is not field-measured — plan quantity IS the basis of payment** for cold milling
and for FDR. For those two items the bid-schedule number is not an estimate.

---

## Tier 2 — backlog, deliberately not started

Not done, and not started: indexing the ~2,200 pages of these three books into Chroma, extracting
the remaining sections (structures, drainage, traffic control, erosion, pavement marking, all of
Division III materials), or building a per-state item-number → category table covering every pay
item. Tier 1 targeted the families that move our buckets; the board's own framing is that 40.7% of
rows carry 83–99% of the quantity.

The concrete next step, if Tier 2 is ever picked up: the per-state keying decision is already
settled by Q4 — it must be three tables, not one, and for ND/SD the stable key is
`(section, item_name)`, not a number.

---

## What is in the CSV, and what a "missing" row means there

68 rows: MN 28 · ND 20 · SD 20. Columns:
`state, item_number, item_name, unit, spec_section, includes, excludes, source_pdf, page,
printed_page, measurement_page, measurement_clause, csi_bucket_expected, notes`.

Two distinctions the CSV keeps separate on purpose, per the working rules:

- An `excludes` cell reading **"no exclusions stated in 2211.5"** means the clause was read and it
  names no exclusions. It is a real answer.
- A section I could not locate is **not in the file at all**, and every such case is called out by
  name in this document with the two searches that failed (Q2's ND FDR, Q5's "Special" class).
  Absence from the CSV never means "the book is silent" — it means the row does not exist.

Every row has a `page`. No page, no row.
