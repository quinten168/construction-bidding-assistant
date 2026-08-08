# Session report — 2026-08-07 · crosswalk rulings, vision proof, corpus diagnostics

Written for T and T's advisor. Everything below is marked **RAN** (executed and observed) or
**ESTIMATED** (reasoned, not measured). Nothing is committed; `git diff` is the review surface.

---

## 1. Lead with what did NOT happen

- **Railway / hosted Chroma — not attempted.** T took the whole task. The Railway CLI (v5.31.0) was
  installed on this machine, nothing else.
- **Nothing was committed.** Four files are modified in the working tree plus two new docs.
- **No unit conversion was applied anywhere.** Per T's decision, conversion is a later layer with a
  CSI-verified factor table. The unit study below proposes factors; none is applied and none is
  presented as fact.
- **Vision was not built.** One real API call was made to prove the approach. That is all.
- **F1 / F2 / F3 (regenerate, always-show-buckets, audit export) — not started.**
- **CAD-vector fix not built** — scoped and ticketed only, per instruction.
- **All five investigations finished.** A (unit study), B (110-vs-117), C (CP/SP), D (vision),
  E (CAD pollution). None was stopped for time.

## 2. The headline finding: FDR was counting as zero in production, for a reason nobody had found

While applying CSI's ruling I recomputed the corpus against the live crosswalk and found a delta far
larger than the ruling could explain. Cause (**RAN**, verified by direct lookup):

`05_knowledge/quantity_crosswalk.py`'s `SPEC_MAP` contains the keyword **`RECLAIM`**. The pay item is
**`FULL DEPTH RECLAMATION`**. "RECLAMATION" does not contain the substring "RECLAIM" — the letters
diverge at position 6 (`RECLAM…` vs `RECLAI…`). So Full Depth Reclamation matched **no keyword at
all**, fell through to `other`, and reached no bucket.

**1,235,282 SY of FDR across 14 plans has been reporting as zero.** This is a different and more
embarrassing bug than the one the July mapping exercise was convened to fix (that one was
material-noun-beats-action-verb; this one is a typo-class substring miss). It was invisible because a
missing keyword and a deliberate exclusion produce the identical output: nothing.

The ruling layer fixes it as a side effect. **The underlying fragility — a flat first-match-wins
substring list with no test that every known pay item matches something — is not fixed.** Ticket
below.

## 3. Decisions applied

| # | T's decision | Status |
|---|---|---|
| 1 | FDR = option 3. Record CSI's ruling as CATEGORY, keep the quantity where it is measurable. Do not convert units in the mapping layer. | **Applied** |
| 2 | Approve and apply the other 8 rulings | **Applied** |
| 3 | Record both corrupt-chunk definitions rather than reconciling | **Recorded**, §7 |
| 4 | Railway is T's | **Dropped entirely** |
| 5 | CSI does carry the CP/SP number, heavily NULL | **Accepted — and I was wrong.** §8 |

### The category/bucket split (decision 1, as built)

The defect T identified is real and now recorded in the code: a name like `base_tons` or `mill_sy`
bakes a UNIT into a CATEGORY. CSI answered a category question ("FDR is base work") and the system
heard a unit instruction ("put square yards in a tons column"), which would have zeroed 1.2M SY.

Two fields now exist and are allowed to disagree:

- **`csi_category`** — what kind of work this is. Unit-independent. This is what CSI rules on.
- **`csi_bucket`** — which total the quantity is summed into. Still unit-guarded.

For FDR: `csi_category='base'` (CSI's ruling, honoured) with the quantity counted in `milling_sy`
(where it is measurable). Both surfaced. No invented arithmetic, nothing zeroed, customer not ignored.

A third state was also added, because two were not enough: `excluded` (CSI ruled it out on purpose)
is now distinct from `other` (not a tracked bucket) and from `None` (we never matched it). Those are
three different facts and collapsing them is precisely what hid the FDR bug. F2 depends on this
distinction.

## 4. W1 — files changed (RAN, verified)

| File | Change |
|---|---|
| `pipelines/plan_reader/05_knowledge/quantity_crosswalk.py` | `CSI_RULINGS_2026_08_07` ruling layer (11 ordered item-level overrides + 13 do-not-count patterns), `CROSSWALK_VERSION = 2`, `csi_category()`, `map_line_v2()`, `ensure_stamp_columns()` |
| `pipelines/plan_reader/04_tools/05_parse_bid_schedule.py` | fresh parses write `csi_category` + `crosswalk_version` |
| `pipelines/plan_reader/04_tools/10_remap_buckets.py` | re-maps re-stamp both |
| `docs/2026-08-07_identity_design.md` | new — Step 2 row-identity vs project-identity design |

**Why an item-level override layer instead of editing `SPEC_MAP`:** the rulings split items that
share a keyword. `REMOVE BITUMINOUS PAVEMENT` becomes milling while `REMOVE BITUMINOUS DRIVEWAY
PAVEMENT` becomes nothing. One keyword cannot express that, so overrides are per-item and ordered,
narrower pattern first.

**Note on which mapping Alex actually marked up:** the pre-read CSI reviewed is generated from
`11_build_material_map.py`'s `FAMILIES`, which is *not* the mapping that runs
(`05_knowledge/quantity_crosswalk.py` is). They disagree — e.g. Portland Cement was already `other`
in the live file but `BASE` in the pre-read. The rulings are therefore encoded as explicit
authoritative overrides rather than relying on any coincidental agreement.

**Verification (RAN):**
- `pytest pipelines/plan_reader` → **36 passed**.
- `py_compile` clean on all three Python files.
- `map_line()` still returns a 2-tuple — both consumers (`05_parse_bid_schedule.py:216,420`,
  `10_remap_buckets.py:53`) depend on that shape and are unchanged.
- All 11 rulings resolve as intended; two unaffected control items (`SUPERPAVE FAA 45`,
  `AGGREGATE BASE COURSE CL 5`) still map via `SPEC_MAP`.
- `10_remap_buckets.py --dry-run` → 100 plans, writes nothing.

**Corpus delta, frozen rows vs recomputed (RAN):** 33 rows change bucket.

| bucket | frozen (v1) | recomputed (v2) | delta |
|---|---:|---:|---:|
| `milling_sy` | 542,262 | 1,777,544 | **+1,235,282** |
| `base_tons` | 1,008,322 | 1,010,975 | +2,653 |
| `grading_quantity` | 2,137,441 | 2,138,441 | +1,000 |
| `shoulder_tons` | 47,211 | 45,871 | −1,340 |
| `hot_mix_tons` | 1,150,328 | 1,146,412 | **−3,915** |

**The `hot_mix_tons` −3,915 deserves attention given the standing priority.** It is one row,
`REMOVAL OF BITUMINOUS SURFACING | TON`, which previously matched the `BITUMINOUS` keyword and was
counted as placed hot mix. It is a removal, so it should never have been in `Mixed_tons`. This
slightly qualifies the earlier "Mixed_tons delta is zero" observation: zero was measured against the
*pre-read* mapping, not the live one.

**Not yet run:** `10_remap_buckets.py` for real against `csi_v2.db`. The stamp columns do not exist
in the table until it runs. Dry-run only so far — deliberate, since it rewrites 100 plans.

## 5. Step 0 diagnostics (RAN)

### 0a — the scanned plan set is not representative of the corpus, but is representative of plan sets

205 PDFs, 118 project folders, 33,735 pages.

| | PDFs | % | pages | % pages |
|---|---:|---:|---:|---:|
| mixed | 131 | 63.9% | 30,176 | 89.5% |
| text_only | 56 | 27.3% | 2,833 | 8.4% |
| image_only | 18 | 8.8% | 726 | 2.2% |

By filename: **43% of plan-set-named files are image-only, median 124 chars/page**, versus 2,413 for
proposals. So CP 029-086-024 generalises to plan sets, not to the corpus.

**Plan-set support is a day, not a week** — 726 pages across 18 files, and the pages that matter are
a handful each. Three of the 18 are misfiled scanned prevailing-wage/signature boilerplate, not plan
sheets. One folder (`2026_TODD-CO-MN_CSAH-2`) is 7 of the 18 on its own.

### 0b — corpus quality and plan-set support are the same problem, via two mechanisms

`convert_failures.log` is **157 lines of which only 18 are genuine per-PDF failures**. The other 139
are two environment-wide batch aborts (106 × `ModuleNotFoundError: pymupdf4llm`, 33 × `database is
locked`) that say nothing about any PDF. Anyone reading that log top-down gets the wrong picture.

| failure class | n | folder has an image-only PDF |
|---|---:|---:|
| empty/near-empty conversion | 4 | **4/4** |
| conversion timeout >300s | 7 | 0/7 |
| PdfminerException | 4 | 0/4 |
| ValueError: Point: bad args | 2 | 0/2 |

**The plain statement, with the correction to the original hypothesis:** they are the same problem,
but the failure mode is two-sided. Scanned-image plan sets produce **absence** — 5 of 7 image-only
folders have literally 0 chunks in Chroma, so they contribute zero corrupt chunks because they
contribute zero chunks. CAD-vector plan sets produce **pollution** — a text layer of stationing runs
that indexes as 65–96% garbage. Vision fixes the first. It does not fix the second, which needs the
CAD text layer excluded from indexing and is cheaper.

> ⛔ **PARTIALLY REFUTED by §6-E, later the same session.** The pollution half stands. The clause
> "and drives the >300s timeouts" is **wrong** — I inferred it from the overlap between the
> worst-chunk list and the timeout list without testing it. Direct profiling shows the timeouts are a
> page-count problem: two PDFs that converted *successfully* extrapolate to 542s and 1111s. There are
> **three** distinct causes here (CAD pollution, page-count timeouts, and a pdfplumber per-page
> exception), not one. I stated a correlation as a cause.

## 6. Agent findings

### B — the 110-vs-117 contradiction: **my earlier claim was wrong** (RAN)

I reported "110 of 118 folders have no reader output, so the reader never ran them." That measured
the wrong artifact.

The per-folder `<plan_id>.json` is written **only by the single-plan CLI** (`run.py` → `lib.write_json`),
run on 8 plans in a 2026-06-11 pilot. The bulk path writes to SQLite + a colocated `.md` + a
hash-named cache in `00_input/_md_cache/` (431 files), and the API path writes to
`00_input/_report_payload_cache/` (12 files) — three separate JSON populations, and I conflated the
rarest with "reader output."

**The real proof-of-processing artifact: a `plans` row with `convert_status='converted'`,
corroborated by `sections`.** 117 attempted → 100 converted, 17 failed with a recorded reason; and
`sections` covers exactly those 100. 117/117 plan_ids match a folder; the one folder without a row
is `2026-06-15_Jay_Plans`, a staging directory, not a project.

Also: **`plans_manifest.csv` (tracked in git) is stale** — it marks 11 plans processed and 106 not,
reflecting the same June pilot, and `01_bulk_convert.py` only reads it, never updates it. It is the
likely origin of the "110 unprocessed" framing and agrees with my wrong scan for the same wrong
reason. Chroma is the worst processing signal: 210 distinct doc_ids, only 112 of 117 plan_ids
present, plus 98 legacy stem-keyed ids.

### D — vision: one real call, 8/8 correct (RAN)

One Tier-1 call against `CP 029-086-024 FINAL PLANS.pdf` page 1 (5 pages, 0 extractable chars),
rendered at ~151 DPI, `claude-opus-5`, strict JSON schema with all fields nullable. Ground truth
established by independently reading the same rendered image.

**8 of 8 fields correct. Zero hallucinations, zero misses.** It passed two adversarial traps on the
sheet: it returned `null` for bid_date despite a prominent "DATE 1/9/26" in the engineer's
certification block, and it chose Hubbard County Highway Department as letting agency over MnDOT,
which appears in larger type as the spec authority. It also correctly reported the printed project
number `C.P. 029-086-024` rather than the `SAP 029-640-011` in the filename.

**Measured cost: $0.0339 per plan** (5,225 input / 312 output tokens, Opus 5 list). Not estimated.

Caveats stated honestly: this is **n=1**. It justifies building Tier 1, not a claimed accuracy rate.
And Tier 1 does not fully solve identity — **bid date and bid time are genuinely not on the title
sheet**; in this package they live in the separate proposal PDF the text path already handles. Tier 1
solves identity for the plan set; pairing plan set + proposal solves it for the project.

**A latent blocker was found by reading the code:** `s3_extract.py:135` hardcodes `temperature=0`,
which is rejected with a 400 on Opus 4.7+/Opus 5/Sonnet 5. The current `MODEL` is
`claude-sonnet-4-6`, which still accepts it, so it is dormant — but any vision path on Opus 5 must
drop it. Ticketed.

**Good Tier-2 answer that page 1 handed us:** the title sheet carries an INDEX OF PLAN SHEETS mapping
sheet number → description ("2 ESTIMATED QUANTITIES & TABULATIONS"). Extracting that index in the
Tier-1 call costs ~nothing and turns Tier 2 from "N images" into "3–5 images regardless of set size"
(~$0.10–0.17/plan instead of ~$2.40 for a 100-sheet set). **Unsolved sub-problem, stated plainly:**
drawing sheet numbers are not guaranteed to equal PDF page indices, and reconciling them needs a
second signal. Untested.

### A — unit study (RAN; factors ESTIMATED and all marked UNVERIFIED)

**CSI's actual bid weighting** (606 distinct projects where CSI bid, 2023-08 → 2025-08): MN 43.9%,
ND 35.8%, SD 14.5%, IA 3.6%, NE 1.3%, MT 0.8%. MN and ND are 80% of the book; neither can be the
default.

Sample: 25 plans by largest-remainder quota, seeded RNG. **The corpus cannot supply the IA quota —
there are zero Iowa plans in `csi_v2.db`**; that slot went to MN. Achieved MN 12 / ND 9 / SD 4.
Cross-checked against all 66 corpus plans: **every family's canonical unit is identical in sample and
full corpus**, so sampling drives no conclusion.

Canonical units: hot mix TON (86%), aggregate base TON (46% — *weakest winner, CY is 7 rows*),
aggregate surfacing TON (93%), earthwork CY (84%), cold milling SY (91%), FDR SY (100%),
removal_pavement SY (90%), salvaged_base TON (67%, thin and split cleanly by state).

The conversion table has 13 rows, **every one marked UNVERIFIED**, and **5 marked "NO DEFENSIBLE
FACTOR — ask CSI"** rather than guessed. The most important structural finding:

> **Depth is stated on 0 of 41 `removal_pavement` rows and 1 of 15 FDR rows.** Any ruling that needs a
> depth-based conversion is unimplementable on 93–100% of those families today. `removal_pavement`'s
> canonical unit (SY) does not match its assigned bucket (`grading_yards`, CY) — that is the main
> path, not an edge case.

Also flagged: CSI's own 1.75 Ton/CY factor (attributed to Mark) has never been checked against a
plan, and bituminous vs aggregate base are not the same density.

### C — CP/SP number (RAN; one derived ground-truth set is the investigator's construction)

**`source_project_id` is CONFIRMED as the CP/SP carrier.** 1,272/1,598 non-null (20.4% NULL), holding
`SAP 012-603-017`, `SP 0714-35`, `CP 073-123-025`, `PCN 07Y7`, ND job numbers, IA `CALL 154 …`.
Places checked before asserting: all 61 columns of `scratch.bid_projects`, all 7 `scratch` tables, all
8 `public` tables, name-matching across both schemas, `data/processed/projects.csv`, and
`data/processed/bidder_results.csv` (which has no identifier column at all).

**A second carrier exists and must not be trusted:** `public.plans.dot_project_id` is 117/117 filled
but **badly polluted** — 33 of 117 values are just the PDF filename (QuestCDN eBidDoc numbers like
`8428114`, verified absent from the document text), and others are route numbers (`TH-94`, `CSAH-2`,
`CR-12`). Only ~47/117 are genuine project numbers.

**The correlation hypothesis: confirmed statistically, but the practical conclusion runs the other
way.**

| CSI engagement | n | % `source_project_id` NULL |
|---|---:|---:|
| did not bid | 992 | 23.7% |
| bid and lost | 488 | 15.6% |
| won | 118 | 12.7% |

Odds ratio 1.76, χ² = 16.9, p = 4.0e-5. **Four alternative explanations tested and none accounts for
it**: the effect reproduces within every state, survives within bid_year (which is a real predictor of
NULL but not a confounder, since CSI's engagement rate is flat across years), `source_batch` is
degenerate, and the Mantel-Haenszel OR stratified by state × year is 1.92 — slightly *stronger* than
crude, so confounding is not producing the signal.

**But: even on projects CSI WON, 12.7% are NULL and only ~43% carry a strict CP/SP/SAP/PCN shape.**
There is no subset where the column is reliable. Framing it as "identifier on engaged projects" would
still be wrong ~1 time in 8 on the best possible slice. Also, `pct_neither` exactly equals `pct_null`
in every row — **whenever `source_project_id` is NULL, `project_name` carries no number either**, so
`project_name` is not a fallback for the missing 20%.

**Where it appears in documents:** median first match at **char offset 512, page 1**; 69% on page 1,
82% by page 5. MN uses `S.A.P./S.P./C.P.` and label phrases (`State Aid Project No.`); ND is dual-form
(federal `HEN-7-052(034)000` paired with `(PCN-22484)`, where job number ≡ PCN digits); SD is
extremely consistent (`PROJECT NO. NH 0073(80)78 (PCN 07Y4)`).

**Section routing is unavailable: `sections.section_type` is NULL for all 37,261 rows.**

**Two precision traps that make the regex I proposed unsafe** — a correction to my own suggestion:
ND special provisions render as `SP 1`, `SP 2`, `SP 3`; MN spec references render as `SP 2020` and mix
designations as `SP 12.5 NON WEAR`. All match `\m(CP|SP|SAP|PCN|NH|IM|STBG)\M[- ]?[0-9]`. A bare
`\d{4}-\d{2}` also matches ISO dates.

**Tested extraction strategy (RAN over 100 markdown docs):** normalize Unicode hyphens, then union of
prefix-anchored + label-phrase-anchored + free structural shapes, rejecting date shapes, ranked
prefix > label > free and earlier-offset first.

| scope | top-1 correct | correct in top-3 |
|---|---:|---:|
| whole document | **83.0%** | **89.4%** |
| first 20k chars | 78.7% | 85.1% |
| first 6k chars | 76.6% | 83.0% |

Per state top-1: MN 89.5%, SD 90.0%, ND 81.2%. **Recommendation: scan the whole document (whole-doc
beats first-6k by 6.4pp for little cost) and surface the top 3 with confidence rather than one
value** — that buys the same +6.4pp and fits the verify-gate UI that already exists.

Most remaining misses are genuine ambiguity, not regex failure: several documents legitimately carry
**multiple** project numbers (`SAP 018-603-024 & SAP 018-611-029`), so this should be a multi-value
field rather than one forced answer.

**Caveat stated by the investigator:** there is no hand-labelled gold set in the repo. The 47-document
ground truth was constructed by filtering `dot_project_id` down to genuine project numbers — a
reasonable construction, but the investigator's own, not authoritative.

### E — CAD-vector pollution (RAN): the two symptoms have DIFFERENT causes

**This refutes half of §5-0b above, including a claim I made confidently.**

**Garbage chunks: CONFIRMED as CAD vector text.** Cross-section elevation dumps
(`-29.0' 1924.69 -18.0' 1924.89`), profile PVI/K/LVC blocks, station runs, `OHP OHP OHP` utility
linework, `|Col1|Col2|` table skeletons.

**>300s timeouts: REFUTED as CAD-specific.** They are a page-count × fixed-per-page-cost problem.
Measured with pymupdf4llm over 20 evenly-spread pages each:

| PDF | pages | s/page | extrapolated full doc |
|---|---:|---:|---:|
| TIMEOUT CR-1 | 523 | 2.99 | 1565s |
| TIMEOUT CR-9 | 452 | 3.16 | 1430s |
| **OK** `8371604` | 659 | 1.69 | **1111s** |
| **OK** Watonwan | 619 | 0.88 | **542s** |

**Two PDFs that converted successfully extrapolate to 542s and 1111s — both far over the 300s cap.**
The cap is not selecting pathological CAD PDFs; it is selecting *large* PDFs that hit a cold cache.
15 PDFs ≥400 pages did not fail, including the 659-page one. CAD density modulates the rate ~3.4×
but is not the discriminator.

Also refuted: `01_bulk_convert.py:34-36`'s docstring claims "a ~infinite 100%-CPU spin (no output)."
Every one of 20 pages sampled across the 523-page timeout PDF completed, linearly. **There is no
spin** — just linear cost exceeding a fixed wall clock.

The 4 `PdfminerException` failures are a **third** cause: pdfminer is `pdfplumber`, which only runs
inside `_apply_pdfplumber_fallback` (`s1_convert.py:145`) — so the exceptions come from the hybrid
fallback itself, the same path that manufactures the CAD garbage.

**The 1,743 figure is reconciled, not by argument but by independent rediscovery.** E found a second
garbage class the `low_alpha` heuristic was silently merging in: **1,745 mojibake chunks** — text
extracted as control bytes (`\x10!%\x1b<br>5\x01\x07\x167…`) from broken font/CID encoding. That is
T's Aug-3 CID-font-decode figure of 1,743, ±2, found independently by a different method. **79.6% of
it is one PDF** (`2026_UNKNOWN-CO-ND_9943056`, 1,389 chunks) — a per-PDF font defect, not a
corpus-wide one.

So the corrected breakdown of the ~11,100 is: **9,306 CAD vector text (12.4%) + 1,745 mojibake
(2.3%)**. The two figures were never in conflict; one is a subset of the other's superset.

**Infrastructure already exists and is unused:** `lib.is_drawing_page()` (`lib.py:438`) is already
computed and **already stamped on all 75,080 chunks** — 14,139 (18.8%) carry `is_drawing=1`. Nothing
at index time reads it. (It reads NULL if you query `string_value`; Chroma stores booleans in
`bool_value` — which is why the earlier audit missed it.)

**The prize, measured against the live store:** a conjunctive filter
(`too_short OR mojibake OR (is_drawing AND alpha_ratio < 0.35)`) removes **9,437 chunks = 12.6% of
the store at 100.0% precision** — zero good chunks dropped — and 84.8% recall. `is_drawing` alone
would be 55% precision and discard 6,350 good chunks; the conjunction is what buys exactness.

This is not boilerplate dilution: **5,093 bad chunks are tagged `DECISION` and 2,878 `PRICING`** —
the two retrieval tiers the design most depends on.

**Overlap with #58 is 26%, and they are genuinely different problems.** 2,898 of the bad chunks sit
in #58's blank-provenance stem/UUID doc_ids; the other 8,235 (74%) are correctly namespaced and #58
does nothing for them. Fix independently — but both land on the same `--reset` rebuild, so sequence
them together.

**Correctly declined to reuse `is_noise`:** its signature is `(description, unit)` over pay-item table
cells, and its 120-char/15-word ceiling would reject every legitimate ~350-word chunk. Reuse the tuple
contract and lift the shared regexes; do not call it.

**Inferred, not run:** that the 7 timeouts were cold-cache while the 15 large survivors were
warm-cache (`convert_failures.log` has no timestamps). **The refutation does not depend on this** — it
rests on two *successful* PDFs measurably exceeding 300s.

## 7. The two corrupt-chunk numbers — recorded with definitions, and now reconciled

T's instruction was to record both definitions rather than reconcile to one number. That was the right
call, and following it produced the reconciliation for free.

| Figure | Definition | Source |
|---:|---|---|
| **1,743** | chunks that failed **CID-font decoding** | Aug 3 Chroma audit |
| **11,059** (14.7% of 75,080) | chunks with **alphabetic ratio < 0.35**, or <20 chars, or >20 words with ≤3 distinct | this session, measured against `06_chroma/chroma.sqlite3` |
| **1,745** | chunks whose text is **control bytes from broken font/CID encoding** | the CAD investigation, found independently |

**1,743 and 1,745 are the same population, ±2, found by two different methods.** The Aug-3 audit
measured decode failure directly; the CAD investigation measured control-byte density in the stored
text. The agreement is strong evidence both are real.

**They were never in conflict.** The corrected breakdown of the ~11,100:

- **9,306 (12.4%)** — CAD vector text. Perfectly decoded; simply not prose.
- **1,745 (2.3%)** — mojibake. Failed decoding. **79.6% of it is one PDF.**

The coarse `low_alpha` heuristic was merging the two because control bytes are also non-alphabetic.
Had I "reconciled to one number" as I initially proposed, this structure would have been averaged
away and the single-PDF concentration never found.

## 8. Corrections to my own earlier claims

Three, stated because getting them wrong cost time:

1. **"110 folders were never processed"** — wrong artifact measured. See §6-B. The DB was right.
2. **"CSI does not carry the CP/SP number"** — wrong, and T corrected me twice. I searched for a
   column literally *named* CP/SP among the 61 in `scratch.bid_projects`, found none, and asserted
   absence. `source_project_id` **is** that column: it holds `'SAP 003-607-027'`, `'CP-13(26)04'`,
   `'SP 010-611-026'`, and is 326/1,598 NULL — exactly "heavily NULL, not absent."
3. **"Mixed_tons delta is zero"** — true against the pre-read mapping, but against the live mapping
   it is −3,915 TON. See §4.

## 9. Open questions for T

1. **Run `10_remap_buckets.py` for real?** It rewrites 100 plans in `csi_v2.db` and creates the stamp
   columns. Dry-run is clean. Not run without a decision.
2. **`removal_pavement` SY → `grading_yards` CY**, with depth on 0 of 41 rows. The unit study says
   this is unimplementable as a conversion. Does it need to go back to CSI as a category question,
   the same shape as FDR?
3. **Still unanswered by CSI and deliberately not assumed:** the riprap confirmation, and whether
   crushing/stockpile stay excluded. Both recorded in code as open.

## 10. Tickets — four filed

| # | Title | Why it matters |
|---|---|---|
| **#83** | `SPEC_MAP` keyword `RECLAIM` never matched `RECLAMATION` | 1.2M SY reported as zero. The fragility, not just the symptom. |
| **#84** | `s3_extract.py:135` hardcodes `temperature=0` | 400s on Opus 5. Dormant today, blocks the vision path. |
| **#85** | 12.6% of the vector store is CAD/mojibake noise; `is_drawing` already computed and unused | 100% precision filter available; 5,093 bad chunks are in the `DECISION` tier. |
| **#86** | The 300s convert timeout is below the honest cost of any large plan set | Refutes the "pathological PDF" / "infinite CPU spin" explanation with measurements. |

Not filed: **`plans_manifest.csv` is stale and misleading** and nothing updates it (agent B). Worth a
ticket; deferred because it overlaps the identity design in `docs/2026-08-07_identity_design.md`.

## 11. Where I was wrong this session

Recorded in full because the pattern matters more than the individual errors. **All four are the same
mistake: asserting from a partial view** — the exact failure CLAUDE.md's working rules warn about, and
the same one the 2026-08-03 handoff recorded against itself.

1. **"110 folders were never processed"** — measured the per-folder `.json`, which only the CLI pilot
   writes. The DB was right. (Caught by agent B.)
2. **"CSI does not carry the CP/SP number"** — searched for a column *named* CP/SP among 61, found
   none, asserted absence. `source_project_id` is it. T corrected me twice before I checked properly.
   (Confirmed by agent C.)
3. **"CAD text drives the >300s timeouts"** — inferred a cause from an overlap between two lists,
   never tested it. Two *successful* PDFs exceed 300s. (Refuted by agent E.)
4. **"Mixed_tons delta is zero"** — true against the pre-read mapping, not the live one (−3,915 TON).

A fifth, narrowly avoided: I proposed the regex `\m(CP|SP|SAP|PCN|NH|IM|STBG)\M[- ]?[0-9]` for CP/SP
extraction. Agent C found it matches ND special provisions (`SP 1`, `SP 2`), MN spec references
(`SP 2020`), and mix designations (`SP 12.5 NON WEAR`). It would have looked like it worked.
