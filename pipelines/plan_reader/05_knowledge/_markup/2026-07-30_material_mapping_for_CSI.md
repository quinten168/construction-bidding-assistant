# Material mapping — for review with CSI

Date: 2026-07-30
Supersedes: `2026-07-03_material_buckets_client_questions.md` (rev 3 — now grounded in a full-corpus test)

## What this is

We read every pay-item line out of the bid schedules in our 117-plan corpus (6,385 line items,
2,434 distinct item names across MN / ND / SD) and grouped them into **families**. Each family is
proposed to roll up into one of the six numbers CSI already tracks.

**Nothing here is switched on yet.** We are showing you the proposal before we wire it, because
about half of these families are judgment calls we should not be making on your behalf.

Two companion files:
- `2026-07-30_material_map_PROPOSED.csv` — one row per family, with blank `csi_answer` /
  `csi_notes` columns to mark up in the meeting.
- `2026-07-30_material_map_EVIDENCE.csv` — every distinct pay-item name behind every family, so
  nothing is a black box.

## Why we are redoing this

We tested against **Stearns County CP 073-123-025** (CR 123 resurfacing, let 08.28.25). The good
news: we pulled all **26 of 26** line items off the bid schedule correctly. The bad news: the
mapping put them in the wrong buckets.

| Pay item | Quantity | We reported it as | It should be |
|---|---|---|---|
| Mill Bituminous Surface (1.0" / 1.5" / 4.0") | **70,263 SY** | asphalt — then dropped | milling |
| Full Depth Reclamation | **70,167 SY** | unrecognized | *(open question, below)* |
| Remove Concrete Driveway Pavement | 44 SY | unrecognized | removal |
| Motor Grader / Truck / Loaders | hourly | unrecognized | equipment rental |

So the job reported **zero milling** on a project that is essentially all milling and reclaim, and
got labeled "HMA Overlay" instead of a mill/reclaim-and-pave. Corpus-wide the same fault strands
**1.6M SY of milling** and **1.2M SY of reclamation**.

The cause was that our matcher looked at the *material* word before the *action* word — so
"**MILL** BITUMINOUS surface" read as asphalt because it saw "bituminous". We have rebuilt it to
resolve the action first (mill / remove / salvage / place). That part is a straightforward fix.
What we cannot fix without you is the questions below.

---

## The six buckets

| Bucket | Your column | What we propose rolls into it |
|---|---|---|
| **ASPHALT** | MIX TN | Hot mix placed: Superpave FAA 42–45 and RAP Superpave (ND), Asphalt Concrete Pavement (SD), Type SP wearing / non-wearing course and spec 2360 (MN), plant mix surfacing |
| **BASE** | BASE TN | Aggregate base placed: Aggregate Base Course CL 5 / CL 13, Class 5 Aggregate Base, subbase course, spec 2211 |
| **SHOULDER** | SHLDR TN | Shoulder gravel and aggregate surfacing: Shoulder Base Aggregate CL 1, Aggregate Surfacing, gravel surfacing, spec 2118 |
| **GRADING** | GRADE CY | Earthwork: common / unclassified excavation, embankment, borrow, foundation fill, foreslope reshaping |
| **MILLING** | MILL SY | Surface removal: Mill Bituminous Surface (MN), Milling Pavement Surface (ND), Cold Milling Asphalt Concrete (SD), spec 2232 |
| **OTHER** | — | Not a CSI quantity — carried as a scope flag: traffic control, pavement marking, erosion & turf, structures (culvert, bridge, pipe, riprap), signing, guardrail, utilities, equipment rental, testing, mobilization |

Two notes on the sheet:
- **Crushing and stockpile are not extracted.** In your historical data those columns are filled on
  under 5% of rows, and our corpus found 1 plan with stockpile and 0 with crushing. We treat them as
  internal sourcing decisions rather than plan quantities. Say the word if that is wrong.
- **Riprap sits under structures, not asphalt.** It is quarried rock slope protection measured in
  CY/TON at culvert ends. Flagging it because it appeared on an early draft of the asphalt list.

---

## The open questions

Ordered by how much quantity rides on the answer.

### 1. Full Depth Reclamation — ~1,199,000 SY, 14 plans. Currently reported as zero.
FDR grinds the existing asphalt *and* the base underneath into a new base layer, then you pave over
it. It is measured in SY like milling, but it rebuilds the roadbed like grading.
**Is FDR your MILL SY number, your GRADE CY number, or does it need its own line?**
Same question for Stabilized FDR and for cold in-place recycling.

### 2. Milling is measured in TONS in North Dakota — 230,625 T.
MnDOT and SDDOT measure milling in SY; NDDOT's "Milling Pavement Surface" is priced by the ton.
Your MILL SY column cannot hold both. **Do you want a separate milling-tons line, or should we
convert?** If convert, what factor?

### 3. Topsoil — ~539,000 CY, 19 plans. Currently filed as erosion control, so invisible in GRADE CY.
Strip, salvage, borrow, and place topsoil are all large CY quantities.
**Is topsoil handling part of your grading number, or is it turf-establishment work you price
separately?**

### 4. Pavement removal → grading.
On the site visit Mark said removal tonnage does not count toward base, but pavement removal "is
considered grading work" and converts to cubic yards.
- **(a)** Confirm the rule applies only to *pavement and base* removal. Our corpus has 158 removal
  item types, and most of them are `REMOVE SILT FENCE`, `REMOVE SIGN`, `REMOVE PIPE` — applying the
  rule literally would dump fence removal into your earthwork number.
- **(b)** Is **1.75 Ton/CY** your standard factor (that is what the Dunn County plan sheet used), or
  does it vary by material?

### 5. Aggregate Surfacing — Class 1 vs Class 5 vs Special. ~67,000 T.
We currently put *all* aggregate surfacing into SHLDR TN.
**Is Class 5 surfacing really base material to you, with only Class 1 / Special being shoulder
gravel?**

### 6. Cement and soil stabilization — ~197,000 SY.
Cement Stabilized Base Course, Stabilized Subgrade, Cement Treated Subgrade. These are measured in
SY at a stated depth, not tons, so they cannot enter BASE TN as written.
**Do you self-perform stabilization? Do you want it as a quantity or as a scope flag?**

### 7. Salvaged / remove-and-relay base — ~83,000 SY plus 14,000 T.
The material is re-used, not purchased. **Does it count toward BASE TN because you still have to
move and place it, or is it excluded because you are not buying aggregate?**

### 8. PG binder, tack and prime coat — 56,029 T.
Priced as their own TON lines. We propose **excluding** them from MIX TN so mix tonnage is not
double-counted — the binder is already inside the mix. **Confirm?**

### 9. Asphalt patching — appears as both TON and SY.
**Does patch tonnage belong in MIX TN, or do you price patching separately from mainline paving?**

### 10. Seal coat / chip seal / blotter — ~37,700 SY plus 5,700 T.
**Is this work CSI bids? Does it belong in ASPHALT, or is it a different line of business?**

### 11. Rock, muck and shale excavation, undercutting — ~46,000 CY.
Priced well above common excavation. **Inside GRADE CY, or called out separately because they change
the price per yard?**

### 12. Concrete flatwork — curb & gutter, sidewalk, PCC.
**Does CSI ever self-perform any of it, or is it always subbed?** If always subbed we carry it as a
flag and never as a CSI quantity.

### 13. Smaller ones
- **Geotextile / geogrid / drainage fabric** (~266,000 SY) — propose flag only, never a tonnage. Is
  fabric a cost driver worth surfacing on the report?
- **Subgrade preparation** — measured three different ways (RDST road-stations in MN, SY in SD, CY
  in ND). Grading work, but not a cubic-yard quantity. Flag only, or convert?
- **Sawing** (LF) — propose incidental, flag only.
- **Clearing & grubbing** — flag, or part of grading?

---

## Two things we would like from you

1. **Where do you read quantities?** Some projects have a priced bid schedule in the proposal *and*
   quantity sheets in the plan set (Basis of Estimate / Estimate of Quantities). When the two
   disagree, which do you trust, and which do you read first?
2. **Does the letting agency change the vocabulary?** Do pay-item names shift between a state DOT
   job and a county / city / township / SAP-CSAH job, or does everyone in a state use that state's
   spec book?

## One thing we can do to make this permanent

MnDOT bid schedules carry a **Mat No.** column — the Stearns sheet lists `2232.504` for milling,
`2360.509` for hot mix, `2215.504` for reclamation, `2211.509` for base. That number is the DOT's
own published classification, and it does not care how the county spelled the item name. We
currently discard that column. Capturing it would let us map on the spec number first and fall back
to item names only for jobs that omit it — which would make this mapping far more durable than a
keyword list. Worth confirming that county and city lettings in your area do carry these numbers.
