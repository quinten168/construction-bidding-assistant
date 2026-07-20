# How We Classified Job Types (and Built the Sweet-Spot Table)

**A 3-minute explainer for the team.** · 2026-06-11
*Full version: `2026-06-04_00_METHODOLOGY.md` · Results: `2026-06-04_sweetspot_findings.md`*

---

## The idea in one line

We label every project by the **kind of work** it is (its "archetype"), so we can
ask two questions in the same vocabulary:


---

## 1. How a project gets its job type

Every project has a bill of materials: tons of asphalt (`MIX_TN`), cubic yards of
earthwork (`GRADE_CY`), tons of base/shoulder, square yards of milling, etc. We
run each project down a **priority ladder** — the *first* rule that matches wins,
and we stop there:

| Order | Test | → Label |
|---|---|---|
| 1 | Box culvert present **OR** ≥ 5 different material types | **Complex/Messy** |
| 2 | More than **10,000 tons** of asphalt (`MIX_TN`) | **Large Volume** |
| 3 | Earthwork is **≥ 50%** of the material mix | **Earthwork Heavy** |
| 4 | Base + Shoulder are **≥ 60%** of the mix **and** asphalt is **< 20%** | **Shoulder/Base Only** |
| 5 | *(anything that didn't match above)* | **Standard Paving** |
| — | No material quantities recorded at all | *Unknown/NoQty* (set aside) |

**Why this order matters.** We check **complexity first, then size, then
composition** — on purpose. A big, complicated job (box culvert + 10,000+ tons of
asphalt) lands in **Complex/Messy**, not Large Volume, because the complexity is
what defines CSI's edge on it. The ladder encodes that priority.

*(This is the exact logic in `scripts/2026-06-04_02_archetypes.py`, the
`rule_archetype()` function.)*

---

## 1b. Where these five categories came from (the methodology)

We didn't invent the categories — we **used CSI's own five named archetypes**
(Complex/Messy, Large Volume, Standard Paving, Earthwork Heavy, Shoulder/Base
Only, from the project domain glossary) and then **codified them as data rules**
so a computer can apply them consistently to all 1,591 projects. That's the ladder
above.

But we didn't just trust that those five labels match how the data actually
clusters. We ran a **second, independent method** and compared:

| Method | What it is | Course / technique |
|---|---|---|
| **(1) Rule-based** *(what the table uses)* | CSI's 5 named types, turned into the threshold ladder above. Speaks CSI's language. | Domain rules |
| **(2) Discovered** *(the cross-check)* | Let the data group itself: **PCA** to compress the 7-material recipe into 2–3 axes, then **K-means** to find natural clusters. No human labels. | EDA 6411 — Wk4 (PCA), Wk5 (clustering) |

**How we picked the number of data clusters.** For method (2) we tested k = 3…6
and chose **k = 6** because it had the highest *silhouette score* (0.57 — a
standard measure of how cleanly separated the clusters are). We also re-ran it
with a different random start and got essentially identical clusters
(*stability ARI = 0.996*), so the grouping isn't an artifact of one random seed.

**What the comparison told us.** The two methods only **agree weakly**
(*Adjusted Rand Index ≈ 0.25*). That disagreement is itself a finding, not a
problem: CSI's taxonomy blends **scale** ("Large Volume") and **complexity**
("Complex/Messy") into what the data sees as a pure **shape** question — so a
pure shape-clustering naturally cuts across CSI's named buckets. The data's own
clusters are cleaner single-material shapes (asphalt-dominant, earthwork-dominant,
milling-dominant, etc.).

**Why we report the rule-based labels (not the discovered ones).** They speak
CSI's language and are directly actionable in a bid meeting. We keep the discovered
clustering as a **validation layer** — it confirms the rule-based types are real
groupings in the data, and it surfaces things the rules miss (e.g. shoulder-heavy
work has by far the lowest bomb rate — CSI prices it tight when it wins).

---

## 2. "Share" means recipe, not amount

Rules 3 and 4 talk about **shares** (e.g. "earthwork ≥ 50% of the mix"), not raw
tonnage. That's deliberate. We convert each project's quantities into
**proportions that add up to 100%** — its *recipe*:

> "76% asphalt, 7% earthwork, 6% base, …"

This makes the label about the **shape of the job, not its dollar size**. A $50k
repaving and a $5M repaving are the *same kind of work* (mostly asphalt), so they
get the same recipe and the same label. Size is tracked separately, not baked into
the type.

> ⚠️ *Small caveat:* the recipe mixes units (tons, cubic yards, square yards) in
> one denominator, so it's a rough "compositional fingerprint" for grouping —
> not a literal physical fraction. Good enough to sort jobs by shape.

---

## 3. What the three columns in the table mean

| Column | Plain English |
|---|---|
| **Bid rate** | Of *all* projects of this type, what % did CSI choose to bid on? (CSI's revealed preference.) |
| **Win-well rate** | Of the projects CSI bid, what % did it **win at a tight price**? A win where it did *not* overpay. |
| **Bomb share of wins** | Of the jobs CSI *won* in this type, what % were **"bombs"** — won by bidding **>14% under** the next-lowest bidder (i.e. money left on the table)? |

The key one is **win-well** vs. just "win." A win isn't good if CSI overpaid to
get it — that's the $22.3M leak. Splitting wins into *well-priced wins* vs *bombs*
is what makes the table actionable.

---

## 4. The table, and how to read it

| Archetype | bid rate | win-well rate | bomb share of wins | read |
|---|--:|--:|--:|---|
| **Large Volume** | 54% | 13.4% | 32% | ✅ sweet spot — lean in |
| **Complex/Messy** | 48% | 13.0% | 30% | ✅ sweet spot — CSI's edge |
| Shoulder/Base Only | 36% | 6.7% | 40% | ⚪ marginal |
| **Standard Paving** | 28% | 8.2% | **61%** | 🔴 pricing leak — when it wins, it overpays |
| **Earthwork Heavy** | 26% | 4.4% | **70%** | 🔴 avoid / reprice — worst on both |

**Two zones to act on:**

- 🟢 **Lean in — Large Volume + Complex/Messy.** High bid rate, high win-well,
  low bomb rate. This is CSI's defensible edge — protect and prioritize it.
- 🔴 **Fix pricing — Standard Paving + Earthwork Heavy.** CSI already bids these
  *least*, but **60–70% of the few it wins are bombs**. The fix is **price
  discipline** on these archetypes, not bidding more or less of them.

**Bottom line:** CSI's *bid-selection* instinct is already well-calibrated (it
bids where it wins well — correlation 0.91). The money leak is a **pricing**
problem inside the two low-value archetypes, not a selection problem.

---

## Caveats (worth knowing before you quote it)

- **Small win count.** CSI won only 117 jobs in the window, so per-archetype win
  numbers are descriptive, not a precise model.
- **Labels are rule-based** on CSI's own five named archetypes (the thresholds
  above) — not a black-box clustering.
- **~14% of projects** have no recorded quantities and sit in *Unknown/NoQty*,
  held aside from the table.
- **"Bomb" uses gap-to-runner-up**, not true profit margin (we have no cost data
  in this file) — it's the best available proxy for "left money on the table."

*Want the full why-we-did-it-this-way? See `2026-06-04_00_METHODOLOGY.md`.*
