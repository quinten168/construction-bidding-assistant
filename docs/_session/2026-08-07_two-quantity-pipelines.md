# Session report 4 — 2026-08-07 · publish landed, and the two quantity pipelines never shared a mapping

Fourth report of the day. Companions: `2026-08-07_crosswalk-and-vision.md`, `_remap-run.md`,
`_coverage-test-and-milling.md`.

---

## Lead: what did NOT happen

- **F2 rendering — NOT STARTED.**
- **Extraction schema v2 — NOT STARTED.**
- **No cache-migration build, no mapping restructure** — both specs written, neither built, per
  instruction.
- The Wednesday mitigation in decision #4 **was not applied, because it is not needed.** See §2.

## 1. (c) and (d) — done

**(c) published.** All 8 tables as `postgres`. Grants survived by construction via
`ALTER DEFAULT PRIVILEGES`; no manual reapplication was required. `public.materials` now carries
`milling_sy = 2,826,995` plus the new `csi_category` / `crosswalk_version` columns.

**Grant proof, and its limit.** I could not log in as `csi_reader` — `postgres` is not a member of
that role on Supabase, so `SET ROLE csi_reader` was denied, and I do not have its password. Instead:
`has_table_privilege('csi_reader', …)` returned **SELECT=True, UPDATE=False on all 8 tables**, plus
schema USAGE. That is the server evaluating the privilege, not me reading ACL text — but it is **not**
a login test, and T is getting the DSN so a real one can run.

**(d) loaded a real report** through `final_report.assemble()`. Gotchas came through from Postgres.
Quantities did not — they are read from the payload cache (`final_report.py:312`).

## 2. THE FINDING: there are two quantity pipelines and they have never shared a mapping

Decision #4 assumed the corrected milling number would reach a report once its cache entry was
cleared or a fresh plan was processed. **It would not, and the reason matters more than the fix.**

**The live PDF-drop path never touches `quantity_crosswalk.py`.** Verified three ways:

1. **Grep** — `report.py`, `final_report.py`, `s3_extract.py`, `s4_extract_rag.py`, `schema.py`,
   `lib.py`: **0 references** to `quantity_crosswalk` / `map_line` / `csi_bucket` in any of them.
2. **Reverse grep** — the only importers are `04_tools/05_parse_bid_schedule.py`,
   `10_remap_buckets.py`, `09_build_material_crosswalk.py`, `12_build_material_preread.py`, and the
   new test. All batch tooling.
3. **Runtime module graph** — imported `backend.report` and inspected `sys.modules`:
   `crosswalk modules loaded: NONE`.

The two pipelines:

| | BATCH / corpus | LIVE / PDF drop |
|---|---|---|
| how quantities are derived | `05_parse_bid_schedule.py` → `quantity_crosswalk.SPEC_MAP` → per-line bucket | **Claude is asked for the totals directly** |
| the ask | deterministic keyword matching | `schema.py:87` declares `milling_sy` an `extract` field; `s3_extract.py:52` instructs *"Sum the bid-schedule line items if needed"* |
| lands in | `materials` → `plan_metrics` → `public.*` | payload cache → the report |
| affected by today's fixes | ✅ yes | ❌ **no** |

### The consequence, which reframes five weeks of work

**The three six-figure bugs were all in the path the customer does NOT use.**

Evidence from the 12 cached payloads (the LLM path's own output), compared against the corpus:

| plan | LLM MILL | batch MILL (post-fix) |
|---|---:|---:|
| `8376434` | 154,218 | 154,218 — **exact** |
| `2023_DUNN-CO-ND_CP-13` | 51,929 | 51,929 — **exact** |
| `9747843` | 31,500 | 34,500 — 8.7% apart |

9 of 12 cached payloads carry a MILL quantity, so the LLM path extracts milling routinely.

**The decisive case is Stearns `9813645` — the exact plan CSI complained about.** The July handoff
records that the reader "reported **zero milling** on a job that is almost entirely milling and
reclamation." The cached LLM payload for that plan reports **MILL = 70,263 SY**.

And the reconciliation is exact. Post-fix, the batch path gives Stearns `milling_sy = 140,430`,
composed of:

```
MILL BITUMINOUS SURFACE (1.0")   68,167 SY
MILL BITUMINOUS SURFACE (1.5")       96 SY
MILL BITUMINOUS SURFACE (4.0")    2,000 SY
                                 -------- = 70,263   <-- exactly the LLM's number
FULL DEPTH RECLAMATION           70,167 SY  (csi_category='base', per Alex)
                                 --------
                                  140,430
```

**The LLM path had Stearns right all along, to the square yard.** The two paths now differ by exactly
one thing: whether FDR counts as milling. The batch path includes it (bucket `milling_sy`, category
`base`); the LLM path excludes it — which is *closer to Alex's ruling* that FDR is base work.

So CSI's original complaint was tested against the batch corpus numbers, not against the product.
That does not make today's work wasted — the corpus feeds the competitor model, the analytics, and
every published table — but it does relocate the bug.

## 3. Answer to decision #4, in two lines

**Do nothing. The demo already shows correct milling, and neither clearing a cache entry nor
processing a fresh plan would change it — the drop path does not use the corrected code.** If you
want to show the 2,826,995 figure specifically, it is a *corpus* number and belongs on a data/
analytics surface (`public.materials`), not in a plan report.

**Caveat, stated because it is unverified:** I did not run a fresh PDF end-to-end through the live
path tonight. The evidence above is 12 previously-cached payloads plus three code reads. A single
real drop of a milling-heavy plan would settle it, and that is the one thing I would do before
Wednesday.

## 4. Second-order consequence worth a decision

The two pipelines will drift, because nothing keeps them aligned. Today's `csi_category` /
`bucket_gap_reason` / CSI-ruling work exists **only** in the batch path. The report a customer sees
cannot currently distinguish `excluded_by_csi` from `never_matched`, because it never calls the code
that computes them.

**This directly blocks F2 as specified.** F2's four gap states live in `quantity_crosswalk.py`; the
report renders from `_QMAP` over LLM output. Rendering four states requires either:

- **(a)** the drop path adopting the crosswalk (an architectural change, and the mapping spec's
  L1/L2/L3 design is the right home for it), or
- **(b)** F2 rendering only the two states the LLM path can actually produce today — "extracted" vs
  "not extracted" — which is *still* a real improvement over a blank cell, but is not the four-state
  design.

I did not choose. It is a judgment call that changes what F2 is.

## 5. Files changed this segment

| File | Change |
|---|---|
| `04_tools/publish_to_supabase.py` | corrected the stale "the app does not read Supabase" docstring; documented the gotchas-vs-quantities split |
| `docs/_spec/cache_to_db_migration.md` | **new** — the migration spec |
| `docs/_spec/mapping_architecture.md` | **new** — the four-layer spec |
| `docs/_session/issues.md` | **new** — 53 open issues, triaged |

67 passed, 1 xfailed. Nothing committed.

## 6. Open for T

1. **F2 scope** — (a) or (b) in §4?
2. **One real PDF drop before Wednesday** to confirm §3 empirically rather than by inference.
3. From the issues triage: **#64** (anon holds INSERT/UPDATE/TRUNCATE on all 8 public tables, RLS
   off) is called the top handoff blocker. Everything published tonight sits under that.
4. Today's fixes are uncommitted on one laptop — a 5.2× correction to the headline milling number
   living in one working tree.
