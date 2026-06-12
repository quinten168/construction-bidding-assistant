# RAG Corpus Report — 2026-06-11

Vector DB: `/Users/t/Library/Mobile Documents/com~apple~CloudDocs/00 MSBA + Coding/00_summer 2026/00_CSI_ELP/01_Summer_2026/02_modules/plan_reader/06_chroma`  ·  collection `csi_plans`  ·  embedding `all-MiniLM-L6-v2` (384-dim, cosine)

**4,338 chunks** across **11 documents**.

## Chunks per document

| Document | Chunks |
|---|--:|
| 2023_WATONWAN-CO-MN_SP-8303-48_LOST | 1061 |
| 2025_DOUGLAS-CO-MN_SAP-021-600-023_NOBID | 884 |
| 2025_WATONWAN-CO-MN_WATLINE-TRAIL_NOBID | 478 |
| 2023_YANKTON-CO-SD_P-PH-0052_WON | 399 |
| 2023_DUNN-CO-ND_CP-13_WON | 327 |
| 2025_JACKSON-CO-MN_SAP-032-629-048_NOBID | 324 |
| 2025_HAND-CO-SD_08MQ_NOBID | 323 |
| 2023_WALSH-CO-ND_HWY-9_LOST | 177 |
| 2025_STUTSMAN-CO-ND_CR-68_NOBID | 162 |
| 2023_BROOKINGS-CO-SD_SURFACING_LOST | 149 |
| 2023_OTTER-TAIL-CO-MN_CP-4069-304_LOST | 54 |

## Section tag distribution (heuristic tagger)

Soft signal only — used for citations + optional `--section` filtering. A high `unknown` share means the header patterns miss that DOT's format.

| Section | Chunks | Share |
|---|--:|--:|
| bid_schedule | 986 | 23% |
| title_index | 514 | 12% |
| special_provisions | 497 | 11% |
| general_notes | 472 | 11% |
| traffic_staging | 449 | 10% |
| proposal_front_data | 357 | 8% |
| contract_front | 276 | 6% |
| prevailing_wage | 250 | 6% |
| agreement | 235 | 5% |
| eeo_federal | 88 | 2% |
| specifications | 75 | 2% |
| geotechnical | 63 | 1% |
| prosecution_of_work | 41 | 1% |
| general_conditions | 24 | 1% |
| bonds_forms | 10 | 0% |
| unknown | 1 | 0% |

## Chunk size distribution (words per chunk)

Target is ~350 words / ~50 overlap (set in `lib.chunk_text`).

| Stat | Words | Chars |
|---|--:|--:|
| min | 3 | 24 |
| p25 | 207 | 1,304 |
| median | 321 | 2,135 |
| p75 | 345 | 3,021 |
| max | 9988 | 140,762 |

### Section mix per document

- **2023_BROOKINGS-CO-SD_SURFACING_LOST** — agreement 51, title_index 33, traffic_staging 24, contract_front 19
- **2023_DUNN-CO-ND_CP-13_WON** — bid_schedule 204, agreement 64, special_provisions 20, contract_front 13
- **2023_OTTER-TAIL-CO-MN_CP-4069-304_LOST** — bid_schedule 34, contract_front 10, traffic_staging 7, proposal_front_data 2
- **2023_WALSH-CO-ND_HWY-9_LOST** — special_provisions 77, agreement 36, specifications 22, contract_front 12
- **2023_WATONWAN-CO-MN_SP-8303-48_LOST** — general_notes 370, traffic_staging 204, title_index 149, special_provisions 89
- **2023_YANKTON-CO-SD_P-PH-0052_WON** — title_index 296, traffic_staging 60, proposal_front_data 20, general_notes 19
- **2025_DOUGLAS-CO-MN_SAP-021-600-023_NOBID** — bid_schedule 482, special_provisions 135, prevailing_wage 120, agreement 54
- **2025_HAND-CO-SD_08MQ_NOBID** — proposal_front_data 323
- **2025_JACKSON-CO-MN_SAP-032-629-048_NOBID** — bid_schedule 222, general_notes 83, traffic_staging 18, proposal_front_data 1
- **2025_STUTSMAN-CO-ND_CR-68_NOBID** — traffic_staging 85, geotechnical 37, contract_front 28, specifications 6
- **2025_WATONWAN-CO-MN_WATLINE-TRAIL_NOBID** — special_provisions 175, prevailing_wage 130, contract_front 86, prosecution_of_work 37
