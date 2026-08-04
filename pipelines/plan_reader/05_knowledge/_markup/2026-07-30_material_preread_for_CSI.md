# Material Roll-Up — Pre-Read
Quick calibration for the CSI bidding & estimating team  ·  July 30, 2026

## What we need from you

We pulled every priced line item out of the bid schedules in 117 plans (MN / ND / SD) and sorted each material into the five quantity columns you already track. **We have not turned any of this on yet.** Before we do, we need you to tell us whether the roll-ups are right.

For each material: **Keep** it where we put it, **Move** it to a different column, or **Drop** it if it should not be counted at all.

Materials are listed **most-frequent first** — the ones you see on the most jobs are at the top of each table.

## Why we are asking

We tested on **Stearns County CP 073-123-025** (CR 123 resurfacing, let 08.28.25). We read all 26 line items off the bid schedule correctly, but the roll-up put them in the wrong columns:

| Line item on the Stearns bid schedule | Quantity | What we reported |
|---|---|---|
| Mill Bituminous Surface (1.0", 1.5", 4.0") | 70,263 SY | counted as asphalt, then dropped |
| Full Depth Reclamation | 70,167 SY | not counted at all |
| Remove Concrete Driveway Pavement | 44 SY | not counted at all |
| Motor Grader / Truck / Loaders | hourly | not counted at all |

So the job reported **zero milling** on a project that is almost entirely milling and reclamation. Across all 117 plans the same fault leaves **1.6M SY of milling** and **1.2M SY of reclamation** uncounted. We have fixed the mechanism. What we cannot decide for you is which column each material belongs in — that is this document.

A note on the tables: **"Today"** is what the current system does with that material. Where it says *not counted*, that quantity is invisible on the report right now.

---

# Part 1 — What we ARE tracking

Five columns, matching your spreadsheet.

## `Mixed_tons` — Hot mix asphalt placed, in TONS.

**18 materials** (26 spec'd variants) roll into this column.

**AS1. Type Sp Wear Course Mix** — seen in 22 plans · 59,963 SY; 207,673 TON

| Spec / class as printed | Seen in | States | Unit | Today | Qty | Right column? |
|---|---|---|---|---|---|---|
| Type Sp 12.5 Wear Course Mix | 15 | MN,XX | SY,TON | partly counted (Mixed_tons) | 29,695 SY; 129,684 TON | ☐ Keep ☐ Move to ______ ☐ Drop<br>Notes: |
| Type Sp 9.5 Wear Course Mix | 11 | MN,XX | SY,TON | partly counted (Mixed_tons) | 30,268 SY; 77,989 TON | ☐ Keep ☐ Move to ______ ☐ Drop<br>Notes: |

**AS2. Superpave** — seen in 18 plans · 21,100 SY; 699,640 TON

| Spec / class as printed | Seen in | States | Unit | Today | Qty | Right column? |
|---|---|---|---|---|---|---|
| Superpave Faa 45 | 7 | ND | TON | Mixed_tons | 239,816 TON | ☐ Keep ☐ Move to ______ ☐ Drop<br>Notes: |
| Rap - Superpave Faa 43 | 3 | ND | TON | Mixed_tons | 188,959 TON | ☐ Keep ☐ Move to ______ ☐ Drop<br>Notes: |
| Rap - Superpave Faa 45 | 3 | ND | TON | Mixed_tons | 160,900 TON | ☐ Keep ☐ Move to ______ ☐ Drop<br>Notes: |
| Superpave Faa 42 | 2 | ND | TON | Mixed_tons | 78,423 TON | ☐ Keep ☐ Move to ______ ☐ Drop<br>Notes: |
| Superpave Faa 43 | 2 | ND | SY,TON | partly counted (Mixed_tons) | 21,100 SY; 14,454 TON | ☐ Keep ☐ Move to ______ ☐ Drop<br>Notes: |
| Rap Superpave Faa 42 | 1 | ND | TON | Mixed_tons | 17,089 TON | ☐ Keep ☐ Move to ______ ☐ Drop<br>Notes: |

**AS3. Type Sp Non-Wear Course Mix** — seen in 10 plans · 30,315 SY; 53,937 TON

| Spec / class as printed | Seen in | States | Unit | Today | Qty | Right column? |
|---|---|---|---|---|---|---|
| Type Sp 12.5 Non-Wear Course Mix | 9 | MN | SY,TON | partly counted (Mixed_tons) | 30,315 SY; 50,856 TON | ☐ Keep ☐ Move to ______ ☐ Drop<br>Notes: |
| Type Sp 9.5 Non-Wear Course Mix | 1 | MN | TON | Mixed_tons | 3,081 TON | ☐ Keep ☐ Move to ______ ☐ Drop<br>Notes: |

**AS4. Asphalt Concrete Pavement** — seen in 4 plans · 59,392 TON

| Spec / class as printed | Seen in | States | Unit | Today | Qty | Right column? |
|---|---|---|---|---|---|---|
| Asphalt Concrete Pavement | 4 | SD | TON | Mixed_tons | 59,392 TON | ☐ Keep ☐ Move to ______ ☐ Drop<br>Notes: |

**AS5. Type Sp Bituminous Wear Course** — seen in 2 plans · 86,816 TON

| Spec / class as printed | Seen in | States | Unit | Today | Qty | Right column? |
|---|---|---|---|---|---|---|
| Type Sp 12.5 Bituminous Wear Course | 2 | MN | TON | Mixed_tons | 86,816 TON | ☐ Keep ☐ Move to ______ ☐ Drop<br>Notes: |

**AS6. Asphalt Concrete Composite** — seen in 2 plans · 29,453 TON

| Spec / class as printed | Seen in | States | Unit | Today | Qty | Right column? |
|---|---|---|---|---|---|---|
| Asphalt Concrete Composite | 1 | SD | TON | Mixed_tons | 21,744 TON | ☐ Keep ☐ Move to ______ ☐ Drop<br>Notes: |
| Asphalt Concrete Composite, Pg58 | 1 | SD | TON | Mixed_tons | 7,709 TON | ☐ Keep ☐ Move to ______ ☐ Drop<br>Notes: |

**AS7. Patching** — seen in 2 plans · 7,200 SY; 200 TON

| Spec / class as printed | Seen in | States | Unit | Today | Qty | Right column? |
|---|---|---|---|---|---|---|
| Patching | 2 | ND | SY,TON | **not counted** | 7,200 SY; 200 TON | ☐ Keep ☐ Move to ______ ☐ Drop<br>Notes: |

**AS8. Plant Mix Surf** — seen in 1 plans · 24,069 TON

| Spec / class as printed | Seen in | States | Unit | Today | Qty | Right column? |
|---|---|---|---|---|---|---|
| Plant Mix Surf | 1 | MT | TON | **not counted** | 24,069 TON | ☐ Keep ☐ Move to ______ ☐ Drop<br>Notes: |

**AS9. Type Sp Wear Course** — seen in 1 plans · 5,100 TON

| Spec / class as printed | Seen in | States | Unit | Today | Qty | Right column? |
|---|---|---|---|---|---|---|
| Type Sp 12.5 Wear Course | 1 | MN | TON | Mixed_tons | 5,100 TON | ☐ Keep ☐ Move to ______ ☐ Drop<br>Notes: |

**AS10. Bituminous Base Patch Special** — seen in 1 plans · 2,500 SY

| Spec / class as printed | Seen in | States | Unit | Today | Qty | Right column? |
|---|---|---|---|---|---|---|
| Bituminous Base Patch Special | 1 | MN | SY | **not counted** | 2,500 SY | ☐ Keep ☐ Move to ______ ☐ Drop<br>Notes: |

**AS11. Type Sp Bit Mix For Tight Blade Leveling** — seen in 1 plans · 1,380 TON

| Spec / class as printed | Seen in | States | Unit | Today | Qty | Right column? |
|---|---|---|---|---|---|---|
| Type Sp 4.75 Bit Mix For Tight Blade Leveling | 1 | MN | TON | Mixed_tons | 1,380 TON | ☐ Keep ☐ Move to ______ ☐ Drop<br>Notes: |

**AS12. Hot Mix Asphalt Pavement Ches Sddot Type 1** — seen in 1 plans · 1,344 TON

| Spec / class as printed | Seen in | States | Unit | Today | Qty | Right column? |
|---|---|---|---|---|---|---|
| Hot Mix Asphalt Pavement, Ches, Sddot, Class E Type 1, Pg 58 | 1 | SD | TON | partly counted (Mixed_tons) | 1,344 TON | ☐ Keep ☐ Move to ______ ☐ Drop<br>Notes: |

**AS13. Hot Mix Asphalt Superpave - Base Course** — seen in 1 plans · 1,031 TON

| Spec / class as printed | Seen in | States | Unit | Today | Qty | Right column? |
|---|---|---|---|---|---|---|
| Hot Mix Asphalt , Superpave, Faa 43 - Base Course | 1 | ND | TON | Mixed_tons | 1,031 TON | ☐ Keep ☐ Move to ______ ☐ Drop<br>Notes: |

**AS14. Asphalt Patching - Hbp Aggregate** — seen in 1 plans · 400 SY

| Spec / class as printed | Seen in | States | Unit | Today | Qty | Right column? |
|---|---|---|---|---|---|---|
| Asphalt Patching - Hbp , Aggregate | 1 | ND | SY | **not counted** | 400 SY | ☐ Keep ☐ Move to ______ ☐ Drop<br>Notes: |

**AS15. Commercial Mix Asphalt** — seen in 1 plans · 354 TON

| Spec / class as printed | Seen in | States | Unit | Today | Qty | Right column? |
|---|---|---|---|---|---|---|
| Commercial Grade Hot Mix Asphalt | 1 | ND | TON | Mixed_tons | 354 TON | ☐ Keep ☐ Move to ______ ☐ Drop<br>Notes: |

**AS16. Excavation - New Installations And Existing Asphalt Patches** — seen in 1 plans · 320 SY

| Spec / class as printed | Seen in | States | Unit | Today | Qty | Right column? |
|---|---|---|---|---|---|---|
| Excavation - New Installations And Existing Asphalt Patches | 1 | ND | SY | **not counted** | 320 SY | ☐ Keep ☐ Move to ______ ☐ Drop<br>Notes: |

**AS17. Bituminous Patching Mix** — seen in 1 plans · 287 TON

| Spec / class as printed | Seen in | States | Unit | Today | Qty | Right column? |
|---|---|---|---|---|---|---|
| Bituminous Patching Mix | 1 | MN | TON | Mixed_tons | 287 TON | ☐ Keep ☐ Move to ______ ☐ Drop<br>Notes: |

**AS18. Asphalt Concrete For Patching** — seen in 1 plans · 5 TON

| Spec / class as printed | Seen in | States | Unit | Today | Qty | Right column? |
|---|---|---|---|---|---|---|
| Asphalt Concrete For Patching | 1 | SD | TON | Mixed_tons | 5 TON | ☐ Keep ☐ Move to ______ ☐ Drop<br>Notes: |

<sub>6 further item name(s) matched this column but never carried a quantity in any plan (lump-sum lines, or rows our parser did not read a number from). They cannot affect the total, so they are left out of the table above: Extend Runway 15, Grind 2- Rumble Stripes In Asphalt Concrete, Grind Rumble Stripe In Asphalt Concrete, Hot Mix Asphalt, Proposed Typical Sections Table 2 - Hma, Superpave Faa 42 Hot Bituminous Pavement At 2.0 Ton/Cy - =</sub>

**Anything missing from `Mixed_tons`?**

| Material we did not list | Why it belongs here |
|---|---|
|  |  |
|  |  |

## `base_tons` — Aggregate base placed under the pavement, in TONS.

**19 materials** (30 spec'd variants) roll into this column.

**BA1. Aggregate Base** — seen in 33 plans · 17,660 CY; 793,771 TON

| Spec / class as printed | Seen in | States | Unit | Today | Qty | Right column? |
|---|---|---|---|---|---|---|
| Aggregate Base Course Cl 5 | 13 | ND | CY,TON | partly counted (base_tons) | 2,700 CY; 558,547 TON | ☐ Keep ☐ Move to ______ ☐ Drop<br>Notes: |
| Aggregate Base Class 5 | 10 | MN,ND | CY,TON | partly counted (base_tons) | 8,729 CY; 199,939 TON | ☐ Keep ☐ Move to ______ ☐ Drop<br>Notes: |
| Aggregate Base Course Cl 13 | 2 | ND | TON | base_tons | 26,235 TON | ☐ Keep ☐ Move to ______ ☐ Drop<br>Notes: |
| Aggregate Base, Class 5 | 1 | MN | TON | base_tons | 4,100 TON | ☐ Keep ☐ Move to ______ ☐ Drop<br>Notes: |
| Aggregate Base Cl 5 | 1 | MN | TON | base_tons | 3,370 TON | ☐ Keep ☐ Move to ______ ☐ Drop<br>Notes: |
| Class 5 Aggregate Base | 1 | MN | CY | **not counted** | 2,485 CY | ☐ Keep ☐ Move to ______ ☐ Drop<br>Notes: |
| Aggregate Base , Class 5 | 1 | MN | CY | **not counted** | 1,922 CY | ☐ Keep ☐ Move to ______ ☐ Drop<br>Notes: |
| Class 5 Aggregate Base Course | 1 | ND | CY | **not counted** | 1,779 CY | ☐ Keep ☐ Move to ______ ☐ Drop<br>Notes: |
| Aggregate Base Course Class 5 | 1 | ND | TON | **not counted** | 1,330 TON | ☐ Keep ☐ Move to ______ ☐ Drop<br>Notes: |
| Aggregate Base Class 6 | 1 | MN | TON | base_tons | 250 TON | ☐ Keep ☐ Move to ______ ☐ Drop<br>Notes: |
| Aggregate Base Class 5 Modified | 1 | MN | CY | **not counted** | 45 CY | ☐ Keep ☐ Move to ______ ☐ Drop<br>Notes: |

**BA2. Portland Cement** — seen in 4 plans · 13,322 TON

| Spec / class as printed | Seen in | States | Unit | Today | Qty | Right column? |
|---|---|---|---|---|---|---|
| Portland Cement | 4 | ND,SD | TON | **not counted** | 13,322 TON | ☐ Keep ☐ Move to ______ ☐ Drop<br>Notes: |

**BA3. Cement Stabilized Subgrade** — seen in 2 plans · 34,837 SY

| Spec / class as printed | Seen in | States | Unit | Today | Qty | Right column? |
|---|---|---|---|---|---|---|
| Cement Stabilized Subgrade | 2 | MN,ND | SY | **not counted** | 34,837 SY | ☐ Keep ☐ Move to ______ ☐ Drop<br>Notes: |

**BA4. Base Course** — seen in 2 plans · 25,099 TON

| Spec / class as printed | Seen in | States | Unit | Today | Qty | Right column? |
|---|---|---|---|---|---|---|
| Base Course | 2 | SD | TON | base_tons | 25,099 TON | ☐ Keep ☐ Move to ______ ☐ Drop<br>Notes: |

**BA5. Salvaged Base Course** — seen in 2 plans · 9,478 TON

| Spec / class as printed | Seen in | States | Unit | Today | Qty | Right column? |
|---|---|---|---|---|---|---|
| Salvaged Base Course | 1 | ND | TON | base_tons | 4,930 TON | ☐ Keep ☐ Move to ______ ☐ Drop<br>Notes: |
| Base Course, Salvaged | 1 | SD | TON | base_tons | 4,548 TON | ☐ Keep ☐ Move to ______ ☐ Drop<br>Notes: |

**BA6. Cement Stabilized Base Course** — seen in 1 plans · 419,170 SY

| Spec / class as printed | Seen in | States | Unit | Today | Qty | Right column? |
|---|---|---|---|---|---|---|
| Cement Stabilized Base Course | 1 | ND | SY | **not counted** | 419,170 SY | ☐ Keep ☐ Move to ______ ☐ Drop<br>Notes: |

**BA7. Stabilized Base Course** — seen in 1 plans · 157,185 SY

| Spec / class as printed | Seen in | States | Unit | Today | Qty | Right column? |
|---|---|---|---|---|---|---|
| Stabilized Base Course | 1 | ND | SY | **not counted** | 157,185 SY | ☐ Keep ☐ Move to ______ ☐ Drop<br>Notes: |

**BA8. Remove And Relay Salvaged Base Course** — seen in 1 plans · 79,787 SY

| Spec / class as printed | Seen in | States | Unit | Today | Qty | Right column? |
|---|---|---|---|---|---|---|
| Remove And Relay Salvaged Base Course | 1 | ND | SY | **not counted** | 79,787 SY | ☐ Keep ☐ Move to ______ ☐ Drop<br>Notes: |

**BA9. Cement Stabilized Subgrade - Ch** — seen in 1 plans · 76,193 SY

| Spec / class as printed | Seen in | States | Unit | Today | Qty | Right column? |
|---|---|---|---|---|---|---|
| Cement Stabilized Subgrade - Ch | 1 | ND | SY | **not counted** | 76,193 SY | ☐ Keep ☐ Move to ______ ☐ Drop<br>Notes: |

**BA10. Cement Treated Subgrade** — seen in 1 plans · 75,680 SY

| Spec / class as printed | Seen in | States | Unit | Today | Qty | Right column? |
|---|---|---|---|---|---|---|
| Cement Treated Subgrade | 1 | SD | SY | **not counted** | 75,680 SY | ☐ Keep ☐ Move to ______ ☐ Drop<br>Notes: |

**BA11. Soil Stabilization Material** — seen in 1 plans · 9,873 SY

| Spec / class as printed | Seen in | States | Unit | Today | Qty | Right column? |
|---|---|---|---|---|---|---|
| Soil Stabilization Material | 1 | ND | SY | **not counted** | 9,873 SY | ☐ Keep ☐ Move to ______ ☐ Drop<br>Notes: |

**BA12. Salvage And Stockpile Asphalt Mix And Granular Base Material** — seen in 1 plans · 4,548 TON

| Spec / class as printed | Seen in | States | Unit | Today | Qty | Right column? |
|---|---|---|---|---|---|---|
| Salvage And Stockpile Asphalt Mix And Granular Base Material | 1 | SD | TON | **not counted** | 4,548 TON | ☐ Keep ☐ Move to ______ ☐ Drop<br>Notes: |

**BA13. Subbase Course** — seen in 1 plans · 4,084 CY

| Spec / class as printed | Seen in | States | Unit | Today | Qty | Right column? |
|---|---|---|---|---|---|---|
| Subbase Course | 1 | ND | CY | **not counted** | 4,084 CY | ☐ Keep ☐ Move to ______ ☐ Drop<br>Notes: |

**BA14. Remove And Relay Blended Base Course** — seen in 1 plans · 3,650 SY

| Spec / class as printed | Seen in | States | Unit | Today | Qty | Right column? |
|---|---|---|---|---|---|---|
| Remove And Relay Blended Base Course | 1 | ND | SY | **not counted** | 3,650 SY | ☐ Keep ☐ Move to ______ ☐ Drop<br>Notes: |

**BA15. Subbase Course Ches** — seen in 1 plans · 2,546 CY

| Spec / class as printed | Seen in | States | Unit | Today | Qty | Right column? |
|---|---|---|---|---|---|---|
| Subbase Course, Ches | 1 | SD | CY | **not counted** | 2,546 CY | ☐ Keep ☐ Move to ______ ☐ Drop<br>Notes: |

**BA16. Aggregate Base Course Ches** — seen in 1 plans · 1,037 CY

| Spec / class as printed | Seen in | States | Unit | Today | Qty | Right column? |
|---|---|---|---|---|---|---|
| Aggregate Base Course, Ches | 1 | SD | CY | **not counted** | 1,037 CY | ☐ Keep ☐ Move to ______ ☐ Drop<br>Notes: |

**BA17. Salvage Aggregate Base** — seen in 1 plans · 629 CY

| Spec / class as printed | Seen in | States | Unit | Today | Qty | Right column? |
|---|---|---|---|---|---|---|
| Salvage Aggregate Base | 1 | ND | CY | **not counted** | 629 CY | ☐ Keep ☐ Move to ______ ☐ Drop<br>Notes: |

**BA18. Portland Cement Concrete Pavement Ches Sddot** — seen in 1 plans · 75 SY

| Spec / class as printed | Seen in | States | Unit | Today | Qty | Right column? |
|---|---|---|---|---|---|---|
| Portland Cement Concrete Pavement, Ches, Sddot, Class M6 | 1 | SD | SY | **not counted** | 75 SY | ☐ Keep ☐ Move to ______ ☐ Drop<br>Notes: |

**BA19. Aggregate Base I** — seen in 1 plans · 20 TON

| Spec / class as printed | Seen in | States | Unit | Today | Qty | Right column? |
|---|---|---|---|---|---|---|
| Aggregate Base Class 2 I | 1 | MN | TON | base_tons | 20 TON | ☐ Keep ☐ Move to ______ ☐ Drop<br>Notes: |

<sub>8 further item name(s) matched this column but never carried a quantity in any plan (lump-sum lines, or rows our parser did not read a number from). They cannot affect the total, so they are left out of the table above: Aggregate Base And Surface Course, Aggregate Base Preparation, Cl 5 Aggregate Base Ton 20 10 10 670, Liquid Base Stabilizer, Recycled Pavement, Soil Stabilization…</sub>

**Anything missing from `base_tons`?**

| Material we did not list | Why it belongs here |
|---|---|
|  |  |
|  |  |

## `shldr_tons` — Shoulder gravel and aggregate surfacing, in TONS.

**11 materials** (20 spec'd variants) roll into this column.

**SH1. Aggregate Surfacing** — seen in 18 plans · 1,311 CY; 45,073 TON

| Spec / class as printed | Seen in | States | Unit | Today | Qty | Right column? |
|---|---|---|---|---|---|---|
| Aggregate Surfacing Class 1 | 6 | MN,XX | CY,TON | partly counted (shldr_tons) | 331 CY; 17,661 TON | ☐ Keep ☐ Move to ______ ☐ Drop<br>Notes: |
| Aggregate Surfacing Class 5 | 4 | MN | TON | shldr_tons | 2,623 TON | ☐ Keep ☐ Move to ______ ☐ Drop<br>Notes: |
| Aggregate Surfacing Special | 3 | MN | TON | shldr_tons | 2,820 TON | ☐ Keep ☐ Move to ______ ☐ Drop<br>Notes: |
| Aggregate Surfacing, Class 1 | 2 | MN,XX | TON | shldr_tons | 6,182 TON | ☐ Keep ☐ Move to ______ ☐ Drop<br>Notes: |
| Aggregate Surfacing Class Special | 2 | MN | TON | shldr_tons | 1,695 TON | ☐ Keep ☐ Move to ______ ☐ Drop<br>Notes: |
| Aggregate Surfacing Class 1 Mod | 1 | MN | TON | **not counted** | 11,302 TON | ☐ Keep ☐ Move to ______ ☐ Drop<br>Notes: |
| Aggregate Surfacing Class 1 Mod 5 | 1 | MN | TON | shldr_tons | 2,440 TON | ☐ Keep ☐ Move to ______ ☐ Drop<br>Notes: |
| Aggregate Surfacing , Class 5 | 1 | MN | CY | **not counted** | 980 CY | ☐ Keep ☐ Move to ______ ☐ Drop<br>Notes: |
| Aggregate Surfacing Class 2 | 1 | MN | TON | shldr_tons | 350 TON | ☐ Keep ☐ Move to ______ ☐ Drop<br>Notes: |

**SH2. Aggregate Surface Course** — seen in 5 plans · 1,360 TON

| Spec / class as printed | Seen in | States | Unit | Today | Qty | Right column? |
|---|---|---|---|---|---|---|
| Aggregate Surface Course Cl 13 | 5 | ND | TON | base_tons | 1,360 TON | ☐ Keep ☐ Move to ______ ☐ Drop<br>Notes: |

**SH3. Shoulder Base Aggregate** — seen in 3 plans · 12,100 TON

| Spec / class as printed | Seen in | States | Unit | Today | Qty | Right column? |
|---|---|---|---|---|---|---|
| Shoulder Base Aggregate Class 1 | 2 | MN | TON | shldr_tons | 1,868 TON | ☐ Keep ☐ Move to ______ ☐ Drop<br>Notes: |
| Shoulder Base Aggregate, Cl 1 | 1 | MN | TON | shldr_tons | 10,232 TON | ☐ Keep ☐ Move to ______ ☐ Drop<br>Notes: |

**SH4. Gravel Surfacing** — seen in 3 plans · 1,340 TON

| Spec / class as printed | Seen in | States | Unit | Today | Qty | Right column? |
|---|---|---|---|---|---|---|
| Gravel Surfacing | 3 | SD | TON | shldr_tons | 1,340 TON | ☐ Keep ☐ Move to ______ ☐ Drop<br>Notes: |

**SH5. Traffic Service Aggregate** — seen in 2 plans · 1,313 TON

| Spec / class as printed | Seen in | States | Unit | Today | Qty | Right column? |
|---|---|---|---|---|---|---|
| Traffic Service Aggregate | 2 | ND | TON | **not counted** | 1,313 TON | ☐ Keep ☐ Move to ______ ☐ Drop<br>Notes: |

**SH6. Graunular Material Furnish** — seen in 1 plans · 9,825 TON

| Spec / class as printed | Seen in | States | Unit | Today | Qty | Right column? |
|---|---|---|---|---|---|---|
| Graunular Material, Furnish | 1 | SD | TON | **not counted** | 9,825 TON | ☐ Keep ☐ Move to ______ ☐ Drop<br>Notes: |

**SH7. Shot Rock** — seen in 1 plans · 8,078 TON

| Spec / class as printed | Seen in | States | Unit | Today | Qty | Right column? |
|---|---|---|---|---|---|---|
| Shot Rock | 1 | SD | TON | **not counted** | 8,078 TON | ☐ Keep ☐ Move to ______ ☐ Drop<br>Notes: |

**SH8. Access Gravel** — seen in 1 plans · 735 CY

| Spec / class as printed | Seen in | States | Unit | Today | Qty | Right column? |
|---|---|---|---|---|---|---|
| Access Gravel | 1 | MN | CY | **not counted** | 735 CY | ☐ Keep ☐ Move to ______ ☐ Drop<br>Notes: |

**SH9. Shoulder Gravel** — seen in 1 plans · 156 CY

| Spec / class as printed | Seen in | States | Unit | Today | Qty | Right column? |
|---|---|---|---|---|---|---|
| Shoulder Gravel | 1 | MT | CY | **not counted** | 156 CY | ☐ Keep ☐ Move to ______ ☐ Drop<br>Notes: |

**SH10. Aggregate Suracing** — seen in 1 plans · 42 TON

| Spec / class as printed | Seen in | States | Unit | Today | Qty | Right column? |
|---|---|---|---|---|---|---|
| Aggregate Suracing, Class 1 | 1 | MN | TON | **not counted** | 42 TON | ☐ Keep ☐ Move to ______ ☐ Drop<br>Notes: |

**SH11. Alley & Shouldering Aggregate Surfacing** — seen in 1 plans · 38 SY

| Spec / class as printed | Seen in | States | Unit | Today | Qty | Right column? |
|---|---|---|---|---|---|---|
| Class 5 Alley & Shouldering Aggregate Surfacing | 1 | MN | SY | **not counted** | 38 SY | ☐ Keep ☐ Move to ______ ☐ Drop<br>Notes: |

<sub>1 further item name(s) matched this column but never carried a quantity in any plan (lump-sum lines, or rows our parser did not read a number from). They cannot affect the total, so they are left out of the table above: Blend, Haul, And Stockpile Granular Material</sub>

**Anything missing from `shldr_tons`?**

| Material we did not list | Why it belongs here |
|---|---|
|  |  |
|  |  |

## `grading_yards` — Earthwork moved, in CUBIC YARDS.

**50 materials** (61 spec'd variants) roll into this column.

**GR1. Common Excavation** — seen in 30 plans · 1,099,104 CY

| Spec / class as printed | Seen in | States | Unit | Today | Qty | Right column? |
|---|---|---|---|---|---|---|
| Excavation - Common | 11 | MN,ND | CY | grading_yards | 594,959 CY | ☐ Keep ☐ Move to ______ ☐ Drop<br>Notes: |
| Common Excavation-Type A | 7 | ND | CY | grading_yards | 235,976 CY | ☐ Keep ☐ Move to ______ ☐ Drop<br>Notes: |
| Common Excavation-Type B | 4 | ND | CY | grading_yards | 17,245 CY | ☐ Keep ☐ Move to ______ ☐ Drop<br>Notes: |
| Common Excavation | 3 | MN,ND | CY | grading_yards | 19,925 CY | ☐ Keep ☐ Move to ______ ☐ Drop<br>Notes: |
| Common Excavation- Type A | 2 | ND,SD | CY | grading_yards | 214,524 CY | ☐ Keep ☐ Move to ______ ☐ Drop<br>Notes: |
| Excavation -Common | 1 | MN | CY | grading_yards | 7,707 CY | ☐ Keep ☐ Move to ______ ☐ Drop<br>Notes: |
| Excavation Common | 1 | MN | CY | grading_yards | 6,788 CY | ☐ Keep ☐ Move to ______ ☐ Drop<br>Notes: |
| Common Excavation - Type A | 1 | ND | CY | grading_yards | 1,980 CY | ☐ Keep ☐ Move to ______ ☐ Drop<br>Notes: |

**GR2. Topsoil** — seen in 12 plans · 434,715 CY

| Spec / class as printed | Seen in | States | Unit | Today | Qty | Right column? |
|---|---|---|---|---|---|---|
| Topsoil | 12 | ND,SD | CY | **not counted** | 434,715 CY | ☐ Keep ☐ Move to ______ ☐ Drop<br>Notes: |

**GR3. Subgrade Preparation** — seen in 11 plans · 52,544 SY

| Spec / class as printed | Seen in | States | Unit | Today | Qty | Right column? |
|---|---|---|---|---|---|---|
| Subgrade Preparation | 7 | MN | SY | **not counted** | 31,444 SY | ☐ Keep ☐ Move to ______ ☐ Drop<br>Notes: |
| Subgrade Preparation-Type A | 4 | ND | SY | **not counted** | 21,100 SY | ☐ Keep ☐ Move to ______ ☐ Drop<br>Notes: |

**GR4. Common Embankment** — seen in 10 plans · 466,553 CY

| Spec / class as printed | Seen in | States | Unit | Today | Qty | Right column? |
|---|---|---|---|---|---|---|
| Common Embankment | 10 | MN,ND | CY | grading_yards | 466,553 CY | ☐ Keep ☐ Move to ______ ☐ Drop<br>Notes: |

**GR5. Borrow-Excavation** — seen in 10 plans · 323,910 CY

| Spec / class as printed | Seen in | States | Unit | Today | Qty | Right column? |
|---|---|---|---|---|---|---|
| Borrow-Excavation | 9 | ND | CY | grading_yards | 275,468 CY | ☐ Keep ☐ Move to ______ ☐ Drop<br>Notes: |
| Borrow - Excavation | 1 | ND | CY | grading_yards | 48,442 CY | ☐ Keep ☐ Move to ______ ☐ Drop<br>Notes: |

**GR6. Remove Bituminous Pavement** — seen in 9 plans · 53,630 SY

| Spec / class as printed | Seen in | States | Unit | Today | Qty | Right column? |
|---|---|---|---|---|---|---|
| Remove Bituminous Pavement | 9 | MN,MT,XX | SY | **not counted** | 53,630 SY | ☐ Keep ☐ Move to ______ ☐ Drop<br>Notes: |

**GR7. Common Topsoil Borrow** — seen in 7 plans · 1,830 CY; 285 TON

| Spec / class as printed | Seen in | States | Unit | Today | Qty | Right column? |
|---|---|---|---|---|---|---|
| Common Topsoil Borrow | 7 | MN,XX | CY,TON | **not counted** | 1,830 CY; 285 TON | ☐ Keep ☐ Move to ______ ☐ Drop<br>Notes: |

**GR8. Removal Of Bituminous Surfacing** — seen in 6 plans · 1,870 SY; 3,915 TON

| Spec / class as printed | Seen in | States | Unit | Today | Qty | Right column? |
|---|---|---|---|---|---|---|
| Removal Of Bituminous Surfacing | 6 | ND | SY,TON | partly counted (Mixed_tons) | 1,870 SY; 3,915 TON | ☐ Keep ☐ Move to ______ ☐ Drop<br>Notes: |

**GR9. Unclassified Excavation** — seen in 5 plans · 59,721 CY

| Spec / class as printed | Seen in | States | Unit | Today | Qty | Right column? |
|---|---|---|---|---|---|---|
| Unclassified Excavation | 5 | ND,SD | CY | partly counted (grading_yards) | 59,721 CY | ☐ Keep ☐ Move to ______ ☐ Drop<br>Notes: |

**GR10. Select Granular Embankment** — seen in 5 plans · 23,670 CY

| Spec / class as printed | Seen in | States | Unit | Today | Qty | Right column? |
|---|---|---|---|---|---|---|
| Select Granular Embankment | 5 | MN | CY | grading_yards | 23,670 CY | ☐ Keep ☐ Move to ______ ☐ Drop<br>Notes: |

**GR11. Common Excavation-Subcut** — seen in 5 plans · 5,230 CY

| Spec / class as printed | Seen in | States | Unit | Today | Qty | Right column? |
|---|---|---|---|---|---|---|
| Common Excavation-Subcut | 3 | ND | CY | grading_yards | 1,944 CY | ☐ Keep ☐ Move to ______ ☐ Drop<br>Notes: |
| Common Excavation - Subcut | 2 | ND | CY | grading_yards | 3,286 CY | ☐ Keep ☐ Move to ______ ☐ Drop<br>Notes: |

**GR12. Removal Of Concrete** — seen in 5 plans · 1,902 SY

| Spec / class as printed | Seen in | States | Unit | Today | Qty | Right column? |
|---|---|---|---|---|---|---|
| Removal Of Concrete | 3 | ND,SD | SY | **not counted** | 1,676 SY | ☐ Keep ☐ Move to ______ ☐ Drop<br>Notes: |
| Removal Of Concrete Pavement | 2 | ND | SY | **not counted** | 226 SY | ☐ Keep ☐ Move to ______ ☐ Drop<br>Notes: |

**GR13. Remove Concrete Driveway Pavement** — seen in 5 plans · 898 SY

| Spec / class as printed | Seen in | States | Unit | Today | Qty | Right column? |
|---|---|---|---|---|---|---|
| Remove Concrete Driveway Pavement | 5 | MN,XX | SY | **not counted** | 898 SY | ☐ Keep ☐ Move to ______ ☐ Drop<br>Notes: |

**GR14. Common Excavation-Waste** — seen in 3 plans · 28,546 CY

| Spec / class as printed | Seen in | States | Unit | Today | Qty | Right column? |
|---|---|---|---|---|---|---|
| Common Excavation-Waste | 3 | ND | CY | grading_yards | 28,546 CY | ☐ Keep ☐ Move to ______ ☐ Drop<br>Notes: |

**GR15. Placing Topsoil** — seen in 3 plans · 9,181 CY

| Spec / class as printed | Seen in | States | Unit | Today | Qty | Right column? |
|---|---|---|---|---|---|---|
| Placing Topsoil | 3 | SD | CY | **not counted** | 9,181 CY | ☐ Keep ☐ Move to ______ ☐ Drop<br>Notes: |

**GR16. Foundation Fill** — seen in 3 plans · 5,110 CY

| Spec / class as printed | Seen in | States | Unit | Today | Qty | Right column? |
|---|---|---|---|---|---|---|
| Foundation Fill | 3 | ND | CY | **not counted** | 5,110 CY | ☐ Keep ☐ Move to ______ ☐ Drop<br>Notes: |

**GR17. Topsoil-Imported** — seen in 3 plans · 2,167 CY

| Spec / class as printed | Seen in | States | Unit | Today | Qty | Right column? |
|---|---|---|---|---|---|---|
| Topsoil-Imported | 3 | ND | CY | **not counted** | 2,167 CY | ☐ Keep ☐ Move to ______ ☐ Drop<br>Notes: |

**GR18. Subgrade Repair** — seen in 3 plans · 207 CY; 1,495 SY

| Spec / class as printed | Seen in | States | Unit | Today | Qty | Right column? |
|---|---|---|---|---|---|---|
| Subgrade Repair | 3 | ND,SD | CY,SY | partly counted (grading_yards) | 207 CY; 1,495 SY | ☐ Keep ☐ Move to ______ ☐ Drop<br>Notes: |

**GR19. Remove Aggregate Base** — seen in 2 plans · 72,531 TON

| Spec / class as printed | Seen in | States | Unit | Today | Qty | Right column? |
|---|---|---|---|---|---|---|
| Remove Aggregate Base | 2 | ND | TON | base_tons | 72,531 TON | ☐ Keep ☐ Move to ______ ☐ Drop<br>Notes: |

**GR20. Topsoil-Borrow Area** — seen in 2 plans · 62,538 CY

| Spec / class as printed | Seen in | States | Unit | Today | Qty | Right column? |
|---|---|---|---|---|---|---|
| Topsoil-Borrow Area | 2 | ND,SD | CY | **not counted** | 62,538 CY | ☐ Keep ☐ Move to ______ ☐ Drop<br>Notes: |

**GR21. Contractor Furnished Borrow Excavation** — seen in 2 plans · 2,600 CY

| Spec / class as printed | Seen in | States | Unit | Today | Qty | Right column? |
|---|---|---|---|---|---|---|
| Contractor Furnished Borrow Excavation | 2 | SD | CY | grading_yards | 2,600 CY | ☐ Keep ☐ Move to ______ ☐ Drop<br>Notes: |

**GR22. Removal Of Pavement** — seen in 2 plans · 2,494 TON

| Spec / class as printed | Seen in | States | Unit | Today | Qty | Right column? |
|---|---|---|---|---|---|---|
| Removal Of Pavement | 2 | ND | TON | **not counted** | 2,494 TON | ☐ Keep ☐ Move to ______ ☐ Drop<br>Notes: |

**GR23. Excavation - Subgrade** — seen in 2 plans · 1,888 CY

| Spec / class as printed | Seen in | States | Unit | Today | Qty | Right column? |
|---|---|---|---|---|---|---|
| Excavation - Subgrade | 2 | MN | CY | partly counted (grading_yards) | 1,888 CY | ☐ Keep ☐ Move to ______ ☐ Drop<br>Notes: |

**GR24. Remove Bituminous Driveway Pavement** — seen in 2 plans · 862 SY

| Spec / class as printed | Seen in | States | Unit | Today | Qty | Right column? |
|---|---|---|---|---|---|---|
| Remove Bituminous Driveway Pavement | 2 | MN | SY | **not counted** | 862 SY | ☐ Keep ☐ Move to ______ ☐ Drop<br>Notes: |

**GR25. Structure Excavation Box Culvert** — seen in 2 plans · 202 CY

| Spec / class as printed | Seen in | States | Unit | Today | Qty | Right column? |
|---|---|---|---|---|---|---|
| Structure Excavation, Box Culvert | 2 | SD | CY | **not counted** | 202 CY | ☐ Keep ☐ Move to ______ ☐ Drop<br>Notes: |

**GR26. Remove Concrete Pavement** — seen in 2 plans · 20 SY

| Spec / class as printed | Seen in | States | Unit | Today | Qty | Right column? |
|---|---|---|---|---|---|---|
| Remove Concrete Pavement | 2 | MN | SY | **not counted** | 20 SY | ☐ Keep ☐ Move to ______ ☐ Drop<br>Notes: |

**GR27. Remove Aggregate Base & Surfacing** — seen in 1 plans · 129,500 TON

| Spec / class as printed | Seen in | States | Unit | Today | Qty | Right column? |
|---|---|---|---|---|---|---|
| Remove Aggregate Base & Surfacing | 1 | ND | TON | base_tons | 129,500 TON | ☐ Keep ☐ Move to ______ ☐ Drop<br>Notes: |

**GR28. Granular Embankment** — seen in 1 plans · 77,328 CY

| Spec / class as printed | Seen in | States | Unit | Today | Qty | Right column? |
|---|---|---|---|---|---|---|
| Granular Embankment | 1 | ND | CY | grading_yards | 77,328 CY | ☐ Keep ☐ Move to ______ ☐ Drop<br>Notes: |

**GR29. Excavation - Muck** — seen in 1 plans · 33,548 CY

| Spec / class as printed | Seen in | States | Unit | Today | Qty | Right column? |
|---|---|---|---|---|---|---|
| Excavation - Muck | 1 | ND | CY | grading_yards | 33,548 CY | ☐ Keep ☐ Move to ______ ☐ Drop<br>Notes: |

**GR30. Topsoil Stripping & Spreading** — seen in 1 plans · 30,000 SY

| Spec / class as printed | Seen in | States | Unit | Today | Qty | Right column? |
|---|---|---|---|---|---|---|
| Topsoil Stripping & Spreading | 1 | ND | SY | **not counted** | 30,000 SY | ☐ Keep ☐ Move to ______ ☐ Drop<br>Notes: |

**GR31. Remove & Salvage Topsoil** — seen in 1 plans · 13,665 CY

| Spec / class as printed | Seen in | States | Unit | Today | Qty | Right column? |
|---|---|---|---|---|---|---|
| Remove & Salvage Topsoil | 1 | ND | CY | **not counted** | 13,665 CY | ☐ Keep ☐ Move to ______ ☐ Drop<br>Notes: |

**GR32. Topsoil Strip & Spread** — seen in 1 plans · 12,114 CY

| Spec / class as printed | Seen in | States | Unit | Today | Qty | Right column? |
|---|---|---|---|---|---|---|
| Topsoil Strip & Spread | 1 | MN | CY | **not counted** | 12,114 CY | ☐ Keep ☐ Move to ______ ☐ Drop<br>Notes: |

**GR33. Select Granular Borrow** — seen in 1 plans · 12,024 CY

| Spec / class as printed | Seen in | States | Unit | Today | Qty | Right column? |
|---|---|---|---|---|---|---|
| Select Granular Borrow | 1 | MN | CY | grading_yards | 12,024 CY | ☐ Keep ☐ Move to ______ ☐ Drop<br>Notes: |

**GR34. Remove And Dispose Of Bituminous Pavement** — seen in 1 plans · 6,528 SY

| Spec / class as printed | Seen in | States | Unit | Today | Qty | Right column? |
|---|---|---|---|---|---|---|
| Remove And Dispose Of Bituminous Pavement | 1 | ND | SY | **not counted** | 6,528 SY | ☐ Keep ☐ Move to ______ ☐ Drop<br>Notes: |

**GR35. Overburden Excavation For Riprap** — seen in 1 plans · 6,418 CY

| Spec / class as printed | Seen in | States | Unit | Today | Qty | Right column? |
|---|---|---|---|---|---|---|
| Overburden Excavation For Riprap | 1 | SD | CY | **not counted** | 6,418 CY | ☐ Keep ☐ Move to ______ ☐ Drop<br>Notes: |

**GR36. Undercutting** — seen in 1 plans · 5,050 CY

| Spec / class as printed | Seen in | States | Unit | Today | Qty | Right column? |
|---|---|---|---|---|---|---|
| Undercutting | 1 | SD | CY | **not counted** | 5,050 CY | ☐ Keep ☐ Move to ______ ☐ Drop<br>Notes: |

**GR37. Topsoiling** — seen in 1 plans · 2,850 CY

| Spec / class as printed | Seen in | States | Unit | Today | Qty | Right column? |
|---|---|---|---|---|---|---|
| Topsoiling | 1 | SD | CY | **not counted** | 2,850 CY | ☐ Keep ☐ Move to ______ ☐ Drop<br>Notes: |

**GR38. Subcut Aggregate** — seen in 1 plans · 2,482 TON

| Spec / class as printed | Seen in | States | Unit | Today | Qty | Right column? |
|---|---|---|---|---|---|---|
| Subcut Aggregate | 1 | ND | TON | **not counted** | 2,482 TON | ☐ Keep ☐ Move to ______ ☐ Drop<br>Notes: |

**GR39. Remove Pavement** — seen in 1 plans · 1,880 SY

| Spec / class as printed | Seen in | States | Unit | Today | Qty | Right column? |
|---|---|---|---|---|---|---|
| Remove Pavement | 1 | MN | SY | **not counted** | 1,880 SY | ☐ Keep ☐ Move to ______ ☐ Drop<br>Notes: |

**GR40. Bridge End Embankment** — seen in 1 plans · 1,218 CY

| Spec / class as printed | Seen in | States | Unit | Today | Qty | Right column? |
|---|---|---|---|---|---|---|
| Bridge End Embankment | 1 | SD | CY | **not counted** | 1,218 CY | ☐ Keep ☐ Move to ______ ☐ Drop<br>Notes: |

**GR41. Contractor Furnished Borrow** — seen in 1 plans · 905 CY

| Spec / class as printed | Seen in | States | Unit | Today | Qty | Right column? |
|---|---|---|---|---|---|---|
| Contractor Furnished Borrow | 1 | SD | CY | grading_yards | 905 CY | ☐ Keep ☐ Move to ______ ☐ Drop<br>Notes: |

**GR42. Embankment- Type A** — seen in 1 plans · 775 CY

| Spec / class as printed | Seen in | States | Unit | Today | Qty | Right column? |
|---|---|---|---|---|---|---|
| Embankment- Type A | 1 | ND | CY | grading_yards | 775 CY | ☐ Keep ☐ Move to ______ ☐ Drop<br>Notes: |

**GR43. Unclassified Excavation Digouts** — seen in 1 plans · 692 CY

| Spec / class as printed | Seen in | States | Unit | Today | Qty | Right column? |
|---|---|---|---|---|---|---|
| Unclassified Excavation, Digouts | 1 | SD | CY | grading_yards | 692 CY | ☐ Keep ☐ Move to ______ ☐ Drop<br>Notes: |

**GR44. Excavation - Rock** — seen in 1 plans · 300 CY

| Spec / class as printed | Seen in | States | Unit | Today | Qty | Right column? |
|---|---|---|---|---|---|---|
| Excavation - Rock | 1 | MN | CY | grading_yards | 300 CY | ☐ Keep ☐ Move to ______ ☐ Drop<br>Notes: |

**GR45. Pavement Removal** — seen in 1 plans · 250 SY

| Spec / class as printed | Seen in | States | Unit | Today | Qty | Right column? |
|---|---|---|---|---|---|---|
| Pavement Removal | 1 | ND | SY | **not counted** | 250 SY | ☐ Keep ☐ Move to ______ ☐ Drop<br>Notes: |

**GR46. Granular Borrow Mat'L** — seen in 1 plans · 250 CY

| Spec / class as printed | Seen in | States | Unit | Today | Qty | Right column? |
|---|---|---|---|---|---|---|
| Granular Borrow Mat'L | 1 | MN | CY | grading_yards | 250 CY | ☐ Keep ☐ Move to ______ ☐ Drop<br>Notes: |

**GR47. Drilled Shaft Excavation** — seen in 1 plans · 182 CY

| Spec / class as printed | Seen in | States | Unit | Today | Qty | Right column? |
|---|---|---|---|---|---|---|
| Drilled Shaft Excavation | 1 | SD | CY | grading_yards | 182 CY | ☐ Keep ☐ Move to ______ ☐ Drop<br>Notes: |

**GR48. Structure Excavation Bridge** — seen in 1 plans · 176 CY

| Spec / class as printed | Seen in | States | Unit | Today | Qty | Right column? |
|---|---|---|---|---|---|---|
| Structure Excavation, Bridge | 1 | SD | CY | **not counted** | 176 CY | ☐ Keep ☐ Move to ______ ☐ Drop<br>Notes: |

**GR49. Loam Topsoil Borrow** — seen in 1 plans · 125 CY

| Spec / class as printed | Seen in | States | Unit | Today | Qty | Right column? |
|---|---|---|---|---|---|---|
| Loam Topsoil Borrow | 1 | MN | CY | **not counted** | 125 CY | ☐ Keep ☐ Move to ______ ☐ Drop<br>Notes: |

**GR50. Approach Slab Underdrain Excavation** — seen in 1 plans · 8 CY

| Spec / class as printed | Seen in | States | Unit | Today | Qty | Right column? |
|---|---|---|---|---|---|---|
| Approach Slab Underdrain Excavation | 1 | SD | CY | grading_yards | 8 CY | ☐ Keep ☐ Move to ______ ☐ Drop<br>Notes: |

<sub>18 further item name(s) matched this column but never carried a quantity in any plan (lump-sum lines, or rows our parser did not read a number from). They cannot affect the total, so they are left out of the table above: Box Culvert Excavation, Box Culvert Excavation - Site 1, Box Culvert Excavation - Site 2, Box Culvert Excavation - Site 3, Channel Excavation, Class 1 Excavation…</sub>

**Anything missing from `grading_yards`?**

| Material we did not list | Why it belongs here |
|---|---|
|  |  |
|  |  |

## `mill_sy` — Existing surface ground off, in SQUARE YARDS.

**11 materials** (12 spec'd variants) roll into this column.

**MI1. Mill Bituminous Surface** — seen in 15 plans · 758,983 SY

| Spec / class as printed | Seen in | States | Unit | Today | Qty | Right column? |
|---|---|---|---|---|---|---|
| Mill Bituminous Surface | 13 | MN,XX | SY | **not counted** | 715,755 SY | ☐ Keep ☐ Move to ______ ☐ Drop<br>Notes: |
| Mill Bituminous Pavement | 2 | MN | SY | **not counted** | 43,228 SY | ☐ Keep ☐ Move to ______ ☐ Drop<br>Notes: |

**MI2. Full Depth Reclamation** — seen in 13 plans · 1,166,396 SY

| Spec / class as printed | Seen in | States | Unit | Today | Qty | Right column? |
|---|---|---|---|---|---|---|
| Full Depth Reclamation | 13 | MN,ND,XX | SY | **not counted** | 1,166,396 SY | ☐ Keep ☐ Move to ______ ☐ Drop<br>Notes: |

**MI3. Milling Pavement Surface** — seen in 12 plans · 462,779 SY; 230,625 TON

| Spec / class as printed | Seen in | States | Unit | Today | Qty | Right column? |
|---|---|---|---|---|---|---|
| Milling Pavement Surface | 12 | ND | SY,TON | partly counted (mill_sy) | 462,779 SY; 230,625 TON | ☐ Keep ☐ Move to ______ ☐ Drop<br>Notes: |

**MI4. Cold Milling Asphalt Concrete** — seen in 5 plans · 75,664 SY

| Spec / class as printed | Seen in | States | Unit | Today | Qty | Right column? |
|---|---|---|---|---|---|---|
| Cold Milling Asphalt Concrete | 5 | SD | SY | mill_sy | 75,664 SY | ☐ Keep ☐ Move to ______ ☐ Drop<br>Notes: |

**MI5. Mill Bituminous Surfacing** — seen in 2 plans · 290,393 SY

| Spec / class as printed | Seen in | States | Unit | Today | Qty | Right column? |
|---|---|---|---|---|---|---|
| Mill Bituminous Surfacing | 2 | MN | SY | **not counted** | 290,393 SY | ☐ Keep ☐ Move to ______ ☐ Drop<br>Notes: |

**MI6. Cold Recycled Plant Mix** — seen in 1 plans · 285,692 SY

| Spec / class as printed | Seen in | States | Unit | Today | Qty | Right column? |
|---|---|---|---|---|---|---|
| Cold Recycled Plant Mix | 1 | MT | SY | **not counted** | 285,692 SY | ☐ Keep ☐ Move to ______ ☐ Drop<br>Notes: |

**MI7. Stabilized Full Depth Reclamation** — seen in 1 plans · 28,713 SY

| Spec / class as printed | Seen in | States | Unit | Today | Qty | Right column? |
|---|---|---|---|---|---|---|
| Stabilized Full Depth Reclamation | 1 | MN | SY | **not counted** | 28,713 SY | ☐ Keep ☐ Move to ______ ☐ Drop<br>Notes: |

**MI8. Full Depth Bituminous Reclamation** — seen in 1 plans · 3,870 SY

| Spec / class as printed | Seen in | States | Unit | Today | Qty | Right column? |
|---|---|---|---|---|---|---|
| Full Depth Bituminous Reclamation | 1 | MN | SY | **not counted** | 3,870 SY | ☐ Keep ☐ Move to ______ ☐ Drop<br>Notes: |

**MI9. Cold Milling** — seen in 1 plans · 3,819 SY

| Spec / class as printed | Seen in | States | Unit | Today | Qty | Right column? |
|---|---|---|---|---|---|---|
| Cold Milling | 1 | MT | SY | mill_sy | 3,819 SY | ☐ Keep ☐ Move to ______ ☐ Drop<br>Notes: |

**MI10. Recycling Agent Cir-Ee** — seen in 1 plans · 1,377 TON

| Spec / class as printed | Seen in | States | Unit | Today | Qty | Right column? |
|---|---|---|---|---|---|---|
| Recycling Agent Cir-Ee | 1 | MT | TON | **not counted** | 1,377 TON | ☐ Keep ☐ Move to ______ ☐ Drop<br>Notes: |

**MI11. Mill Transition Area** — seen in 1 plans · 75 SY

| Spec / class as printed | Seen in | States | Unit | Today | Qty | Right column? |
|---|---|---|---|---|---|---|
| Mill Transition Area | 1 | ND | SY | **not counted** | 75 SY | ☐ Keep ☐ Move to ______ ☐ Drop<br>Notes: |

**Anything missing from `mill_sy`?**

| Material we did not list | Why it belongs here |
|---|---|
|  |  |
|  |  |

---

# Part 2 — What we are NOT tracking

These are real pay items we read off the bid schedule but do **not** roll into any of your five columns. We carry them as a yes/no flag on the report instead ("this job has concrete work"), not as a quantity.

**The question for each group: should any of these actually be counted?**

| Group | Seen in | Example materials | Quantity we are ignoring | Should we count it? |
|---|---|---|---|---|
| **Traffic control** | 63 plans | Traffic Control; Traffic Control Signs; Flagging | — | ☐ Keep as flag ☐ Count it as ______ |
| **Mobilization & contract admin** | 59 plans | Mobilization; Contract Bond; Maint And Restoration Of Haul Roads | — | ☐ Keep as flag ☐ Count it as ______ |
| **Erosion control & turf** | 48 plans | Silt Fence; Seeding; Storm Drain Inlet Protection | 164 CY; 226,424 SY; 202 TON | ☐ Keep as flag ☐ Count it as ______ |
| **Structures (culvert, bridge, pipe, riprap)** | 40 plans | Rc Pipe Apron; Random Riprap Class Iii; Pipe Conc Reinf Cl Iii | 197,582 CY; 682 SY; 13,068 TON | ☐ Keep as flag ☐ Count it as ______ |
| **Pavement marking** | 36 plans | Pvmt Mk Painted Line; Epoxy Pvmt Mk Line; Pvmt Mk Painted-Message | — | ☐ Keep as flag ☐ Count it as ______ |
| **Binder & coatings (tack, prime, PG cement)** | 33 plans | Tack Coat; Pg 58H; Pg 58S | 56,029 TON | ☐ Keep as flag ☐ Count it as ______ |
| **Removals that are not pavement or base** | 30 plans | Remove Fiber Rolls; Remove Silt Fence; Remove Pipe Culverts | 10 CY | ☐ Keep as flag ☐ Count it as ______ |
| **Signing** | 28 plans | Delineator Drums; Object Markers - Culverts; Reset Sign Panel | — | ☐ Keep as flag ☐ Count it as ______ |
| **Fabric, geogrid, geotextile** | 24 plans | Geosynthetic Material Type Rr; Geosynthetic Material Type G; Geosynthetic Material Type R1 | 266,118 SY | ☐ Keep as flag ☐ Count it as ______ |
| **Testing & quality management** | 22 plans | Bituminous Laboratory; Hma - Bituminous Materials; E-Ticketing | 33,818 TON | ☐ Keep as flag ☐ Count it as ______ |
| **Concrete flatwork (curb, gutter, sidewalk, PCC)** | 20 plans | Concrete Walk; Truncated Domes; Sidewalk Concrete | 2,186 SY | ☐ Keep as flag ☐ Count it as ______ |
| **Sawing** | 17 plans | Sawing Bituminous Pavement; Sawing Bit Pavement; Sawing Concrete Pavement | — | ☐ Keep as flag ☐ Count it as ______ |
| **Seal coat / chip seal / blotter** | 15 plans | Bituminous Seal Coat; Blotter Material Cl 44 | 37,712 SY; 5,700 TON | ☐ Keep as flag ☐ Count it as ______ |
| **Utilities** | 14 plans | Hydrant; Gate Valve & Box; Connect To Existing Sanitary Sewer | — | ☐ Keep as flag ☐ Count it as ______ |
| **Clearing & grubbing** | 12 plans | Grubbing; Clearing & Grubbing; Clearing | — | ☐ Keep as flag ☐ Count it as ______ |
| **Guardrail** | 7 plans | Remove & Reset Guardrail; Remove Guardrail; Remove Guardrail - Plate Beam | — | ☐ Keep as flag ☐ Count it as ______ |
| **Equipment rental (hourly)** | 6 plans | Motor Grader; Skid Loader; Sediment Removal Backhoe | — | ☐ Keep as flag ☐ Count it as ______ |
| **Water & dust control** | 1 plans | Calcium Chloride Solution | — | ☐ Keep as flag ☐ Count it as ______ |

Two we want to call out specifically:

- **Crushing and stockpile.** Your spreadsheet has columns for both, but they are filled on under 5% of historical rows, and in 117 plans we found 1 with stockpile and 0 with crushing. We treat them as internal sourcing decisions rather than plan quantities. Correct?
- **Riprap** sits under structures, not asphalt — it is quarried rock slope protection at culvert ends and on slopes, measured in CY/TON. Flagging it because an early draft of our asphalt list had it in the wrong place.

---

# Part 3 — Materials we could not place

45 priced materials carrying a real quantity that we could not confidently assign to any column. These are the ones most likely to be wrong, so they are worth your eyes even though the quantities are smaller.

| Material | Seen in | States | Unit | Total qty | Which column? |
|---|---|---|---|---|---|
| Concrete Driveway Pavement | 6 plans | MN | SY | 1,631 SY | ☐ Mixed_tons ☐ base_tons ☐ shldr_tons ☐ grading_yards ☐ mill_sy ☐ Do not count |
| Penetrating Water Repellent Treatment | 2 plans | ND | SY | 1,524 SY | ☐ Mixed_tons ☐ base_tons ☐ shldr_tons ☐ grading_yards ☐ mill_sy ☐ Do not count |
| Reinforcement Fabric | 2 plans | SD | SY | 945 SY | ☐ Mixed_tons ☐ base_tons ☐ shldr_tons ☐ grading_yards ☐ mill_sy ☐ Do not count |
| Controlled Density Fill | 2 plans | SD | CY | 88 CY | ☐ Mixed_tons ☐ base_tons ☐ shldr_tons ☐ grading_yards ☐ mill_sy ☐ Do not count |
| Concrete Valley Gutter | 2 plans | MN | SY | 54 SY | ☐ Mixed_tons ☐ base_tons ☐ shldr_tons ☐ grading_yards ☐ mill_sy ☐ Do not count |
| Structural Concrete | 2 plans | MN,ND | CY | 37 CY | ☐ Mixed_tons ☐ base_tons ☐ shldr_tons ☐ grading_yards ☐ mill_sy ☐ Do not count |
| Non-Reinf Concrete Pvmt Cl Ae- Doweled | 1 plans | ND | SY | 11,285 SY | ☐ Mixed_tons ☐ base_tons ☐ shldr_tons ☐ grading_yards ☐ mill_sy ☐ Do not count |
| Concrete Penetrating Sealer | 1 plans | SD | SY | 1,506 SY | ☐ Mixed_tons ☐ base_tons ☐ shldr_tons ☐ grading_yards ☐ mill_sy ☐ Do not count |
| Concrete Median Paving | 1 plans | ND | SY | 1,088 SY | ☐ Mixed_tons ☐ base_tons ☐ shldr_tons ☐ grading_yards ☐ mill_sy ☐ Do not count |
| Salvage And Reuse Existing Aggregate | 1 plans | ND | CY | 1,000 CY | ☐ Mixed_tons ☐ base_tons ☐ shldr_tons ☐ grading_yards ☐ mill_sy ☐ Do not count |
| Non Reinf Concrete Pvmt Cl Ae-Doweled | 1 plans | ND | SY | 933 SY | ☐ Mixed_tons ☐ base_tons ☐ shldr_tons ☐ grading_yards ☐ mill_sy ☐ Do not count |
| Rapid Stabilization Method 4 | 1 plans | MN | SY | 780 SY | ☐ Mixed_tons ☐ base_tons ☐ shldr_tons ☐ grading_yards ☐ mill_sy ☐ Do not count |
| Clean Rock | 1 plans | ND | TON | 758 TON | ☐ Mixed_tons ☐ base_tons ☐ shldr_tons ☐ grading_yards ☐ mill_sy ☐ Do not count |
| Granular Bedding | 1 plans | MN | CY | 700 CY | ☐ Mixed_tons ☐ base_tons ☐ shldr_tons ☐ grading_yards ☐ mill_sy ☐ Do not count |
| Full Depth Bituminous Street Repair | 1 plans | XX | SY | 478 SY | ☐ Mixed_tons ☐ base_tons ☐ shldr_tons ☐ grading_yards ☐ mill_sy ☐ Do not count |
| Mineral Filler-Cir | 1 plans | MT | TON | 462 TON | ☐ Mixed_tons ☐ base_tons ☐ shldr_tons ☐ grading_yards ☐ mill_sy ☐ Do not count |
| Polystyrene Insulation | 1 plans | MN | SY | 400 SY | ☐ Mixed_tons ☐ base_tons ☐ shldr_tons ☐ grading_yards ☐ mill_sy ☐ Do not count |
| Remove Aggregate | 1 plans | MN | CY | 362 CY | ☐ Mixed_tons ☐ base_tons ☐ shldr_tons ☐ grading_yards ☐ mill_sy ☐ Do not count |
| Granular Backfill | 1 plans | MN | TON | 350 TON | ☐ Mixed_tons ☐ base_tons ☐ shldr_tons ☐ grading_yards ☐ mill_sy ☐ Do not count |
| Granular Foundation Mat'L | 1 plans | MN | CY | 350 CY | ☐ Mixed_tons ☐ base_tons ☐ shldr_tons ☐ grading_yards ☐ mill_sy ☐ Do not count |
| Hydrated Lime | 1 plans | MT | TON | 337 TON | ☐ Mixed_tons ☐ base_tons ☐ shldr_tons ☐ grading_yards ☐ mill_sy ☐ Do not count |
| Class 1-H Removal | 1 plans | ND | SY | 333 SY | ☐ Mixed_tons ☐ base_tons ☐ shldr_tons ☐ grading_yards ☐ mill_sy ☐ Do not count |
| Class 1 Removal | 1 plans | ND | SY | 333 SY | ☐ Mixed_tons ☐ base_tons ☐ shldr_tons ☐ grading_yards ☐ mill_sy ☐ Do not count |
| Remove Driveway Pavement | 1 plans | MN | SY | 236 SY | ☐ Mixed_tons ☐ base_tons ☐ shldr_tons ☐ grading_yards ☐ mill_sy ☐ Do not count |
| Temporary Traffic Surface Aggregate | 1 plans | ND | TON | 200 TON | ☐ Mixed_tons ☐ base_tons ☐ shldr_tons ☐ grading_yards ☐ mill_sy ☐ Do not count |
| Reinforced Concrete Driveway Pavement | 1 plans | MN | SY | 195 SY | ☐ Mixed_tons ☐ base_tons ☐ shldr_tons ☐ grading_yards ☐ mill_sy ☐ Do not count |
| Class A45 Concrete, Drilled Shaft | 1 plans | SD | CY | 182 CY | ☐ Mixed_tons ☐ base_tons ☐ shldr_tons ☐ grading_yards ☐ mill_sy ☐ Do not count |
| Stabilizing Aggregate | 1 plans | MN | CY | 130 CY | ☐ Mixed_tons ☐ base_tons ☐ shldr_tons ☐ grading_yards ☐ mill_sy ☐ Do not count |
| Filter Aggregate, Fa | 1 plans | MN | CY | 100 CY | ☐ Mixed_tons ☐ base_tons ☐ shldr_tons ☐ grading_yards ☐ mill_sy ☐ Do not count |
| Trm Type 1 | 1 plans | ND | SY | 54 SY | ☐ Mixed_tons ☐ base_tons ☐ shldr_tons ☐ grading_yards ☐ mill_sy ☐ Do not count |
| Select Granular Backfill | 1 plans | SD | TON | 49 TON | ☐ Mixed_tons ☐ base_tons ☐ shldr_tons ☐ grading_yards ☐ mill_sy ☐ Do not count |
| Cement Powder Based On 5% | 1 plans | MN | TON | 40 TON | ☐ Mixed_tons ☐ base_tons ☐ shldr_tons ☐ grading_yards ☐ mill_sy ☐ Do not count |
| Fine Aggregate Bedding | 1 plans | MN | CY | 39 CY | ☐ Mixed_tons ☐ base_tons ☐ shldr_tons ☐ grading_yards ☐ mill_sy ☐ Do not count |
| Concrete Median Nose Paving | 1 plans | ND | SY | 36 SY | ☐ Mixed_tons ☐ base_tons ☐ shldr_tons ☐ grading_yards ☐ mill_sy ☐ Do not count |
| Salvage Aggregate | 1 plans | MN | CY | 20 CY | ☐ Mixed_tons ☐ base_tons ☐ shldr_tons ☐ grading_yards ☐ mill_sy ☐ Do not count |
| Coarse Aggregate Bedding | 1 plans | MN | CY | 20 CY | ☐ Mixed_tons ☐ base_tons ☐ shldr_tons ☐ grading_yards ☐ mill_sy ☐ Do not count |
| Overlay Concrete | 1 plans | ND | CY | 19 CY | ☐ Mixed_tons ☐ base_tons ☐ shldr_tons ☐ grading_yards ☐ mill_sy ☐ Do not count |
| Ancillary Armor | 1 plans | MT | CY | 19 CY | ☐ Mixed_tons ☐ base_tons ☐ shldr_tons ☐ grading_yards ☐ mill_sy ☐ Do not count |
| Class 3 Removal | 1 plans | ND | SY | 17 SY | ☐ Mixed_tons ☐ base_tons ☐ shldr_tons ☐ grading_yards ☐ mill_sy ☐ Do not count |
| Porous Backfill | 1 plans | SD | TON | 16 TON | ☐ Mixed_tons ☐ base_tons ☐ shldr_tons ☐ grading_yards ☐ mill_sy ☐ Do not count |

---

# The judgment calls we could not make for you

These are the ones where our best guess could go either way. Ordered by how much quantity rides on the answer.

1. **Full Depth Reclamation — 1,166,000 SY, 14 plans, currently counted as nothing.** FDR grinds the asphalt *and* the base below it into a new base layer. Is that `mill_sy`, is it `grading_yards` because you are rebuilding the roadbed, or does it need its own column?
2. **Milling is measured in TONS in North Dakota — 230,625 T.** MN and SD measure it in SY. `mill_sy` cannot hold both. Separate tons line, or a conversion?
3. **Topsoil — 539,000 CY.** Strip, salvage, borrow and place. Currently filed as erosion control, so it never reaches `grading_yards`. Is topsoil part of your grading number?
4. **Pavement removal.** Mark said pavement removal "is considered grading work" and converts to CY. (a) Does that apply only to pavement and base removal? We have 158 removal item types and most are *remove silt fence*, *remove sign*, *remove pipe*. (b) Is 1.75 Ton/CY your standard factor?
5. **Aggregate Surfacing Class 1 vs Class 5 vs Special — 67,000 T.** We put all of it in `shldr_tons`. Is Class 5 really base material to you?
6. **Salvaged / remove-and-relay base.** The material is re-used, not bought. Does it count toward `base_tons` because you still move and place it?
7. **PG binder, tack and prime — 56,029 T.** We propose excluding these from `Mixed_tons` so mix tonnage is not double-counted (the binder is already inside the mix). Confirm?

---

### Two more things

**Where do you read quantities?** Some projects have a priced bid schedule in the proposal *and* quantity sheets in the plan set (Basis of Estimate / Estimate of Quantities). When they disagree, which do you trust, and which do you read first?

**Does the letting agency change the wording?** Do pay-item names shift between a state DOT job and a county / city / township / SAP-CSAH job, or does everyone in a state use that state's spec book? *(We can see the vocabulary differs by state — MN says "Type SP", ND says "Superpave", SD says "Asphalt Concrete". A state-by-state comparison is a separate piece of work we have not done yet.)*
