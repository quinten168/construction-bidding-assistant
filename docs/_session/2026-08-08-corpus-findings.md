# Corpus Findings — 2026-08-08

What is actually sitting in `CSI ELP 2026/` and why several settled decisions have to reopen.

I read the Aug 8 internal transcript, the Project Estimation Checklist, the Haul sheet, one `rtv-csv` bid item list, and scanned the folder tree. This is what changed.

---

## Inventory

| What | Count | Where |
|---|---|---|
| Bid result emails (`.msg`) | **909** | `<bid year>/<month>/Bid Results/` |
| PDFs, all types | 1,792 | throughout |
| Advertisement / addendum PDFs | 217 | project folders |
| Project folders under `Plans Proposals` | 95 | 2023 year alone |
| **`rtv-csv` bid item lists** | **38** | project folders |
| Notes & Quotes PDFs | 20 | project folders, 3 MB to 344 MB |
| Daily Ads PDFs | 174 | `Daily Ads/` |
| **No Bid project folders** | **150** | `No Bid/` |
| Project Estimation Checklists | 2 | `1 Estimating Info/` |
| Haul sheets | 4 | `1 Material Info/Blank Sheets/` |
| Other | — | `MN Pit List.xlsx`, `2026 Plant Schedule`, plant-sets `.kmz`, `GP by Job` for 23/24/25 |

Wenyu said on the call that there are "very few plans for us to test" for 23 and 25. That is true of what was pulled from Box in May. It is not true of what is on disk. The team is validating against a slice that does not reflect the corpus.

---

## 1. The `rtv-csv` bid item lists are the biggest find

38 files, machine readable, one per project. Header is `Category, Line, Item, Quantity`:

```
Base Bid - Participating,14,2104.504 REMOVE BITUMINOUS PAVEMENT (S Y),"15,067"
Base Bid - Participating,15,2106.507 EXCAVATION - COMMON (C Y),"7,707"
Base Bid - Participating,24,2211.509 AGGREGATE BASE CLASS 5 (TON),"5,849"
```

Three things fall out of this and each one is worth more than a week of the work currently on the board.

**A free golden dataset.** We have spent the entire project without a single extraction verified against a source document. Task 4 on the Aug 7 board — "sample extraction validation, never been done" — was scoped as a human transcribing bid schedules by hand for five plans. Thirty-eight of them already exist as CSV. Extraction validation stops being a manual exercise and becomes a join.

**The spec item number is right there.** `2211.509`. `2104.504`. `2360.509`. We have been building a fuzzy keyword matcher to guess whether `REMOVE AGGREGATE BASE` means base or demolition, and the state already answered that question by assigning the item a number. The number keys directly into the spec books the executor is about to index. That is the deterministic layer, and it is not something we have to invent — it is something we have to read.

This does not replace the LLM path. Item numbers only appear on state-form bid schedules, and municipal and consultant-let projects often write freeform descriptions with no number at all. But where the number exists it should win outright, and the keyword heuristic should never get a vote.

**The `Category` column answers a question we logged as needing an estimator.** "Duplicate 64,750 TON rows — alternate bid or double count?" Alternates are labelled `Alternate A`, `Alternate B` versus `Base Bid - Participating`. Sum the base bid, keep alternates separate, and the duplicate problem is a labelling problem rather than a mystery.

## 2. The Project Estimation Checklist is closer to done than anyone thinks

Adam's stated pain point. Here is the whole sheet against what we extract today:

| Checklist field | Do we have it? |
|---|---|
| Bid Date | Broken. This is item 5 below |
| County / State | Yes |
| Start ("within 90 days of sub completion") | No |
| Completion date | No |
| Job Name / # | Partial, 326 of 1,598 null |
| **Air Miles, shop to center of project** | Needs the midpoint. **This is what the midpoint is for** |
| Material Description / Unit / Quantity | Yes |
| Comment, Unit Price, Pit Name | No, estimator-entered |
| Will the pit take excavated material and structure? | No |
| Borrow (Clay) price needed out of a pit? | No |
| Materials mined below water? | No |
| **RAP available off project (plan qty)** | **No. We do not extract RAP at all** |
| Assumed available (90%), tons for Mix, tons for Shouldering, total excess/short | Arithmetic on RAP plus mix tons |
| Does the project have to be looked at, and when? | No |
| **Onsite crushing / stockpiling required? Type, location, quantity** | **We closed this as out of scope** |

Two corrections come out of that table.

**The midpoint has a concrete business use and it is not the map pin.** Air miles from shop to center of project is a line an estimator fills in by hand today, and the Haul sheet then consumes job length and a "does haul come out to middle" flag to compute trucking cost per ton. Midpoint plus gross length are not nice-to-haves for a map, they are inputs to a cost the estimator is already calculating manually.

**Crushing and stockpile should not have been closed.** We closed them on the evidence that under 5% of historical rows mention them and 1 of 117 plans had stockpile. That evidence was about *pay items*, and it was correct about pay items. But onsite crushing and stockpiling is a question on the checklist with three sub-fields, which means the estimator has to answer it on every job whether or not it appears as a line item. A field that is usually empty and always asked is a different thing from a field nobody needs. Reopen as a checklist field, not as a bucket.

**RAP is a real gap.** It has a plan quantity, a 90% availability convention, and it nets against mix and shouldering tons. We extract none of it.

## 3. Project identity is solved in the filesystem, not by geocoding

Every project folder is named the same way:

```
02.16.23 WALSH CO ND - WALSH CTY HWY 9 - HMA OVERLAY - KLJ2003-00613
02.22.23 CROW WING CO MN - SAP 018-603-024 & SAP 018-611-029 CSAH 3 & CSAH 11 ROUNDABOUT
```

Bid date, county, state, description, project number. And all 909 bid result emails carry date *and time*:

```
BID RESULTS 02_16_23 10_00 AM WALSH CO ND WALSH CTY HWY 9 - HMA OVERLAY - KLJ2003-00613.msg
```

Quinten wants bid date plus lat/long. T proposed state plus county plus reverse-geocoded city. Both are attempts to reconstruct from the document something CSI has been writing down consistently for three years in a filename.

My read: the identity key should be the state project number where one exists, with `{state}_{county}_{bid_date}` as the fallback, and the folder-name parse used to backfill the 326 nulls and to build the historical crosswalk. Reverse geocoding is a good way to get a city for display. It is a weak way to establish identity, because two projects in the same city on the same day are not distinguishable and two spellings of the same city are not the same string.

This is also worth pushing back on with Quinten directly. Lat/long as an identity component means a project's identity depends on a computed value that is currently null whenever gross length is missing. Identity should not depend on a derived field.

## 4. Document types are labelled in the filenames

Consistent across three bid years:

| Pattern | Type |
|---|---|
| `<number> AD.pdf` | Advertisement for bids. Small, and the authoritative bid date |
| `<number> QUANITIES.pdf` | Bid schedule. Misspelled identically every time, which makes it easy to match |
| `<number>.pdf` | Plan set, large |
| `<number>a1.pdf`, `a2`, `a3` | Addenda in order |
| `Proposal*.pdf` | Proposal, boilerplate heavy |
| `Notes & Quotes.pdf` | Estimator working notes |
| `Plan Holders*.pdf` / `rtv-csv-for-Plan Holders*.xlsx` | Bidder list |
| `rtv-csv-for-Bid Item List*.csv` | Machine-readable bid schedule |
| `GOOD Plans` / `JUNK Plans` | An estimator's own quality label, seen on Yankton |

T's proposed three-way classifier (proposal / plan set / both) is right and the filename gives us free training labels. But it should be five-way, not three: **advertisement, proposal, plan set, addendum, combined**. Addenda change quantities after the fact and we currently have no concept of them at all. That is a correctness problem hiding in plain sight — if a plan was extracted before addendum 2 revised the quantities, our number is wrong and nothing flags it.

## 5. Bid date, now with a much cheaper answer

Confirmed from the transcript that this is a live CI blocker, not a nice-to-have. Capacity is computed per bidding season, the season is determined by the bid date, and when the bid date is missing the system falls back to the construction completion date, lands in the wrong season, and reports zero capacity. Quinten also flagged that the capacity window is anchored on *today* rather than on the bid date, which is a second bug in the same area and is his to fix.

We already knew the date is in the plan set on the Advertisement for Bids page. What is new: there are **217 standalone AD PDFs** and **174 Daily Ads digests** in the corpus. An advertisement is a two-page document whose entire purpose is to state the bid date. Parsing the standalone AD where one exists is dramatically cheaper and more reliable than retrieving one page out of 466, and the Daily Ads folder is effectively a bid calendar for the whole region.

So the fix has three layers, cheapest first: parse the standalone AD file when the folder has one, fall back to the Advertisement for Bids page inside the plan set, and fall back to human entry in the review step. Wenyu is already building that third layer into the human-in-the-loop popup and asked for the field to exist.

## 6. Notes & Quotes — taxonomy first, as T said

20 files in the 2023 year, 3 MB to 344 MB. They are scanned. The 344 MB Blue Earth file is not something to run vision over speculatively.

T's instinct to get a lay of the land before deciding is right and I would hold that line hard. What these contain is how estimators actually think: subcontractor quotes, phone notes, scratch arithmetic, the reasoning behind a number. That is genuinely valuable and it is also the single easiest place on this project to spend a week and ship nothing. Sample five, categorise what is in them, write one page on whether there is a there there, and stop.

## 7. Two things from the transcript that need correcting before they propagate

**T said on the call "public doesn't need to really exist anymore."** In context he was talking about where new writes go, and new writes going to `scratch` is right. But `public` holds `full_markdown` for plans whose source PDFs no longer convert, so dropping it loses data that cannot be regenerated. If Quinten acts on the sentence as stated, that is a real loss. Worth a one-line message to the group.

**The cache exchange did not land.** Quinten came away thinking the cache was being removed, Mochen thought it was being kept, and both are half right. Job one is speed and stays. Job two is that `final_report.py` reads quantities out of the cache instead of the database, and that is what changes. This is now written down in the tasks doc so it stops being relitigated on calls.

---

## What I would reprioritise

Bid date extraction moves to P0 and stops being an extraction subtask. It is blocking a CI feature that is on the demo.

Extraction validation moves from "3 hours of manual transcription" to "join against 38 CSVs" and should happen before Wednesday, because it converts every accuracy claim in the presentation from an assertion into a measurement.

The spec-item-number path should be specced before the keyword heuristic gets any more work. We have been hand-building a classifier for a field that is already coded.

The Project Estimation Checklist export is the highest-value feature on the board that nobody has started, it maps to fields we mostly already have, and Adam described filling it in by hand as the thing he hates most about his job. That is the demo slide.
