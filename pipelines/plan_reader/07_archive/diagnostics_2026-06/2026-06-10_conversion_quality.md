# PDF→Markdown conversion-quality scorecard (2026-06-10)

**Old path:** pdfplumber `.extract_text()` → flat text, **0 tables**.  
**New path:** pymupdf4llm → Markdown (`core/convert.py`), tables + headings kept.

Question answered (T's Q3): *is conversion good enough, and does it beat the old path?*

## Headline

- **Tables recovered:** 1160 Markdown tables / 10,361 table rows across the corpus — vs **0** on the old flat-text path. The bid-schedule quantity tables (MIX_TN, GRADE_CY, …) now survive as structured rows.
- **Headings recovered:** 93 ATX headings give `detect_section` cleaner anchors.
- **Section-tagger anchors:** taggable pages 421 → 342 (-79).
- **Page fidelity:** 11/11 plans preserved page count exactly.

## Document structure — what kind of docs are these? (T's Q2)

Every per-plan PDF CSI pulls is a **combined proposal+plan** document — a bid schedule and special provisions up front, engineering drawings behind. None are standalone plan-sets, so document-level type is `proposal` across the board. The structural variation that matters is *within* a document (prose vs drawing/spec pages), which is what the section disposition (Task C) acts on.

| Plan | St | doc_type | drawing-pg frac | median chars/pg | image-only pgs |
|---|:--:|:--:|--:|--:|--:|
| 2023_OTTER-TAIL-CO-MN_CP-4069-304_LOST | MN | proposal | 0.09 | 2,105 | 1 |
| 2023_WATONWAN-CO-MN_SP-8303-48_LOST | MN | proposal | 0.09 | 2,442 | 23 |
| 2025_DOUGLAS-CO-MN_SAP-021-600-023_NOBID | MN | proposal | 0.02 | 3,211 | 0 |
| 2025_JACKSON-CO-MN_SAP-032-629-048_NOBID | MN | proposal | 0.71 | 1,852 | 19 |
| 2025_WATONWAN-CO-MN_WATLINE-TRAIL_NOBID | MN | proposal | 0.06 | 2,567 | 2 |
| 2023_DUNN-CO-ND_CP-13_WON | ND | proposal | 0.08 | 3,515 | 8 |
| 2023_WALSH-CO-ND_HWY-9_LOST | ND | proposal | 0.15 | 3,200 | 26 |
| 2025_STUTSMAN-CO-ND_CR-68_NOBID | ND | proposal | 0.54 | 2,299 | 1 |
| 2023_BROOKINGS-CO-SD_SURFACING_LOST | SD | proposal | 0.02 | 3,241 | 0 |
| 2023_YANKTON-CO-SD_P-PH-0052_WON | SD | proposal | 0.28 | 2,079 | 0 |
| 2025_HAND-CO-SD_08MQ_NOBID | SD | proposal | 0.49 | 14,625 | 0 |

## By state

| State | Plans | MD tables | MD table-rows | MD headings | Sec-pages old→new | Scanned pages (old) |
|---|--:|--:|--:|--:|:--:|--:|
| MN | 5 | 777 | 6,855 | 59 | 262→208 | 57 |
| ND | 3 | 246 | 2,181 | 18 | 92→80 | 45 |
| SD | 3 | 137 | 1,325 | 16 | 67→54 | 0 |

## Per plan

| Plan | St | Pages (old/new) | MD tables | MD rows | MD headings | Sec-pages old→new | Scanned(old/new) |
|---|:--:|:--:|--:|--:|--:|:--:|:--:|
| 2023_OTTER-TAIL-CO-MN_CP-4069-304_LOST | MN | 34/34 | 12 | 84 | 14 | 14→10 | 2/2 |
| 2023_WATONWAN-CO-MN_SP-8303-48_LOST | MN | 619/619 | 237 | 2,167 | 29 | 137→103 | 28/27 |
| 2025_DOUGLAS-CO-MN_SAP-021-600-023_NOBID | MN | 252/252 | 88 | 1,252 | 1 | 59→50 | 1/1 |
| 2025_JACKSON-CO-MN_SAP-032-629-048_NOBID | MN | 139/139 | 349 | 2,323 | 3 | 10→5 | 20/20 |
| 2025_WATONWAN-CO-MN_WATLINE-TRAIL_NOBID | MN | 280/280 | 91 | 1,029 | 12 | 42→40 | 6/6 |
| 2023_DUNN-CO-ND_CP-13_WON | ND | 171/171 | 68 | 445 | 2 | 45→36 | 8/8 |
| 2023_WALSH-CO-ND_HWY-9_LOST | ND | 188/188 | 30 | 315 | 15 | 37→33 | 26/26 |
| 2025_STUTSMAN-CO-ND_CR-68_NOBID | ND | 135/135 | 148 | 1,421 | 1 | 10→11 | 11/11 |
| 2023_BROOKINGS-CO-SD_SURFACING_LOST | SD | 166/166 | 25 | 155 | 10 | 41→39 | 0/0 |
| 2023_YANKTON-CO-SD_P-PH-0052_WON | SD | 144/144 | 26 | 510 | 6 | 16→15 | 0/0 |
| 2025_HAND-CO-SD_08MQ_NOBID | SD | 37/37 | 86 | 660 | 0 | 10→0 | 0/0 |

## Reading this

- **MD tables / rows > 0** is the win that matters most: quantities are no longer number-soup. SD plan-sets (drawings) will show fewer tables — that's expected, they *are* drawings, not tabular proposals (see doc-type detection, Task B).
- **Scanned pages (old)** flags plans that will need OCR (docling/LlamaParse) — pages where neither path recovers text.
- Section-tagger gains feed Task C (section disposition): cleaner anchors → more reliable KEEP/DROP decisions.
