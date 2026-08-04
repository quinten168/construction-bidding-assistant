# Material map — master table

Generated 2026-07-30 by `04_tools/11_build_material_map.py` from the 6,385-line corpus. Do not hand-edit — edit `FAMILIES` in the script and re-run.

`CONFIRMED` = safe to wire. `NEEDS_CSI_RULING` = a judgment call, not wired until CSI answers (see `2026-07-30_material_mapping_for_CSI.md`).

## ASPHALT — MIX TN — hot mix placed, tons

| Family | Status | Unit | Matches on | Example pay items (corpus) | Plans | Quantity |
|---|---|---|---|---|---|---|
| `hot_mix_placed` | CONFIRMED | TON | SUPERPAVE, TYPE SP, WEARING COURSE, WEAR COURSE, NON WEAR… | Extend Runway 15-33 1,000 Ft On North End With Hot Mix Asphaltic Concr; Superpave Faa 45; Rap - Superpave Faa 43 | 53 | SY 111,378; TON 1,170,194 |
| `asphalt_patching` | NEEDS_CSI_RULING ⚠ | TON|SY | PATCHING, PATCH | Patching; Bituminous Base Patch Special; Asphalt Patching - 4" Hbp (Faa 43, Pg58S-34), 9" Aggregate (Cl 5) | 5 | SY 10,420; TON 487 |

## BASE — BASE TN — aggregate base placed, tons

| Family | Status | Unit | Matches on | Example pay items (corpus) | Plans | Quantity |
|---|---|---|---|---|---|---|
| `salvaged_base` | NEEDS_CSI_RULING ⚠ | TON|SY | SALVAGED BASE, BASE COURSE, SALVAGED, REMOVE AND RELAY, RECYCLED PAVEMENT, SALVAGED AGGREGATE… | Remove And Relay Salvaged Base Course; Salvaged Base Course; Base Course, Salvaged | 5 | SY 83,437; TON 14,026 |
| `aggregate_base_placed` | CONFIRMED | TON | AGGREGATE BASE, BASE COURSE, SUBBASE, CLASS 5 AGGREGATE, 2211 | Cl 5 Aggregate Base Ton 20 10 10 670; Aggregate Base Course Cl 5; Cement Stabilized Base Course | 43 | CY 25,956; SY 576,355; TON 818,890 |
| `stabilized_base` | NEEDS_CSI_RULING ⚠ | SY|TON | CEMENT STABILIZED, STABILIZED BASE, STABILIZED SUBGRADE, SOIL STABILIZATION, LIQUID BASE STABILIZER… | Cement Stabilized Subgrade - 12 Inch; Cement Treated Subgrade; Soil Stabilization | 9 | SY 196,658; TON 13,322 |

## SHOULDER — SHLDR TN — shoulder / surfacing gravel, tons

| Family | Status | Unit | Matches on | Example pay items (corpus) | Plans | Quantity |
|---|---|---|---|---|---|---|
| `shoulder_aggregate` | CONFIRMED | TON | SHOULDER BASE AGGREGATE, SHOULDER GRAVEL, SHOULDER AGGREGATE | Shoulder Base Aggregate, Cl 1; Shoulder Base Aggregate Class 1; Shoulder Gravel | 4 | CY 156; TON 12,100 |
| `aggregate_surfacing` | NEEDS_CSI_RULING ⚠ | TON | AGGREGATE SURFACING, AGGREGATE SURACING, AGGREGATE SURFACE COURSE, GRAVEL SURFACING, TRAFFIC SERVICE AGGREGATE… | Aggregate Surfacing Class 1; Aggregate Surfacing Class 1 Mod.; Graunular Material, Furnish | 30 | CY 2,046; SY 38; TON 67,031 |

## GRADING — GRADE CY — earthwork, cubic yards

| Family | Status | Unit | Matches on | Example pay items (corpus) | Plans | Quantity |
|---|---|---|---|---|---|---|
| `removal_pavement` | NEEDS_CSI_RULING ⚠ | SY|TON | REMOVE BITUMINOUS, REMOVAL OF BITUMINOUS, REMOVE AND DISPOSE OF BITUMINOUS, REMOVE CONCRETE PAVEMENT, REMOVE CONCRETE DRIVEWAY… | Remove Aggregate Base & Surfacing; Remove Aggregate Base; Remove Bituminous Pavement | 25 | SY 67,840; TON 208,440 |
| `special_excavation` | NEEDS_CSI_RULING ⚠ | CY | ROCK EXCAVATION, EXCAVATION - ROCK, EXCAVATION ROCK, MUCK EXCAVATION, EXCAVATION - MUCK… | Excavation - Muck; Undercutting; Excavation - Subgrade | 23 | CY 46,223; SY 1,495; TON 2,482 |
| `topsoil` | NEEDS_CSI_RULING ⚠ | CY | TOPSOIL, LOAM TOPSOIL | Topsoil; Topsoil-Borrow Area; Topsoil Stripping & Spreading | 27 | CY 539,185; SY 30,000; TON 285 |
| `earthwork` | CONFIRMED | CY | COMMON EXCAVATION, EXCAVATION - COMMON, EXCAVATION COMMON, EXCAVATION AND EMBANKMENT, UNCLASSIFIED EXCAVATION… | Excavation - Common; Common Embankment (Cv); Borrow-Excavation | 42 | CY 2,109,392 |
| `subgrade_prep` | NEEDS_CSI_RULING ⚠ | SY|RDST | SUBGRADE PREPARATION, SUBGRADE PREP | Subgrade Preparation; Subgrade Preparation-Type A-12In; Subgrade Preparation (P) | 13 | SY 52,544 |

## MILLING — MILL SY — surface removal, square yards

| Family | Status | Unit | Matches on | Example pay items (corpus) | Plans | Quantity |
|---|---|---|---|---|---|---|
| `cold_milling` | CONFIRMED | SY | MILL BITUMINOUS, COLD MILLING, MILLING PAVEMENT, MILL TRANSITION, COLD PLANE… | Milling Pavement Surface; Mill Bituminous Surfacing 1.5" (P); Mill Bituminous Surface (2.0") | 36 | SY 1,591,713; TON 230,625 |
| `full_depth_reclamation` | NEEDS_CSI_RULING ⚠ | SY | FULL DEPTH RECLAMATION, RECLAMATION, RECLAIM | Full Depth Reclamation; Full Depth Reclamation (P); Stabilized Full Depth Reclamation (P) | 14 | SY 1,198,979 |
| `cold_recycle` | NEEDS_CSI_RULING ⚠ | SY|TON | COLD RECYCLED, COLD IN PLACE, CIR , RECYCLING AGENT | Cold Recycled Plant Mix; Recycling Agent Cir-Ee | 1 | SY 285,692; TON 1,377 |

## OTHER — not a CSI quantity — tracked as a scope flag only

| Family | Status | Unit | Matches on | Example pay items (corpus) | Plans | Quantity |
|---|---|---|---|---|---|---|
| `sawing` | NEEDS_CSI_RULING ⚠ | LF | SAWING, SAW CUT, SAWCUT | Sawing Bituminous Pavement (Full Depth); Saw Cut Bituminous Pavement; Sawing Bit Pavement (Full Depth) | 17 | — |
| `removal_other` | CONFIRMED | * | REMOVE SILT FENCE, REMOVE FIBER ROLL, REMOVE SIGN, SALVAGE SIGN, REMOVAL OF PIPE… | Remove Fiber Rolls 12In; Remove Silt Fence; Remove Silt Fence Unsupported | 30 | CY 10 |
| `signing` | CONFIRMED | * | SIGN TYPE, SIGN PANEL, SIGN POST, INSTALL SIGN, DELINEATOR… | Traffic Barrier Design Type 31; Delineator Drums; Traffic Barrier Design Bullnose | 28 | — |
| `asphalt_qc` | CONFIRMED | * | BITUMINOUS LABORATORY, INTELLIGENT COMPACTION, E TICKETING, E-TICKETING, QUALITY MANAGEMENT… | Quality Management - E Ticketing; Quality Management - E-Ticketing; Quality Management -E- Ticketing | 22 | TON 33,818 |
| `asphalt_binder` | NEEDS_CSI_RULING ⚠ | TON|GAL | ASPHALT CEMENT, TACK COAT, PRIME COAT, FOG SEAL, EMULSIFIED ASPHALT… | Tack Coat; Prime Coat; Bituminous Material For Tack Coat | 33 | TON 56,029 |
| `seal_coat` | NEEDS_CSI_RULING ⚠ | TON|SY | SEAL COAT, CHIP SEAL, FLUSH SEAL, BLOTTER | Bituminous Seal Coat; Blotter Material Cl 44 | 15 | SY 37,712; TON 5,700 |
| `geosynthetic` | NEEDS_CSI_RULING ⚠ | SY | GEOSYNTHETIC, GEOGRID, GEOTEXTILE, SEPARATION FABRIC, DRAINAGE FABRIC | Geosynthetic Material Type G; Geosynthetic Material Type Rr; Geosynthetic Material Type R1 | 24 | SY 266,118 |
| `clearing` | NEEDS_CSI_RULING ⚠ | ACRE|EA | CLEARING, GRUBBING | Grubbing; Clearing; Clearing And Grubbing | 12 | — |
| `equipment_rental` | CONFIRMED | HOUR | MOTOR GRADER, CU YD TRUCK, FRONT END LOADER, SKID LOADER, DOZER… | Motor Grader; Skid Loader; Dozer | 6 | — |
| `traffic_control` | CONFIRMED | * | TRAFFIC CONTROL, FLAGGING, PILOT CAR, BARRICADE, LANE CLOSURE… | Work Zone Traffic Control Cp-3836(023) & Cp-3836(023) Spur; Work Zone Traffic Control Cp-3823(023); Rumble Strips - Asphalt Shoulder | 63 | — |
| `pavement_marking` | CONFIRMED | * | PAVEMENT MARKING, PVMT MK, PAINTED, EPOXY, STRIPING | Williams County, Nd Sta 90+00 To 110+00 Permanent Striping County Road; Williams County, Nd Sta 70+00 To 90+00 Permanent Striping County Road ; Williams County, Nd Sta 50+00 To 70+00 Permanent Striping County Road  | 36 | — |
| `erosion_turf` | CONFIRMED | * | SILT FENCE, EROSION, SEEDING, SEED , MULCH… | Williams County, Nd Sta 110+00 To 116+36 Permanent Erosion Control Cou; Williams County, Nd Sta 90+00 To 110+00 Permanent Erosion Control Coun; Williams County, Nd Sta 30+00 To 50+00 Permanent Erosion Control Count | 48 | CY 164; SY 226,424; TON 202 |
| `structures` | CONFIRMED | * | RIPRAP, RIP RAP, CULVERT, BRIDGE, PIPE… | Sap 065-599-098 - Sacred Heart Township Construct Bridge # 65K12 On 80; 065-599-098 Bridge Participating:; 065-599-097 Bridge Participating: | 40 | CY 197,582; SY 682; TON 13,068 |
| `concrete` | NEEDS_CSI_RULING ⚠ | * | CURB AND GUTTER, CURB & GUTTER, SIDEWALK, CONCRETE PAVEMENT, CONCRETE WALK… | 4" Concrete Walk; 6" Concrete Walk; Concrete Curb & Gutter Design B424 | 20 | SY 2,186 |
| `guardrail` | CONFIRMED | * | GUARDRAIL, END TERMINAL, CABLE BARRIER, CRASH CUSHION | Remove Guardrail; Remove Guardrail - Plate Beam; Mgs Guardrail | 7 | — |
| `utilities` | CONFIRMED | * | WATER MAIN, SANITARY SEWER, HYDRANT, CONDUIT, CASING… | Clean And Televise Sanitary Sewer Service Laterals; 2" Non-Metallic Conduit; 8" Sanitary Sewer | 14 | — |
| `water_dust` | CONFIRMED | * | DUST CONTROL, DUST PALLIATIVE, CALCIUM CHLORIDE, WATER FOR | Calcium Chloride Solution | 1 | — |
| `mobilization_admin` | CONFIRMED | LS | MOBILIZATION, CONTRACT BOND, FIELD OFFICE, AS BUILT, HAUL ROADS | Mobilization; Contract Bond; Field Office | 59 | — |

---

**16 of 33 families still need a CSI ruling.** Full per-item evidence: `2026-07-30_material_map_EVIDENCE.csv`.
