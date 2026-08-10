# Spec — split `bid_deadline` out of the shared `SCALAR_QUERIES` entry

**2026-08-10.** Owner: whoever holds `pipelines/plan_reader/01_pipeline/s4_extract_rag.py`.
Diagnosis this builds on: `docs/_session/2026-08-10-bid-date.md` §2.

---

## 1. The defect

`SCALAR_QUERIES[2]` (`s4_extract_rag.py:42-45`) is one retrieval query serving three fields:

```python
(["bid_deadline", "substantial_completion", "final_completion"],
 "bid opening date bids due proposal deadline letting date substantial completion final "
 "completion contract time working days calendar days notice to proceed completion deadline "
 "liquidated damages complete the work by"),
```

Two thirds of that string is about *completion*. `fill_rag_fields` pulls **k=5** with it. In a
466-page proposal the completion / contract-time / liquidated-damages boilerplate occupies the
whole top-5 and the single Advertisement for Bids page never appears.

Measured on `2025_MURRAY-CO-MN_CSAH-2_NOBID` (the Fulda CSAH 2 plan set, 521 chunks): the chunk
that states the deadline — `:p9:c0`, "until Thursday, August 7, 2025, at 11:00am local time" —
ranks **40th**. It is in the store (`DOWN_WEIGHT`, not `DROP`); retrieval simply never reaches it.

## 2. What is being decided

**Decision A — give `bid_deadline` its own `SCALAR_QUERIES` entry.**
Cost: one extra Claude call per plan (~6 → ~7 in `fill_rag_fields`). Accepted: the call is small
(two fields' worth of prompt over 5 chunks) and the field is one CSI cannot bid without.

**Decision B — the completion entry keeps its query string byte-identical.**
Not "a rewritten completion query". Identical text, identical `k`, identical `where` filter →
identical retrieved context → `substantial_completion` / `final_completion` cannot regress. This is
provable rather than merely measured. Six alternative completion queries were measured (§4); none
beat the incumbent at hit@5, so the incumbent stays.

**Decision C — no deterministic fallback for the completion dates tonight.** Owner's explicit
instruction. Recorded as an open task in `docs/_session/TASKS.md`.

**Decision D — a JSON parse failure in the RAG scalar path stops looking like a real null.**
`extract.call_json` returns `None` on a parse failure and `fill_rag_fields` does `or {}`, so every
field in the group is written as a clean null cell — byte-identical to "the plan states no value".
In scope only because it is a one-line fix inside the file being edited.

## 3. The new query, and how it was chosen

The winning query mirrors the *sentence shape* of a real Advertisement for Bids rather than listing
keywords. MiniLM is a sentence embedder; a bag of nouns embeds nowhere near a paragraph of prose.

```
Bids for the construction of the Project will be received at the office until 11:00 a.m. local
time, at which time the Bids received will be publicly opened and read aloud. Advertisement for
Bids. Letting date. Bids close.
```

The concrete clock time is not an overfit to Murray's 11:00am — substituting `10:00 a.m.` and
`2:00 p.m.` gives hit@5 of 19 and 20 against this variant's 20, and Murray rank 3 in all three. A
version with the time removed ("until local time on the date stated") drops to hit@5 = 10. The
numeral is what makes the query look like a bid-opening sentence.

`Letting date` / `Bids close` are the MnDOT and SDDOT proposal-cover wording and are kept.

## 4. Acceptance — measurement, not assertion

Ground truth is defined by a strict regex over the raw Chroma chunks: a chunk counts only if it
**states** the answer (a `received … until <date>` / `Letting Date: <date>` sentence for the bid
deadline; a `substantially complete on or before <date>` sentence for completion), not if it merely
mentions the concept. On Murray that selects exactly `:p9:c0` and `:p55:c0` respectively.

| | before | after | gate |
|---|---|---|---|
| Murray `:p9:c0` rank | 40 | **3** | must be ≤ 5 |
| `bid_deadline` hit@5 over 33 plans | 12 (36%) | **20 (61%)** | must not fall |
| `substantial_completion` / `final_completion` hit@5 over 24 plans | 7 (29%) | 7 (29%) | must not fall |

The completion row is unchanged **by construction**, not by luck — same query, same k.

## 5. Coverage test

`pipelines/plan_reader/01_pipeline/test_bid_deadline_retrieval.py`. It asserts the Murray
advertisement chunk is retrieved **within k=5** by the shipped query, and that the corpus-wide
hit@5 does not fall below the measured floor. It skips (never silently passes) when
`06_chroma/` is absent. A test that asserts "5 results came back" would be worthless here.

## 6. Out of scope

- Raising `k` globally. It costs tokens on every RAG field on every plan to fix one field.
- A deterministic completion-date parser (P0 #5).
- `schema.py`, `report.py`, `final_report.py` — owned by other agents this round.
