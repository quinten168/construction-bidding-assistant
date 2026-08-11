# 2026-08-10 — Baseline non-determinism of the live material mapping (N=10)

**Task B. Read-only measurement. Nothing in the repo was fixed, and nothing shared was edited.**

The live material mapping is seven prose field descriptions in
`pipelines/plan_reader/01_pipeline/schema.py`, interpreted by a model at `temperature=0`. On
2026-08-10 a re-warm of 14 cached plans moved 12 field values on the same documents. This measures
how much of that movement is reproducible behaviour and how much is sampling.

Script: `pipelines/plan_reader/03_evaluation/2026-08-10_nondeterminism_measurement.py`
Raw data: `pipelines/plan_reader/03_evaluation/outputs/2026-08-10_nondeterminism.json`,
`…_nondeterminism_extension.json`

---

## 0. What was measured, stated plainly

**Field set: commit `50731a5` (schema.py byte-identical at `7370005`, the current branch head — a
later docs-only commit landed mid-run and changed nothing in the extraction path; verified with
`git diff 50731a5..HEAD -- schema.py s3_extract.py`, empty).** 24 `extract` fields.
**It DOES include tonight's 2a `*_measured_unit` / `*_unconverted` additions** (commit `0bd858d`,
17:33). Model `claude-sonnet-4-6`, `temperature=0`, `MAX_CHARS=180,000`,
`EXTRACT_MAX_TOKENS=6000`.

**This is the same field set that produced the "after" column of the 12-move table, but NOT the
same one that produced every "before".** The payload-cache backups make the baselines explicit:

| plans | "before" value came from | field set behind it |
|---|---|---|
| Stearns 9813645, Dunn Job 23388 | the 14:19 demo re-warm (`_report_payload_cache_backup_2026-08-10_174031`, mtimes 14:16 / 14:18) | **post-ruling, pre-2a** |
| the other 10 plans | caches written 09:26–16:11, all predating the 13:06 mapping change | **pre-ruling, pre-2a** |

So the 12-row table mixes two different comparisons. For Stearns and Dunn, before→after isolates
**the 2a field additions plus sampling — the rulings were already in both arms.** For everything
else it is rulings + 2a + sampling combined. That was not stated on the board and it changes two
of the twelve conclusions.

### Input construction — the live path, reproduced once per plan

`report.py::process_pdf` sends only the proposal pages, not the whole document. The harness rebuilds
exactly that chain — `lib.detect_structure` → `s1_convert.convert_pages` → `pages_to_markdown(only
proposal pages)` → `s3_extract.smart_truncate(…, MAX_CHARS)` — **once**, hashes the result, and
reuses the identical string for all 10 runs. `process_pdf` is never called; **Chroma was touched
zero times.**

| plan | doc type | pages | proposal pages | chars sent | truncated | input sha256 |
|---|---|---:|---|---:|---|---|
| Stearns 9813645 (MN) | proposal | 80 | 1–80 | 180,039 | yes (from 246,293) | `fa8ea4be…` |
| Crow Wing SAP 018-603-024 (MN) | proposal | 232 | 1–232 | 180,040 | yes (from 761,736) | `bd46989e…` |
| Dunn Job 23388 (ND) | combined | 351 | 311 pages | 180,040 | yes (from 836,637) | `50f0082f…` |
| 8428114 Burleigh (ND) | combined | 260 | 1–238 | 180,040 | yes (from 561,690) | `dc57faed…` |
| 9809481 Clay/Moorhead (MN) | combined | 164 | 1–133, 157–164 | 180,040 | yes (from 402,491) | `cc245b9c…` |
| 8416165 Cass (ND) † | combined | 50 | 23–50 | 29,594 | **no** | `22dd2423…` |
| 8435627 Emmons (ND) † | combined | 453 | 1–402 | 180,040 | yes (from 1,009,194) | `fea681d2…` |
| Job 24133 Morton (ND) † | combined | 146 | 1–88, 90–146 | 180,040 | yes (from 387,606) | `bebfefc1…` |

† Extension set — not in the task's five. Added because without them five of the twelve rows could
only be answered "cannot tell", including both sub-percent moves the task asks about specifically.

**80 runs, 80 OK, 0 ERROR.** A failed or unparseable response is recorded `status=ERROR` with
`values=None` and is excluded from every distribution — it is never counted as a null. There were
none, so no distribution below is contaminated.

---

## 1. Per-field distributions

### The seven quantity fields — every unstable cell, all eight plans

| plan | field | distinct | mode | mode n | all observed |
|---|---|---:|---|---|---|
| Dunn Job 23388 | **GRADE** | 4 | 41,035 | 4/10 | 41035×4, 43035×3, 34788×2, 43535×1 |
| 8428114 Burleigh | **GRADE** | 5 | 3,450 | 4/10 | 3450×4, 2650×2, 2900×2, 4500×1, 4450×1 |
| 8416165 Cass | **MILL** | 4 | 192,221 | 4/10 | 192221×4, 212221×3, 212521×2, 192521×1 |
| 8435627 Emmons | **MIX** | 2 | 1,588 | 9/10 | 1588×9, 2106×1 |
| Job 24133 Morton | **SHLDR** | 2 | null | 7/10 | null×7, 170×3 |

**Every other quantity cell was unanimous 10/10.** Full stable values:

| plan | MIX | BASE | GRADE | SHLDR | MILL | CRUSH | STOCK |
|---|---|---|---|---|---|---|---|
| Stearns 9813645 | 14,480 | 270 | 200 | 460 | 70,263 | null | null |
| Crow Wing SAP 018-603-024 | 4,732 | 5,849 | 15,876 | 478 | 15,067 | null | null |
| Dunn Job 23388 | 121,421 | 6,506 | *unstable* | null | 408,216 | null | null |
| 8428114 Burleigh | 2,100 | 1,070 | *unstable* | null | null | null | null |
| 9809481 Clay | null | null | 12,159 | null | null | null | null |
| 8416165 Cass | 27,900 | null | null | null | *unstable* | null | null |
| 8435627 Emmons | *unstable* | null | 8,814 | null | 6,603 | null | null |
| Job 24133 Morton | null | null | 4,911 | *unstable* | 152 | null | null |

### Instability rate by field (8 plans × 7 fields = 56 cells)

| field | unstable plans | rate |
|---|---:|---:|
| `grading_quantity` (GRADE) | 2 / 8 | **25%** |
| `milling_sy` (MILL) | 1 / 8 | 13% |
| `hot_mix_tons` (MIX) | 1 / 8 | 13% |
| `shoulder_tons` (SHLDR) | 1 / 8 | 13% |
| `base_tons` (BASE) | 0 / 8 | 0% |
| `crushing_tons` (CRUSH) | 0 / 8 | 0% |
| `stockpile_tons` (STOCK) | 0 / 8 | 0% |
| **total** | **5 / 56** | **8.9%** |

`crushing_tons` and `stockpile_tons` were null on all 8 plans, so their 0% is "never produced a
value", not "produced the same value reliably". That is a weaker result than BASE's 0/8 and is not
evidence those descriptions are good.

### The 2026-08-10 companion fields (2a / milling unit capture)

Mostly stable, with two exceptions worth recording because they are new tonight:

| plan | field | observed |
|---|---|---|
| 8416165 Cass | `milling_measured_unit` | SY×5, OTHER×2, SY+TON×2, SY+OTHER×1 — **4 distinct on a plan whose milling is entirely SY** |
| 8428114 Burleigh | `base_measured_unit` / `base_unconverted` | TON+OTHER×9 / `Salvaged Base Course \| 1050 \| CY`×9, and null×1 |
| 8435627 Emmons | `base_unconverted` | 3 distinct item lists (a subset-selection difference, not a value difference) |

`milling_tons` was unanimous on all 8 plans, including Dunn's 67,007 T (10/10). The milling
unit-capture feature is the most reproducible thing measured tonight; the 2a tons-bucket capture is
close behind, with the caveat that *which* items land in `*_unconverted` wobbles on two plans.

---

## 2. Classification of all 12 moves

Rule applied: a move whose "after" value is the **unanimous or dominant** outcome of 10 runs AND
matches a ruling's predicted direction is a **ruling effect**. A field taking several values across
10 runs is **noise**, regardless of direction. A stable value that no ruling predicts is a **prose
effect** — real and reproducible, but not something CSI ratified.

| # | plan | field | before → after | verdict | evidence |
|---|---|---|---|---|---|
| 1 | Stearns 9813645 | MILL | 140,430 → 70,263 | **REGRESSION, stable** | 70,263 is 10/10. Both arms had the rulings, so this is not a ruling firing. 70,263 = the three MILL BITUMINOUS SURFACE lines (68,167 + 96 + 2,000); FDR = 70,167 SY is printed in the same sent text and CSI ruling #9 says it belongs in `milling_sy`. **At HEAD the model stably omits it.** The re-warm's pinned expectation of 140,430 is not met, and not met by chance. |
| 2 | Dunn Job 23388 | GRADE | 34,998 → 41,035 | **NOISE** | 4 distinct values in 10 runs; 41,035 is only the mode at 4/10. 41,035 is the arithmetically complete sum (15,285 + 6,447 + 4,352 + 1,898 + 1,469 + 11,584), so the mode is the right answer — but it is a 40% answer, not a reproducible one. |
| 3 | Crow Wing | GRADE | 7,707 → 15,876 | **PROSE EFFECT, stable** | 15,876 is 10/10 and decomposes exactly: EXCAVATION-COMMON 7,707 + SELECT GRANULAR EMBANKMENT (CV) 6,505 + COMMON EMBANKMENT (CV) 1,664. The new description names "embankment"; no numbered CSI ruling does. **Note: the rtv-csv golden for this plan says `grade_cy = 7,707`, so the "exact golden match" claimed in `latest_report.md` §1a is now broken by design.** |
| 4 | Crow Wing | MILL | None → 15,067 | **RULING EFFECT, stable** | 10/10. Exactly `REMOVE BITUMINOUS PAVEMENT \| S Y \| 15067` — CSI 08-07 "grading → milling". The 326 SY driveway line is correctly excluded, also 10/10. Cleanest ruling confirmation in the set. |
| 5 | Crow Wing | SHLDR | None → 478 | **RULING EFFECT, stable** | 10/10. AGGREGATE SURFACING CLASS 5 113 T + AGGREGATE SURFACING SPECIAL 365 T = 478, exactly what the new `shoulder_tons` clause says to count "pending a CSI ruling". |
| 6 | 8416165 Cass | MILL | 193,207 → 192,521 | **NOISE, and far worse than the move suggests** | 4 distinct values spanning 192,221–212,521. **192,521 occurred 1 time in 10 and is not the mode; 193,207 never occurred at all.** See §4. |
| 7 | 8428114 Burleigh | GRADE | 1,600 → 4,500 | **NOISE** | 5 distinct values in 10 runs. **4,500 occurred 1 time in 10.** The plan has parallel alternate schedules (C1 1,600 CY and D1 1,850 CY Common Excavation, plus C3/D3 Salvaged Base Course 1,050 CY each) and the model picks a different subset each run. Mode 3,450 = C1+D1. |
| 8 | 8435627 Emmons | MILL | 75 → 6,603 | **cannot be attributed from this run** | 6,603 is 10/10 stable at HEAD, so the *current* value is reproducible. But 75 came from a pre-ruling arm I did not re-run, so I cannot separate "ruling fired" from "2a additions changed it". Direction is consistent with the removal rulings. |
| 9 | 8435627 Emmons | MIX | 1,586 → 1,588 | **NOISE (the +2 is the small tail of a wide distribution)** | 1,588×9, 2,106×1. The mode is solid, but the field can return a value 33% higher. See §4. |
| 10 | Job 24133 | BASE | 170 → None | **RULING/PROSE EFFECT, stable** | BASE = null 10/10. The item leaving `base_tons` is real and reproducible. |
| 11 | Job 24133 | SHLDR | None → 170 | **NOISE — this is the half that does not hold** | SHLDR = null×7, 170×3. The item is `AGGREGATE SURFACE COURSE CL 13 \| TON \| 170`, which **no description names**: `base_tons` names "AGGREGATE BASE CLASS 5/6/13", `shoulder_tons` names "AGGREGATE SURFACING CLASS 1/2/5/SPECIAL". Combined with #10, **7 runs in 10 drop the 170 t out of every bucket.** The "clean bucket move" is actually a silent loss 70% of the time. |
| 12 | 9809481 Clay | GRADE | 45 → 12,159 | **PROSE EFFECT, stable — but unratified** | 12,159 is 10/10 = EXCAVATION-COMMON (EV) 45 + TOPSOIL STRIP & SPREAD 12,114. **No CSI ruling mentions topsoil.** The 270× jump is real and reproducible; whether topsoil strip & spread is grading is a question CSI has not answered. |

**Tally: 3 ruling/prose effects that are stable and correct (4, 5, 10), 3 stable prose effects that
CSI never ratified (3, 12, and half of 10/11), 1 stable regression (1), 4 noise (2, 6, 7, 9, 11),
1 unattributable (8).**

---

## 3. Is GRADE the whole story?

**No — but it is the worst field, and it is the only one that is bad in a *large* way.**

- GRADE is unstable on 2 of 8 plans (25%), double the rate of any other field, and it accounts for
  2 of the 5 unstable cells.
- **But three other fields each broke on a plan too:** MILL on 8416165 (4 values), MIX on 8435627
  (2 values), SHLDR on Job 24133 (2 values). Fixing `grading_quantity` alone would leave 3 of the 5
  unstable cells in place.
- Where GRADE is unstable it is unstable *badly*: 4 and 5 distinct values, modes of only 4/10, and
  spreads of 21.5% and 54.7% of the mean. The other three unstable fields have modes of 4/10, 9/10
  and 7/10 respectively — only 8416165's MILL is comparably bad.
- The mechanism is consistent across all the GRADE failures and is **subset selection, not
  arithmetic**: the plan lists 5–7 candidate earthwork line items and the model includes a different
  subset each run. That is what "the loosest description of the seven" buys — the description says
  what *kinds* of work count but does not resolve topsoil, alternate schedules, waste/subcut splits,
  or removals.
- Two GRADE cells were rock-stable at 10/10 anyway (Crow Wing 15,876, 9809481 12,159, 8435627 8,814,
  Job 24133 4,911 — 4 of 6 plans that produced a GRADE value). So GRADE is not uniformly broken; it
  breaks specifically on documents with several plausible earthwork subsets.

---

## 4. Are the two sub-percent moves the same phenomenon as a 270× jump?

**They are the same phenomenon, and the sub-percent size is an accident of which two draws you
happened to compare. Treating "it only moved 0.35%" as reassuring is exactly wrong.**

**8416165 MILL, −686 (0.35%).** The 10-run distribution is `192221×4, 212221×3, 212521×2,
192521×1`, a span of **20,300 SY, 10% of the mean**. Neither number in the reported move is the
mode, and `193,207` — the "before" — **never appeared once in 10 runs**. The values decompose into
two independent binary choices: a **±300** offset that matches the printed
`Mill / Grind Asphalt Pvmt 2" to 4" Thick 300 SY` line exactly, and a **±20,000** offset I could not
attribute to a single printed line item and do not claim to have explained. The observed 686 is a
near-collision between two draws from a distribution that routinely moves by 20,000.

**8435627 MIX, +2 (0.13%).** The distribution is `1588×9, 2106×1` — the mode is strong, but the tail
is **+33%**, not +0.13%. Again the observed move is far smaller than the field's real spread.

The generalisation, which matters for how the board reads any future re-warm: **the magnitude of a
run-to-run delta carries no information about the underlying instability of the field.** A 0.13%
move and a 270× move can both come from stable fields, unstable fields, or genuine ruling effects.
Only a distribution tells you which. Two of tonight's four "small" moves are noise and one 270× move
(9809481) is perfectly reproducible.

---

## 5. Which numbers can we quote to CSI?

**Answer: yes, but only per-cell, and only three of tonight's twelve moves qualify.**

Of the 56 quantity cells measured, 51 (91%) were unanimous across 10 runs at `temperature=0`, and
where a stable value could be traced to the source document it was arithmetically exact — Crow Wing
MILL 15,067 is the printed line item, SHLDR 478 is 113 + 365, 9809481 GRADE 12,159 is 45 + 12,114,
Dunn MILL_TON 67,007 is 63,092 + 3,915. That is a genuinely good reproducibility rate and it means
the extractor is not "randomly guessing"; the 9% that moves, moves for identifiable reasons (a
document with alternate bid schedules, or an item no description names). But three separate problems
stop us from quoting a *plan's* numbers as a set. First, stability is not correctness: Stearns MILL
is 70,263 in 10 runs out of 10 and still contradicts CSI's own FDR ruling by 70,167 SY, and Crow
Wing GRADE is 15,876 in 10 runs out of 10 while the rtv-csv ground truth for that column says 7,707
— so a confidently reproducible number can be confidently wrong against both a ruling and a source
document. Second, three of the twelve moves the board is currently treating as ruling effects
(8416165 MILL, 8428114 GRADE, Job 24133 SHLDR) reproduce **1, 1 and 3 times out of 10**, and the
Job 24133 case is worse than noise — 7 runs in 10 drop 170 tons out of *every* bucket, so a move
that reads as a clean `BASE → SHLDR` reclassification is actually a silent loss most of the time.
Third, the twelve-row table itself has two different baselines behind it, so for Stearns and Dunn it
was never measuring the rulings at all. **The three moves that can be quoted as reproducible ruling
effects are Crow Wing MILL 15,067, Crow Wing SHLDR 478, and Job 24133's BASE going to null** — each
10/10 and each traceable to a named ruling and a printed line item. **Everything else needs either a
correction (Stearns), a CSI decision (topsoil on 9809481, `AGGREGATE SURFACE COURSE CL 13` on Job
24133, embankment in GRADE), or a tighter description before a number goes on a slide.** For
Wednesday, the honest framing is per-number rather than per-plan: quote the three above, quote the
stable single-line values, and do not present GRADE on any plan with alternate bid schedules.

---

## 6. Follow-ups this measurement did not do (deliberately — read-only task)

1. **Stearns MILL is a live defect.** `tools/2026-08-10_rewarm_demo_cache.py` pins
   `{"MILL": 140430}` as the demo expectation and the current field set stably returns 70,263. One
   of the two is wrong and the demo will show 70,263.
2. **The pre-2a field set was not re-measured.** Whether the 2a additions *caused* the Stearns
   regression, or whether the 14:16 value of 140,430 was itself a lucky draw, needs N=10 on the
   `0bdb4e9` schema. That would be one more 10-run arm on one plan.
3. **`AGGREGATE SURFACE COURSE CL 13` and `TOPSOIL STRIP & SPREAD` need CSI rulings.** Both are
   currently decided by prose ambiguity, and one of them loses 170 t 70% of the time.
4. **`crushing_tons` / `stockpile_tons` produced no value on any of 8 plans.** Their 0% instability
   is vacuous, not a pass.
