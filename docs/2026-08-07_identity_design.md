# Row identity vs. project identity — design for review

Date: 2026-08-07 · Status: **DESIGN ONLY, nothing built.** Approve before implementation.

Every number in this document was measured against live `scratch.bid_projects` (1,598 rows) and
`scratch.bid_results` (6,803 rows) on 2026-08-07, not inferred. Queries are reproducible from the
"Evidence" section at the bottom.

---

## 1. The two things we have been conflating

| | ROW identity | PROJECT identity |
|---|---|---|
| Question | "is this the same PDF I already read?" | "is this the same real-world job as a CSI historical row?" |
| Nature | a **key**. Deterministic, total, stable. | a **matching problem**. Probabilistic, partial, revisable. |
| Answer | `plan_uid` (PDF byte hash) — already correct, keep it | scored reconciliation, run as a separate step |
| Failure mode | collision (never observed) | false merge (destroys a row) / false split (duplicates one) |

The cost of the last week came from trying to make one identifier do both jobs. A key that is also a
match becomes wrong whenever the world disagrees with it, and a key cannot be "somewhat" wrong.

## 2. Recommended primary key: keep `plan_uid`, and stop overloading `project_natural_key`

**PK for plan_reader rows: `plan_uid`** (SHA-256 of the PDF bytes). It is deterministic, requires no
extraction to succeed, cannot be affected by a bad geocode or an unparseable date, and is already
implemented. Nothing about the reconciliation design below changes it.

**`project_natural_key` is demoted from key to attribute.** Today it is
`{state}_{county}_{city}_{bid_date}` and it is doing double duty: it is the PK of
`scratch.bid_projects` *and* the intended join to history. It cannot be both, for a reason now
measured rather than suspected:

> **`geocoded_city` is populated on 0 of 1,598 rows. So is `geocoded_zip`.**

The `city` component of every existing key is the `UNKNOWN` sentinel or came from somewhere other
than the geocoder. A key whose discriminating component is constant is not discriminating. This is
also the direct answer to "evaluate city and zip as alternatives" in §4 — there is nothing to
evaluate against, and the coverage is not merely poor, it is zero.

Recommendation: keep `project_natural_key` as a stable surrogate for the CI join that already
depends on it, but **stop treating it as evidence of sameness**, and add an explicit
`matched_project_key` column that reconciliation writes and only reconciliation owns.

## 3. Reconciliation as a separate step

Runs after extraction, never inside it. Never deletes, never merges automatically above the
threshold — it proposes.

**Stage 1 — blocking key (exact).** `state` + `county` + `bid_date`. Coverage is excellent:
`state` 100%, `bid_date` 100%, `county` 99.9%. This is cheap and correct as a *candidate generator*.
It is not a decision: it produced 198 same-county-same-date pairs in the corpus, and their median
separation is 10.3 miles, so most of them are genuinely different jobs that happened to let the same
day in the same county.

**Stage 2 — geographic proximity as the tiebreaker among Stage-1 candidates.**

### Recommended N = 1 mile. Justification, measured.

I compared two distributions inside the same county+state: pairs sharing a `bid_date` (which
*contains* the true same-project pairs) against pairs with different `bid_date`s (which are all
definitely different projects, so they are the false-positive baseline).

| radius | same bid_date | different bid_date | discrimination |
|---:|---:|---:|---:|
| 0.5 mi | 8.6% | 1.1% | **7.8×** |
| **1 mi** | **14.6%** | **2.9%** | **5.0×** |
| 2 mi | 19.2% | 7.1% | 2.7× |
| 5 mi | 30.3% | 21.0% | 1.4× |
| 10 mi | 49.5% | 41.6% | 1.2× |
| 25 mi | 84.3% | 84.3% | **1.0× — none** |

**The discrimination collapses fast.** At 5 miles proximity is barely better than chance; at 10 it is
noise; at 25 it is nothing at all, because a 25-mile radius covers most of a typical MN/ND county.
Any N large enough to absorb a human's guessing error is also large enough to match unrelated
projects. That is the central finding, and it is why proximity has to be a tiebreaker rather than a
matcher.

I recommend **1 mile** as the auto-accept radius and **1–5 miles as a review band** that surfaces the
pair to a human rather than merging it. Above 5 miles, proximity contributes nothing and should not
be scored at all.

### The caveat that limits all of this

You told me the lat/long on CSI's 2024/2025 historical rows is a human eyeballing a midpoint into a
spreadsheet. **I could not measure that error** — doing so needs Jay's ArcGIS midpoints for the same
projects side by side, and I do not have them. If the typical human error exceeds ~1 mile, a 1-mile
radius will miss true matches, and the table above says widening it to compensate buys false
positives faster than it buys true ones. **This is the single measurement that should happen before
this design is built**: take 20 projects with both a human and an ArcGIS midpoint and plot the error.
If the error is mostly under a mile, this design works. If it is 5+ miles, geographic proximity is
not a usable tiebreaker for historicals at all and we should fall back to human review on the
Stage-1 candidate set, which is small (198 pairs corpus-wide).

**Why proximity is still better than city or zip here:** not because it is strong, but because city
and zip are at 0% coverage and rural highway midpoints frequently reverse-geocode to no locality at
all — your hypothesis, and the 0/1,598 figure is consistent with it (the geocoder was also disabled
for billing reasons, #56, so the 0% has two possible causes and I have not separated them). Proximity
at least degrades gracefully and is measurable; city is absent and would need to be built before it
could be evaluated.

## 4. Where CP/SP fits — and your correction, tested

You corrected me that CSI *does* carry the CP/SP number, heavily NULL. **Both halves need adjusting.**

There is **no CP/SP column** in `bid_projects` (I checked all 61 columns). The number is embedded as
free text inside `source_project_id` (1,272/1,598 non-null) and `project_name` (1,587/1,598), e.g.
`'SAP 003-607-027'`, `'CP-13(26)04'`, `'SP 033-606-023 MN PROJ STBG 3325(273) …'`. So it is neither
absent nor a NULL-able column — it is unparsed text in two columns, which is a third thing and needs
a regex extraction pass before it can be used at all.

**Your hypothesis — that the number was only recorded for jobs CSI engaged with — is directionally
right but too weak to act on.** The naive test is degenerate (1,587 of 1,598 rows have bid results,
so "has results" splits nothing). Testing CSI's own participation instead:

| CSI engagement | rows | has CP/SP-shaped id | `source_project_id` non-null |
|---|---:|---:|---:|
| did not bid | 992 | 36.7% | 76.3% |
| bid, lost | 488 | 49.2% | 84.4% |
| **won** | 118 | 45.8% | 87.3% |

The effect is real and significant at these sample sizes, but it is ~37% → ~46–49%, not the
near-total presence "identifier on engaged projects" implies, and it is **non-monotonic** for CP/SP
(won is lower than bid-and-lost). `source_project_id` presence is monotonic but only spans 76% → 87%.

**Conclusion: the column is neither "reliable" nor "reliable on engaged projects". It is ~40%
present regardless of engagement.** It cannot carry historical matching under any framing.

**Where it does fit, unchanged from your instruction: extract it going forward.** It is the DOT's own
identifier, it appears on both plan sets and proposals, and it is the join key for the multi-document
model (4b's source arbitration depends on having one). It makes NEW-to-NEW matching exact and cheap.
It just cannot reach backwards.

## 5. Does this retire Monday's content-hash suffix and provisional-key machinery?

**Partly. Recommend keeping both, with a narrower job.**

- **Content-hash suffix on sentinel keys** (`ef6d360`) — **KEEP.** It exists so a key collision cannot
  destroy a row, and that is a row-identity concern, which this design does not touch. It is also the
  mitigation for the 2026-08-03 destroyed row. Retiring it would re-open that hole.
- **Provisional keys** (`key_provisional`, `key_provisional_reason`) — **KEEP, and they become more
  useful, not less.** Under this design a row is provisional exactly when reconciliation has not
  matched it, which is a real and now-explicit state rather than a workaround. #73's "recomputing
  provisional keys needs a MERGE strategy, not a bare UPDATE" stays open and is if anything more
  clearly required, because reconciliation will be re-run as evidence improves.

What *is* retired is the **premise** behind them: that a provisional key becomes real once extraction
gets good enough. It does not. It becomes real when reconciliation matches it, which is a separate
event that may never happen for a project CSI has no history of — and that is a correct outcome, not
a failure.

---

## Evidence

Measured 2026-08-07 against live `scratch` via `SUPABASE_TEAM_DB_URL`:

- 61 columns on `bid_projects`; no column matching `%cp%`/`%sp%number%`/`%proj%no%`.
- Coverage: `state` 1598/1598, `bid_date` 1598/1598, `county` 1596/1598, coordinates 1590/1598
  (99.5%), `geocoded_city` **0/1598**, `geocoded_zip` **0/1598**.
- Distance distributions: 198 same-county+state+bid_date pairs, 11,101 same-county different-date
  pairs, haversine miles.
- CP/SP regex: `\m(CP|SP|SAP|PCN|NH|IM|STBG)\M[- ]?[0-9]` over `source_project_id` and `project_name`.

**UNVERIFIED / not measured:**

- The magnitude of human midpoint-guessing error on historical rows. Gates the N=1 recommendation.
- Whether `geocoded_city` is 0% because the geocoder never ran, because it was billing-disabled
  (#56), or because rural midpoints genuinely return no locality. Three causes, one observation.
- Whether the 198 same-day same-county pairs contain any true duplicates at all. Nobody has looked at
  them by hand; the design assumes some exist.
