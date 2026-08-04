# Plan: retire `csi_v2.db`, make Postgres the source of truth

**Written 2026-07-27. Decision by T, 2026-07-27, reaffirmed after review.**
This **reverses** the 2026-07-22 decision recorded in `00_master_plan.md` §4 ("local SQLite is
the operational store; Supabase stays a published read-only snapshot"). That decision is
superseded, not forgotten — the reasoning behind it is answered in §6.

---

## 0. The one-paragraph version

Today a local 160 MB SQLite file is authoritative, and a hand-run script copies 8 of its 12
tables into hosted Postgres so the team can read them. That copy is stale by construction, holds
two thirds of the schema, and is destroyed and rebuilt on every run. This plan inverts it:
Postgres becomes the store every writer writes to, the publisher is deleted, and `csi_v2.db`
becomes a dated archive file. The end state is one store, live for everyone, with no copy step.

---

## 1. What is true right now

Measured 2026-07-27 against `origin/main`, not inferred.

| | `csi_v2.db` (SQLite) | Supabase Postgres |
|---|---|---|
| role | operational source of truth | read-only published snapshot |
| tables | 12 | 8 |
| size | 160 MB (167,538,688 bytes) | ~2.3 MB |
| written by | 13 writers | 1 (the publisher) |
| read by the app | yes | **no** |
| freshness | live | last manual publish |

**Tables in SQLite but not in Postgres**, all of which must land before Postgres can be
authoritative:

| table | rows | why it was excluded | migration note |
|---|---:|---|---|
| `sections` | 37,261 | bulk chunk text, "RAG fodder" | Chroma holds chunk text *and* embeddings, so retrieval never reads this. Confirm no non-RAG reader before deciding whether it moves or dies. |
| `conversations` | 44 | not in the publish set | written live by `trace.py:190`. Must move; it is the only table with a runtime writer outside the pipeline. |
| `section_intelligence` | 18 | **type bug** | `low_sample_flag` declared `REAL`, stores `"Y"`/`""`. Postgres rejects it. Retype at the source first. |
| `field_registry` | 0 | empty | create the DDL, no data to move. |

Plus `plans.full_markdown` — 75.8 MB, single cells up to 4.7 MB, 97% of the payload. The
publisher strips it. A source of truth cannot.

**The 13 writers**, from `docs/DATA_INVENTORY.md`:

- **Runtime (`apps/api/backend/`), 3 coupling points:** `config.py:45,80`, `trace.py:190`,
  `final_report.py:36,101`.
- **Pipeline (`04_tools/`), 10 writers:** `00_init_db`, `01_bulk_convert`, `02_split_sections`,
  `05_parse_bid_schedule`, `06_derive_classification`, `07_gotcha_prefilter` +
  `07_gotcha_extract`, `08_doc_type_flags` / `09_schedule_detect` / `10_remap_buckets`,
  `09_build_material_crosswalk` / `10_load_location_intelligence` /
  `11_load_section_intelligence`.

25 SQLite-specific SQL constructs across the tree (`INSERT OR REPLACE`, `AUTOINCREMENT`,
`PRAGMA`, `sqlite_master`) have no Postgres equivalent and need rewriting rather than porting.

---

## 2. The risk this plan exists to manage

**SQLite's dynamic typing has been absorbing type violations for months, and Postgres will
reject every one of them.**

This is not speculative. `section_intelligence` already cannot publish for exactly this reason,
and the publisher already carries a workaround for a second instance — `read_table` coerces
empty strings to NULL for every non-text column, because "a column declared numeric can still
hold `''`". Those are two found bugs in the 8 tables anyone has looked at closely. The remaining
4 tables and 75.8 MB of text have never been type-checked against Postgres at all.

Every one of these fails at migration time, in bulk, at the least convenient moment. So the
first phase is an audit, not a port.

---

## 3. Phases

Each phase ends in a state that is safe to stop at. Nothing here is one-way until Phase 5.

### Phase 0 — team unblock (independent, do now)

Apply `04_tools/team_access.sql`. Creates the `csi_team` role and `scratch` schema.
**Not part of the migration and not blocked by it**; the team needs a writable login regardless
of where the data comes from. Already validated: `04_tools/test_team_access.sh`, 20/20 on
Postgres 15.

### Phase 1 — type audit

For all 12 tables, compare every column's declared SQLite type against what it actually holds,
and against what Postgres would accept. Output: a table of every violation and its fix.
Read-only; touches nothing.

Fix the violations **at the SQLite source** while it is still authoritative and cheap to change.
`section_intelligence.low_sample_flag` is the known first entry.

### Phase 2 — full schema in Postgres

Extend the publisher's DDL generation to all 12 tables including `plans.full_markdown` and
`sections`. Land the complete schema and data in Postgres, still as a snapshot, still with
SQLite authoritative. Verify row counts and spot-check values table by table.

At the end of this phase Postgres holds everything SQLite does. Nothing has been repointed. This
is the natural stopping point if priorities change.

### Phase 3 — repoint the readers

Move read paths to Postgres first, because a wrong read is visible and reversible, while a wrong
write corrupts. `final_report.py`, `config.py:corpus_state`, and the `04_tools` scripts' read
queries. Run both stores in parallel and diff the outputs.

### Phase 4 — repoint the writers

The real work. 13 writers, `INSERT OR REPLACE` → `INSERT ... ON CONFLICT DO UPDATE`,
`AUTOINCREMENT` → `bigserial` or `identity`, `PRAGMA table_info` → `information_schema.columns`.

Do `trace.py` **last**: it is the only live runtime writer, so it is the one that breaks the
running app if it is wrong.

### Phase 5 — retire

Delete `publish_to_supabase.py` and its `--force` dependency machinery. Rename `csi_v2.db` to
`csi_v2_archive_YYYY-MM-DD.db` and keep it read-only for one full cycle before considering it
disposable. Update `CLAUDE.md`, `docs/ARCHITECTURE.md`, `docs/DATA_ACCESS.md`, and
`00_master_plan.md` §4.

---

## 4. What this fixes, and what it does not

**Fixes:** the copy step and its staleness; the drop-and-recreate hazard and the `--force` flag
it forced; the team reading a snapshot instead of the real thing; two stores that can disagree
about the same plan; the "this store is not live" caveat.

**Does not fix — say this out loud so nobody expects it:** the #12 finding that the live
extractor and the `04_tools` batch extractor produce *different values for the same fields* —
quantities disagreeing on 4 of 8 shared plans, gotcha counts on 7 of 8, different join keys
(PDF stem vs corpus `plan_id`), the base/shoulder bucket swap. Those are two code paths, not two
databases. After this migration they will disagree inside one table instead of across two, which
is arguably worse, because the seam that currently makes the disagreement visible is gone.

**Therefore: the #10 contract work is a prerequisite for trusting the result, not a follow-up.**
Migrating first is still fine — it just must not be mistaken for having resolved #12.

---

## 5. Cost and sequencing

Phase 1 is cheap and pure profit: it finds bugs that exist today whether or not the migration
happens. Phases 2–4 are the expense, concentrated in Phase 4.

**Do not re-extract.** Re-running extraction over the 117-plan corpus costs real money
(`plan_metrics.extraction_cost` records what was already spent) and would discard a curated
corpus to regain data that migrates fine. Migrate the rows; do not rebuild them.

**Sequencing against `#13`/`#14`/`#15`:** consolidation is going to rewrite these same writers.
Doing consolidation against SQLite and then migrating means touching all 13 twice. If the
migration is happening, Phase 4 and the consolidation work should be the same pass.

---

## 6. Answering the 2026-07-22 reasoning

The July 22 decision kept SQLite because Postgres-only was judged premature. What changed:

- **"The team can read the snapshot."** They could read it. They could not write, which is what
  they actually needed, and the snapshot was two thirds of the schema.
- **"Migration is later."** Later has a cost that compounds: every writer added or changed
  between now and then is written twice.
- **"SQLite is operationally simpler."** True, and it is why this is phased rather than a
  cutover. But simple-for-one-machine is precisely the property that made the team unable to
  use it.

What has *not* changed, and is the one thing worth staying honest about: consolidating storage
does not consolidate semantics. See §4.
