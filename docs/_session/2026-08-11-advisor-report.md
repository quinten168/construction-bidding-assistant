# Advisor report — 2026-08-11

Written for the advisor session. Supersedes the 2026-08-10 report where they conflict.
Presentation **Wed Aug 12**. Handoff to Shane **Mon Aug 17**. Program ends **Fri Aug 21**.

Two PRs are open and neither is merged:

| PR | branch | what it is |
|---|---|---|
| **#104** | `2026-08-10-mapping-honesty` | the whole night's work. Tested, measured, awaiting review |
| **#105** | `2026-08-10-pr102-flag-off` | a teammate's conversion engine, landed **dormant** behind a default-off flag. Supersedes #102, which should be closed as merged-via |

---

## 1. The headline: we now have CSI's decisions as ground truth, parsed from the file

Alex returned the material-mapping document with his marks. Until today we were working from a
hand-transcribed summary of it. We now parse the `.docx` XML directly:
**272 checkboxes, 81 checked, 191 unchecked, 0 absent, 0 malformed**, verified two ways (the
`w14:checked` attribute and an independent glyph scan). No tracked changes, no comments, all
write-in blanks empty.

That parse did three things a summary could not.

**It found two rulings we had inverted.** `GRANULAR BEDDING` and `FULL DEPTH BITUMINOUS STREET
REPAIR` were sitting in our do-not-count list when Alex had assigned them to `grading_yards` and
`Mixed_tons`. The fingerprint proves it was our transcription error rather than his decision: the
13-entry list was the 11 genuinely unassigned rows **plus those 2**. After the fix the list is
**exactly 11**, which confirms the diagnosis arithmetically rather than by argument.

**It found four rulings nobody had recorded**, three of which close questions this project had
logged as open: topsoil to `grading_yards` (about 539,000 CY, pre-read Q3), Salvaged Base Course to
`base_tons` (Q6), Aggregate Surfacing Class 1/2/5/Special to `shldr_tons` (Q5, the 67,000 T
question), and Patching to `Mixed_tons`.

**It stopped us asserting something Alex never said.** The summary said "riprap confirmed not
asphalt". Both riprap boxes are unchecked. He answered 81 of 82 questions and skipped that one. The
code already carried riprap as open, so the code was right and the summary was wrong. Nothing was
encoded.

---

## 2. Encoded is not the same as firing, and that distinction is the finding

We audited in two layers: is each ruling **encoded**, and does it **fire** on the live path. They
disagree more than expected.

**13 of 17 testable rulings fire.** Both driveway exclusions, Cement Stabilized Subgrade excluded
10/10 on the demo plan, Portland Cement excluded 13/13 on Dunn, the CL 13 split with no drift,
Remove Bituminous Pavement 13/13 including N=10 on the demo plan.

**Traffic Service Aggregate does not fire, and it is the most important result of the week.**
0 hits in 23 runs before the pass, 1 in 43 after. The model is not confused. It quotes the ruling
back and does the arithmetic in its own reasoning field:

> `{"value": 6506, "reason": "... Adding: 6,506 + 820 = 7,326. ... So base_tons = 6,506 + 820 = 7,326."}`

It writes 7,326 in the reason and returns 6,506 in the value, at high confidence. Meanwhile
`shoulder_tons` is null with a reason saying the item was moved to base. So the material **left one
bucket and never arrived in the other**. Three methods, corroborated 24 hours apart on a different
schema revision.

**A ruling that is encoded, quoted back, and applied in the model's own reasoning still fails to
move the number.** More prose cannot fix that class of failure. This is now measured rather than
suspected, and it is the argument for the coded-item-number layer
(`docs/_spec/2026-08-10-spec-item-number-layer.md`), which is deliberately **not** being built
before Wednesday.

---

## 3. The numbers we can defend on Wednesday

**Extraction accuracy, first time this project has had a measurement rather than an assertion:**
pooled precision **0.983**, recall **0.667**, and **0.00% variance on all six bucketed items**.
Where extraction finds a bucketed item, the quantity is exactly right. The failure mode is recall,
not accuracy.

**Stability: 51 of 56 quantity cells unanimous across 10 runs (91%).** Instability concentrates in
`grading_quantity`, whose failure mode is subset selection over five to seven candidate earthwork
items rather than arithmetic.

**Quotable per cell, not per plan.** Three ruling effects are each 10/10 and traceable to a named
ruling and a printed line item: Crow Wing `MILL` 15,067, Crow Wing `SHLDR` 478, Job 24133
`BASE` to null.

**Do not put `GRADE` on screen for any plan with alternate bid schedules.** Two independent reasons
now: the subset-selection instability, and the topsoil work which fires but did not stabilise the
field (6 distinct values in 10 on Dunn).

**Stability is not correctness.** Two values are 10/10 stable and wrong: Crow Wing `GRADE` = 15,876
disagrees with the rtv-csv ground truth of 7,707, and Stearns contradicted CSI's own FDR ruling
until today's change. That pairing is worth saying out loud, because a stable number looks
trustworthy.

---

## 4. Corrections to inherit

Several claims made earlier in this project, some of them by me, did not survive measurement.

| claim | what is true |
|---|---|
| "38 machine-readable bid item lists" | **8**. The 38 is every `rtv-csv-*` file; 27 are bidder lists. But the real ground truth is **larger**: 26 item-level files across four states, plus about 2,120 lettings in the year spreadsheets |
| "217 standalone advertisement PDFs" | **8 strict, 22 with a broader matcher**. The 217 counted advertisements and addenda together, and the 180 addenda dominate it |
| "the `Category` column resolves the duplicate 64,750 TON question" | It does not. The duplicate is **one bid item printed three times, once per proposal revision**. That is a new silent-failure mode and the first one that **inflates** rather than under-reports |
| "the 605x asphalt miss is the HMA/SUPERPAVE vocabulary" | **Confirmed and fixed.** I briefly reported the opposite from a harness that fed the model more text than production does. On the live path's own input the old prose gives 200 and the new gives 121,421 |
| "Stearns doubled to 140,430, tell CSI" | **Withdrawn.** It reproduced at 70,263, and after today's FDR change 70,263 is the intended value |
| "Crow Wing is an exact golden match on both fields" | **Half.** `BASE` still matches at 5,849. `GRADE` returns 15,876 against the golden's 7,707, stably |
| "spec item numbers are the deterministic layer" | **MN only.** Zero ND or SD rows match MnDOT's 2xxx scheme, and ND is 35.8% of CSI's bidding |
| "909 bid-result emails" | 953 |

The general lesson, which is worth carrying into how this project reports: **a single sample was
repeatedly mistaken for a measurement.** Every number above that changed, changed because someone
ran it ten times instead of once.

---

## 5. What shipped today

**CSI's rulings are now in the artifact that actually runs.** The live PDF-drop path derives every
quantity from seven prose field descriptions in `schema.py`; the keyword crosswalk is batch-only and
never loads there. Alex marked up a document generated from an artifact that does not run, so until
today none of his rulings were in the product.

**FDR now follows Alex's mark to base.** His ruling is FDR to base; we had been reporting the
quantity in `milling_sy`. It now lands in `base_unconverted` carrying `FULL DEPTH RECLAMATION |
70167 | SY` verbatim, because FDR is measured in square yards and depth is stated on 1 of 15 corpus
rows, so a tons figure cannot be derived honestly. Stearns is 70,263 across 15 runs with zero
variance. **Dunn's `milling_sy` goes to null**, because its 408,216 was entirely the FDR line, and
it comes back as a status rather than a silent null: `tons_only`, with `milling_tons` = 67,007 on
10/10.

**Also landed:** the bid date in three layers (the diagnosis was retrieval, not the boilerplate
filter, and the fix took the advertisement chunk from rank 40 to rank 3, corpus hit@5 from 12 to 20);
phasing carried through to the payload, having been extracted and silently discarded; off-unit
capture so a material found in the wrong unit is never a bare null; a truncation guard so an
extraction that overflows the token cap can no longer be cached as an empty plan; the competitor-card
crash; a five-minute plan no longer reporting "cannot reach the backend"; and the frontend finally
able to render a gap state at all.

Tests went from 150 to **182 passing**.

---

## 6. What is still broken, stated plainly

- **Traffic Service Aggregate**, above. 1 in 43.
- **Clean Rock** 0/13 to 7/20. The structural gap is closed (grading gained off-unit capture); recall
  is not fixed. Same enumeration-completeness shape as `milling_tons`.
- **`grading_quantity` is the least stable field** and the topsoil work did not stabilise it.
- **`never_matched` is unreachable in production.** `map_line_v2`, which emits the gap reason, has
  exactly one caller and it is a test. The live parser discards the reason.
- **`s4_extract_rag`'s gotcha pass still does `or []` on a `None`**, so a truncated gotcha pass reads
  as "no gotchas". Gotchas are the risk flags an estimator actually reads. Two lines per call site.
- **Two rulings are `untested-no-plan`**: Salvaged Base Course and Full Depth Bituminous Street
  Repair have zero priced rows in the corpus. Encoded per Alex, unexercised.
- **A presentation defect:** `grading_unconverted` names items it was told to exclude. No total is
  corrupted.

---

## 7. Decisions waiting

1. **Merge #105, then #104.** #105 lands the conversion engine dormant; three gaps must land on top
   before the flag flips, the blocking one being **per-value provenance** (a derived number currently
   renders with blank confidence and no page while its real evidence sits under a key no quantity row
   points to).
2. **Do rulings #5/#6/#9 apply retroactively, or from 2026-08-07 forward?** Four golden `MILL SY`
   values equal the pre-ruling extraction to the unit, and two `BASE TN` values equal the
   post-ruling one. So some of Alex's rulings describe CSI's existing practice and others change it.
   This is worth more than the factor table and it is one question to Alex.
3. **The factor table**, for sign-off. All three of CSI's own numbers reproduce exactly in code
   (base 3,851.75, shoulder 13.09, mix 1,901.34). The apparent discrepancy in his mix column is a
   rounding artifact in his per-item figures, not a factor error.
4. **`AGGREGATE SURFACE COURSE CL 13`** currently disagrees between the live path (shoulder, per
   NDDOT §302 naming) and the batch crosswalk (base). Both live, labelled, until CSI rules.
5. **Post-Wednesday: a history purge for `data/processed/bidder_results.csv`**, paired with a
   conversation with CSI about their data living in a GitHub repo.

---

## 8. Method notes worth keeping

- **The mapping is a prompt, so a passing unit test proves nothing about it.** The proof is a
  differential re-run of both arms over the same documents at temperature 0, with every diff
  classified against the ruling that predicts it. An unexplained diff blocks.
- **Coverage tests over unit tests.** A test that fails when a keyword matches zero corpus rows
  caught more than thirty passing unit tests did. One such test was itself found under-reporting
  today: a tolerant matcher was reporting two real priced items as zero-hit because of converter
  markup.
- **The standing rule, now at twelve instances:** never let a failure and a legitimate empty answer
  share a return value. Today added two more: an extraction truncated at the token cap was
  indistinguishable from a plan with nothing in it, and a superseded proposal revision page is
  indistinguishable from a second line item.
- **Two named methods on any absence claim.** This caught the riprap non-mark and the two inverted
  rulings.
