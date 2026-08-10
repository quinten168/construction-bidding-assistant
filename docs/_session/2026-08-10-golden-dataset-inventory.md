# Golden Dataset — Inventory (Phase A)

**2026-08-10.** P0 #1. What machine-readable ground truth actually exists in `CSI ELP 2026`,
where it is, what it covers, and how much of it joins to a plan we have already extracted.

Phase B (the benchmark table) is specced separately in
`docs/_spec/2026-08-10-benchmark-table.md`. **No DDL has been applied.**

---

## 0. Two corrections to the board, both material

### 0.1 The corpus must be read from the local mirror, not Box

`/Users/t/Library/CloudStorage/Box-Box/CSI ELP 2026` **lists** fine and **reads** not at all.
Metadata (names, sizes, tree) comes from Box's local cache; content requires hydration from
Box's servers and that is currently failing.

Two verification methods, both named:
1. **Direct read, random sample.** 25 files sampled at random across the tree: **0 readable,
   25 `TimeoutError [Errno 60]`.** A targeted retry on the 8 Bid Item List CSVs failed 4/4
   attempts each. A single-file patient retry ran 10 attempts over 206 seconds and never
   succeeded.
2. **Network isolation control.** `curl` to `app.box.com` returned 302 in 0.24s and Google
   returned 200 during the same window, so this is not local connectivity, and it reproduced
   identically with the command sandbox disabled — so it is not the sandbox either.

Use instead:
```
/Users/t/Library/Mobile Documents/com~apple~CloudDocs/00 MSBA + Coding/00_summer 2026/00_CSI_ELP/CSI ELP 2026
```
File counts are identical on both mirrors (pdf 1792/1792, msg 953/953, QUANITIES 33/33), so
counts taken from Box remain valid. **Any file actually opened on the Box path may have failed
silently** — the same failure/empty conflation this project has hit nine times, one layer out.

### 0.2 "38 `rtv-csv-for-Bid Item List*.csv`" is a miscount. The real number is 8.

38 is the count of **all** `rtv-csv-*` files of every kind. Broken down:

| kind | count | states what? |
|---|---|---|
| `rtv-csv-for-Plan Holders*` | **27** | bidder lists — **no quantities** |
| `rtv-csv-for-Bid Item List*` | **8** | the actual golden bid schedules (6 `.csv` + 2 `.xlsx`) |
| `rtv-csv-for-Bid Abstract Summary*` | 1 | award summary |
| `rtv-csv-for-Projects*` | 1 | project metadata |
| `rtv-csv-for-undefined*` | 1 | misc |
| **total** | **38** | |

Three verification methods: (a) filename glob `rtv-csv-for-Bid Item List*` over the whole tree
returns 8; (b) grouping all 38 `rtv-csv-*` files by their kind token sums to 38 with 8 in the
Bid Item List bucket; (c) identical counts on both mirrors, so this is not an
unmaterialized-file artifact.

**"38 golden plans" cannot go in the presentation.** The honest headline is better than 8
anyway — see §1.

---

## 1. Inventory by source class

Corpus totals: **2,971 files**, 1,792 PDF, 953 `.msg`, 135 Excel, 34 CSV.

### Class A — machine-readable bid schedules (item-level quantities, zero parsing risk)

| # | Source class | Count | Location pattern | Format | States |
|---|---|---|---|---|---|
| A1 | `rtv-csv-for-Bid Item List*` | **8** | project folders | CSV ×6, XLSX ×2 | MN ×8 |
| A2 | `Bid Items.xlsx` | **8** | project folders, incl. `1 Bid Docs/` | XLSX | SD ×2, ND ×1, MN ×1, 4 unlabeled |
| A3 | `Proposal_NDOT_*` | **10** | project folders | CSV ×7, XLSX ×3 | NE ×10 |
| | **Class A total** | **26** | | | **MN, ND, SD, NE** |

This is the real golden set: **26 machine-readable bid schedules across four states**, not 8 in
one state. A2 and A3 were not on the board at all.

**A1 schema — three variants, all handled** (`tools/golden/2026-08-10_golden_parse.py`):

```
V1  Category,Line,Item,Quantity                     -- Item is a packed string
    Base Bid - Participating,14,2104.504 REMOVE BITUMINOUS PAVEMENT (S Y),"15,067"
    Base Bid - Participating,24,2211.509 AGGREGATE BASE CLASS 5 (TON),"5,849"

V2  Category, Line, Number, Description, Unit, Quantity
    Uncategorized,1,2021.501,MOBILIZATION,LS,1
    Uncategorized,2,2101.505,GRUBBING,AC,5.2

V3  Category,, Line, Number,, Description, Unit, Quantity   -- V2 + blank padding cols
    CP 67-25 CR 67 Overlay...,,3,2360.509,,"TYPE SP 12.5 WEARING COURSE MIXTURE (2,B)",TON,520
```

Parsed: **8/8 files, 0 failures, 772 item rows.**

**A3 schema — richest of the three, and it has a section column:**
```
Line,Item,Quantity,Unit,Description,Price,Proposal,Call Order,Agency ID,Section,Is Favorite
0004,1010.01,26007,CY,EXCAVATION (ESTABLISHED QUANTITY),,22885,205,NDOT,0001,false
0007,1101.00,3107,SY,REMOVE PAVEMENT,,22885,205,NDOT,0001,false
```

**A2 schema (`Bid Items.xlsx`), single sheet `Table 1`:**
```
Line | (blank) | Item | Quantity | Unit | (blank) | Description | Price
1    |         | 2011601/00003 | 1    | LS   |         | Mobilization | 
```
⚠️ **A2's `Item` column is not trustworthy on the SD files.** On Mellette Co SD every one of
45 rows carries the identical item `2011601/00003`; on Day Co SD it increments `/00003…/00009`
independently of the description. That is a PDF-table-extraction artifact, not a real item
number. Use A2 for **description + unit + quantity only** until this is re-derived.

### Class B — CSI's own hand-maintained bucket totals ⭐ the largest source by far

| Source | Rows | Location | Format |
|---|---|---|---|
| `2023 Spreadsheet.xlsx` (sheet `2023`) | 585 | corpus top level | XLSX |
| `2024 Spreadsheet.xlsx` (sheet `2024`) | 731 | corpus top level | XLSX |
| `2024 & 2025 Spreadsheet.xlsx` (sheets `2025`, `2024`) | 966 + 731 dup | corpus top level | XLSX |
| **distinct project-lettings** | **≈2,282** | | |

Columns are **our seven buckets, by name**:
```
DATE | TIME | LOCATION | PROJECT | State | LOW BIDDER | LOW BID TOTAL | 2ND BIDDER | 2ND BID TOTAL
| MIX TN | GRADE CY | BASE TN | SHLDR TN | MILL SY | CRUSH TN | STOCK TN
```
Real row: `2023-08-03 | 11:00 | STEARNS CO MN, MELROSE | 2023 RAILROAD AVE NW | MIX TN 2425 | BASE TN 4732`

Bucket population:

| bucket | 2023 (585) | 2024 (731) | 2025 (966) |
|---|---|---|---|
| MIX TN | 383 | 538 | 685 |
| BASE TN | 403 | 541 | 724 |
| GRADE CY | 357 | 542 | 747 |
| MILL SY | 223 | 293 | 337 |
| SHLDR TN | 41 | 206 | 151 |
| STOCK TN | 37 | 38 | 54 |
| CRUSH TN | 2 | 13 | 7 |
| **≥1 quantity** | **486** | **706** | **928** |

**≈2,120 project-lettings carry at least one CSI-stated bucket quantity.** This is bucket-level
rather than item-level, so it validates `plan_metrics` rather than `materials` — which is
precisely the layer the report shows a customer. It also carries `DATE` + `TIME` + `LOCATION` +
`State`, i.e. the exact identity key the board settled on, so it joins to `scratch.bid_projects`
without a new key.

Note `CRUSH TN` is populated 22 times in 2,282 rows — independent support for the standing
decision to delete `crushing_tons` as a *bucket*.

### Class C — bid schedules needing PDF text extraction

| Source | Count | Location | Notes |
|---|---|---|---|
| `*QUANITIES.pdf` (misspelled consistently) | **33** | project folders, all in the `2023 Bid year` tree | MN 18, ND 12, SD 3 |

**30 of 33 have a text layer; 3 are image-only** (`2023 Bid Proposal QUANITIES.pdf`,
`matson pt rd lida tw (003) QUANITIES.pdf`, `7_Signature Pages QUANITIES.pdf`) — zero
characters, not "no items". ~5 more have broken ToUnicode CMaps and extract as mojibake
(`5(029(6,/7)(1&(` = `REMOVE SILT FENCE`, a +29 ASCII shift). Both hazards produce a
believable-looking zero if unchecked.

### Class D — bid amounts, not quantities

| Source | Count | Location | Contains |
|---|---|---|---|
| Bid-result emails `.msg` | **953** | `<bid year>/<month>/Bid Results/` (707 in 2026, 216 in 2023, 26 in 2025, 3 No Bid, 1 in 2026 JOBS) | bidder + total; date & time in the filename |
| `GP by Job *.xlsx` | **3** (`12.31.23`, `12.31.24 Rylee's Notes`, `12.31.25`) | corpus top level | Job No, Description, PM, State, Division-Cost Code, Billings, Costs, Gross Profit, GP% — **financial actuals, no quantities** |
| `rtv-csv-for-Plan Holders*` | 27 | project folders | bidder lists |
| `rtv-csv-for-Bid Abstract Summary*` | 1 | project folder | award summary |

`GP by Job` is cost-code level (`HOT MIX-PLACING`, `BASE CREW-TRUCKING`) and is a margin source,
not a quantity source. It does not validate extraction; it would validate a future pricing model.

### Class E — other machine-readable, quantity-adjacent

`MN Pit List.xlsx` (already in the runtime), `2026 Plant Schedule 5.8.26.xlsx`,
`CSI_competitor_review_final_two_tabs JJF.xlsx`, `Bid items per add #2.xlsx` (**one addendum-revised
bid item list — the only machine-readable evidence of the addenda problem in the corpus**),
`Haul.xlsx` ×2, `Crushing.xlsx` ×2, `Mix Price.xlsx` ×2, `Mob.xlsx` ×2, `Design.xlsx` ×2,
`Comparison.xlsx` ×3, `ACBurnerTack Calc.xlsm` ×2, `Pages from *.pdf.xlsx` ×5.

---

## 2. Overlap with plans we have already extracted

`pipelines/plan_reader/csi_v2.db` (symlink → iCloud): `plans` 117, `materials` 6,385,
`plan_metrics` 100. Plans by state: MN 47, ND 41, SD 24, XX 4, MT 1.

**Join key: the state project number (SAP/SP/CP), present in both the corpus folder name and
`plans.dot_project_id`.** Matching is an explicit hand-verified table in
`tools/golden/2026-08-10_golden_join.py`, not fuzzy — a wrong match silently corrupts every
number downstream.

### The overlap number: **5 of 8** Class-A1 golden files match an extracted plan; **2 of 8** are joinable at item level.

| Golden project | plan_id | status |
|---|---|---|
| Crow Wing SAP 018-603-024 | `2023_CROW-WING-CO-MN_SAP-018-603-024_NOBID` | **OK** |
| Watonwan SAP 083-090-007 | `2025_WATONWAN-CO-MN_WATLINE-TRAIL_NOBID` | **OK** |
| Blue Earth SAP 007-616-035 | `2023_BLUE-EARTH-CO-MN_SAP-007-616-035_NOBID` | KEY_UNUSABLE |
| Blue Earth SAP 007-626-019 | `2023_BLUE-EARTH-CO-MN_SAP-007-626-019_NOBID` | KEY_UNUSABLE |
| Pope SAP 061-615-008 | `2023_POPE-CO-MN_SAP-061-615-008_NOBID` | EXTRACTED_ZERO_ITEMS |
| Carver SP 1008-106 | — | NO_EXTRACTION |
| Marshall 25049 | — | NO_EXTRACTION |
| Murray 25051 | — | NO_EXTRACTION |

Four distinct outcomes, deliberately not collapsed into one "no match" — a plan we never
extracted, a plan we extracted to zero items, and a plan whose join key is the wrong column are
three different bugs with three different fixes.

### `materials.bid_item_no` is not consistently the spec item number — this is a finding

5,830 of 6,385 rows (91.3%) are non-empty, but only **331 rows corpus-wide** match `dddd.ddd`.
Crow Wing stores `2104.504`; Blue Earth stores `1, 2, 3`. **The extractor keeps whichever
numeric column it happened to read.** There is no reliable spec-item join key today. That is
the strongest available argument for P0 #3's spec-item-number path, and it is why the two Blue
Earth plans report `KEY_UNUSABLE` rather than a misleading 0% recall.

### Measured accuracy on the 2 joinable plans

```
plan                                          gold  extr  match   prec  recall
2023_CROW-WING-CO-MN_SAP-018-603-024_NOBID      45    46     45  0.978   1.000
2025_WATONWAN-CO-MN_WATLINE-TRAIL_NOBID         42    13     13  1.000   0.310
pooled                                          87    59     58  0.983   0.667
```

Per-bucket absolute variance, matched items only:

| bucket | items | golden total | abs variance | err % |
|---|---|---|---|---|
| base_tons | 1 | 5,849 | 0 | **0.00%** |
| grading_quantity | 2 | 34,918 | 0 | **0.00%** |
| hot_mix_tons | 1 | 4,732 | 0 | **0.00%** |
| shoulder_tons | 2 | 478 | 0 | **0.00%** |
| (unbucketed) | 46 | 126,613 | 2,512 | 1.98% |

**The headline this project has never been able to say: where extraction finds a bucketed item,
the quantity is exactly right — 0.00% variance on all six bucketed items across both plans.**
Crow Wing is a full independent confirmation of the free match the coordinator spotted:
`2106.507 EXCAVATION - COMMON = 7,707` and `2211.509 AGGREGATE BASE CLASS 5 = 5,849` agree
exactly with `grading_quantity` and `base_tons`.

The failure mode is **recall, not accuracy.** Watonwan found 13 of 42 items (29 missed,
including `2211.507 AGGREGATE BASE CLASS 5 = 5,724 CY` and
`2360.509 TYPE SP 12.5 WEARING COURSE = 155 TON` — both bucket-bearing). Pope found zero of 43.
Nearly all of the 1.98% unbucketed variance is one row: `2573.503 SILT FENCE, TYPE MS`,
golden 2,569 vs extracted 57.

Lump-sum items whose extracted quantity is NULL are scored `MATCHED_KEY_NULL_QUANTITY`, never as
an extracted zero — scoring them as zero would report 100% variance on every LS item and bury
the real numeric errors.

---

## 3. The two things asked about specifically

### 3.1 The `Category` column and the two 64,750 TON rows — answered, and the board's premise was wrong

**The board expected `Category` to label `Alternate A` / `Alternate B` versus
`Base Bid - Participating`. In the 8 machine-readable files it does not. There are ZERO
alternate rows.** All 10 distinct category values:

```
415  Uncategorized                     15  Base
135  Base Bid - Participating           9  SAP 051-042-021 CSAH 42 overlay ...
 91  Base Bid - SAP 007-626-019         9  SAP 051-647-006 CSAH 47 Overlay ...
 65  Base Bid - ROADWAY                 8  CP 67-25 CR 67 Overlay ...
 23  Base Bid - STORM SEWER             2  SAP 51-040-001 HWY Dept. Parking lot ...
```
Method: substring scan for `ALT|ADD|OPT|DEDUCT|SCHEDULE` over all 10 distinct values → 0 hits;
and a duplicate-detection pass over (description, unit, quantity) within each file → 2 groups,
both **different roadway segments of one contract** (CR 67 vs CSAH 47), which are additive, not
alternates. So `Category` is really a *section/segment* column here, and where it does group,
the groups are additive.

**On `2026_BURKE-WARD-CO-ND_JOB-22484` specifically — the corpus does cover it, and the answer
is neither of the two options we had logged.**

Found at `2026 JOBS/26003 BURKE & WARD COS ND/`, project `HEN-7-052(034)000 (PCN-22484)`, bid
opening 2025-11-14. The bid schedule is in `Job 22484 Request for Proposal.pdf` (214pp,
`BID ITEMS` from page 7). NDDOT form: `Item No. | Spec No. | Code No. | Description | Unit | Approx. Quantity`.

`REMOVE AGGREGATE BASE & SURFACING | 202 | 0021 | TON | 64,750.` appears on pages 7, 8 **and 9**.

> **They are the same single bid item printed three times — once per revision of the proposal
> form. Not a base/alternate pair, not two segments, and not a double count in the source.**

The proof is in the page headers: all three are sheet `5 of 11` with different `Rev:` stamps —
p7 `Rev: 11/12/2025`, p8 `Rev: 11/6/2025`, p9 unstamped (original). The item numbering shifts
confirm the sequence: the row is item `002` in the original and Addendum-1 versions and item
`003` in the Addendum-2 version, because `E-TICKETING / 109 / 1000 / L SUM` was inserted above
it. `Addendum 2 Job 22484.pdf` p2 says exactly that under `CHANGES MADE TO BID ITEMS FOR JOB`.
The 64,750 TON quantity never changed across any revision.

A scan of all 214 pages plus both addenda for `ALTERNATE|ALT A/B|BASE BID|SCHEDULE A/B` returned
**0 hits** — this is a single-schedule NDDOT letting with no alternates at all.

**Consequence for the extractor:** counting the whole PDF as one document yields 129,500 or
194,250 TON. The correct rule for NDDOT proposals is *take only the highest `Rev:` date for each
`Page N of M`*. This is a new, unlogged silent-failure mode: **a superseded revision page is
indistinguishable from a real second line item**, and it inflates rather than zeroes — the
opposite direction from every bug on the standing list.

**Alternates do exist in this corpus, just not in the machine-readable MN files** — 8 of the 15
ND+SD `QUANITIES.pdf` files carry explicit grouping bands, and the two kinds require opposite
handling:

- *Mutually exclusive* — Burleigh Co ND (`8428114`): `Alternate A - Asphalt with Geogrid` vs
  `Alternate B - Asphalt without Geogrid`, each carrying 2,100 TON Superpave and differing
  aggregate (1,070 vs 2,020 TON). Only one gets built. Beadle Co SD (`8389379`): `Base Bid`
  items 1–9 then `Alternate Bid` items `A1`–`A7`, repeating `Asphalt Concrete Pavement`
  (10,170.2 then 3,449.8 Ton) in an `A`-prefixed line namespace.
- *Additive* — Richland Co ND (`8435580`): `BASE BID – SECTION 1` and `BASE BID – SECTION 2`,
  both built.

**The header text is the only signal separating the two.** A quantity roll-up that sums rows
blindly double-counts the first kind and under-reports nothing — and there is no way to tell
which is which from the row alone.

### 3.2 Spec item number coverage and the numbering scheme by state

**Coverage: 771 of 772 golden rows (99.87%) carry a state spec item number.**

| file | with number | % |
|---|---|---|
| Blue Earth SAP 007-616-035 | 88/88 | 100.0% |
| Crow Wing SAP 018-603-024 | 92/92 | 100.0% |
| Blue Earth SAP 007-626-019 | 91/91 | 100.0% |
| Pope SAP 061-615-008 | 43/43 | 100.0% |
| Watonwan SAP 083-090-007 | 60/60 | 100.0% |
| Carver SP 1008-106 | 354/355 | 99.7% |
| Marshall 25049 (city) | 15/15 | 100.0% |
| Murray 25051 | 28/28 | 100.0% |

The single exception is `TRAINEES | HOUR | 2500` — a federal labor requirement, not a
construction pay item. **There is no freeform-description case in this sample at all.**

⚠️ **A defect in my own first pass, recorded because it is the standing failure shape.** My
initial regex `^\d{4}\.\d{3}$` rejected MnDOT's *extended* form `2104.503/00315` and reported
Marshall at 46.7% coverage — a false "this city job writes freeform descriptions" conclusion.
8 rows corpus-wide use the extended form. Corrected to `^\d{4}\.\d{3}(/\d+)?$`. A missing
suffix and a missing number rendered identically.

**MnDOT `2xxx` distribution** across the 771 numbered rows (min `2011.601`, max `2582.518`):

| prefix | n | | prefix | n | | prefix | n |
|---|---|---|---|---|---|---|---|
| 2101 | 10 | | 2501 | 61 | | 2545 | 28 |
| 2104 | 76 | | 2502 | 24 | | 2550 | 20 |
| 2106 | 21 | | 2503 | 49 | | 2563 | 14 |
| 2118 | 13 | | 2504 | 35 | | 2564 | 23 |
| 2232 | 8 | | 2506 | 39 | | 2573 | 38 |
| 2360 | 28 | | 2511 | 17 | | 2574 | 14 |
| 2401 | 9 | | 2521 | 16 | | 2575 | 42 |
| 2411 | 9 | | 2531 | 23 | | 2582 | 57 |
| 2451 | 8 | | | | | (29 more prefixes) | 81 |

#### Do ND and SD use MnDOT's 2xxx scheme? **No. Zero. They are not translatable by pattern.**

Method: both MnDOT patterns (`\b2\d{3}\.\d{3}\b` and the e-Construction form `\b\d{7}/\d{5}\b`)
regexed over all 12 ND and all 3 SD `QUANITIES.pdf` files, full text, every page — **0 matches**.

| State | QUANITIES files | Dominant scheme | Example |
|---|---|---|---|
| MN | 18 | MnDOT 2xxx, **two variants** | `2021.501 MOBILIZATION` / `2021501/00010 MOBILIZATION` |
| ND | 12 | ND spec+code, **two variants** | `203.0101 Common Excavation-Type A` / `202 0021` |
| SD | 3 | **freeform, sequential line numbers only** | `2 Asphalt Concrete Pavement 10,170.2 Ton` |
| NE | 0 QUANITIES, but **10 `Proposal_NDOT_*`** | 4-digit dotted, own space | `1010.01 EXCAVATION`, `1101.00 REMOVE PAVEMENT` |
| IA / MT | 0 | — | — |

- **MN's two variants are the same number.** `2021501/00010` is `2021.501` with the decimal
  dropped and a 5-digit suffix appended (MnDOT e-Construction). Of the 18: 5 dotted, 5
  e-Construction, 5 freeform city/consultant, 3 image-only.
- **ND's number space does not overlap MnDOT's and is semantically different.** ND `202`=removals,
  `203`=excavation, `302`=aggregate base, `430`=superpave; MnDOT `2104`=removals, `2105`=excavation,
  `2211`=aggregate base, `2360`=bituminous. A crosswalk table is required — no pattern rewrite works.
  Of the 12: 2 dotted `nnn.nnnn`, 1 with explicit `SPEC No. / CODE No.` split columns, 9 freeform
  consultant/EJCDC C-410 forms (KLJ, Williams County, airport) using plain sequential numbering.
- **The SD result is not evidence about SDDOT.** All 3 SD files are *county* surfacing projects
  (Beadle, Brookings) on EJCDC forms, not SDDOT state lettings. The `\d{3}E\d{4}` SDDOT pattern
  also matched 0 times, but **this corpus contains no SDDOT letting QUANITIES file**, so SDDOT's
  own scheme is `UNVERIFIED` here.
- **NE has its own dotted 4-digit space** (`0030.10` mobilization, `1010.01` excavation) — also
  non-overlapping with MnDOT.

**Implication for P0 #3.** "Coded item number wins where present" is sound for MN and gets 99.87%
there. It does **not** generalize: ND needs a spec+code crosswalk, ND consultant forms (9 of 12)
and all SD county forms have no code at all, and NE needs its own table. **ND is 35.8% of CSI's
bidding**, so the deterministic layer covers the minority of the business until an ND crosswalk
exists. The LLM path is not a fallback for the long tail — it is the primary path outside MN.

---

## 4. Recommended weighting for Phase B

1. **Class B (year spreadsheets, ~2,120 rows with quantities) is the benchmark backbone.**
   Two orders of magnitude more coverage than the rtv-csvs, it is CSI's own numbers, it is
   bucket-level (the layer the customer sees), and it carries the settled identity key.
2. **Class A (26 schedules, 4 states) is the item-level truth set** — the only thing that can
   score `materials` and the crosswalk per item.
3. **Class C (33 QUANITIES PDFs) extends item-level truth into ND/SD**, at the cost of PDF
   extraction and with 3 image-only files that must not be counted as zero.
4. Class D validates a pricing model, not extraction. Out of scope for this benchmark.

---

## 5. Artifacts produced

| path | what |
|---|---|
| `tools/golden/2026-08-10_golden_parse.py` | parses all 8 A1 files, 3 schema variants, coverage assertions |
| `tools/golden/2026-08-10_golden_rows.csv` | 772 normalised golden item rows |
| `tools/golden/2026-08-10_golden_join.py` | joins golden → `materials`, 4 distinct non-OK statuses |
| `tools/golden/2026-08-10_golden_comparison.csv` | 88 per-item comparison rows |
| `docs/_spec/2026-08-10-benchmark-table.md` | Phase B DDL + join design — **awaiting review, not applied** |

Both scripts return a non-zero exit code when a keyword or file set matches zero rows, so a
silent empty result is not a passing run.

---

## 6. Things in the repo that contradict the board

1. **`docs/_session/2026-08-08-tasks-deployment.md:31` and `2026-08-08-corpus-findings.md:17,31`**
   state 38 `rtv-csv` bid item lists. The real number is 8. §0.2.
2. **`2026-08-08-corpus-findings.md:47`** says alternates are labelled `Alternate A`/`Alternate B`
   in the `Category` column and that this resolves the 64,750 question. Neither holds: there are
   0 alternate rows in the 8 files, and the 64,750 duplication is superseded revision pages. §3.1.
3. **`2026-08-08-corpus-findings.md:13` / HANDOFF** say 909 `.msg` bid-result emails. Disk shows
   **953** on both mirrors.
4. **The board treats the state item number as a general deterministic layer.** It is a
   MN-only layer today. ND/SD/NE each use a disjoint scheme, and 9 of 12 ND files have no code
   at all. §3.2.
5. **Not a contradiction but unlogged:** `plan_metrics` has 100 rows for 117 plans, and one
   golden-matched plan (`2023_POPE-CO-MN_SAP-061-615-008_NOBID`) has **zero** `materials` rows
   while a 43-item bid schedule exists for it. Extraction produced nothing and nothing flagged it.
