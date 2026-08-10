# Phasing plumbing — carrying `phasing_requirements` to the payload and the report

2026-08-10. Applies the plumbing the diagnosis agent deliberately did not apply
(`docs/_session/2026-08-10-key-dates-phasing.md` §7, "the one-line plumbing fix").
Spec written first, per the standing rule: `docs/_spec/2026-08-10-payload-carry-through.md`.
Commit `1aa0221`.

---

## 1. The drop, confirmed two ways before touching anything

The prior agent's diagnosis reproduced independently. Both methods named:

1. **Static.** `grep -rn "phasing_requirements" apps/ --exclude-dir=.next --exclude-dir=node_modules`
   → **exit 1, 0 hits.** (The unfiltered grep hits ~126 KB of `.next/` build output and
   `mock-plan.ts` — all the word "phasing" in UI mock copy and the `phasing_staging` gotcha code,
   none of them the field.)
2. **Empirical.** `phasing_requirements` is absent from **all 12**
   `pipelines/plan_reader/00_input/_report_payload_cache/*.json`. Six of the twelve do contain the
   substring "phasing" — as the `phasing_staging` code inside `gotchas[]`, not the field. Every
   one of the twelve has exactly 19 `identity` keys and the field is not among them.

Both assembly sites were confirmed by reading: `report.py::identity_fields` (11 keys, no phasing)
and `final_report.py::_payload_from_plan_id`'s `identity` (13 keys, no phasing).

## 2. Where it is carried through now

| Site | What was added |
|---|---|
| `apps/api/backend/payload_carry.py` **(new)** | The registry: `CARRIED_FIELDS`, `presence_status()`, `carried_values()`, `carried_statuses()`, `render_value()`, `render_label()`. Dependency-free so both assembly modules can import it. |
| `apps/api/backend/report.py` | `identity_fields_from_record()` — the identity dict, **extracted out of `process_pdf` to module level** so the carry-through is testable without a PDF, a Chroma index, or a Claude call. Spreads `payload_carry.carried_values(record)`. |
| `apps/api/backend/report.py` | `process_pdf`'s `rep["identity"]` spreads `payload_carry.carried_statuses(record)`. |
| `apps/api/backend/report.py` | `apply_verification()` re-derives the statuses from the **post-edit** identity, so a human who types phasing into the verify gate does not leave a payload that carries their text and still says `extraction_failed`. |
| `apps/api/backend/final_report.py` | `_payload_from_plan_id`'s `identity` — values + statuses, same registry. |
| `apps/api/backend/final_report.py` | `render_markdown` §① Plan Snapshot — a **Phasing** row. |
| `apps/api/backend/final_report.py` | `to_csv` — value in `value`, status in `detail`. |

Because `field_confidence` is built from `identity_fields`, phasing now also reaches the verify-gate
UI **as a cell** — its `confidence` and its `page` survive, so an estimator can be pointed at the
page. That was free, and it is the difference between a claim and a citable claim.

**Generic, not hardcoded** — as the brief asked. `CARRIED_FIELDS` is a one-line tuple. The
concurrent milling raw-value/unit work adds its entry there and gets all seven sites above; I did
**not** add their field. `interim_completion_dates` / `phase_break_interval` join it the moment
`schema.py` gains them.

**§④ of `final_report.py` was not opened.** `git diff` confirms four hunks, none inside the
competitor block.

## 3. Empty vs failed — does the distinction survive to the rendered report?

**Yes, all the way to the page and the CSV.** Each carried field emits a second key,
`<name>_status`, three-valued:

| status | when | §① Plan Snapshot renders |
|---|---|---|
| `detected` | key present, value non-empty | the text (300-char budget, same as gotcha evidence) |
| `none_found` | key present, value null/empty | `_None stated in the plan._` |
| `extraction_failed` | **key absent from the record** | `⚠️ **Not captured** — this plan's extraction did not return the field.` |

A missing key resolves to `extraction_failed`, never `none_found`. This is load-bearing: three of
the six date fields have no key at all in the 8 stale corpus JSONs, and the 12 already-cached
payloads carry neither key — rendering those as "this plan has no phasing" would be exactly the
failure-vs-empty collapse the standing rule bans. An identity carrying neither key renders as
`extraction_failed`.

Deliberately **not** `or "—"` in the snapshot table: an em dash would make the two look identical
on the page. `render_value()` never returns an empty string, and a test asserts that for all four
input states including `None`.

### 3.1 The residual hole, declared and not fixed

Upstream of everything I own, `s3_extract.call_json` returns `None` on a JSON **parse** failure
(`s3_extract.py:142-144`); `fill_rag_fields` then does `_coerce_cell(f, None)`, which writes
`cell(None, "", None)` — byte-identical to the cell an honest "the plan states no phasing" produces.
So inside `record`, a parse-failed scalar group and a genuine null are already the same value.
`none_found` therefore means *"the record held a null"*, not *"Claude successfully said no"*.

This cannot be closed from the assembly layer and I did not pretend to. A **transport/API** error is
not in this hole — it raises out of `fill_rag_fields`, `process_pdf` catches it and returns
`{"ok": false, reason, message}`, and no payload is assembled at all.

**The one-line upstream fix**, for whoever owns `s4_extract_rag.py` (extraction path, another
task's owner): in the scalar loop, distinguish `call_json` returning `None` from `{}` and either
drop the key or stamp the cells as failed. `presence_status()` already routes a missing key to
`extraction_failed`, so that fix needs no change on my side.

## 4. The coverage test

`apps/api/tests/test_phasing_payload_carry.py` — **14 tests, all passing.**

**Named plan: `2023_MOUNTRAIL-CO-ND_8371604_NOBID`**, from the prior agent's evidence (§3 of the
diagnosis). It is known to have phasing and the phasing is cited: `csi_v2.db.gotchas` holds its
`phasing_staging` flag on **p.8**, confidence `high`, verbatim evidence

> "Construction in this phase may not begin until Phases 1 & 2 are completed."

The test **reads that string out of the database at run time** and asserts it arrives non-empty
through both assembly sites and into the rendered markdown. A frozen fixture would keep passing even
if the corpus stopped containing a single phased plan; this one fails loudly, with a message saying
to pick another real plan rather than hardcode the string.

The Watonwan case is what the plan-with-no-phasing assertions are *contrasted against*, never the
thing that proves the fix — per the brief, a test that passes on a plan with no phasing proves
nothing. `none_found` and `extraction_failed` are asserted `!=` at the payload layer and asserted to
render differently at the report layer.

**Verified red before green.** With `CARRIED_FIELDS` emptied, **8 of the 14 fail** — including
`identity_fields dropped phasing_requirements` and `§① Plan Snapshot has no Phasing row`. Restored,
all 14 pass.

## 5. What else was run

- `python3 -m py_compile` on all three backend files — clean.
- Full `apps/api` pytest, minus three modules that fail to **import** on a pre-existing missing
  `rapidfuzz` in this sandbox (`test_tools.py`, `test_bid_projects_writer.py`,
  `test_competitor_registry_admin.py` — unrelated to this change, none of them import
  `payload_carry`): **46 passed, 1 failed**, the failure being the known rough-edge-6 MnDOT GIS
  flake (`test_compute_midpoint_matches_cli_for_known_mn_plan`). Same result as the documented
  baseline.
- The test stubs `rapidfuzz` in `sys.modules` to import `backend.report`; nothing on the
  identity-assembly path touches it, and any *other* missing module skips loudly with the reason
  rather than passing silently.

**Not verified:** no live backend round-trip — the `/api/report` → verify-gate → finalize path has
never actually run against a real server here (same constraint as rough edges 7/8). What is proven
is that the payload carries the key and the renderer prints it; what is not proven by running is the
HTTP hop between them. The 12 cached payloads on disk still lack the key — they were written before
this change and are not rewritten by it (and no bulk republish was run, per the standing rule about
the teammate's live finalizes).

## 6. Not done, on purpose

- Did **not** add the milling raw-value/unit field — the fourth agent's, and the registry is now
  ready for it.
- Did **not** touch `schema.py`, `report-card.tsx`, the `Competitor` TS type,
  `apps/web/src/app/api/report/**`, or §④ of `final_report.py`.
- The web UI does not yet *display* the new snapshot row — `report-card.tsx` is another agent's
  file. The markdown/CSV/PDF exports do, and the payload carries it, so the display change is a
  one-row addition whenever that file is free.
