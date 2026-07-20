# CSI Competitive Sweet-Spot Analysis — Methodology & Rationale

> **⚠️ Partly superseded (2026-06-17).** The **modeling methodology** below (Q1/Q2
> separation, leakage guards, the bid/win models) is still current. But the **project
> archetype labels** described here are the *old* binary-presence rule. The archetype rule
> was replaced by the **share-gated v2 rule** — see **`2026-06-15_project_type_definitions.md`**
> (the canonical reference) and **`README.md`** (how that decision was made). The original
> findings doc moved to `archive/2026-06-04_sweetspot_findings.md`.

**Date:** 2026-06-04 · **Author:** TK · **Audience:** CSI ELP team
**Read alongside:** `2026-06-15_project_type_definitions.md` (the current archetype rule) and the
notebooks in `notebooks/` (annotated, runnable code).

This document explains **what we built, why, and the reasoning behind every
metric and driver we chose** — so the team can critique it and walk a client
through it. The companion findings doc has the answers; this doc has the *how
and why*.

---

## 1. The business question, restated

CSI wants its **competitive sweet spot**: the kinds of jobs it tends to *bid*
on, and the kinds it tends to *win*. Behind that is the Fall 2025 finding that
CSI leaves ~$22.3M on the table by winning some jobs at too-low prices.

We deliberately split this into **two separate questions** and refused to merge
them into one model:

| | Question | Population | Why separate |
|---|---|---|---|
| **Q1** | When does CSI *decide to bid*? | All 1,591 projects (603 bid / 988 not) | Needs the no-bid jobs. This is a *selection* question. |
| **Q2** | When CSI bids, does it *win*, and at what price quality? | Only the 603 it bid | CSI only bids a non-random 38% of jobs — mixing the two would let that selection contaminate the win analysis. |

**Rationale for separation (the key methodological decision):** if you train a
single "did CSI win this job" model over all projects, you conflate two
different behaviors — *choosing* to compete and *succeeding* when competing. A
job CSI never bid has no win outcome; treating it as a "loss" is wrong. Keeping
Q1 and Q2 apart is the honest structure. (Formally this is a *selection model*;
the gold-standard correction is Heckman's two-stage estimator, which is **not**
in the MSBA toolkit — see §6 — so we keep two clean models and interpret Q2
*associationally*, using archetype stratification as the pragmatic control.)

---

## 2. The data, in one paragraph

Source: `2026-06-03_csi_bid_master.csv` — **one row per (project × bidder) bid**,
6,916 rows, Aug 2023–Aug 2025. We collapse it to **one row per project**
(1,591). Crucially, the file records *every* bidder on each project, so jobs CSI
*skipped* are present — that's what makes Q1 answerable. We verified the
material quantities are listed for the **whole let market, not just CSI's bids**
(87% of no-bid jobs have material data, ≈ the 85% for bid jobs), so we can
characterize jobs CSI never touched.

> **Correction we made:** the initial inventory said CSI wins "421 / 70%" of its
> bids. That 421 was a *row* count (≈104 won projects × ~4 bidder rows). The
> true rate is **117 wins / 603 bids = 19%**. This flips the story from "selective
> high-converter" to "bids broadly, wins a minority, overpays on 41% of wins."

---

## 3. The three workstreams

```
        WS-A  Project Archetyping  (the "spine" — built once)
                        │  produces one archetype label per project
          ┌─────────────┴─────────────┐
        WS-1  Q1 bid/no-bid          WS-2  Q2 win + price-quality
        (all 1,591 projects)         (603 bid projects)
          └─────────────┬─────────────┘
                  Sweet-spot 2×2 map
```

The **archetype** is the connective tissue: we label every project by the
*kind* of job it is, then ask both "does CSI bid this kind?" and "does CSI win
this kind well?" in the same vocabulary.

---

## 4. WS-A explained — what "normalize the material vector to proportions" means

This is the part worth slowing down on, because it's the conceptual core.

**The problem.** Every project has a bill of materials — tons of asphalt
(`MIX_TN`), cubic yards of earthwork (`GRADE_CY`), tons of base/shoulder,
square yards of milling, etc. We want to group projects by the *kind of work*
they are. But raw quantities are dominated by **size**: a $5M repaving and a
$50k repaving are the *same kind of job* (mostly asphalt) but have wildly
different tonnages. If we cluster on raw tonnage, we'd just be re-discovering
"big vs small," which we already know from `Project_Size_Dollars`.

**The fix — proportions (a "recipe," not an "amount").** For each project we
convert its quantity vector into **shares that sum to 1**:

```
                MIX_TN                                    20,626
prop_MIX_TN = ───────────────────────────────  e.g.  ─────────────── = 0.76
              MIX_TN + GRADE_CY + BASE_TN + …          (total of all)
```

So a project becomes a *recipe*: "76% asphalt, 6% base, 7% grade, …" — its
**shape**, independent of scale. Now the $5M and the $50k asphalt jobs have
nearly identical recipes (`prop_MIX_TN ≈ 0.76` for both) and land in the same
group. **That's the whole point of the sentence you asked about:** "a $50k and a
$5M job with the same shape land together."

**Then we append a few non-recipe signals** that matter for *kind of job* but
aren't materials:
- `Project_Size_Dollars` — scale (kept as a *separate* axis, not mixed into the
  recipe, so it doesn't drown the shape).
- `BOX` (box culvert present), `PREVAILING_WAGES` — complexity flags.
- `n_mat_types` (count of non-zero material types) — a crude "how many trades"
  complexity proxy.

**Why it only runs on ~85% of projects.** ~15% of projects have *no* material
quantities recorded, so they have no recipe to cluster. We state that honestly:
those 215 projects get an `Unknown/NoQty` label and are held aside from the
clustering; for them we fall back to the always-present axes
(`Project_Size_Dollars`, and for competitive context `Num_Valid_Bidders`).

**Two ways to define archetypes (we did both and compared):**
1. **Rule-based** — codify CSI's own five named archetypes (Complex/Messy, Large
   Volume, Standard Paving, Earthwork Heavy, Shoulder/Base Only) as thresholds
   on the recipe + flags. Speaks CSI's language.
2. **Discovered** — let the data cluster itself: **PCA** (to compress the
   7-material recipe into 2-3 axes for stability/visualization) then **K-means**
   (to find natural groups). We chose **k=6** (highest silhouette = 0.57; re-seed
   stability ARI = **0.996**, i.e. essentially identical clusters on a different
   random start).

**Why compare them?** Their agreement is only **ARI ≈ 0.25** (low). That
disagreement is itself a finding: CSI's taxonomy mixes *scale* ("Large Volume")
and *complexity* ("Complex/Messy") concepts into what is otherwise a *shape*
question, so a pure shape-clustering cuts across CSI's labels. The data's
clusters are cleaner single-material shapes (MILL-, GRADE-, MIX-, BASE-, SHLDR-,
CRUSH-dominant).

> *Caveat we flag everywhere:* the proportions mix units (tons, cubic yards,
> square yards) in one denominator. It's a **compositional fingerprint**, not a
> physical fraction — fine for grouping by shape, not a literal "76% of the
> material is asphalt by weight."

---

## 5. Rationale for the metrics & drivers we selected

### 5a. Features used to characterize a job (inputs to both models)
| Feature | Why chosen | Notes |
|---|---|---|
| `log_size` = log10(`Project_Size_Dollars`) | Size is the strongest, always-present job descriptor. **Log** because project value spans $3 → $168M; raw dollars would let a few mega-projects dominate. | Primary size axis. |
| `State` (one-hot) | CSI's edge is geographic (pits in MN); ND/SD economics differ. | Captures "home turf." |
| `rule_archetype` + material `prop_*` | The job's *shape* — the WS-A spine. | Lets the model use "kind of work." |
| `BOX`, `PREVAILING_WAGES`, `n_mat_types` | Complexity proxies — CSI claims an edge on messy/complex jobs, so we must measure complexity. | Coarse; richer complexity needs the Plan Reader. |

### 5b. What we deliberately EXCLUDED, and why (the leakage decision)
For **Q1 (bid/no-bid)** we excluded everything not knowable *before CSI decides
to bid*:
- `Num_Valid_Bidders`, `Num_Bidders`, `Market_Tightness_Category` — these are
  **realized competition**. CSI doesn't know how many rivals will show up when
  it decides to bid. Including them would be **leakage** (using the future to
  predict the past) and violates project Hard Rule 10.
- `Winner_Amount`, `Second_Place_Amount`, `Bid_Quality`, `Margin_*`, `Bid_Rank`,
  and all `CSI_*` outcomes — these only exist *after* the auction.

For **Q2 (win)** we kept the *same* RFP-knowable feature set (not realized
competition) on purpose: we want the win signal expressed in **job-characteristic
space** ("what kinds of jobs does CSI win?"), which is the sweet-spot question —
not "did fewer rivals show up." Adding bidder counts would raise AUC but answer a
different question.

### 5c. Why these *outcome* metrics
| Metric | Definition | Why it's the right lens |
|---|---|---|
| **Bid rate** | P(CSI bids) per archetype | Answers Q1 directly — CSI's revealed preference. |
| **Win rate when bidding** | wins / bids | The raw "do we win" rate (117/603 = 19%). |
| **Win-well rate** | won at a *tight* price (`Bid_Quality` ∈ {Excellent, Acceptable Win}) / bids | A win isn't good if you overpaid. This is the *profitable*-win rate. |
| **Bomb rate / bomb-share-of-wins** | `Bid_Quality == "Bomb"` (won but bid >14% under 2nd place; median margin −14.5%) | This **is** the $22.3M "money left on the table" — the central inefficiency. |

**Why win-well, not just win:** the whole CSI problem is overpaying to win. A
model that maximizes *win rate* would push CSI toward more bombs. Splitting wins
into **well-priced wins vs bombs** is what makes the sweet spot actionable.

**Why no predictive margin model:** we tested a win classifier on job
characteristics — **ROC-AUC ≈ 0.51 (no signal)**. Whether CSI wins a job it bid
is driven by *price*, not job type. So a regression predicting margin from job
features would be modeling noise. The existing `Bid_Quality` / `Margin_Pct`
fields tell the price story descriptively, with no model risk. (Reversible — if
a specific "Bomb cluster" warrants it later, or CSI cost data is joined, we can
revisit.)

### 5d. Why permutation importance (not raw model coefficients)
For the bid model we report **permutation importance** (how much ROC-AUC drops
when a feature is shuffled). It's model-agnostic, handles the one-hot/numeric
mix cleanly, and measures *predictive* contribution rather than just coefficient
magnitude. (SHAP would be an alternative; permutation importance avoids an extra
dependency and is taught-toolkit-friendly.)

---

## 6. Method → MSBA coursework mapping

| Step | Method | Course |
|---|---|---|
| WS-A construction | **PCA** + **K-means / DBSCAN** on the recipe vector | EDA 6411 **Wk4 (PCA)**, **Wk5 (clustering)** |
| Using archetype to control selection | stratify / match on archetype | Causal Inference 6441 **Wk6 (PSM/matching)** |
| Q1 bid model, Q2 win model | logistic regression, gradient boosting, **AUC/PR** | MSBA 6421 **Wk1-3, Wk5**; 6131 Lec 2-4 |
| Reuse of bid-quality buckets | bomb/win bucketing | Fall 2025 `competitor_bid_quality_analysis.py` |
| *(not used)* formal selection correction | Heckman two-stage | **Not taught** — flagged as out-of-scope stretch |

---

## 7. Results in three lines (full version in findings doc)
1. **Sweet spot = Large Volume + Complex/Messy** — CSI bids these most (54%/48%)
   *and* wins them well (≈13%) with low bomb rates.
2. **CSI's selection is already well-calibrated** — bid-rate and win-well-rate
   correlate **0.91** across archetypes. It bids where it wins well.
3. **The leak is pricing, not selection** — 60-70% of CSI's wins in **Standard
   Paving** and **Earthwork Heavy** are bombs. The lever is price discipline on
   those archetypes, not different bidding.

---

## 8. Caveats (state these to any client)
- Win N is small (117) → the win *model* is under-powered **by design**; lean on
  the descriptive price overlay, not the model's AUC.
- Proportions mix units (compositional fingerprint, not physical fraction).
- ~14% of projects lack material data (`Unknown/NoQty`).
- Opportunity set = jobs that were let *and* we have results for in CSI's
  regions → Q1 is "bid given awareness," not pure demand.
- "Win-well / bomb" uses *competitive gap-to-winner* as the proxy for money left
  on the table — **not** true profit margin (no cost data in this file).

---

## 9. File map (`06_sweetspot/`)
```
README.md                         ← START HERE (the rule + how it was decided)
2026-06-15_project_type_definitions.md  ← the canonical archetype rule
2026-06-04_00_METHODOLOGY.md      ← this file (model approach + rationale)
archive/2026-06-04_sweetspot_findings.md  ← old findings (superseded labels)
notebooks/   01..05 annotated, runnable .ipynb (team walkthrough)
scripts/     01..05 .py (the same logic, headless)
outputs/     project_base.csv, project_archetypes.csv, *_by_archetype.csv,
             sweetspot_summary.csv, and 4 PNG figures
```
**Pipeline order:** 01 base table → 02 archetypes → 03 bid model → 04 win model
→ 05 sweet-spot map. Each step reads the prior step's CSV from `outputs/`.
