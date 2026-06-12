# RAG Corpus Report — 2026-06-09

Vector DB: `/Users/t/Library/Mobile Documents/com~apple~CloudDocs/00 MSBA + Coding/00_summer 2026/00_CSI_ELP/01_Summer_2026/02_modules/plan_reader/chroma`  ·  collection `csi_plans`  ·  embedding `all-MiniLM-L6-v2` (384-dim, cosine)

**3,744 chunks** across **11 documents**.

## Chunks per document

| Document | Chunks |
|---|--:|
| 2023_WATONWAN-CO-MN_SP-8303-48.pdf | 1053 |
| 00 Prosoal.pdf | 451 |
| 9804001.pdf | 436 |
| 2023_YANKTON-CO-SD_P-PH-0052.pdf | 325 |
| 2023_DUNN-CO-ND_CP-13.pdf | 308 |
| 2023_WALSH-CO-ND_HWY-9.pdf | 300 |
| 2023_BROOKINGS-CO-SD_SURFACING.pdf | 294 |
| SAP 032-629-048 Plan.pdf | 213 |
| 9758035.pdf | 206 |
| 08MQ_NonSection.pdf | 110 |
| 2023_OTTER-TAIL-CO-MN_CP-4069-304.pdf | 48 |

## Section tag distribution (heuristic tagger)

Soft signal only — used for citations + optional `--section` filtering. A high `unknown` share means the header patterns miss that DOT's format.

| Section | Chunks | Share |
|---|--:|--:|
| contract_front | 1258 | 34% |
| general_notes | 548 | 15% |
| traffic_staging | 460 | 12% |
| title_index | 432 | 12% |
| special_provisions | 384 | 10% |
| bid_schedule | 238 | 6% |
| specifications | 214 | 6% |
| prevailing_wage | 131 | 3% |
| unknown | 76 | 2% |
| proposal_front | 3 | 0% |

## Chunk size distribution (words per chunk)

Target is ~350 words / ~50 overlap (set in `lib.chunk_text`).

| Stat | Words | Chars |
|---|--:|--:|
| min | 2 | 3 |
| p25 | 184 | 1,066 |
| median | 305 | 1,691 |
| p75 | 345 | 2,131 |
| max | 572 | 23,068 |

### Section mix per document

- **2023_BROOKINGS-CO-SD_SURFACING.pdf** — contract_front 211, title_index 45, traffic_staging 26, bid_schedule 11
- **2023_DUNN-CO-ND_CP-13.pdf** — contract_front 176, traffic_staging 57, title_index 32, special_provisions 20
- **2023_OTTER-TAIL-CO-MN_CP-4069-304.pdf** — bid_schedule 29, contract_front 9, traffic_staging 5, proposal_front 3
- **2023_WALSH-CO-ND_HWY-9.pdf** — contract_front 212, special_provisions 60, specifications 20, bid_schedule 6
- **2023_WATONWAN-CO-MN_SP-8303-48.pdf** — general_notes 342, traffic_staging 206, contract_front 170, special_provisions 115
- **2023_YANKTON-CO-SD_P-PH-0052.pdf** — title_index 228, traffic_staging 58, unknown 20, general_notes 19
- **9804001.pdf** — contract_front 213, prevailing_wage 86, traffic_staging 48, general_notes 41
- **08MQ_NonSection.pdf** — general_notes 49, traffic_staging 32, unknown 29
- **SAP 032-629-048 Plan.pdf** — bid_schedule 98, general_notes 97, unknown 14, traffic_staging 4
- **9758035.pdf** — specifications 126, contract_front 73, unknown 4, traffic_staging 3
- **00 Prosoal.pdf** — contract_front 194, special_provisions 187, prevailing_wage 45, traffic_staging 21
