# RAG Query Results — 2026-06-11

Retrieved top-5 chunks per query (cosine distance, lower = closer). Retrieval only (--no-llm).

Distance rule of thumb (from prior runs): **<0.45 strong · 0.45–0.65 moderate · >0.7 weak/likely-absent**.

## Q: What are the prevailing wage or Davis-Bacon wage requirements?

*Why we ask:* CONTROL: smart_truncate drops this mid-doc field (extractor scores 0%). Does RAG recover it? If yes, that's the case for RAG-based extraction.

| # | Document | Page | Section | Distance | Preview |
|--:|---|--:|---|--:|---|
| 1 | 2023_WATONWAN-CO-MN_SP-8303-48_LOST | 353 | eeo_federal | 0.284 | Whenever the minimum wage rate prescribed in the contract for a class of laborers or mecha… |
| 2 | 2025_WATONWAN-CO-MN_WATLINE-TRAIL_NOBID | 196 | prevailing_wage | 0.361 | e. _Unfunded plans._ If the contractor does not make payments to a trustee or other third … |
| 3 | 2023_WATONWAN-CO-MN_SP-8303-48_LOST | 352 | eeo_federal | 0.366 | under the Copeland Act (29 CFR part 3)), the full amount of wages and bona fide fringe ben… |
| 4 | 2023_WATONWAN-CO-MN_SP-8303-48_LOST | 353 | eeo_federal | 0.382 | of the wages required by the contract, the contracting agency may, after written notice to… |
| 5 | 2025_WATONWAN-CO-MN_WATLINE-TRAIL_NOBID | 197 | prevailing_wage | 0.413 | [benefits under a plan or program described in 40 U.S.C.](https://www.govinfo.gov/link/usc… |

---

## Q: Are there construction phasing or staging requirements?

*Why we ask:* Known gotcha in SAP 032 (two-phase construction).

| # | Document | Page | Section | Distance | Preview |
|--:|---|--:|---|--:|---|
| 1 | 2025_DOUGLAS-CO-MN_SAP-021-600-023_NOBID | 65 | agreement | 0.437 | Contractor’s cost of, or time required for, performance of the Work; subject, however, to … |
| 2 | 2023_WATONWAN-CO-MN_SP-8303-48_LOST | 51 | contract_front | 0.442 | **SUPPLEMENTAL SPECIFICATIONS** To the 2020 Standard Specifications for Construction Septe… |
| 3 | 2025_HAND-CO-SD_08MQ_NOBID | 9 | proposal_front_data | 0.446 | Documentation of the<br>preconstruction meeting will be filed with the SWPPP documents.<br… |
| 4 | 2025_HAND-CO-SD_08MQ_NOBID | 9 | proposal_front_data | 0.446 | Documentation of the<br>preconstruction meeting will be filed with the SWPPP documents.<br… |
| 5 | 2023_DUNN-CO-ND_CP-13_WON | 15 | bid_schedule | 0.464 | **ARTICLE 22 – STATE LAWS AND REGULATIONS** 22.01 All applicable laws, ordinances and the … |

---

## Q: Is there a box culvert in the project scope?

*Why we ask:* Both plans have BOX=X — retrieval should hit culvert pay items / notes.

| # | Document | Page | Section | Distance | Preview |
|--:|---|--:|---|--:|---|
| 1 | 2025_WATONWAN-CO-MN_WATLINE-TRAIL_NOBID | 218 | prevailing_wage | 0.459 | All maintenance excavation shall be limited to no<br>more than the channel dimensions (len… |
| 2 | 2025_JACKSON-CO-MN_SAP-032-629-048_NOBID | 23 | general_notes | 0.460 | EXCAVATION AND BACKFILL WITH COMMON EMBANKMENT ARE NOT TABULATED SEPARATELY BUT ARE INCLUD… |
| 3 | 2025_HAND-CO-SD_08MQ_NOBID | 31 | proposal_front_data | 0.483 | W - Outside Face of Wing Wall<br>Box Culvert Box Culvert I.F. WW - Inside Face of Wing Wal… |
| 4 | 2023_WATONWAN-CO-MN_SP-8303-48_LOST | 429 | traffic_staging | 0.495 | EXCAVATION AND BACKFILL WITH SELECT GRADING MATERIAL ARE NOT TABULATED SEPARATELY BUT ARE … |
| 5 | 2025_HAND-CO-SD_08MQ_NOBID | 6 | proposal_front_data | 0.505 | The plans quantity for “Contractor Furnished<br>Borrow Excavation” as shown in the Estimat… |

---

## Q: Is dewatering or groundwater control required?

*Why we ask:* Known gotcha in 08MQ (box culvert dewatering, groundwater elev 1442).

| # | Document | Page | Section | Distance | Preview |
|--:|---|--:|---|--:|---|
| 1 | 2023_WATONWAN-CO-MN_SP-8303-48_LOST | 517 | traffic_staging | 0.424 | Temporary dewatering activities may be required for roadway construction and utility work.… |
| 2 | 2023_YANKTON-CO-SD_P-PH-0052_WON | 89 | title_index | 0.426 | I DEWATERING AND SEDIMENT COLLECTING CONSTRUCTION ENTRANCE I STATEOF III- ____P _R_OJ_EC_T… |
| 3 | 2025_HAND-CO-SD_08MQ_NOBID | 3 | proposal_front_data | 0.432 | Erosion and sediment control measures identified in the<br>Wolf Creek is classified as war… |
| 4 | 2025_HAND-CO-SD_08MQ_NOBID | 3 | proposal_front_data | 0.452 | The Storm Water Pollution Prevention Plan (SWPPP) will be developed prior<br>(DANR) and th… |
| 5 | 2025_HAND-CO-SD_08MQ_NOBID | 11 | proposal_front_data | 0.463 | Upon completion of construction, the<br>area at the washout facility will be properly stab… |

---

## Q: Are there historic bridge, Section 4(f), or MOA cultural resource requirements?

*Why we ask:* Known gotcha in 08MQ (NRHP-eligible historic bridge, MOA).

| # | Document | Page | Section | Distance | Preview |
|--:|---|--:|---|--:|---|
| 1 | 2025_WATONWAN-CO-MN_WATLINE-TRAIL_NOBID | 259 | special_provisions | 0.461 | S.P. 083-090-006 **SB-1** **(1502) PRE-FABRICATED PEDESTRIAN/BICYCLE BRIDGE** **SUPERSTRUC… |
| 2 | 2023_BROOKINGS-CO-SD_SURFACING_LOST | 166 | specifications | 0.463 | 23000659 2023 Brookings County Surfacing Project **TECHNICAL SPECIFICATIONS** **(by Refere… |
| 3 | 2025_WATONWAN-CO-MN_WATLINE-TRAIL_NOBID | 262 | special_provisions | 0.494 | S.P. 083-090-006 SB-1.8 Pre-fabricated Superstructure Plan Requirements and Submittals Pre… |
| 4 | 2025_HAND-CO-SD_08MQ_NOBID | 5 | proposal_front_data | 0.496 | Removal of existing fencing, Furnish and install temporary and/or Temporary fence and/or p… |
| 5 | 2025_WATONWAN-CO-MN_WATLINE-TRAIL_NOBID | 263 | special_provisions | 0.509 | a) If minor modifications of the substructures are required to accommodate the pedestrian/… |

---

## Q: Is there a high pressure gas line or utility conflict in the project area?

*Why we ask:* Known gotcha in SAP 032 (Enterprise Products high-pressure gas line).

| # | Document | Page | Section | Distance | Preview |
|--:|---|--:|---|--:|---|
| 1 | 2023_WALSH-CO-ND_HWY-9_LOST | 52 | agreement | 0.575 | General Conditions. 46. _Technical Data_ Environmental Conditions at the Site. available t… |
| 2 | 2025_DOUGLAS-CO-MN_SAP-021-600-023_NOBID | 53 | agreement | 0.575 | General Conditions. 46. _Technical Data_ Environmental Conditions at the Site. available t… |
| 3 | 2023_DUNN-CO-ND_CP-13_WON | 49 | general_conditions | 0.585 | conditions at the Site, then the data contained in boring logs, recorded measurements of s… |
| 4 | 2025_DOUGLAS-CO-MN_SAP-021-600-023_NOBID | 239 | bid_schedule | 0.593 | Accuracy is<br>typically set to 15-mm vertical and to applicable hori-<br>zontal survey an… |
| 5 | 2025_DOUGLAS-CO-MN_SAP-021-600-023_NOBID | 239 | bid_schedule | 0.593 | Accuracy is<br>typically set to 15-mm vertical and to applicable hori-<br>zontal survey an… |

---

## Q: Are there seasonal work restrictions for endangered species like the NLEB or whooping crane?

*Why we ask:* Known gotcha in 08MQ (NLEB Apr15-Oct31, whooping crane stoppage).

| # | Document | Page | Section | Distance | Preview |
|--:|---|--:|---|--:|---|
| 1 | 2025_HAND-CO-SD_08MQ_NOBID | 2 | proposal_front_data | 0.374 | Adult Whooping Cranes' black wing tips are visible<br>during flight.<br> <br>**Action Take… |
| 2 | 2025_HAND-CO-SD_08MQ_NOBID | 2 | proposal_front_data | 0.374 | Adult Whooping Cranes' black wing tips are visible<br>during flight.<br> <br>**Action Take… |
| 3 | 2025_WATONWAN-CO-MN_WATLINE-TRAIL_NOBID | 226 | prevailing_wage | 0.481 | and the pups cannot yet fly. To minimize these impacts, **the DNR recommends that tree** *… |
| 4 | 2023_YANKTON-CO-SD_P-PH-0052_WON | 5 | proposal_front_data | 0.486 | These environmental commitments are not subject to change 29+00 - one-quarter mile of a kn… |
| 5 | 2025_WATONWAN-CO-MN_WATLINE-TRAIL_NOBID | 234 | prevailing_wage | 0.524 | Migratory Bird Treaty Act Based on the proposed scope of work proposed and/or the timing o… |

---

## Q: What is the total tonnage of hot mix asphalt (HMA / mix)?

*Why we ask:* Quantity retrieval — should hit the bid schedule / estimated quantities.

| # | Document | Page | Section | Distance | Preview |
|--:|---|--:|---|--:|---|
| 1 | 2023_YANKTON-CO-SD_P-PH-0052_WON | 113 | title_index | 0.309 | prior to stockpiling the material within the aforementioned site. 270E0200 Blend. Haul, an… |
| 2 | 2023_WATONWAN-CO-MN_SP-8303-48_LOST | 272 | special_provisions | 0.380 | MnDOT SD-15 August 27, 2021 Schedule of Materials Control for 2020 Standard Specifications… |
| 3 | 2023_YANKTON-CO-SD_P-PH-0052_WON | 119 | title_index | 0.391 | PG 64-34 Asphalt Binder 143 Tons feet wide (Rate= 0.05 gallon per square yard). ~ CLASS Q3… |
| 4 | 2023_YANKTON-CO-SD_P-PH-0052_WON | 117 | title_index | 0.392 | 260+71 WBPL 1 1 1.0 and repair of the existing surface for Section 9. 265+53 TL 1 1 1.0 4.… |
| 5 | 2025_DOUGLAS-CO-MN_SAP-021-600-023_NOBID | 174 | prevailing_wage | 0.394 | \|**Production Testing Rates**\|Mixture Moisture Content\|2360.2.G.7.k\|As directed by the Eng… |

---

## Q: What earthwork or grading excavation quantity in cubic yards is required?

*Why we ask:* Quantity retrieval — grade_cy; tests bid-schedule retrieval.

| # | Document | Page | Section | Distance | Preview |
|--:|---|--:|---|--:|---|
| 1 | 2023_YANKTON-CO-SD_P-PH-0052_WON | 10 | title_index | 0.366 | A copy of the subsurface/subgrade investigation is available at the Mitchell excavation fr… |
| 2 | 2025_HAND-CO-SD_08MQ_NOBID | 9 | proposal_front_data | 0.378 | Documentation of the<br>preconstruction meeting will be filed with the SWPPP documents.<br… |
| 3 | 2025_HAND-CO-SD_08MQ_NOBID | 9 | proposal_front_data | 0.378 | Documentation of the<br>preconstruction meeting will be filed with the SWPPP documents.<br… |
| 4 | 2025_HAND-CO-SD_08MQ_NOBID | 6 | proposal_front_data | 0.394 | The plans quantity for “Contractor Furnished<br>Borrow Excavation” as shown in the Estimat… |
| 5 | 2025_HAND-CO-SD_08MQ_NOBID | 6 | proposal_front_data | 0.394 | The plans quantity for “Contractor Furnished<br>Borrow Excavation” as shown in the Estimat… |

---

## Q: What is the marketing budget and social media advertising plan for this project?

*Why we ask:* CONTROL: absent topic. Correct behaviour = 'Not found in the retrieved sections.'

| # | Document | Page | Section | Distance | Preview |
|--:|---|--:|---|--:|---|
| 1 | 2025_STUTSMAN-CO-ND_CR-68_NOBID | 17 | contract_front | 0.720 | Docusign Envelope ID: E2F6D524-F5AE-470F-8E24-37489C1839D5 County Road 68 Emergency Grade … |
| 2 | 2025_WATONWAN-CO-MN_WATLINE-TRAIL_NOBID | 59 | contract_front | 0.721 | **S-1** **(1212) OPENING OF PROPOSALS** The provisions of MnDOT 1212 are modified with the… |
| 3 | 2025_WATONWAN-CO-MN_WATLINE-TRAIL_NOBID | 173 | contract_front | 0.738 | PRE-AWARD A. The Contractor must complete and submit a Workforce Plan if the low bid amoun… |
| 4 | 2023_WATONWAN-CO-MN_SP-8303-48_LOST | 339 | special_provisions | 0.738 | \|~~TOTAL DBE PARTICIPATION DOLLARS BASED ON ADVERTISED DBE GOAL~~(Total prime bid $ * DBE … |
| 5 | 2025_WATONWAN-CO-MN_WATLINE-TRAIL_NOBID | 161 | special_provisions | 0.738 | \|~~TOTAL DBE PARTICIPATION DOLLARS BASED ON ADVERTISED DBE GOAL~~(Total prime bid $ * DBE … |

---

