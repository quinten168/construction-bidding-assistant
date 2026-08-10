# Bid-date query split — P0 #4a

**2026-08-10.** The fix the diagnosis in `docs/_session/2026-08-10-bid-date.md` §2 identified, plus
the measurement that proves it and the measurement that proves nothing else got worse.

Spec: `docs/_spec/2026-08-10-bid-date-query-split.md`.

---

## 1. Headline

| | before | after |
|---|---|---|
| **Murray p.9 rank** (`2025_MURRAY-CO-MN_CSAH-2_NOBID:p9:c0`, "until Thursday, August 7, 2025, at 11:00am local time") | **40** | **3** — inside k=5 ✅ |
| `bid_deadline` hit@5 across 33 plans that state a deadline | 12 (36%) | **20 (61%)** |
| `substantial_completion` / `final_completion` hit@5 across 24 plans | 7 (29%) | **7 (29%) — unchanged by construction** |

`s4_extract_rag.fill_rag_fields` pulls **k=5**. Before this change the page that answers the
question was 35 places outside the window Claude ever saw.

## 2. What changed

One entry in `SCALAR_QUERIES` (`pipelines/plan_reader/01_pipeline/s4_extract_rag.py`) became two.

`bid_deadline` gets its own query:

```
Bids for the construction of the Project will be received at the office until 11:00 a.m. local
time, at which time the Bids received will be publicly opened and read aloud. Advertisement for
Bids. Letting date. Bids close.
```

`substantial_completion` + `final_completion` keep the **byte-identical** old string. Same text,
same `k=5`, same `where` filter, therefore the same retrieved context — those two fields cannot have
regressed, and that is provable rather than merely measured. The re-run confirms it: 7/24 before,
7/24 after, Murray 71st before, 71st after.

**Cost: one extra Claude call per plan** (`fill_rag_fields` goes from ~6 to ~7). Accepted — it is a
two-field prompt over five chunks, and `bid_deadline` is a field CSI cannot bid without.

### Why a sentence and not a keyword list

Every keyword-bag variant scored 33–42% hit@5 and left Murray at rank 7–23. The prose variants
scored 55–64% and put Murray at 2–3. MiniLM is a *sentence* embedder; a bag of nouns does not land
near a paragraph of advertisement prose. This is the single largest effect in the whole sweep and
it is worth remembering the next time a retrieval query in this repo gets written as a keyword list.

### The clock time is not an overfit

`11:00 a.m.` in the query is not Murray's answer leaking in. Substituting `10:00 a.m.` gives hit@5
19; `2:00 p.m.` gives 20; the shipped `11:00 a.m.` gives 20. Murray ranks 3 under all three.
Removing the time entirely ("until local time on the date stated") collapses hit@5 to 10. The
numeral is what makes the string *look like* a bid-opening sentence to the embedder — any plausible
bid-opening hour does the job. (The query is never shown to Claude; only the retrieved chunks are,
so there is no leakage path even in principle.)

## 3. How it was measured — ground truth, not vibes

Ground truth is a **strict** regex over the raw Chroma chunks: a chunk counts only if it *states*
the answer, not if it mentions the concept.

- bid: a `bids … received … until <date>` sentence, or `Letting Date: <date>`, or
  `bid opening … <date>`.
- completion: a `substantially complete … on or before <date>` sentence.

A first, looser version of the regex matched five Murray chunks — a table of contents, the
publication line, a cross-reference in the Instructions to Bidders — and would have reported the
bid deadline as rank 11 instead of 40. Tightened until it selects exactly `:p9:c0` and `:p55:c0`,
which are the two chunks that actually carry Murray's answers.

The eval set is discovered from the store, not hardcoded: every canonical `20xx_…` plan with ≥100
chunks and 1–3 ground-truth chunks. That gives **33 plans** for the bid deadline and **24** for the
completion pair.

Per-plan bid-deadline result, new rank ← old rank (all 33; `-` = not in the top 100):

```
  1 <-  40  2023_CLAY-CO-MN_8429196          1 <-   5  2023_OTTER-TAIL-CO-MN_8412890
  1 <-   3  2023_WILKIN-CO-MN_TH-75          1 <-   8  2025_DIVIDE-CO-ND_9776856
  1 <-   2  2026_OTTER-TAIL-CO-MN_CSAH-82    1 <-   3  2026_SWIFT-CO-MN_CSAH-15
  1 <-   2  2026_UNKNOWN-CO-MN_TH-114        1 <-   1  2026_UNKNOWN-CO-MN_TH-94
  2 <-   4  2023_MAHNOMEN-CO-MN_SP-4407-13   2 <-  33  2023_MCLEAN-CO-ND_8370470
  2 <-   5  2025_WATONWAN_WATLINE-TRAIL      2 <-  92  2026_UNKNOWN-CO-ND_ND-2026
  3 <-   8  2023_WATONWAN-CO-MN_SP-8303-48   3 <-   5  2025_HUBBARD-CO-MN_SP-2905-39
  3 <-  40  2025_MURRAY-CO-MN_CSAH-2         3 <-  59  2026_MOUNTRAIL-CO-XX_CR-2
  4 <-   5  2023_CLAY-CO-MN_TH-94            4 <-   5  2023_KANDIYOHI-CO-MN_TH-23
  5 <-  63  2023_BURLEIGH-CO-ND_8428114      5 <-   4  2023_HUBBARD-CO-MN_TH-200
  7 <-   -  2023_RICHLAND-CO-ND_ND-10        9 <-  39  2025_DOUGLAS-CO-MN_SAP-021-600-023
 32 <-  96  2025_DUNN-CO-ND_9782095         33 <-  85  2026_DUNN-CO-ND_ND-9969
 37 <-  57  2023_EMMONS-CO-ND_8435627       46 <-  85  2023_DUNN-CO-ND_CP-13
 55 <-   -  2026_BOWMAN-CO-ND_10211449       - <-   -  4 SD/ND plans (see below)
```

**One plan moved in the wrong direction and it does not leave k=5**: Hubbard TH-200, 4 → 5. Every
other change is an improvement or a tie. Two plans that were not retrievable at all inside the top
100 now are.

**The residue is ND/SD county-let work**, and it is a different failure. Their advertisements are
worded `Notice is hereby given that sealed bids will be received by the County Commission … until
10:00 AM (MT), February 15, 2023` (Dunn CP-13) or headed `BID OPENING DATE – February 28, 2023 at
1:30 PM` on a project-manual cover (Brookings, Beadle — both IMEG). Three query variants that
added that vocabulary explicitly all scored *worse* overall (33–52%), so it was not shipped. Those
plans are exactly the ones `04_tools/bid_date/` layers 1 and 2 already read deterministically —
which is the argument for the layering, not against it.

## 4. Coverage test

`pipelines/plan_reader/01_pipeline/test_bid_deadline_retrieval.py` — 11 tests, all passing.

It does not assert "retrieval returned 5 results". It asserts:

- **the Murray advertisement chunk is inside k=5** under the query read out of `SCALAR_QUERIES`
  itself, so the test cannot drift away from the shipped configuration;
- the chunk is in the store at all (rules out "the converter or the boilerplate filter lost it" as
  an explanation for any future miss);
- **the OLD query still fails the same case** — a guard on the diagnosis. If that one ever passes,
  the store changed underneath us and every "before" number here is stale;
- corpus-wide hit@5 does not fall below **18** (measured 20; floored below so a re-ingest that
  shifts chunk boundaries does not fail the suite, but a collapse does);
- `bid_deadline` is served by exactly one entry, that entry is `["bid_deadline"]` alone, and the
  completion query is still the exact incumbent string;
- the bid query contains none of the six completion terms that caused the dilution;
- a doc with no matching chunk returns five real hits and a clean `None` rank, while a
  **nonexistent** `doc_id` returns `[]` — those are different facts and the harness does not flatten
  them.

Skips (never silently passes) when `06_chroma/` is absent.

Suites: `pipelines/plan_reader/01_pipeline` **66 passed**; `04_tools/bid_date` **50 passed**;
`apps/api` **49 passed, 2 failed** — both pre-existing and unrelated (`test_midpoint_bridge`, rough
edge 6's MnDOT GIS flake; `test_competitor_registry_admin::test_consolidate…`, a `UniqueViolation`
against the live Supabase).

## 5. Also fixed: a parse failure and an honest null shared a return value

Handed over from the phasing agent. `s3_extract.call_json` returns `None` **only** on a JSON parse
failure — transport and API errors raise, `process_pdf` returns `ok: false`, and no payload is
assembled. `fill_rag_fields` did `call_json(...) or {}`, so a parse failure wrote a clean null cell
into every field of the group, byte-identical to "the plan states no value". Tenth-plus instance of
the standing rule, sitting in the RAG scalar path.

Now:

```python
data = extract.call_json(...)
if data is None:
    record.setdefault("rag_scalar_parse_failures", []).extend(f["name"] for f in fields)
    continue
```

The cells are left as `blank_record` made them and the failure is **named** on the record. Two tests
prove the distinction in both directions: a parse failure lands in
`rag_scalar_parse_failures`, and an honest `{"value": null}` does not.

**Nothing downstream consumes `rag_scalar_parse_failures` yet.** `report.py` and `final_report.py`
are owned by other agents this round. Whoever plumbs it should treat a field named in that list as
`extraction_failed`, not `none_found`.

## 6. Reconciliation with upstream #90 — confirmed, not assumed

`origin/main` is 9 commits ahead; `0c0d1d7` (#90) touches this file. Read via
`git diff HEAD...origin/main -- pipelines/plan_reader/01_pipeline/s4_extract_rag.py`.

- **#90 did NOT change `bid_deadline` retrieval.** Its entire diff to this file is inside
  `SCALAR_PROMPT`. The combined three-field `SCALAR_QUERIES` entry and the `k=5` pull are unchanged
  upstream, so the defect fixed here is still present on `origin/main`. The split is needed.
- **#90's "required bid deadline" is a verify-gate UI requirement**, weighted in
  `verify-extraction.tsx` (+119) and `chat-data.ts` — it makes a human confirm a bid deadline before
  "Confirm & continue". That is **layer 3** of the bid-date design. Tonight's deterministic layers 1
  and 2 and this query split all *feed* that required field, so the human has a correct value to
  confirm instead of a blank box to type into. They compose; nothing duplicates.
- **Merge risk: low but real.** This change is in `SCALAR_QUERIES` (~line 38–75); #90's is in
  `SCALAR_PROMPT` (~line 86–97). Distinct hunks, and my edit does not depend on the prompt text —
  expect a clean auto-merge. The one thing to eyeball after the merge is that `SCALAR_PROMPT` ends
  up in #90's two-level-confidence form and `SCALAR_QUERIES` ends up with four entries.
- **`schema.CONFIDENCES = ("high", "medium", "low")` is stale upstream.** #90's prompt no longer
  emits `"medium"`, but `_coerce_cell` still accepts it. Not a bug today; it is a value that can
  never occur being treated as valid. `schema.py` belongs to another agent tonight — flagged in
  `TASKS.md`, not touched.
- **#90 answers the board's open "CONFIDENCE LEVELS — client-facing" question**: high = stated
  verbatim, low = inferred or uncertain, plus a per-field `reason`. Board updated.

## 7. What was deliberately not done

- **No deterministic fallback for the two completion dates.** Owner's explicit instruction. Logged
  as `TASKS.md` 4a-ii with the measurement — and with the finding that, unlike `bid_deadline`,
  **rewording will not fix it**: six alternative completion queries were measured and none beat the
  incumbent at hit@5. The completion date is stated in far more varied places than the bid date, so
  that field probably needs a deterministic layer like `04_tools/bid_date/`, not a better query.
- **`k` was not raised.** Raising it costs tokens on every RAG field on every plan to fix one field.
- **No re-ingest, no rebuild, no mutation of `06_chroma/`.** All measurement is `collection.get` /
  `collection.query` and a read-only `sqlite3` connection (`?mode=ro`) for the doc-id enumeration.
  A teammate was running the app live throughout.
- `schema.py`, `report.py`, `final_report.py`, `report-card.tsx` untouched.

## 8. Naming deviation, flagged

`test_bid_deadline_retrieval.py` has no `YYYY-MM-DD` prefix. It is a pytest module imported by name
and a leading digit is not a valid Python identifier; it follows the existing precedent of
`test_phasing_coverage.py`, `test_join_key.py`, `test_bid_projects_record.py`. Both documents
produced tonight are dated.
