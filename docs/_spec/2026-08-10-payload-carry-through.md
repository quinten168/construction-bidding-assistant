# Spec — carrying extracted narrative fields through payload assembly

Status: **accepted**, 2026-08-10. Applies the plumbing half of
`docs/_spec/2026-08-10-phasing-gotcha.md` §4.3 ("`phasing_requirements` stays and becomes the
narrative slot"). Diagnosis: `docs/_session/2026-08-10-key-dates-phasing.md` §2.

---

## 1. The decision

`phasing_requirements` is extracted, paid for with a Claude call, written into `record`, and then
dropped at payload assembly — it is in neither `report.py::identity_fields` nor
`final_report.py::_payload_from_plan_id`. Confirmed two ways, both named:

1. `grep -rn "phasing_requirements" apps/ --exclude-dir=.next --exclude-dir=node_modules` → exit 1,
   **0 hits**.
2. Empirical — the key is absent from **all 12** `00_input/_report_payload_cache/*.json`.
   (Six of the twelve contain the substring "phasing", but only as the `phasing_staging` gotcha
   code inside `gotchas[]`. The `identity` block of every one of the twelve has exactly 19 keys
   and `phasing_requirements` is not among them.)

The naive fix is one line in each of two places. **The decision this spec exists to settle is
whether to hardcode the field name a third and fourth time**, given that a concurrent task is
adding a captured raw milling value + unit that hits the same seam.

**Decision: a single carry registry, `apps/api/backend/payload_carry.py`, listing the record
fields that must survive into `payload["identity"]`. Both assembly sites and the renderer read the
registry. Adding a field is one tuple entry, not four edits.**

## 2. Why a separate module and not a constant in `report.py`

`report.py` imports the plan-reader pipeline at module scope (`lib`, `s2_indexer`,
`s3_extract`, …), which pulls in chromadb / sentence_transformers / pymupdf4llm. `final_report.py`
imports none of that and must not start. A tuple and two pure functions in their own dependency-free
module is the only shape both can import. Runtime-imported module → exempt from the date prefix,
same exemption `phasing.py` and `taxonomy.py` take.

## 3. The three-valued status — standing rule "a failure and an empty answer never share a value"

Each carried field `F` contributes **two** keys to `payload["identity"]`:

| key | value |
|---|---|
| `F` | the extracted value (`cell["value"]`), or `null` |
| `F_status` | `"detected"` \| `"none_found"` \| `"extraction_failed"` |

Derivation, at the assembly layer:

- **key absent from `record`** → `extraction_failed`. The extractor never wrote the field: a stale
  per-plan JSON (three of the six date fields have no key in the 8 corpus JSONs — session doc §1.2),
  a schema/artifact version skew, or a stage that did not run. Claiming "this plan has no phasing"
  for an artifact that never had the field is a lie, and it is the exact lie the standing rule bans.
- **key present, value empty** (`None`/`""`/`"null"`) → `none_found`. We looked; the plan states none.
- **key present, value non-empty** → `detected`.

Rendering, `final_report.render_markdown` §① and `to_csv`. **No status renders blank:**

| status | §① Plan Snapshot cell |
|---|---|
| `detected` | the extracted text (truncated to 300 chars, same budget as gotcha evidence) |
| `none_found` | `_None stated in the plan._` |
| `extraction_failed` | `⚠️ **Not captured** — this plan's extraction did not return the field.` |

An `identity` with neither key (the 12 payloads cached before today) renders as
`extraction_failed`, which is the truthful reading of a payload that predates the field.

### 3.1 The residual hole, declared not fixed

`s4_extract_rag.fill_rag_fields` calls `s3_extract.call_json`, which returns `None` on a JSON
**parse** failure (`s3_extract.py:142-144`) and then `_coerce_cell(f, None)` writes
`cell(None, "", None)` — byte-identical to the cell a genuine "the plan states no phasing" produces.
So inside `record`, a parse-failed group and an honest null are already the same value, one layer
upstream of everything this spec owns. This spec cannot close that from the assembly layer and does
not pretend to: `none_found` here means "the record held a null", not "Claude successfully said no".

An API/transport error is *not* in this hole — it raises out of `fill_rag_fields`, `process_pdf`
catches it and returns `{"ok": false, reason, message}`, so no payload is assembled at all.

The one-line upstream fix, for whoever owns `s4_extract_rag.py` (not this agent — that file is in
the extraction path another task owns): in `fill_rag_fields`'s scalar loop, distinguish
`call_json` returning `None` from returning `{}` and stamp the affected cells with
`confidence="extraction_failed"` (or drop the key) rather than a clean null. The registry's
`presence_status()` already routes a missing key to `extraction_failed`, so that fix needs no change
here.

## 4. Registry contents at time of writing

```python
CARRIED_FIELDS = ("phasing_requirements",)
```

`interim_completion_dates` and `phase_break_interval` (phasing-gotcha spec §7.3) join it the moment
`schema.py` gains them — the main session owns that file. The concurrent milling raw-value/unit work
adds its own entry; **this agent does not add it.**

## 5. Coverage test

`apps/api/tests/test_phasing_payload_carry.py`. It runs on **`2023_MOUNTRAIL-CO-ND_8371604_NOBID`**,
a plan known to have phasing: `csi_v2.db.gotchas` holds its `phasing_staging` flag on **p.8** with
verbatim evidence *"Construction in this phase may not begin until Phases 1 & 2 are completed."*
The test **reads that string out of the database at run time** and feeds it through both assembly
sites and the renderer — a hardcoded fixture would pass even if the corpus stopped containing a
single phased plan, which is the failure mode the working rules call out.

A plan with no phasing is asserted separately, and asserted to be `!=` the failed case. A test that
only exercised the empty plan would prove nothing, per the task brief.
