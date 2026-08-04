# Material Mapping for CSI review
Proposed roll-up of plan materials into your quantity columns  ·  v3  ·  August 3, 2026

## What this is

This is **the mapping we intend to use**. We read every priced line item off the bid schedules in the plans we have processed and assigned each material to one of your six buckets. **If there are no objections, we will use this.**

Mark any row you disagree with: **Move** it to a different bucket, or **Do not count** it if it should not be counted at all. Most-frequent materials first.

**In the Word version every checkbox is clickable.** Open it in Word and click the boxes; you do not need to print it. The blanks and the empty tables are typed into the same way.

Based on **66 plans** with a priced bid schedule (MN / ND / SD).

## The six buckets

| Bucket | What goes in it |
|---|---|
| `Mixed_tons` | Hot mix asphalt placed, TONS |
| `base_tons` | Aggregate base placed under the pavement, TONS |
| `shldr_tons` | Shoulder gravel and aggregate surfacing, TONS |
| `grading_yards` | Earthwork moved, CUBIC YARDS |
| `mill_sy` | Existing surface ground off, SQUARE YARDS |
| `other` | Real work, but not one of your five quantities. Carried as a scope flag |

---

# The mapping

## `Mixed_tons`: Hot mix asphalt placed, in TONS.

| Ref | Material | Classes seen | Plans | States | Unit | Change | Object? |
|---|---|---|---|---|---|---|---|
| AS1 | **Type Sp Wear Course Mix** | Type SP 9.5, Type SP 12.5 | 22 | MN,XX | SY,TON | **partly NEW** | ☐ Agree ☐ Move to ______ ☐ Do not count |
| AS2 | **Superpave** | FAA 45, FAA 43, FAA 42, RAP | 18 | ND | SY,TON | **partly NEW** | ☐ Agree ☐ Move to ______ ☐ Do not count |
| AS3 | **Type Sp Non-Wear Course Mix** | Type SP 12.5, Type SP 9.5 | 10 | MN | SY,TON | **partly NEW** | ☐ Agree ☐ Move to ______ ☐ Do not count |
| AS4 | **Asphalt Concrete Pavement** |  | 4 | SD | TON | no change | ☐ Agree ☐ Move to ______ ☐ Do not count |
| AS5 | **Type Sp Bituminous Wear Course** | Type SP 12.5 | 2 | MN | TON | no change | ☐ Agree ☐ Move to ______ ☐ Do not count |
| AS6 | **Asphalt Concrete Composite** | PG 58 | 2 | SD | TON | no change | ☐ Agree ☐ Move to ______ ☐ Do not count |
| AS7 | **Patching** |  | 2 | ND | SY,TON | **NEW, not counted today** | ☐ Agree ☐ Move to ______ ☐ Do not count |

> **One to confirm: riprap. Riprap is quarried rock slope protection, placed at culvert ends and on slopes and measured in CY or TON. We do NOT count it as asphalt and it does not reach Mixed_tons; we carry it under structures as a scope flag. An early draft of our asphalt list had it in the wrong place, so we want this one confirmed rather than assumed.**  ☐ Agree, riprap is not asphalt ☐ No, count riprap in Mixed_tons

**Anything missing from `Mixed_tons`?**

| Material we did not list | Why it belongs here |
|---|---|
|  |  |

## `base_tons`: Aggregate base placed under the pavement, in TONS.

| Ref | Material | Classes seen | Plans | States | Unit | Change | Object? |
|---|---|---|---|---|---|---|---|
| BA1 | **Aggregate Base** | Cl 13, Cl 5, Cl 6 | 33 | MN,ND | CY,TON | **partly NEW** | ☐ Agree ☐ Move to ______ ☐ Do not count |
| BA2 | **Portland Cement** |  | 4 | ND,SD | TON | **NEW, not counted today** | ☐ Agree ☐ Move to ______ ☐ Do not count |
| BA3 | **Cement Stabilized Subgrade** |  | 2 | MN,ND | SY | **NEW, not counted today** | ☐ Agree ☐ Move to ______ ☐ Do not count |
| BA4 | **Base Course** |  | 2 | SD | TON | no change | ☐ Agree ☐ Move to ______ ☐ Do not count |
| BA5 | **Salvaged Base Course** |  | 2 | ND,SD | TON | no change | ☐ Agree ☐ Move to ______ ☐ Do not count |

**Anything missing from `base_tons`?**

| Material we did not list | Why it belongs here |
|---|---|
|  |  |

## `shldr_tons`: Shoulder gravel and aggregate surfacing, in TONS.

| Ref | Material | Classes seen | Plans | States | Unit | Change | Object? |
|---|---|---|---|---|---|---|---|
| SH1 | **Aggregate Surfacing** | Cl 5, SP Ecial, Cl 1, Cl Special, Cl 2 | 18 | MN,XX | CY,TON | **partly NEW** | ☐ Agree ☐ Move to ______ ☐ Do not count |
| SH2 | **Aggregate Surface Course** | Cl 13 | 5 | ND | TON | **MOVED from base_tons** | ☐ Agree ☐ Move to ______ ☐ Do not count |
| SH3 | **Shoulder Base Aggregate** | Cl 1 | 3 | MN | TON | no change | ☐ Agree ☐ Move to ______ ☐ Do not count |
| SH4 | **Gravel Surfacing** |  | 3 | SD | TON | no change | ☐ Agree ☐ Move to ______ ☐ Do not count |
| SH5 | **Traffic Service Aggregate** |  | 2 | ND | TON | **NEW, not counted today** | ☐ Agree ☐ Move to ______ ☐ Do not count |

**Anything missing from `shldr_tons`?**

| Material we did not list | Why it belongs here |
|---|---|
|  |  |

## `grading_yards`: Earthwork moved, in CUBIC YARDS.

| Ref | Material | Classes seen | Plans | States | Unit | Change | Object? |
|---|---|---|---|---|---|---|---|
| GR1 | **Common Excavation** |  | 30 | MN,ND,SD | CY | no change | ☐ Agree ☐ Move to ______ ☐ Do not count |
| GR2 | **Topsoil** |  | 12 | ND,SD | CY | **NEW, not counted today** | ☐ Agree ☐ Move to ______ ☐ Do not count |
| GR3 | **Subgrade Preparation** |  | 11 | MN,ND | SY | **NEW, not counted today** | ☐ Agree ☐ Move to ______ ☐ Do not count |
| GR4 | **Common Embankment** |  | 10 | MN,ND | CY | no change | ☐ Agree ☐ Move to ______ ☐ Do not count |
| GR5 | **Borrow-Excavation** |  | 10 | ND | CY | no change | ☐ Agree ☐ Move to ______ ☐ Do not count |
| GR6 | **Remove Bituminous Pavement** |  | 9 | MN,MT,XX | SY | **NEW, not counted today** | ☐ Agree ☐ Move to ______ ☐ Do not count |
| GR7 | **Common Topsoil Borrow** |  | 7 | MN,XX | CY,TON | **NEW, not counted today** | ☐ Agree ☐ Move to ______ ☐ Do not count |
| GR8 | **Removal Of Bituminous Surfacing** |  | 6 | ND | SY,TON | **MOVED from Mixed_tons** | ☐ Agree ☐ Move to ______ ☐ Do not count |
| GR9 | **Unclassified Excavation** |  | 5 | ND,SD | CY | **partly NEW** | ☐ Agree ☐ Move to ______ ☐ Do not count |
| GR10 | **Select Granular Embankment** |  | 5 | MN | CY | no change | ☐ Agree ☐ Move to ______ ☐ Do not count |
| GR11 | **Common Excavation-Subcut** |  | 5 | ND | CY | no change | ☐ Agree ☐ Move to ______ ☐ Do not count |
| GR12 | **Removal Of Concrete** |  | 5 | ND,SD | SY | **NEW, not counted today** | ☐ Agree ☐ Move to ______ ☐ Do not count |
| GR13 | **Remove Concrete Driveway Pavement** |  | 5 | MN,XX | SY | **NEW, not counted today** | ☐ Agree ☐ Move to ______ ☐ Do not count |
| GR14 | **Common Excavation-Waste** |  | 3 | ND | CY | no change | ☐ Agree ☐ Move to ______ ☐ Do not count |
| GR15 | **Placing Topsoil** |  | 3 | SD | CY | **NEW, not counted today** | ☐ Agree ☐ Move to ______ ☐ Do not count |
| GR16 | **Foundation Fill** |  | 3 | ND | CY | **NEW, not counted today** | ☐ Agree ☐ Move to ______ ☐ Do not count |
| GR17 | **Topsoil-Imported** |  | 3 | ND | CY | **NEW, not counted today** | ☐ Agree ☐ Move to ______ ☐ Do not count |
| GR18 | **Subgrade Repair** |  | 3 | ND,SD | CY,SY | **partly NEW** | ☐ Agree ☐ Move to ______ ☐ Do not count |
| GR19 | **Remove Aggregate Base** |  | 2 | ND | TON | **MOVED from base_tons** | ☐ Agree ☐ Move to ______ ☐ Do not count |
| GR20 | **Topsoil-Borrow Area** |  | 2 | ND,SD | CY | **NEW, not counted today** | ☐ Agree ☐ Move to ______ ☐ Do not count |
| GR21 | **Contractor Furnished Borrow Excavation** |  | 2 | SD | CY | no change | ☐ Agree ☐ Move to ______ ☐ Do not count |
| GR22 | **Removal Of Pavement** |  | 2 | ND | TON | **NEW, not counted today** | ☐ Agree ☐ Move to ______ ☐ Do not count |
| GR23 | **Excavation - Subgrade** |  | 2 | MN | CY | **partly NEW** | ☐ Agree ☐ Move to ______ ☐ Do not count |
| GR24 | **Remove Bituminous Driveway Pavement** |  | 2 | MN | SY | **NEW, not counted today** | ☐ Agree ☐ Move to ______ ☐ Do not count |
| GR25 | **Structure Excavation Box Culvert** |  | 2 | SD | CY | **NEW, not counted today** | ☐ Agree ☐ Move to ______ ☐ Do not count |
| GR26 | **Remove Concrete Pavement** |  | 2 | MN | SY | **NEW, not counted today** | ☐ Agree ☐ Move to ______ ☐ Do not count |

**Anything missing from `grading_yards`?**

| Material we did not list | Why it belongs here |
|---|---|
|  |  |

## `mill_sy`: Existing surface ground off, in SQUARE YARDS.

| Ref | Material | Classes seen | Plans | States | Unit | Change | Object? |
|---|---|---|---|---|---|---|---|
| MI1 | **Mill Bituminous Surface** |  | 15 | MN,XX | SY | **NEW, not counted today** | ☐ Agree ☐ Move to ______ ☐ Do not count |
| MI2 | **Full Depth Reclamation** |  | 13 | MN,ND,XX | SY | **NEW, not counted today** | ☐ Agree ☐ Move to ______ ☐ Do not count |
| MI3 | **Milling Pavement Surface** |  | 12 | ND | SY,TON | **partly NEW** | ☐ Agree ☐ Move to ______ ☐ Do not count |
| MI4 | **Cold Milling Asphalt Concrete** |  | 5 | SD | SY | no change | ☐ Agree ☐ Move to ______ ☐ Do not count |
| MI5 | **Mill Bituminous Surfacing** |  | 2 | MN | SY | **NEW, not counted today** | ☐ Agree ☐ Move to ______ ☐ Do not count |

**Anything missing from `mill_sy`?**

| Material we did not list | Why it belongs here |
|---|---|
|  |  |

---

## `other`: real work, not one of your five quantities

These are real pay items. They do not roll into a quantity column. We carry them as a yes/no scope flag on the report instead. **Object if any of these should be counted.**

| Group | Plans | Example materials | Object? |
|---|---|---|---|
| **Traffic control** | 63 | Traffic Control; Traffic Control Signs; Flagging | ☐ Agree, flag only ☐ Count as ______ |
| **Mobilization & contract admin** | 59 | Mobilization; Contract Bond; Maint And Restoration Of Haul Roads | ☐ Agree, flag only ☐ Count as ______ |
| **Erosion control & turf** | 48 | Silt Fence; Seeding; Storm Drain Inlet Protection | ☐ Agree, flag only ☐ Count as ______ |
| **Structures (culvert, bridge, pipe, riprap)** | 40 | Rc Pipe Apron; Random Riprap Class Iii; Pipe Conc Reinf Cl Iii | ☐ Agree, flag only ☐ Count as ______ |
| **Pavement marking** | 36 | Pvmt Mk Painted Line; Epoxy Pvmt Mk Line; Pvmt Mk Painted-Message | ☐ Agree, flag only ☐ Count as ______ |
| **Binder & coatings (tack, prime, PG cement)** | 33 | Tack Coat; Pg 58H; Pg 58S | ☐ Agree, flag only ☐ Count as ______ |
| **Removals that are not pavement or base** | 30 | Remove Fiber Rolls; Remove Silt Fence; Remove Pipe Culverts | ☐ Agree, flag only ☐ Count as ______ |
| **Signing** | 28 | Delineator Drums; Object Markers - Culverts; Reset Sign Panel | ☐ Agree, flag only ☐ Count as ______ |
| **Fabric, geogrid, geotextile** | 24 | Geosynthetic Material Type Rr; Geosynthetic Material Type G; Geosynthetic Material Type R1 | ☐ Agree, flag only ☐ Count as ______ |
| **Testing & quality management** | 22 | Bituminous Laboratory; Hma - Bituminous Materials; E-Ticketing | ☐ Agree, flag only ☐ Count as ______ |
| **Concrete flatwork (curb, gutter, sidewalk, PCC)** | 20 | Concrete Walk; Truncated Domes; Sidewalk Concrete | ☐ Agree, flag only ☐ Count as ______ |
| **Sawing** | 17 | Sawing Bituminous Pavement; Sawing Bit Pavement; Sawing Concrete Pavement | ☐ Agree, flag only ☐ Count as ______ |
| **Seal coat / chip seal / blotter** | 15 | Bituminous Seal Coat; Blotter Material Cl 44 | ☐ Agree, flag only ☐ Count as ______ |
| **Utilities** | 14 | Hydrant; Gate Valve & Box; Connect To Existing Sanitary Sewer | ☐ Agree, flag only ☐ Count as ______ |
| **Clearing & grubbing** | 12 | Grubbing; Clearing & Grubbing; Clearing | ☐ Agree, flag only ☐ Count as ______ |
| **Guardrail** | 7 | Remove & Reset Guardrail; Remove Guardrail; Remove Guardrail - Plate Beam | ☐ Agree, flag only ☐ Count as ______ |
| **Equipment rental (hourly)** | 6 | Motor Grader; Skid Loader; Sediment Removal Backhoe | ☐ Agree, flag only ☐ Count as ______ |
| **Water & dust control** | 1 | Calcium Chloride Solution | ☐ Agree, flag only ☐ Count as ______ |

- **Crushing and stockpile** are not extracted: filled on under 5% of your historical rows, and of the 117 plan sets we have processed, 1 had stockpile and none had crushing. Correct to treat these as internal sourcing decisions rather than plan quantities?

---

## Still unassigned: we need your call

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
