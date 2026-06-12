# RAG Query Results — 2026-06-09

Retrieved top-5 chunks per query (cosine distance, lower = closer). Retrieval only (--no-llm).

Distance rule of thumb (from prior runs): **<0.45 strong · 0.45–0.65 moderate · >0.7 weak/likely-absent**.

## Q: What are the prevailing wage or Davis-Bacon wage requirements?

*Why we ask:* CONTROL: smart_truncate drops this mid-doc field (extractor scores 0%). Does RAG recover it? If yes, that's the case for RAG-based extraction.

| # | Document | Page | Section | Distance | Preview |
|--:|---|--:|---|--:|---|
| 1 | 00 Prosoal.pdf | 196 | prevailing_wage | 0.356 | payments to a trustee or other third person, the contractor may classification and wage ra… |
| 2 | 2023_WATONWAN-CO-MN_SP-8303-48.pdf | 355 | contract_front | 0.366 | Bacon and Related Acts contained in 29 CFR parts 1, 3, and 5 workweek of forty hours witho… |
| 3 | 2023_WATONWAN-CO-MN_SP-8303-48.pdf | 352 | contract_front | 0.367 | training is being required by special provision, the contractor than those contained in th… |
| 4 | 00 Prosoal.pdf | 195 | contract_front | 0.373 | will be required to collect and report training data. The wages and bona fide fringe benef… |
| 5 | 00 Prosoal.pdf | 199 | prevailing_wage | 0.383 | clauses shall be inserted in addition to the clauses required by 29 CFR 5.5(a) or 29 CFR 4… |

---

## Q: Are there construction phasing or staging requirements?

*Why we ask:* Known gotcha in SAP 032 (two-phase construction).

| # | Document | Page | Section | Distance | Preview |
|--:|---|--:|---|--:|---|
| 1 | 2023_WATONWAN-CO-MN_SP-8303-48.pdf | 51 | contract_front | 0.411 | SUPPLEMENTAL SPECIFICATIONS To the 2020 Standard Specifications for Construction September… |
| 2 | 2023_DUNN-CO-ND_CP-13.pdf | 15 | bid_schedule | 0.449 | ARTICLE 22 – STATE LAWS AND REGULATIONS 22.01 All applicable laws, ordinances and the rule… |
| 3 | 2023_WALSH-CO-ND_HWY-9.pdf | 60 | contract_front | 0.470 | of the delay, disruption, or interference on the critical path to completion of the Work. … |
| 4 | 9804001.pdf | 61 | contract_front | 0.470 | of the delay, disruption, or interference on the critical path to completion of the Work. … |
| 5 | 2023_BROOKINGS-CO-SD_SURFACING.pdf | 23 | contract_front | 0.470 | 4.01 A pre-bid conference will not be conducted for this Project. ARTICLE 5—SITE AND OTHER… |

---

## Q: Is there a box culvert in the project scope?

*Why we ask:* Both plans have BOX=X — retrieval should hit culvert pay items / notes.

| # | Document | Page | Section | Distance | Preview |
|--:|---|--:|---|--:|---|
| 1 | 08MQ_NonSection.pdf | 25 | general_notes | 0.481 | Q, = Designated peak discharge for the basin approaching Structure Excavation, Box Culvert… |
| 2 | SAP 032-629-048 Plan.pdf | 22 | general_notes | 0.487 | CONSTRUCTION SEQUENCE CONTRACT PAY ITEM FOR FINE AGGREGATE BEDDING INCLUDES THE COST OF EX… |
| 3 | 2023_WATONWAN-CO-MN_SP-8303-48.pdf | 429 | traffic_staging | 0.495 | EXCAVATION AND BACKFILL WITH SELECT GRADING MATERIAL ARE NOT TABULATED SEPARATELY BUT ARE … |
| 4 | 08MQ_NonSection.pdf | 26 | general_notes | 0.496 | I -------{[ r 12. Cost of Preformed Expansion Joint Filler used in apron construction will… |
| 5 | 08MQ_NonSection.pdf | 27 | general_notes | 0.499 | PLANS BY ULTEIG, SIOUX FALLS, SD BRIDGE ENGINEER MH TF MH DESIGNED BY CK. DESIGN BY DRAFTE… |

---

## Q: Is dewatering or groundwater control required?

*Why we ask:* Known gotcha in 08MQ (box culvert dewatering, groundwater elev 1442).

| # | Document | Page | Section | Distance | Preview |
|--:|---|--:|---|--:|---|
| 1 | 2023_WATONWAN-CO-MN_SP-8303-48.pdf | 517 | special_provisions | 0.424 | Temporary dewatering activities may be required for roadway construction and utility work.… |
| 2 | 2023_YANKTON-CO-SD_P-PH-0052.pdf | 89 | title_index | 0.426 | I DEWATERING AND SEDIMENT COLLECTING CONSTRUCTION ENTRANCE I STATEOF III- ____P _R_OJ_EC_T… |
| 3 | 08MQ_NonSection.pdf | 3 | unknown | 0.442 | vegetation must be removed and all compartments and tanks capable of holding standing wate… |
| 4 | 2023_YANKTON-CO-SD_P-PH-0052.pdf | 6 | unknown | 0.478 | pollutants are suspected of being discharged, a sample must be taken for The seeding recom… |
| 5 | 2023_WATONWAN-CO-MN_SP-8303-48.pdf | 191 | traffic_staging | 0.480 | (1) Bypass Flows for all Culvert Sites Type 2 and Type 3 are listed in the Plans, and for … |

---

## Q: Are there historic bridge, Section 4(f), or MOA cultural resource requirements?

*Why we ask:* Known gotcha in 08MQ (NRHP-eligible historic bridge, MOA).

| # | Document | Page | Section | Distance | Preview |
|--:|---|--:|---|--:|---|
| 1 | 00 Prosoal.pdf | 262 | special_provisions | 0.494 | S.P. 083-090-006 SB-1.8 Pre-fabricated Superstructure Plan Requirements and Submittals Pre… |
| 2 | 08MQ_NonSection.pdf | 5 | unknown | 0.500 | Removal of existing fencing, Furnish and install temporary and/or Temporary fence and/or p… |
| 3 | 2023_BROOKINGS-CO-SD_SURFACING.pdf | 166 | specifications | 0.501 | 23000659 2023 Brookings County Surfacing Project TECHNICAL SPECIFICATIONS (by Reference) G… |
| 4 | 00 Prosoal.pdf | 263 | special_provisions | 0.502 | a) If minor modifications of the substructures are required to accommodate the pedestrian/… |
| 5 | 08MQ_NonSection.pdf | 34 | general_notes | 0.513 | barriers from the end of the bridge and 7'-6" for "Single Slope" shaped barriers from the … |

---

## Q: Is there a high pressure gas line or utility conflict in the project area?

*Why we ask:* Known gotcha in SAP 032 (Enterprise Products high-pressure gas line).

| # | Document | Page | Section | Distance | Preview |
|--:|---|--:|---|--:|---|
| 1 | 2023_WATONWAN-CO-MN_SP-8303-48.pdf | 114 | contract_front | 0.606 | S.P. 8303-48 (TH 15/TH 30=015) S.P. 8304-123 (TH 15/TH 60=015) December 12, 2022 confirm t… |
| 2 | 9758035.pdf | 46 | contract_front | 0.613 | cost when the delay in completion of the WORK is due to the following, and the CONTRACTOR … |
| 3 | 2023_DUNN-CO-ND_CP-13.pdf | 49 | contract_front | 0.615 | or physical conditions relating to existing surface or subsurface structures at the Site (… |
| 4 | 2023_WATONWAN-CO-MN_SP-8303-48.pdf | 517 | special_provisions | 0.619 | Temporary dewatering activities may be required for roadway construction and utility work.… |
| 5 | 2023_YANKTON-CO-SD_P-PH-0052.pdf | 103 | traffic_staging | 0.625 | STATE OF PROJECT SHEET S T H O E T E A T L S SOUTH P-PH 0052(08)332 DAKOTA D19 D31 Plottin… |

---

## Q: Are there seasonal work restrictions for endangered species like the NLEB or whooping crane?

*Why we ask:* Known gotcha in 08MQ (NLEB Apr15-Oct31, whooping crane stoppage).

| # | Document | Page | Section | Distance | Preview |
|--:|---|--:|---|--:|---|
| 1 | 08MQ_NonSection.pdf | 2 | unknown | 0.464 | An adult Whooping Crane is white with a red 120E0600 Contractor Furnished Borrow Excavatio… |
| 2 | 2023_YANKTON-CO-SD_P-PH-0052.pdf | 5 | unknown | 0.486 | These environmental commitments are not subject to change 29+00 - one-quarter mile of a kn… |
| 3 | 00 Prosoal.pdf | 253 | contract_front | 0.512 | Project code: 2024-0087421 05/08/2024 15:49:36 UTC QUALIFICATION INTERVIEW 1. This determi… |
| 4 | 00 Prosoal.pdf | 251 | contract_front | 0.536 | Project code: 2024-0087421 05/08/2024 15:49:36 UTC species or designated critical habitat … |
| 5 | 00 Prosoal.pdf | 234 | contract_front | 0.538 | Migratory Bird Treaty Act Based on the proposed scope of work proposed and/or the timing o… |

---

## Q: What is the total tonnage of hot mix asphalt (HMA / mix)?

*Why we ask:* Quantity retrieval — should hit the bid schedule / estimated quantities.

| # | Document | Page | Section | Distance | Preview |
|--:|---|--:|---|--:|---|
| 1 | 2023_YANKTON-CO-SD_P-PH-0052.pdf | 113 | title_index | 0.309 | prior to stockpiling the material within the aforementioned site. 270E0200 Blend. Haul, an… |
| 2 | 2023_WATONWAN-CO-MN_SP-8303-48.pdf | 261 | bid_schedule | 0.352 | 2360 Mineral Filler 2360 1 per shipment of 50 tons or less, unless previously Testing as d… |
| 3 | 2023_WATONWAN-CO-MN_SP-8303-48.pdf | 272 | special_provisions | 0.390 | MnDOT SD-15 August 27, 2021 Schedule of Materials Control for 2020 Standard Specifications… |
| 4 | 2023_YANKTON-CO-SD_P-PH-0052.pdf | 119 | title_index | 0.391 | PG 64-34 Asphalt Binder 143 Tons feet wide (Rate= 0.05 gallon per square yard). ~ CLASS Q3… |
| 5 | 2023_YANKTON-CO-SD_P-PH-0052.pdf | 117 | title_index | 0.392 | 260+71 WBPL 1 1 1.0 and repair of the existing surface for Section 9. 265+53 TL 1 1 1.0 4.… |

---

## Q: What earthwork or grading excavation quantity in cubic yards is required?

*Why we ask:* Quantity retrieval — grade_cy; tests bid-schedule retrieval.

| # | Document | Page | Section | Distance | Preview |
|--:|---|--:|---|--:|---|
| 1 | 2023_YANKTON-CO-SD_P-PH-0052.pdf | 10 | title_index | 0.366 | A copy of the subsurface/subgrade investigation is available at the Mitchell excavation fr… |
| 2 | 2023_YANKTON-CO-SD_P-PH-0052.pdf | 10 | title_index | 0.406 | However, the Engineer quantity will be used for final payment and the plans quantity of To… |
| 3 | 08MQ_NonSection.pdf | 6 | unknown | 0.420 | STATE OF PROJECT SHEET S T H O E T E A T L S FOR BIDDING PURPOSES ONLY D S A O K U O T T H… |
| 4 | 2023_WATONWAN-CO-MN_SP-8303-48.pdf | 80 | title_index | 0.420 | Add the following to 2574.5, “Soil Preparation, Basis of Payment”: C. Unit Prices In addit… |
| 5 | 2023_DUNN-CO-ND_CP-13.pdf | 134 | title_index | 0.423 | SUMMARY OF QUANTITIES WATER 20 Gal/Ton Aggr. Base Course 100 Mgal/Mile Dust Palliative (11… |

---

## Q: What is the marketing budget and social media advertising plan for this project?

*Why we ask:* CONTROL: absent topic. Correct behaviour = 'Not found in the retrieved sections.'

| # | Document | Page | Section | Distance | Preview |
|--:|---|--:|---|--:|---|
| 1 | 2023_WATONWAN-CO-MN_SP-8303-48.pdf | 386 | bid_schedule | 0.708 | 12/07/2022 Minnesota Department Of Transportation Proposal Schedule of Items Page 4 of 10 … |
| 2 | 2023_WATONWAN-CO-MN_SP-8303-48.pdf | 109 | contract_front | 0.724 | The Contractor must complete and submit a Workforce Plan if the low bid amount is $5,000,0… |
| 3 | 9758035.pdf | 17 | contract_front | 0.732 | Docusign Envelope ID: E2F6D524-F5AE-470F-8E24-37489C1839D5 County Road 68 Emergency Grade … |
| 4 | 2023_YANKTON-CO-SD_P-PH-0052.pdf | 4 | unknown | 0.739 | STATE OF PROJECT SHEET S T H O E T E A T L S ESTIMATE OF QUANTITIES AND ENVIRONMENTAL COMM… |
| 5 | 2023_YANKTON-CO-SD_P-PH-0052.pdf | 3 | unknown | 0.740 | STATE OF PROJECT SHEET S T H O E T E A T L S ESTIMATE OF QUANTITIES AND ENVIRONMENTAL COMM… |

---

