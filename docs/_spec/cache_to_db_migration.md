# Spec — retire the payload cache, use the DB as read-verification

Status: **SPEC ONLY. Nothing built.** For T to grill before implementation.
Date: 2026-08-07. Every fact below was read from the code or measured against live Postgres today.

---

## 1. Why this is a MIGRATION and not a deletion

The team asked for "remove cache mechanics, use the DB as verification." Taken literally that breaks
two things, because the cache is not a cache — **it is the only durable store of a human decision.**

`apps/api/backend/report.py:47-51` and `apply_verification()` (`:276-318`):

> The cache is written **ONLY** by `apply_verification()`, not by `process_pdf()` — a payload is
> cached only once a human has confirmed or edited the extraction.

So `_report_payload_cache/<content_hash>.json` holds, and is the sole holder of:

- the **human's edits** from the verify gate (corrected quantities, user-entered lat/long),
- the fact that a human **verified** this plan at all,
- and the assembled payload that a re-drop returns instantly.

By explicit 2026-07-31 decision, those edits are written **into this JSON**, not into
`corrections.py`'s sidecar (which is reserved for later, post-hoc chat corrections). Delete the cache
and you delete the verification record. That is the whole reason this is a migration.

## 2. What the DB already carries — measured, not assumed

The join key already exists and is the right one: **`scratch.bid_projects.plan_uid` IS the payload
cache's `content_hash`** (`bid_projects_record.py:225` — "it uses `plan_uid` (the PDF content hash),
so it is deterministic and re-derivable"). Same key, both stores. Live today: **11 rows with
`row_source='plan_reader'`, all 11 with a `plan_uid`.**

| payload key | in Postgres? | where |
|---|---|---|
| `quantities` (7 buckets) | ✅ | `bid_projects.mix_tons / base_tons / grading_yards / shldr_tons / mill_sy / crush_tons / stock_tons` |
| quantity units | ✅ | the 7 `*_unit` columns + `unit_source` |
| `identity` (state/county/city/bid_date) | ✅ | typed columns + `geocoded_*` |
| lat/long incl. human-entered | ✅ | `project_latitude/longitude` + `coordinate_provenance` |
| `archetype` | ✅ | `plan_reader_archetype` |
| `content_hash` | ✅ | `plan_uid` |
| provenance/status | ✅ | `row_source`, `row_status`, `missing_fields`, `bid_date_provenance`, `key_provisional*` |

**So the quantities and identity halves are already migrated.** That is further along than the "five
days slipped" framing suggests.

## 3. What the DB does NOT carry — the actual blocker list

This is the answer to "tell me what the DB needs before the cache can go."

| missing | why it matters | proposed home |
|---|---|---|
| **the gotchas themselves** | `bid_projects` stores `gotcha_count` (an integer) only. `public.gotchas` exists but is keyed by **corpus `plan_id`**, not by an uploaded plan's `plan_uid`. A dropped PDF's gotchas have nowhere to live. | new `scratch.plan_gotchas` keyed on `plan_uid`, or add `plan_uid` to `public.gotchas` |
| **`field_confidence`** | added 2026-07-31 to drive the verify gate's 3-level confidence display. Regenerating the verify view without it is impossible. | `scratch.plan_field_confidence(plan_uid, field, confidence, page)` |
| **`structure`** | the doc-structure dict (`plan_set` vs `proposal`, page classification). Cheap to recompute but currently only cached. | JSONB column on `bid_projects`, or recompute |
| **the `verified` flag + who + when** | the single most important thing here. There is **no column anywhere** recording that a human verified a plan. `row_status` is `'partial'` on all 11 live rows and means something else (missing fields). | `verified_at`, `verified_by` on `bid_projects` |
| **the human's edit deltas** | we store the final value but not *that a human changed it, from what*. Needed for F3's trust export and to ever measure extraction accuracy against human corrections. | `scratch.plan_verification_edits(plan_uid, field, auto_value, human_value, edited_at)` |
| **quantity label/order** | `bid_projects` has typed columns, so `[{label,value,unit}]` is reconstructible but loses ordering and any label not in the 7 | acceptable loss — reconstruct from the 7 columns |

**`verified_at` is the load-bearing one.** Without it, "the DB is the verification" is false by
construction: the DB cannot answer the question the cache exists to answer.

## 4. The sibling cache nobody has mentioned

`_report_competitor_prediction_cache/` (`report.py:63-88`) is a second content-hash cache, for the
competitor-prediction cascade. It is a **true** speed cache — `cached_competitor_prediction()`
returns `(found, comp)` so a legitimate `None` is distinguishable from a miss, which is the right
shape and notably better than the CI subprocess's silent-`None` (rough edge 2).

**Recommendation: leave it alone.** It caches a derived computation, not a human decision, and it is
already correctly designed. Retiring "the cache" must not sweep this one up.

## 5. Proposed sequence — each step independently safe

1. **Add the columns/tables in §3. Write BOTH.** `apply_verification()` writes the cache *and* the
   DB. No read path changes. Nothing can break; the cache is still authoritative.
2. **Backfill from the 12 existing cache files.** Small, and it proves the write path against real
   data rather than a fixture.
3. **Add a DB read path behind a flag**, defaulting off. `process_pdf`'s cache-hit check gains a DB
   sibling.
4. **Verify by comparison, not by assertion.** For every one of the 12 cached payloads, assemble the
   report from cache and from DB and **diff them**. They must be identical. This is the gate — not a
   passing test suite, an actual diff of both renderings. (Per CLAUDE.md: verify by observing the
   changed state.)
5. **Flip the default.** Cache becomes a speed layer only — exactly issue **#15**'s title, "Demote
   `_report_payload_cache` to a speed cache keyed by content hash."
6. **Only then** consider deleting it, and probably don't: a content-hash speed cache in front of a
   274-page PDF re-read is worth keeping. **The goal is to stop it being the source of truth, not to
   remove the file.**

## 6. Decisions I need from T before building

1. **Does "remove cache mechanics" mean delete the file, or demote it to a speed cache?** I recommend
   demote (§5.6) and I believe that is what #15 already says, but the request as phrased says remove.
   This changes the end state.
2. **Where do a dropped plan's gotchas live** — extend `public.gotchas` with `plan_uid`, or a new
   `scratch.plan_gotchas`? `public` is drop-and-recreated on every publish, which argues for
   `scratch`. This touches the never-without-asking list (DDL), so I will not choose.
3. **Do we record edit deltas** (auto value vs human value), or only the final value? Deltas cost a
   table and are the only way to ever measure extraction accuracy against human judgment — which is
   the accuracy benchmark you asked for. I recommend yes.
4. **`row_status='partial'` on all 11 live rows** — is that expected, or a latent bug? It is not the
   verified flag, but it is the closest thing and it currently means "missing fields". If it is
   meant to carry verification state too, that is a conflation worth fixing before we add another.

## 7. What this spec does not cover

- The F1 "regenerate the report without re-reading the PDF" feature itself. This spec unblocks it by
  saying what the DB must carry; it does not design the regenerate endpoint.
- Retiring `csi_v2.db` (#50). Different store, different problem.
- Anything about the competitor-prediction cache beyond "leave it alone."
