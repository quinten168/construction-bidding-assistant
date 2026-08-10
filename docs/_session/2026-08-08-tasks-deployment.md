# Tasks & Deployment — Sat Aug 8, evening reset

Supersedes every earlier version. Scope narrowed deliberately: **core quality, core dependencies, solid data practices.** Features do not go on a weak foundation. Good ideas that are not foundation went to the backlog and that is fine.

| Milestone | Date |
|---|---|
| Final presentation | **Wed Aug 12** |
| Handoff to Shane (CSI IT) | **Mon Aug 17, 10am** |
| Program ends | Fri Aug 21 |

---

# THE FIVE P0s

Nothing else competes with these before Wednesday.

| # | Task | Owner | Why it is P0 |
|---|---|---|---|
| **1** | **Golden dataset** — find and join every machine-readable bid item list in the corpus, validate extraction against them | agent | Turns every accuracy claim in the presentation from an assertion into a measurement |
| **2** | **Chroma hosted** | T + agent | Team has to test before Wednesday, multi-user |
| **3** | **Material mapping solid** — Alex's 11 rulings into `schema.py`, no-regression proof, spec-item-number path specced | agent | The one artifact that runs live still does not carry Alex's feedback |
| **4** | **Bid date and time** | agent | Blocking a CI feature that is on the demo |
| **5** | **Key dates and phasing gotchas** | agent | Estimators bid differently when the schedule is split. Currently invisible to us |

Research, parallel, subagents, cheap: **state spec books Tier 1.**

---

## 1. Golden dataset

**The find.** 38 `rtv-csv-for-Bid Item List*.csv` files sit in the project folders under `CSI ELP 2026`. Machine readable:

```
Category,Line,Item,Quantity
Base Bid - Participating,14,2104.504 REMOVE BITUMINOUS PAVEMENT (S Y),"15,067"
Base Bid - Participating,24,2211.509 AGGREGATE BASE CLASS 5 (TON),"5,849"
```

T has additional datasets of this kind beyond the 38. **A subagent explores first and reports what exists before anything is built.**

**Three things this gives us.**

Extraction has never once been validated against a source document. The plan for doing it was a human transcribing five bid schedules by hand. Thirty-eight already exist as CSV, so validation becomes a join.

The state spec item number is present. `2211.509`. We have been hand-building a fuzzy keyword matcher to decide whether `REMOVE AGGREGATE BASE` is base or demolition, and the state already answered by assigning a coded item number that keys into the spec books. Where the number exists it should win outright and the keyword heuristic gets no vote. It will not cover municipal and consultant-let jobs that write freeform descriptions, so the LLM path stays.

The `Category` column labels `Alternate A` / `Alternate B` versus `Base Bid - Participating`, which answers the duplicate 64,750 TON question we had logged as needing an estimator.

**Deliverables.** Inventory of every golden source found. A benchmark table in `scratch` joining extracted quantities to golden quantities by plan and item. Precision, recall and absolute variance per bucket. The `is_golden` / `verified_at` / `verified_by` columns from the earlier board, now with real data behind them.

## 2. Chroma hosted

Decision doc plus setup walkthrough, then T deploys.

Settled, do not re-argue: local `PersistentClient` is what ships to CSI at handoff; hosted is a disposable bridge deleted Aug 17; the team needs multi-user before Wednesday; Shane's deployment is single-user. Railway path is the `chromadb/chroma` Docker image deployed directly, not a GitHub connect.

Must answer rather than defer: does `chromadb` 1.5.9 embed client-side against a hosted server, or does the server need the model? Railway's default volume-backup behaviour? Migration path for 75,080 chunks and how long it runs?

## 3. Material mapping solid

Alex's 11 rulings hand-applied to the seven prose field descriptions in `schema.py`, with a no-regression proof on the five plans where we already have crosswalk agreement. Delete nothing.

Then **spec the spec-item-number path before touching `SPEC_MAP` again.** Layer order becomes: coded item number wins where present, then the LLM read, then the keyword heuristic as a last resort with a loud `never_matched`. We have been building a classifier for a field that is already coded.

Dunn drop test still open: does 72,153 TON of `REMOVE AGGREGATE BASE` land in `base_tons`?

## 4. Bid date and time

**Confirmed from the Aug 8 call that this is a live CI blocker.** Capacity is computed per bidding season, the season comes from the bid date, and when the bid date is missing the system falls back to the construction completion date, lands in the wrong season and reports zero capacity. Quinten separately flagged that the capacity window is anchored on *today* rather than the bid date. That second one is his.

**The earlier note that the bid date is "not on the plan set title sheet, only in the proposal" was wrong** and must not be inherited. It is in the plan set in plain body text: `9786015.pdf` page 9 of 466, City of Fulda CSAH 2, "Thursday, August 7, 2025, at 11:00am local time."

**It is also cheaper than we thought.** There are 217 standalone `AD.pdf` advertisement files in the corpus and 174 daily-ad digests in `Daily Ads/`. An advertisement is a two-page document whose entire purpose is to state the bid date.

Three layers, cheapest first: parse the standalone AD when the folder has one, fall back to the Advertisement for Bids page inside the plan set, fall back to human entry. Wenyu is building that third layer into the human-in-the-loop popup and asked for the field.

Diagnose the plan-set path either way: does that page survive into Chroma as a chunk? If not, the boilerplate filter ate it, and the Chroma audit already found 699 boilerplate paragraphs stripped from one plan. If it does survive, retrieval is not surfacing it. Two methods, name both.

## 5. Key dates and phasing gotchas

Four dates, in priority order:

| Date | Note |
|---|---|
| **Bid submission deadline** | Task 4. The most important one |
| **Project start date** | Often relative, e.g. "within 90 days of substantial completion" |
| **Final completion date** | On the proposal terms |
| Interim / staged completion dates | Only where the schedule is split |

**Phasing is the gotcha that matters.** The pattern estimators care about: the project runs, then breaks, then they come back weeks later to finish. Six weeks is typical. They hate it, they price it differently, and it is currently invisible to us. Extract phasing as a flagged gotcha with the page citation and the stated interval where one is given, not as a boolean.

---

# BACKLOG — good, not foundation

**Project Estimation Checklist export.** Adam's stated pain point, "I just fucking hate doing it," Rebecca confirming. Its header fields map closely to what we already extract: bid date, county/state, job number, materials with unit and quantity. Gaps are completion date, start date, RAP and air miles. This is the best demo slide on the board and it is a feature, so it waits for the foundation. Aug 13 to 16 at the earliest.

**Air miles and the midpoint's real use.** Shop to center of project is a line the estimator fills by hand, and `Haul.xlsx` then consumes job length and a "does haul come out to middle" flag to compute trucking cost per ton. The midpoint is not a map feature, it is an input to a cost they already calculate manually. Gross length, currently marked "Rare, Hard," is the other half.

**RAP.** Straight gap. Plan quantity, a 90% availability convention, nets against mix and shouldering tons. We extract none of it.

**Crushing and stockpile, reopened.** We closed these because they are under 5% of historical pay items. That was correct about pay items and beside the point: onsite crushing/stockpiling is a checklist question with three sub-fields that the estimator answers on every job. A field that is usually empty and always asked is not a field nobody needs. Reopen as a checklist field, not as a bucket.

**Addenda.** We have no concept of them. Filenames label them consistently as `a1`, `a2`, `a3`. If a plan was extracted before addendum 2 revised the quantities, our number is wrong and nothing flags it. Same silent-failure shape as everything else on this project.

**Notes & Quotes.** 20 files in the 2023 year alone, 3 MB to 344 MB, scanned. Taxonomy on five, one page on whether there is value, stop. Easiest place on this project to spend a week and ship nothing.

**Also backlogged:** one declarative mapping source generating the other three · repo file taxonomy and cleanup · cache demotion · F3 full-spec export · F2 four-state · rewire 19 batch writers · retire `csi_v2.db` · Tier 2 vision · Tier 2 spec-book indexing · CAD text-layer exclusion · multi-document model · conversion factors with CSI · front-end errors #51/#52 · `public` drop-and-recreate to upsert · spec-book-driven aggregate class extraction · traffic level

---

# PROJECT IDENTITY — decided

**Key order: state project number where one exists, then `{state}_{county}_{bid_date}`. Folder-name parse backfills the 326 nulls. Reverse geocoding is for display, not identity.**

Every project folder in the corpus is named the same way:

```
02.16.23 WALSH CO ND - WALSH CTY HWY 9 - HMA OVERLAY - KLJ2003-00613
```

Bid date, county, state, description, project number. All 909 bid-result emails carry date and time in the filename. Both proposals on the table were attempts to reconstruct from the document something CSI has been writing down consistently for three years.

**Pushback for Quinten:** lat/long as an identity component makes identity depend on a derived field that is null whenever gross length is missing. Identity should not depend on a computed value. Two projects in the same city on the same day are also not distinguishable by city, so reverse geocoding does not close it either.

---

# DOCUMENT TYPE — five-way, not three

The filenames already label the classes, consistently across three bid years:

| Pattern | Type |
|---|---|
| `<n> AD.pdf` | Advertisement. Small, authoritative on bid date |
| `<n> QUANITIES.pdf` | Bid schedule. Misspelled identically every time, trivially matchable |
| `<n>.pdf` | Plan set. Large, CAD drawings, earthwork summary |
| `<n>a1.pdf`, `a2`, `a3` | Addenda, in order |
| `Proposal*.pdf` | Proposal. Boilerplate heavy, no CAD, typically 8.5x11 |

Combined documents containing both a proposal and a plan set exist and need their own label. Free training labels from the filenames.

---

# CORRECTION LOG — do not inherit the old version

**Bid date** is in the plan set and in 217 standalone AD files. Previously recorded as absent. Wrong.

**CP / SP number.** CSI does carry it, as `source_project_id` on `bid_projects`, 326 of 1,598 null.

**`public` is not disposable.** On the Aug 8 call T said "public doesn't need to really exist anymore." In context that meant new writes go to `scratch`, which is right. But `public` holds `full_markdown` for plans whose source PDFs no longer convert, so dropping it loses data that cannot be regenerated. **Worth one line to the group before Quinten acts on the sentence as stated.**

**The cache.** Quinten left the Aug 8 call thinking it was being removed, Mochen thought it was being kept, both half right. Job one is speed and it stays. Job two is that `final_report.py:312` reads quantities out of the cache instead of the database, and that is the part that changes. Demote, do not remove.

**The 11 `bid_projects` rows** came from the LLM path via `_QMAP`. The crosswalk never touched them.

**Test corpus.** Wenyu said there are very few plans to test for 23 and 25. True of the Box pull from May, not true of disk: 1,792 PDFs, 95 project folders in the 2023 year alone, 150 no-bid folders. The team is validating against a slice that does not reflect the corpus.

---

# CONFIDENCE LEVELS — open, and client-facing

Wenyu asked on the call how high, medium and low are defined and what threshold we set. There is no answer today. The report shows confidence badges to CSI, so if Alex asks Wednesday what "medium confidence" means, we need a sentence. Whatever it is, write it down and make it match what the code does.

---

# NEEDS T OR CSI

| What | Who |
|---|---|
| Hours an estimator spends per plan set today | Alex or Adam. One text |
| `csi_reader` DSN for a true login test | T |
| Conversion factors, the 5 with no defensible answer | CSI, after Wednesday |
| Confidence-level definitions | T decides, then it gets documented |

---

# STANDING RULE

**Never let a failure and a legitimate empty answer share a return value.**

Nine instances: HTTP 200 with an error body · `REVOKE` that succeeds and does nothing · a duplicate check that never examined the destroying case · `--dry-run` that skips the SQL · a missing keyword and a deliberate exclusion rendering identically · confident absence from a partial view · a matcher returning zero instead of an error (×6) · a verified number and an unverified one looking the same · **a plan extracted before an addendum revised the quantities, with nothing flagging it**
