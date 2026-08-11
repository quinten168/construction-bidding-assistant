# Session report — the truncation + cache guard (twelfth instance of the standing rule)

Date: 2026-08-10 · Branch `2026-08-10-mapping-honesty` (PR #104) · Commit `e6f737c`
Files owned and touched: `pipelines/plan_reader/01_pipeline/s3_extract.py`,
`apps/api/backend/report.py`, new `apps/api/tests/test_extraction_truncation_guard.py`.
Not touched: `schema.py`, `apps/web/**`, `pipelines/ci_model/**`, the golden, any cache entry.

**No conversion arithmetic was written.** No factor, no SY/CY→ton multiplication, nothing behind a
flag or a stub.

---

## 1. The defect

`s3_extract.call_json` returned `None` on a `json.loads` failure. A response cut off at `max_tokens`
and a genuinely malformed response both landed there, and `extract_fields` did
`call_json(...) or {}` — producing a **full record of clean null cells**. An overflowing extraction
was byte-identical to a plan that states nothing, and `report.py::apply_verification` would then
write it into the payload cache, where it is permanent and silent.

Measured 2026-08-10 (`docs/_session/2026-08-10-silent-drop-fix.md` §5): six new schema fields pushed
whole-doc output to 2,100–2,176 tokens against the old 2,048 cap on **3 of 18** corpus plans,
`stop_reason='max_tokens'`, and the shipped code logged *"JSON parse failed (Unterminated string…)"*
and returned `county=None`, `milling_sy=None`.

---

## 2. The three-state contract given to `call_json`

`call_json_result(prompt, max_tokens) -> JsonResult(status, data, message, stop_reason)`:

| status | when | `data` |
|---|---|---|
| `OK` | the model answered and it parsed | the parsed JSON — **including a legitimate `{}` / `[]`**, which is an empty ANSWER and is only reachable here |
| `TRUNCATED` | `resp.stop_reason == "max_tokens"` | `None` |
| `MALFORMED` | response ended normally, did not parse | `None` |

Two deliberate details:

- **Classification is read off `resp.stop_reason`, never inferred from the exception text.** The
  test that proves this feeds the *same bytes* twice, differing only in `stop_reason`, and asserts
  two different statuses.
- **Parsed-but-capped is still `TRUNCATED`.** A cut that happens to land on a syntactically complete
  prefix parses fine and is still an incomplete answer; handing a partial record on as a finished
  one is the same collapse one step further in.

**Vocabulary.** Deliberately the one `s4_extract_rag` already uses for this class of problem
(`record["rag_scalar_parse_failures"]`, 2026-08-10): the word for "the model's reply was unreadable"
is a **parse failure**, and truncation is one named *kind* of it — hence `ExtractionParseFailure`
with `.kind ∈ {truncated, malformed}`. No second vocabulary was invented.

**`call_json` itself is unchanged in contract** — it is now a one-line shim over
`call_json_result` returning `.data` (i.e. `None` on either failure). That is on purpose: it is
shared by `s4_extract_rag`'s three passes (which already convert a `None` into an explicit
`rag_scalar_parse_failures` entry rather than a null cell — an honest signal) and by four
`03_evaluation` runners. Fixing the whole-doc collapse did not require editing any of them the night
before a demo. Neither `s4_extract_rag.py` nor any evaluation runner was modified.

---

## 3. What the caller does with a truncated extraction

1. `extract_fields` **raises `ExtractionParseFailure`** instead of returning null cells.
2. `report.py::process_pdf`'s existing `try/except` around convert→ingest→extract catches it and
   calls `_classify_read_error` — **reused, not reinvented**, as instructed. It branches first on the
   duck-typed attribute `e.extraction_failure_kind` (so `report.py` needs no import of the exception
   class, which keeps the change merge-robust) and returns:
   - `("extraction_truncated", "…cut off at the model's output-token limit… Nothing was saved…")`
   - `("extraction_unreadable", "…came back unreadable (malformed JSON)… Nothing was saved…")`
3. `process_pdf` therefore returns `{"ok": False, "reason": …, "message": …}`. **No payload is
   built**, so there is nothing for `apply_verification` to cache and nothing null-celled for the
   verify UI to show. `app.py` already renders `ok:False` + `reason` + `message` — no frontend change
   was needed or made.
4. **Belt-and-braces at the layer that makes it permanent:** `apply_verification`, the only writer of
   the payload cache, now writes only when `rep.get("ok")` is true, and **logs a warning** when it
   refuses (a silently-skipped cache write is its own afternoon).

Malformed is raised too, not just truncated: a whole-doc call whose JSON is unreadable produces an
entirely null record, which is the same collapse. It gets its own reason code so the two never share
one.

`EXTRACT_MAX_TOKENS = 6000` is kept, and asserted by a test so a future edit cannot quietly lower it.

---

## 4. The coverage test — red before green

`apps/api/tests/test_extraction_truncation_guard.py` — **15 tests, all passing** on the branch.

**GREEN** (venv, `apps/api`): `15 passed`. The live test genuinely ran (an API key is present) —
it forces a real `stop_reason == "max_tokens"` with `max_tokens=24` on a 40-key prompt, i.e. the
condition is forced *cheaply*, not by generating a huge document. That is the half a fake client
cannot prove: that the API field is spelled and populated the way `call_json_result` reads it.

**RED**, run at HEAD (`6611df9`) in a throwaway detached `git worktree` — nothing in the working
tree was stashed or moved, because a teammate is running the app live: **10 failures**, of which two
are behavioural rather than `AttributeError`:

```
FAILED …::test_apply_verification_refuses_to_cache_a_non_ok_payload
        AssertionError: assert not True  ← the payload WAS written to the cache
FAILED …::test_a_truncated_extraction_never_lands_in_the_payload_cache
        AssertionError: assert 'read_error' == 'extraction_truncated'
```

plus 8 `AttributeError: module 's3_extract' has no attribute 'call_json_result' /
'ExtractionParseFailure' / 'TRUNCATED'` — the contract simply did not exist. The worktree was
removed afterwards.

The two required assertions specifically:

- *distinguishable ERROR*: `test_truncated_malformed_and_empty_are_three_distinct_values` asserts
  `len(set(statuses)) == 3` over the same call path, and
  `test_classify_read_error_gives_truncation_its_own_reason_code` asserts
  `extraction_truncated ≠ extraction_unreadable ≠ read_error`.
- *must NOT land in the payload cache*:
  `test_a_truncated_extraction_never_lands_in_the_payload_cache` runs **`report.process_pdf` end to
  end** (convert/ingest stubbed, `_PAYLOAD_CACHE` redirected to `tmp_path`) and asserts on the cache
  **directory** — `list(cache_dir.iterdir()) == []` — not on a return value. Observing the changed
  state, per the working rules.

Guards against a hollow green: `test_a_genuinely_empty_extraction_still_returns_a_record` (a model
answering `{}` must still produce a record, so the fix is not "raise on everything");
`test_apply_verification_still_caches_a_good_payload` (the cache guard is not vacuous);
`test_the_legacy_shim_still_returns_none_on_both_failures` (s4/eval callers unaffected).

**No regressions.** `apps/api` suite: `2 failed, 86 passed` — exactly the two documented pre-existing
failures (`test_candidate_pool_consistency`: missing `pyarrow`; `test_midpoint_bridge`: rough edge
6's MnDOT flake). The four `test_bid_results_admin` / two `test_bid_projects_writer` failures seen on
the first full run are live-Supabase-dependent and were excluded from the re-run rather than repeated
(the task forbids Supabase writes). `01_pipeline` suite: `3 failed, 91 passed` — all three in
`test_material_vocabulary_coverage.py`, which is the **other agent's in-flight `schema.py` work**,
not this change. `py_compile` clean on both edited files.

---

## 5. The 14 cached payloads — none is a truncation artifact

Checked, nothing deleted, nothing moved. **Two independent verification methods, both negative:**

1. **Truncation signature.** A `None` from the whole-doc call nulls *every* extract-sourced field at
   once. Scanned all 14 for `state`/`county`/`location`/`sp_number`/`prevailing_wages` **all** null
   **and** `quantities == []` simultaneously: **0 of 14**. Twelve payloads have 0/5 or 1/5 of those
   null; the worst is 2/5.
2. **Derived unit statuses.** A truncated extraction leaves `milling_unit_status` and the three
   `*_unit_status` values at `unknown` (that is exactly the old-arm signature recorded in
   `2026-08-10-silent-drop-fix.md` §3). **Not one `unknown` appears across all 14 payloads** — every
   one is `sy_only` / `tons_only` / `unconverted_only` / `not_present` / `tons_and_unconverted`.

The one payload worth naming, and why it is **not** an artifact: `e9ae6f092ccca1bf.json`
(plan `9462761`, 13th Ave West, Williston ND) is the only one with **zero quantities**. Its identity
is populated (`state=ND`, `location`, `sp_number=25-001`, `bid_deadline`, both completion dates) and
its extract cells carry `confidence: "high"` with page numbers and reasons — a truncated call cannot
produce that, since it produces blank cells with `confidence: ""`. The document is a utilities job
("water, sewer and storm drain… Detention Pond 8"), so no paving quantities is the honest answer, and
all four unit statuses read `not_present` rather than `unknown`.

No cache entry was read-modified, backed up, or removed.

---

## 6. What I expect to conflict with the conversion work (PR #102 follow-on)

The change is deliberately small — two files, and in `report.py` two localised edits — but the
conversion agent touches both files:

1. **`s3_extract.py::extract_fields`** — the highest-risk overlap. I replaced the single line
   `data = call_json(prompt, max_tokens=EXTRACT_MAX_TOKENS) or {}` with a four-line
   `call_json_result` + `raise ExtractionParseFailure(result)` block. Anyone who re-adds an `or {}`
   there, or who rebases a version of this function that still calls `call_json`, silently restores
   the defect. **The conversion layer must run on `result.data` after the `is_ok` check, never before
   it** — converting a truncated record is worse than dropping it.
2. **`report.py::_classify_read_error`** — I prepended a `kind = getattr(e,
   "extraction_failure_kind", None)` block *before* the existing string matching. A conversion-side
   edit that adds its own branch should add it after that block; note the pre-existing
   `"empty" in msg` branch is greedy and would swallow a conversion error whose message mentions
   "empty".
3. **`report.py::apply_verification`** — the cache write is now guarded by `rep.get("ok")` and has an
   `elif` logging branch. A conflict here is textual, not semantic; keep the guard.
4. **`EXTRACT_MAX_TOKENS = 6000`** — the conversion work adds fields (or asks for more per-field
   prose). Every added field costs output tokens, and the budget is now asserted by
   `test_the_six_thousand_token_budget_is_kept`. If fields are added, raise the constant **and** the
   assertion together, in the same commit.
5. `schema.py` is being edited concurrently by another agent; I made **no** change to it and needed
   none. The three `test_material_vocabulary_coverage.py` failures above belong to that work.

## 7. Not done, deliberately

- **`s4_extract_rag` still cannot see truncation.** Its three `call_json` calls (gotchas at
  `max_tokens=2000`, scalars and special-requirements at the 2048 default) get `None` for both
  causes. The scalar path is already honest about it (`rag_scalar_parse_failures`); the gotcha and
  special-requirements paths still do `or []`, so a truncated gotcha pass reads as "no gotchas".
  Switching them to `call_json_result` is a two-line change per call site, but `s4_extract_rag.py` is
  not a file I own and it is the live RAG path the night before a demo. **Recommended as a board
  item — thirteenth instance, already located.**
- No DDL, no Supabase writes, no cache clears, no re-ingest, no PR/push.
