# Material Roll-Up — Pre-Read (short version)
Quick calibration for the CSI bidding & estimating team  ·  July 30, 2026

## What we need from you

We read every priced line item off the bid schedules in 117 plans (MN / ND / SD) and sorted each material into the five quantity columns you already track. **We have not turned any of this on yet.** Tell us whether the roll-ups are right.

For each material: **Keep** it where we put it, **Move** it to another column, or **Drop** it if it should not be counted. Most-frequent materials first.

*This is the short version — one row per material, with the classes we saw listed beside it. The full version lists every class as its own line.*

## Why we are asking

On **Stearns County CP 073-123-025** we read all 26 line items correctly but put them in the wrong columns — 70,263 SY of milling counted as asphalt and then dropped, and 70,167 SY of reclamation not counted at all. The job reported **zero milling** on a job that is almost entirely milling and reclamation. Corpus-wide that is 1.6M SY of milling and 1.2M SY of reclamation uncounted. The mechanism is fixed; which column each material belongs in is your call.

**"Today"** is what the current system does with that material. *not counted* means the quantity is invisible on the report right now.

---

# Part 1 — What we ARE tracking

## `Mixed_tons` — Hot mix asphalt placed, in TONS.

| Ref | Material | Classes seen | Plans | States | Unit | Today | Quantity | Right column? |
|---|---|---|---|---|---|---|---|---|
| AS1 | **Type Sp Wear Course Mix** | Type Sp 9.5, Type Sp 12.5 | 22 | MN,XX | SY,TON | partly counted | 59,963 SY; 207,673 TON | ☐ Keep ☐ Move to ______ ☐ Drop |
| AS2 | **Superpave** | Faa 45, Faa 43, Faa 42 | 18 | ND | SY,TON | partly counted | 21,100 SY; 699,640 TON | ☐ Keep ☐ Move to ______ ☐ Drop |
| AS3 | **Type Sp Non-Wear Course Mix** | Type Sp 12.5, Type Sp 9.5 | 10 | MN | SY,TON | partly counted | 30,315 SY; 53,937 TON | ☐ Keep ☐ Move to ______ ☐ Drop |
| AS4 | **Asphalt Concrete Pavement** | — | 4 | SD | TON | Mixed_tons | 59,392 TON | ☐ Keep ☐ Move to ______ ☐ Drop |
| AS5 | **Type Sp Bituminous Wear Course** | Type Sp 12.5 | 2 | MN | TON | Mixed_tons | 86,816 TON | ☐ Keep ☐ Move to ______ ☐ Drop |
| AS6 | **Asphalt Concrete Composite** | Pg58 | 2 | SD | TON | Mixed_tons | 29,453 TON | ☐ Keep ☐ Move to ______ ☐ Drop |
| AS7 | **Patching** | — | 2 | ND | SY,TON | **not counted** | 7,200 SY; 200 TON | ☐ Keep ☐ Move to ______ ☐ Drop |

<sub>Plus 11 material(s) seen on only one plan: Plant Mix Surf, Type Sp Wear Course, Bituminous Base Patch Special, Type Sp Bit Mix For Tight Blade Leveling, Hot Mix Asphalt Pavement Ches Sddot Type 1, Hot Mix Asphalt Superpave - Base Course, Asphalt Patching - Hbp Aggregate, Commercial Mix Asphalt…</sub>

**Anything missing from `Mixed_tons`?**

| Material we did not list | Why it belongs here |
|---|---|
|  |  |

## `base_tons` — Aggregate base placed under the pavement, in TONS.

| Ref | Material | Classes seen | Plans | States | Unit | Today | Quantity | Right column? |
|---|---|---|---|---|---|---|---|---|
| BA1 | **Aggregate Base** | Cl 13, Cl 5, Cl 6 | 33 | MN,ND | CY,TON | partly counted | 17,660 CY; 793,771 TON | ☐ Keep ☐ Move to ______ ☐ Drop |
| BA2 | **Portland Cement** | — | 4 | ND,SD | TON | **not counted** | 13,322 TON | ☐ Keep ☐ Move to ______ ☐ Drop |
| BA3 | **Cement Stabilized Subgrade** | — | 2 | MN,ND | SY | **not counted** | 34,837 SY | ☐ Keep ☐ Move to ______ ☐ Drop |
| BA4 | **Base Course** | — | 2 | SD | TON | base_tons | 25,099 TON | ☐ Keep ☐ Move to ______ ☐ Drop |
| BA5 | **Salvaged Base Course** | — | 2 | ND,SD | TON | base_tons | 9,478 TON | ☐ Keep ☐ Move to ______ ☐ Drop |

<sub>Plus 14 material(s) seen on only one plan: Cement Stabilized Base Course, Stabilized Base Course, Remove And Relay Salvaged Base Course, Cement Stabilized Subgrade - Ch, Cement Treated Subgrade, Soil Stabilization Material, Salvage And Stockpile Asphalt Mix And Granular Base Material, Subbase Course…</sub>

**Anything missing from `base_tons`?**

| Material we did not list | Why it belongs here |
|---|---|
|  |  |

## `shldr_tons` — Shoulder gravel and aggregate surfacing, in TONS.

| Ref | Material | Classes seen | Plans | States | Unit | Today | Quantity | Right column? |
|---|---|---|---|---|---|---|---|---|
| SH1 | **Aggregate Surfacing** | Cl 5, Cl 1, Cl Special, Cl 2 | 18 | MN,XX | CY,TON | partly counted | 1,311 CY; 45,073 TON | ☐ Keep ☐ Move to ______ ☐ Drop |
| SH2 | **Aggregate Surface Course** | Cl 13 | 5 | ND | TON | base_tons | 1,360 TON | ☐ Keep ☐ Move to ______ ☐ Drop |
| SH3 | **Shoulder Base Aggregate** | Cl 1 | 3 | MN | TON | shldr_tons | 12,100 TON | ☐ Keep ☐ Move to ______ ☐ Drop |
| SH4 | **Gravel Surfacing** | — | 3 | SD | TON | shldr_tons | 1,340 TON | ☐ Keep ☐ Move to ______ ☐ Drop |
| SH5 | **Traffic Service Aggregate** | — | 2 | ND | TON | **not counted** | 1,313 TON | ☐ Keep ☐ Move to ______ ☐ Drop |

<sub>Plus 6 material(s) seen on only one plan: Graunular Material Furnish, Shot Rock, Access Gravel, Shoulder Gravel, Aggregate Suracing, Alley & Shouldering Aggregate Surfacing</sub>

**Anything missing from `shldr_tons`?**

| Material we did not list | Why it belongs here |
|---|---|
|  |  |

## `grading_yards` — Earthwork moved, in CUBIC YARDS.

| Ref | Material | Classes seen | Plans | States | Unit | Today | Quantity | Right column? |
|---|---|---|---|---|---|---|---|---|
| GR1 | **Common Excavation** | — | 30 | MN,ND,SD | CY | grading_yards | 1,099,104 CY | ☐ Keep ☐ Move to ______ ☐ Drop |
| GR2 | **Topsoil** | — | 12 | ND,SD | CY | **not counted** | 434,715 CY | ☐ Keep ☐ Move to ______ ☐ Drop |
| GR3 | **Subgrade Preparation** | — | 11 | MN,ND | SY | **not counted** | 52,544 SY | ☐ Keep ☐ Move to ______ ☐ Drop |
| GR4 | **Common Embankment** | — | 10 | MN,ND | CY | grading_yards | 466,553 CY | ☐ Keep ☐ Move to ______ ☐ Drop |
| GR5 | **Borrow-Excavation** | — | 10 | ND | CY | grading_yards | 323,910 CY | ☐ Keep ☐ Move to ______ ☐ Drop |
| GR6 | **Remove Bituminous Pavement** | — | 9 | MN,MT,XX | SY | **not counted** | 53,630 SY | ☐ Keep ☐ Move to ______ ☐ Drop |
| GR7 | **Common Topsoil Borrow** | — | 7 | MN,XX | CY,TON | **not counted** | 1,830 CY; 285 TON | ☐ Keep ☐ Move to ______ ☐ Drop |
| GR8 | **Removal Of Bituminous Surfacing** | — | 6 | ND | SY,TON | partly counted | 1,870 SY; 3,915 TON | ☐ Keep ☐ Move to ______ ☐ Drop |
| GR9 | **Unclassified Excavation** | — | 5 | ND,SD | CY | partly counted | 59,721 CY | ☐ Keep ☐ Move to ______ ☐ Drop |
| GR10 | **Select Granular Embankment** | — | 5 | MN | CY | grading_yards | 23,670 CY | ☐ Keep ☐ Move to ______ ☐ Drop |
| GR11 | **Common Excavation-Subcut** | — | 5 | ND | CY | grading_yards | 5,230 CY | ☐ Keep ☐ Move to ______ ☐ Drop |
| GR12 | **Removal Of Concrete** | — | 5 | ND,SD | SY | **not counted** | 1,902 SY | ☐ Keep ☐ Move to ______ ☐ Drop |
| GR13 | **Remove Concrete Driveway Pavement** | — | 5 | MN,XX | SY | **not counted** | 898 SY | ☐ Keep ☐ Move to ______ ☐ Drop |
| GR14 | **Common Excavation-Waste** | — | 3 | ND | CY | grading_yards | 28,546 CY | ☐ Keep ☐ Move to ______ ☐ Drop |
| GR15 | **Placing Topsoil** | — | 3 | SD | CY | **not counted** | 9,181 CY | ☐ Keep ☐ Move to ______ ☐ Drop |
| GR16 | **Foundation Fill** | — | 3 | ND | CY | **not counted** | 5,110 CY | ☐ Keep ☐ Move to ______ ☐ Drop |
| GR17 | **Topsoil-Imported** | — | 3 | ND | CY | **not counted** | 2,167 CY | ☐ Keep ☐ Move to ______ ☐ Drop |
| GR18 | **Subgrade Repair** | — | 3 | ND,SD | CY,SY | partly counted | 207 CY; 1,495 SY | ☐ Keep ☐ Move to ______ ☐ Drop |
| GR19 | **Remove Aggregate Base** | — | 2 | ND | TON | base_tons | 72,531 TON | ☐ Keep ☐ Move to ______ ☐ Drop |
| GR20 | **Topsoil-Borrow Area** | — | 2 | ND,SD | CY | **not counted** | 62,538 CY | ☐ Keep ☐ Move to ______ ☐ Drop |
| GR21 | **Contractor Furnished Borrow Excavation** | — | 2 | SD | CY | grading_yards | 2,600 CY | ☐ Keep ☐ Move to ______ ☐ Drop |
| GR22 | **Removal Of Pavement** | — | 2 | ND | TON | **not counted** | 2,494 TON | ☐ Keep ☐ Move to ______ ☐ Drop |
| GR23 | **Excavation - Subgrade** | — | 2 | MN | CY | partly counted | 1,888 CY | ☐ Keep ☐ Move to ______ ☐ Drop |
| GR24 | **Remove Bituminous Driveway Pavement** | — | 2 | MN | SY | **not counted** | 862 SY | ☐ Keep ☐ Move to ______ ☐ Drop |
| GR25 | **Structure Excavation Box Culvert** | — | 2 | SD | CY | **not counted** | 202 CY | ☐ Keep ☐ Move to ______ ☐ Drop |
| GR26 | **Remove Concrete Pavement** | — | 2 | MN | SY | **not counted** | 20 SY | ☐ Keep ☐ Move to ______ ☐ Drop |

<sub>Plus 24 material(s) seen on only one plan: Remove Aggregate Base & Surfacing, Granular Embankment, Excavation - Muck, Topsoil Stripping & Spreading, Remove & Salvage Topsoil, Topsoil Strip & Spread, Select Granular Borrow, Remove And Dispose Of Bituminous Pavement…</sub>

**Anything missing from `grading_yards`?**

| Material we did not list | Why it belongs here |
|---|---|
|  |  |

## `mill_sy` — Existing surface ground off, in SQUARE YARDS.

| Ref | Material | Classes seen | Plans | States | Unit | Today | Quantity | Right column? |
|---|---|---|---|---|---|---|---|---|
| MI1 | **Mill Bituminous Surface** | — | 15 | MN,XX | SY | **not counted** | 758,983 SY | ☐ Keep ☐ Move to ______ ☐ Drop |
| MI2 | **Full Depth Reclamation** | — | 13 | MN,ND,XX | SY | **not counted** | 1,166,396 SY | ☐ Keep ☐ Move to ______ ☐ Drop |
| MI3 | **Milling Pavement Surface** | — | 12 | ND | SY,TON | partly counted | 462,779 SY; 230,625 TON | ☐ Keep ☐ Move to ______ ☐ Drop |
| MI4 | **Cold Milling Asphalt Concrete** | — | 5 | SD | SY | mill_sy | 75,664 SY | ☐ Keep ☐ Move to ______ ☐ Drop |
| MI5 | **Mill Bituminous Surfacing** | — | 2 | MN | SY | **not counted** | 290,393 SY | ☐ Keep ☐ Move to ______ ☐ Drop |

<sub>Plus 6 material(s) seen on only one plan: Cold Recycled Plant Mix, Stabilized Full Depth Reclamation, Full Depth Bituminous Reclamation, Cold Milling, Recycling Agent Cir-Ee, Mill Transition Area</sub>

**Anything missing from `mill_sy`?**

| Material we did not list | Why it belongs here |
|---|---|
|  |  |

---

# Part 2 — What we are NOT tracking

Real pay items we read but do **not** roll into any of your five columns. We carry them as a yes/no flag instead. **Should any of these be counted?**

| Group | Plans | Example materials | Quantity ignored | Count it? |
|---|---|---|---|---|
| **Traffic control** | 63 | Traffic Control; Traffic Control Signs; Flagging | — | ☐ Keep as flag ☐ Count as ______ |
| **Mobilization & contract admin** | 59 | Mobilization; Contract Bond; Maint And Restoration Of Haul Roads | — | ☐ Keep as flag ☐ Count as ______ |
| **Erosion control & turf** | 48 | Silt Fence; Seeding; Storm Drain Inlet Protection | 164 CY; 226,424 SY; 202 TON | ☐ Keep as flag ☐ Count as ______ |
| **Structures (culvert, bridge, pipe, riprap)** | 40 | Rc Pipe Apron; Random Riprap Class Iii; Pipe Conc Reinf Cl Iii | 197,582 CY; 682 SY; 13,068 TON | ☐ Keep as flag ☐ Count as ______ |
| **Pavement marking** | 36 | Pvmt Mk Painted Line; Epoxy Pvmt Mk Line; Pvmt Mk Painted-Message | — | ☐ Keep as flag ☐ Count as ______ |
| **Binder & coatings (tack, prime, PG cement)** | 33 | Tack Coat; Pg 58H; Pg 58S | 56,029 TON | ☐ Keep as flag ☐ Count as ______ |
| **Removals that are not pavement or base** | 30 | Remove Fiber Rolls; Remove Silt Fence; Remove Pipe Culverts | 10 CY | ☐ Keep as flag ☐ Count as ______ |
| **Signing** | 28 | Delineator Drums; Object Markers - Culverts; Reset Sign Panel | — | ☐ Keep as flag ☐ Count as ______ |
| **Fabric, geogrid, geotextile** | 24 | Geosynthetic Material Type Rr; Geosynthetic Material Type G; Geosynthetic Material Type R1 | 266,118 SY | ☐ Keep as flag ☐ Count as ______ |
| **Testing & quality management** | 22 | Bituminous Laboratory; Hma - Bituminous Materials; E-Ticketing | 33,818 TON | ☐ Keep as flag ☐ Count as ______ |
| **Concrete flatwork (curb, gutter, sidewalk, PCC)** | 20 | Concrete Walk; Truncated Domes; Sidewalk Concrete | 2,186 SY | ☐ Keep as flag ☐ Count as ______ |
| **Sawing** | 17 | Sawing Bituminous Pavement; Sawing Bit Pavement; Sawing Concrete Pavement | — | ☐ Keep as flag ☐ Count as ______ |
| **Seal coat / chip seal / blotter** | 15 | Bituminous Seal Coat; Blotter Material Cl 44 | 37,712 SY; 5,700 TON | ☐ Keep as flag ☐ Count as ______ |
| **Utilities** | 14 | Hydrant; Gate Valve & Box; Connect To Existing Sanitary Sewer | — | ☐ Keep as flag ☐ Count as ______ |
| **Clearing & grubbing** | 12 | Grubbing; Clearing & Grubbing; Clearing | — | ☐ Keep as flag ☐ Count as ______ |
| **Guardrail** | 7 | Remove & Reset Guardrail; Remove Guardrail; Remove Guardrail - Plate Beam | — | ☐ Keep as flag ☐ Count as ______ |
| **Equipment rental (hourly)** | 6 | Motor Grader; Skid Loader; Sediment Removal Backhoe | — | ☐ Keep as flag ☐ Count as ______ |
| **Water & dust control** | 1 | Calcium Chloride Solution | — | ☐ Keep as flag ☐ Count as ______ |

- **Crushing and stockpile** are not extracted: filled on under 5% of your historical rows, and 1 of 117 plans had stockpile, 0 had crushing. Correct to treat as internal sourcing?
- **Riprap** sits under structures, not asphalt — quarried rock slope protection, CY/TON.

---

# Part 3 — Materials we could not place

The 15 most common of 45 priced materials we could not confidently assign. Most likely to be wrong, so worth your eyes.

| Material | Plans | States | Unit | Quantity | Which column? |
|---|---|---|---|---|---|
| Concrete Driveway Pavement | 6 | MN | SY | 1,631 SY | ☐ Mixed_tons ☐ base_tons ☐ shldr_tons ☐ grading_yards ☐ mill_sy ☐ Do not count |
| Penetrating Water Repellent Treatment | 2 | ND | SY | 1,524 SY | ☐ Mixed_tons ☐ base_tons ☐ shldr_tons ☐ grading_yards ☐ mill_sy ☐ Do not count |
| Reinforcement Fabric | 2 | SD | SY | 945 SY | ☐ Mixed_tons ☐ base_tons ☐ shldr_tons ☐ grading_yards ☐ mill_sy ☐ Do not count |
| Controlled Density Fill | 2 | SD | CY | 88 CY | ☐ Mixed_tons ☐ base_tons ☐ shldr_tons ☐ grading_yards ☐ mill_sy ☐ Do not count |
| Concrete Valley Gutter | 2 | MN | SY | 54 SY | ☐ Mixed_tons ☐ base_tons ☐ shldr_tons ☐ grading_yards ☐ mill_sy ☐ Do not count |
| Structural Concrete | 2 | MN,ND | CY | 37 CY | ☐ Mixed_tons ☐ base_tons ☐ shldr_tons ☐ grading_yards ☐ mill_sy ☐ Do not count |
| Non-Reinf Concrete Pvmt Cl Ae- Doweled | 1 | ND | SY | 11,285 SY | ☐ Mixed_tons ☐ base_tons ☐ shldr_tons ☐ grading_yards ☐ mill_sy ☐ Do not count |
| Concrete Penetrating Sealer | 1 | SD | SY | 1,506 SY | ☐ Mixed_tons ☐ base_tons ☐ shldr_tons ☐ grading_yards ☐ mill_sy ☐ Do not count |
| Concrete Median Paving | 1 | ND | SY | 1,088 SY | ☐ Mixed_tons ☐ base_tons ☐ shldr_tons ☐ grading_yards ☐ mill_sy ☐ Do not count |
| Salvage And Reuse Existing Aggregate | 1 | ND | CY | 1,000 CY | ☐ Mixed_tons ☐ base_tons ☐ shldr_tons ☐ grading_yards ☐ mill_sy ☐ Do not count |
| Non Reinf Concrete Pvmt Cl Ae-Doweled | 1 | ND | SY | 933 SY | ☐ Mixed_tons ☐ base_tons ☐ shldr_tons ☐ grading_yards ☐ mill_sy ☐ Do not count |
| Rapid Stabilization Method 4 | 1 | MN | SY | 780 SY | ☐ Mixed_tons ☐ base_tons ☐ shldr_tons ☐ grading_yards ☐ mill_sy ☐ Do not count |
| Clean Rock | 1 | ND | TON | 758 TON | ☐ Mixed_tons ☐ base_tons ☐ shldr_tons ☐ grading_yards ☐ mill_sy ☐ Do not count |
| Granular Bedding | 1 | MN | CY | 700 CY | ☐ Mixed_tons ☐ base_tons ☐ shldr_tons ☐ grading_yards ☐ mill_sy ☐ Do not count |
| Full Depth Bituminous Street Repair | 1 | XX | SY | 478 SY | ☐ Mixed_tons ☐ base_tons ☐ shldr_tons ☐ grading_yards ☐ mill_sy ☐ Do not count |

---

# The judgment calls we could not make for you

1. **Full Depth Reclamation — 1,166,000 SY, 14 plans, currently counted as nothing.** FDR grinds the asphalt and the base below it into a new base layer. Is that `mill_sy`, is it `grading_yards` because you are rebuilding the roadbed, or does it need its own column?
2. **Milling is measured in TONS in North Dakota — 230,625 T.** MN and SD measure it in SY. `mill_sy` cannot hold both. Separate tons line, or a conversion?
3. **Topsoil — 539,000 CY.** Currently filed as erosion control, so it never reaches `grading_yards`. Is topsoil part of your grading number?
4. **Pavement removal.** Mark said it "is considered grading work" and converts to CY. (a) Only pavement and base removal, not remove-silt-fence / sign / pipe? (b) Is 1.75 Ton/CY your standard factor?
5. **Aggregate Surfacing Class 1 vs Class 5 vs Special — 67,000 T.** We put all of it in `shldr_tons`. Is Class 5 really base material to you?
6. **Salvaged / remove-and-relay base.** Re-used, not bought. Does it count toward `base_tons` because you still move and place it?
7. **PG binder, tack and prime — 56,029 T.** We propose excluding these from `Mixed_tons` so mix tonnage is not double-counted. Confirm?
