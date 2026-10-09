# Data access: the published plan-extraction tables

This describes how to read the structured data that the Plan Reader pipeline extracts from
highway construction plan sets: what is in it, how to connect, and the limits you need to know
before you build on it.

You do not need this repo, a Python environment, or any of the pipeline code to use it. You need
a connection string and anything that speaks Postgres.

**If you want to run the app rather than just query the data, start with the next section.**

---

## Fresh machine: the 10-minute runbook

*Added 2026-08-03, verified end to end on that date. Follow this in order.*

**You do NOT need:** the 1.5 GB vector store, the 167 MB `csi_v2.db`, the plan corpus, or any
Supabase table access to try the app. Those are for batch tooling and team data, not for running it.

```bash
# 1. clone
git clone https://github.com/Tobias-V-Knight/csi-bid-intelligence.git
cd csi-bid-intelligence

# 2. Python 3.10+ (3.9 is EOL and PEP 604 syntax is used throughout)
python3 --version          # need >= 3.10
python3 -m venv .venv
.venv/bin/pip install -r apps/api/requirements.txt

# 3. env — ONE file, at the repo root
cp .env.example .env
#    edit .env:
#      ANTHROPIC_API_KEY        REQUIRED  (chat + both extraction passes)
#      SUPABASE_TEAM_DB_URL     optional  (only the /bid-results, /pit-list, /competitor-registry,
#                                          /projects admin pages need it — ask Tobias)
#      GOOGLE_GEOCODING_API_KEY optional  (city lookup; unset just yields a null city)

# 4. run — BOTH processes. Starting only one is the usual confusing failure.
./scripts/dev.sh
```

Then open **http://localhost:3000** and drop a plan PDF.

### If you already have a `.venv`, do not rebuild it

⚠️ On Tobias's machine the existing `.venv` is **Python 3.9.6** while `pyproject.toml` says
`>=3.10`. It works — the import failure that used to break it was fixed (#53) — and `scripts/api.sh`
invokes `.venv/bin/uvicorn` directly. **The mismatch looks like a bug and is not; rebuilding that
venv breaks a working setup.** On a genuinely fresh machine, create it with 3.10+.

### No Supabase DSN? Still runnable

```bash
ALLOW_NO_SUPABASE=1 ./scripts/api.sh
```
Chat and PDF upload work. Only the four CI-data admin pages need Postgres.

### The vector store can be empty — this is supported, not a workaround

`pipelines/plan_reader/06_chroma/` is gitignored and **does not need to exist**. It is created on
first use and **self-populates**: `process_pdf` indexes every PDF you drop, and extraction retrieves
only against the plan being processed (every query in `s4_extract_rag.py` is scoped to that plan's
`doc_id`). Verified 2026-08-03 against a genuinely empty directory — it went 0 → 286 chunks and
returned a complete extraction.

**The one limitation:** chat *about the plan you just dropped* works fine. **Cross-plan chat returns
nothing until plans are indexed** — corpus-wide questions ("what do other Stearns County plans say
about aggregate specs?") come back empty on a fresh machine and improve as you process plans.

### `csi_v2.db` is not needed either

The app does not open it (as of #50). It is required only by the `pipelines/plan_reader/04_tools/`
batch scripts. A fresh clone gets a dangling symlink where it would be — that is expected, not
corruption. See the ⛔ section below before deleting anything.

### Ports: 8010, not 8000

API **:8010** (docs at http://localhost:8010/docs), web **:3000**. `apps/api/README.md` says 8000 —
it is stale. Override with `API_PORT` / `WEB_PORT`.

### What success looks like

```bash
curl -s http://localhost:8010/health
{"status":"ok","model":"claude-sonnet-4-6","indexed_plans":205,"warnings":[]}
```

`indexed_plans` is **0 on a fresh machine and that is correct** — it counts what is in your local
vector store. `warnings` should be `[]`; anything in it names its own fix.

A successful PDF drop, in the UI:
1. the file uploads and processing starts (convert → ingest → extract, ~60–90 s for a 250-page plan);
2. a **verification modal opens by itself** showing extracted fields with confidence levels — you
   confirm or edit, or skip;
3. a report card renders: archetype, identity, quantities, gotchas;
4. you can then chat about that plan.

If extraction fails it returns a *classified* reason (scanned PDF, drawings-only plan set, timeout),
not a stack trace. A drawings-only plan set is refused by design — feed it the bid proposal.

---

## Running the app locally — reference

*The section below is the longer-form version of the runbook above.*

### 1. One environment file, at the repo root

```
<repo root>/.env          <- CANONICAL. This is the only place the DSN goes.
```

Create it from the template and fill in the values:

```bash
cd /path/to/csi-bid-intelligence
cp .env.example .env
```

| Variable | Required? | What it is |
|---|---|---|
| `SUPABASE_TEAM_DB_URL` | **yes** (or set `ALLOW_NO_SUPABASE=1`) | Postgres DSN for the `csi_team` login. Read/write on the `scratch` schema. Ask Tobias for the password. |
| `ANTHROPIC_API_KEY` | yes | Chat agent + both extraction passes. |
| `GOOGLE_GEOCODING_API_KEY` | no | Server-side key for the reverse-geocode stage. Unset just disables it (null city), it does not error. **Must not** be the same value as `NEXT_PUBLIC_GOOGLE_MAPS_API_KEY`, which the browser sees. |

**There is exactly one canonical file, on purpose.** `apps/api/.env` still exists for API-specific
overrides, but it must **not** carry a second copy of the DSN — two copies drift. The backend
detects a duplicate and warns at startup.

The file is found relative to the backend source, not your shell's working directory, so it works
no matter where you launch uvicorn from. Real environment variables still win over the file (needed
for Railway/CI); if an exported variable shadows the file with a *different* value, the backend
says so at startup rather than leaving you to guess.

**`data/*.py` and `pipelines/plan_reader/04_tools/*.py` read `os.environ` directly and load no
file.** Before running those, export the file into your shell:

```bash
set -a; source .env; set +a
```

### 2. Start both processes

The app is **two** processes. Starting only one is the most common way to get a confusing error.

```bash
./scripts/dev.sh          # starts both, health-gates the API, Ctrl-C stops both
```

Or individually:

```bash
./scripts/api.sh          # FastAPI on :8010   (docs at http://localhost:8010/docs)
./scripts/web.sh          # Next.js  on :3000
```

`web.sh` warns if no API is listening on :8010. Logs also go to `.dev-logs/`.

> **Ignore `apps/api/README.md`'s port 8000.** It is stale. The port is **8010** everywhere else,
> and the front end proxies to `http://127.0.0.1:8010` by default (override with `BIDINTEL_API_URL`).

### 3. If the backend refuses to start

That is deliberate. A missing or placeholder DSN now **fails at boot** naming the exact file and
variable, rather than starting and failing later with an unrelated-looking error:

```
RuntimeError: SUPABASE_TEAM_DB_URL is not set.
  Expected SUPABASE_TEAM_DB_URL in /path/to/repo/.env
  (create it from the template: cp /path/to/repo/.env.example /path/to/repo/.env)
  Set ALLOW_NO_SUPABASE=1 to start without Postgres (chat and PDF upload work;
  the CI-data admin pages will not).
```

You will also see this if the value is still a template placeholder — `PASTE_…`, `PASSWORD_HERE`,
or anything containing `<` / `>`.

**Only the `/api/ci-data/*` admin pages need Postgres.** To work on chat or PDF upload without a
DSN: `ALLOW_NO_SUPABASE=1 ./scripts/api.sh`.

### 4. You do NOT need the 1.5 GB vector store

**A teammate can run the full PDF-drop → report flow with an empty `pipelines/plan_reader/06_chroma/`
directory.** Nothing to download, nothing to host, no setup. If the directory does not exist it is
created on first use.

Verified empirically on 2026-08-03: `process_pdf` was run against a genuinely empty store. It went
**0 → 286 chunks**, self-populating, and extraction returned a complete result — archetype, state,
location, prevailing wages, traffic level, quantities and gotchas.

This works because of how extraction retrieves, not by luck. Every query in
`01_pipeline/s4_extract_rag.py` is scoped to `{"doc_id": <the plan being processed>}`. The pipeline
**indexes the plan it was handed and then retrieves against those chunks only** — it never consults
the historical corpus. `report.py`'s ingest stage is unconditional, so every dropped PDF populates
the store as a side effect.

**The one real limitation.** Chat *about the plan you just dropped* works fine — the agent scopes to
the active plan. **Cross-plan chat returns nothing until plans are indexed**, because a corpus-wide
question searches the whole collection and an empty collection has nothing in it. So questions like
"what do other Stearns County plans say about aggregate specs?" come back empty on a fresh machine
and get better as you process plans.

If you want the historical corpus locally, the store is regenerable — see
`pipelines/plan_reader/README.md` — but you do not need it to be productive.

### 5. Python version

**This project requires Python 3.10 or newer** (`pyproject.toml`, `requires-python = ">=3.10"`).
3.9 reached end of life in October 2025 and PEP 604 syntax (`float | None`) is used throughout.

If you are on 3.9 you will previously have seen `apps/api` fail to import with
`TypeError: unsupported operand type(s) for |`. That specific instance is fixed (#53), but the
version floor is real — install 3.10+.

---

## What this is

The Plan Reader converts plan-set PDFs into structured rows: identity, bid-item quantities,
risk flags, and where in a document each kind of fact tends to live. Those rows are produced
into a local SQLite file (`csi_v2.db`) on one machine, which made them unreadable to everyone
else.

This store is a **published snapshot** of the small structured tables from that file, copied into
hosted Postgres so the team can query them over a connection string.

> **Superseded in part, 2026-08-03 (#50).** The last sentence used to read "the application does not
> read from Postgres." That is no longer true. `apps/api` now reads the corpus from Postgres on the
> live path — `config.corpus_state` → `public.plans`, and `final_report.py` → `public.gotchas` /
> `public.plan_metrics` — and `backend/trace.py` writes chat turns to `scratch.conversations`.
> Nothing in `apps/api` opens the SQLite file any more. SQLite is still the *production* source for
> the publish step, so it remains the system of record for the eight published tables, but it is no
> longer on the application's read path.

### Where `csi_v2.db` actually lives — it is a symlink, not a local file

`pipelines/plan_reader/csi_v2.db` is a **symbolic link into iCloud Drive**:

```
pipelines/plan_reader/csi_v2.db -> ~/Library/Mobile Documents/com~apple~CloudDocs/
    00 MSBA + Coding/00_summer 2026/00_Client_ELP/01_Summer_2026/02_modules/plan_reader/csi_v2.db
```

This had never been written down, and it misleads in two specific ways:

- **`ls -l` reports 144 bytes** (the length of the link target's path), not the ~167 MB of the real
  file. Anyone sanity-checking the size concludes the database is empty or truncated.
- **It exists on exactly one machine.** A teammate who clones the repo gets a dangling link, not a
  database — which is a different failure from "file not found" and reads as corruption.

The only backup is `/Users/dev/Desktop/csi_v2_backup_2026-08-03.db` (117 plans, `integrity_check ok`,
SHA-256 identical to the iCloud source). **Run audits against the backup, not the symlink.**

### ⛔ DO NOT DELETE `csi_v2.db`. The runtime repoint did NOT retire it.

`apps/api` stopped opening this file on 2026-08-03 (#50). That is easy to mistake for "the file is
now redundant." **It is not.** It holds content that exists nowhere else:

| Held only in SQLite | Size | Why it matters |
|---|---|---|
| `plans.full_markdown` | **75.3 MB**, 100 of 117 plans | The middle of the regeneration chain `PDF → full_markdown → sections → embeddings`. Deliberately excluded from the publish (payload size, ~97% of it). |
| `sections` | **37,261 rows / 74.9 MB** | Input to gotcha prefiltering and bid-schedule parsing. Deliberately excluded from the publish. |
| `section_intelligence` | 18 rows | Held out by a type bug (`low_sample_flag` declared `REAL`, stores `"Y"`/`""`). |
| `conversations` | 46 historical turns | Never migrated. `scratch.conversations` is at 0, and the JSONL sidecar has only 7 turns. Logs — not regenerable from anything. |

**Chroma cannot substitute for any of it.** The vector store's text is *derived and lossy*:
`s2_indexer` strips boilerplate and drops DROP-sections before indexing (one plan alone: 50
DROP-section chunks dropped, 699 boilerplate paragraphs stripped). It cannot reconstitute
`full_markdown` or `sections`.

**And 17 of 117 plans cannot be re-converted even with the source PDF in hand** — `convert_status`
records 7 `conversion timeout (>300s; pathological PDF)`, 4 `PdfminerException`, 4
`empty/near-empty conversion`, 2 `ValueError: Point: bad args`. A further 6 plans have no
resolvable source PDF at all.

**Precise scope, so nobody over- or under-states it.** There is currently **no plan for which
`full_markdown` is the only surviving copy**: 111 of 117 source PDFs still resolve on disk, and all
6 whose PDF is missing also have no `full_markdown` (they are already unrecoverable). The case for
keeping it is not "it is the sole root" — it is that re-deriving it means hours of conversion, 17
plans would fail again exactly as they did before, and the result would be a non-identical corpus.

### The second copy

A verified gzip of the backup — `csi_v2_2026-08-03.db.gz`, 29.8 MB, decompressed SHA-256 identical
to source, restores to a database with `integrity_check ok` — is held by Tobias on **external
media**. It is deliberately **not in any repo, any GitHub Release, or any cloud store**: the
database is derived from the client's data and the client owns it under the current agreement. Do not go looking
for it in git history, and do not upload it anywhere.

Retiring this file requires publishing `sections` and `section_intelligence`, deciding what to do
about `full_markdown`, and migrating the 46 conversation rows. Tracked in #50.

---

## What is in it

Eight tables, roughly 2.3 MB, covering a curated corpus of 117 plans. Five carry per-plan data,
three are corpus-wide reference/lookup tables.

| table | rows | what it is | grain |
|---|---:|---|---|
| `plans` | 117 | one row per plan set: state, county, year, DOT project and contract id, document type, archetype, source paths, convert status | one plan |
| `materials` | 6,385 | bid-schedule line items: item number, raw description, mapped material bucket, spec category, quantity, unit, page, parse confidence | one bid line |
| `plan_metrics` | 100 | per-plan rollup: the seven material buckets, work type, size tier and percentile, bid-item and spec-category counts, gotcha counts, contract duration, extraction cost | one plan |
| `gotchas` | 1,435 | risk flags with verbatim evidence: flag type, family, decision class (`go_no_go` or `pricing`), evidence excerpt, page list, confidence | one flag occurrence |
| `location_intelligence` | 511 | empirical map of where each fact type appears in a document, with prevalence and an authoritative-occurrence rank | one target and section pairing |
| `material_crosswalk` | 2,434 | reference: normalized bid-item description to spec category, per state, with match source and confidence | one description and state pairing |
| `bucket_hierarchy` | 6 | reference: the client's material bucket hierarchy, units, and the grading-tonnage conversions | one sub-bucket |
| `section_taxonomy` | 18 | reference: document section types with relevance and tier | one section type |

`plan_metrics` has 100 rows against `plans`' 117 because the rollup only covers plans that
converted and parsed far enough to produce metrics. Join on `plan_id` and expect misses.

**Join keys.** `plans.plan_id` is the spine. `materials.plan_id`, `plan_metrics.plan_id` and
`gotchas.plan_id` all reference it. `location_intelligence`, `material_crosswalk`,
`bucket_hierarchy` and `section_taxonomy` are corpus-wide reference data and do not join to a
plan. `material_crosswalk` keys on (`normalized_description`, `state`); `bucket_hierarchy` on
`sub_bucket`; `section_taxonomy` on `section_type`.

`materials`, `gotchas` and `location_intelligence` carry an integer `id` primary key. It is a
surrogate assigned during extraction and it is **not stable across republishes**. Do not store
it in another system as a foreign key or use it as a bookmark. Key on `plan_id` plus the
business columns instead.

### What is deliberately not here

`sections`, the table of raw document chunks (37,261 rows), and `plans.full_markdown`, the full
converted text of each document, are both excluded. Together they are about 76 MB, roughly 97%
of the raw file, and they are document text rather than structured data.

---

## How to connect

The store is a standard Postgres database hosted on Supabase. Anything that speaks Postgres
works: `psql`, DBeaver, TablePlus, pandas, R, a BI tool.

**Getting a connection string.** Ask Tobias. Credentials are not in this repo and are not in any
document. The string looks like:

```
postgresql://<user>:<password>@<host>:5432/postgres
```

Keep it out of git. Put it in your own `.env`, which is already gitignored, or your shell profile.

```bash
psql "$SUPABASE_DB_URL"
```

```python
import os, pandas as pd, sqlalchemy
engine = sqlalchemy.create_engine(os.environ["SUPABASE_DB_URL"])
df = pd.read_sql("select * from plan_metrics", engine)
```

A worked query, the go/no-go risk load per plan:

```sql
select p.plan_id, p.county, p.state, m.work_type, m.size_tier,
       count(*) filter (where g.decision_class = 'go_no_go') as go_no_go,
       count(*) filter (where g.decision_class = 'pricing')  as pricing
from plans p
left join plan_metrics m on m.plan_id = p.plan_id
left join gotchas g      on g.plan_id = p.plan_id
group by 1, 2, 3, 4, 5
order by go_no_go desc;
```

---

## Writing your own tables: the `scratch` schema

The published tables in `public` are **read-only to everyone**. That is deliberate and it is not
a credential problem to be worked around: the publisher drops and recreates every one of those
eight tables on each run, so anything you put there is on a timer, and a mistake in `public`
damages the snapshot for the whole team.

You get a schema of your own instead. `scratch` is writable, and the publisher never names it.

| | `public` | `scratch` |
|---|---|---|
| read the snapshot | yes | — |
| create tables | **no** | yes |
| survives a republish | n/a, it *is* the republish | your tables: yes. your views on `public`: **no** |

Two roles exist. Ask Tobias for whichever you need:

- **`csi_reader`** — read-only on `public`. For dashboards, BI tools, anything that only queries.
- **`csi_team`** — the same read access, plus full DDL in `scratch`. For actual work.

`csi_team` connects with `search_path = scratch, public`, so unqualified names do the right thing
with no ceremony:

```sql
create table my_results (id serial primary key, note text);  -- lands in scratch
select count(*) from plans;                                  -- reads public.plans
```

A statement that says `public.` explicitly still fails, and that is correct — it asked for
something the role does not have:

```sql
create table public.my_results (...);
-- ERROR: permission denied for schema public   [42501]
```

If you hit `42501`, you almost certainly wrote `public.` out of habit. Drop the qualifier.

---

## Important: this store is not live

> The published data comes from the offline `04_tools` scripts over the curated plan corpus. It
> does **not** update when a new plan is dropped into the app. Those extractions still land in a
> JSON payload cache. Closing that gap is tracked in issues #12 through #15. This store is real,
> but it is not live.

Read that literally, because the natural assumption is the opposite one. If someone drops a PDF
into the application today, **nothing in this database changes**. There is no trigger, no queue
and no sync job. The rows here are the state of the curated corpus as of the last time someone
ran the publisher by hand.

Practical consequences:

- Plan counts here will not match what the running application has processed.
- A plan you know was uploaded may be absent entirely.
- Do not build an alerting or monitoring flow that assumes freshness.
- If you need to know how current the data is, ask when the publisher last ran.

Refresh is a manual step, described below.

## RAG and the vector store are not included

Only the structured tables are published. The vector store (a local Chroma instance holding
document chunks and their embeddings) is **not** in this database, and **semantic search over
plan documents is not available from this connection string**.

You can query facts that the pipeline already extracted into columns. You cannot ask free-text
questions over document contents. There is no embedding column and no similarity operator here.

Moving the vector store to hosted pgvector is tracked as **issue #22**. No timeline.

---

## Grants, and the trap in republishing

*Added 2026-08-03.*

`public` is **dropped and recreated** on every publish (`publish_to_supabase.py`). Table-level
`GRANT`s are attributes of the table object and **do not survive a `DROP`**. That is why team access
to `public` silently disappeared in the past: each republish created fresh tables with no grants,
and the next teammate query returned `permission denied for table plans`.

What keeps it working now is `ALTER DEFAULT PRIVILEGES`, installed by `04_tools/team_access.sql`:

```
pg_default_acl:  schema=public   owner=postgres   objtype=r
                 -> csi_reader=r/postgres, csi_team=r/postgres
```

**Default privileges are scoped to the role that creates the table.** Publish as anything other than
`postgres` and new tables inherit nothing — the publish succeeds, the data is correct, and everyone
silently loses read access. `publish_to_supabase.py` now asserts `current_user = postgres` before the
first drop and aborts with an explanation rather than producing that outcome.

`scratch` has the equivalent default privileges as of 2026-08-03
(`alter default privileges for role csi_team in schema scratch grant select on tables to csi_reader`),
so a future `csi_reader` inherits SELECT on new CI tables too. `scratch` is upserted, never dropped,
so it was never exposed to this failure — the default privileges are belt-and-braces.

**Row Level Security is not involved.** RLS is disabled on all 12 tables in both schemas with zero
policies attached. It was ruled out by direct inspection on 2026-08-03; if access breaks again, check
grants and the creating role, not RLS.

---

## Refreshing the snapshot

Run by hand, from a machine that has `csi_v2.db`:

```bash
export CSI_V2_DB='/path/to/csi_v2.db'
export SUPABASE_DB_URL='postgresql://...'

# inspect first: reads SQLite, prints per-table counts, sizes and the DDL, writes nothing
python pipelines/plan_reader/04_tools/publish_to_supabase.py --dry-run

# then publish
python pipelines/plan_reader/04_tools/publish_to_supabase.py
```

The publisher replaces all published tables inside a single transaction, so it is safe to re-run
and will not duplicate rows. Readers see either the whole previous snapshot or the whole new one.

Before dropping anything it scans for views that depend on the published tables, wherever they
live, and **refuses to run if it would destroy one** — printing the list and exiting non-zero.
That is the intended outcome, not a bug: someone's work is in the way. Either have them convert
it to a table (`create table ... as select ...`), or re-run with `--force` if you know it is
disposable. `--force` destroys the listed objects unrecoverably.

Because it is a full replacement, **anything you create inside those tables is destroyed on the
next publish**. Use the `scratch` schema described above.

An earlier revision of this document told you to "build your views against a different schema".
That advice was wrong and was corrected on 2026-07-27. A different schema does not save a view.
`drop table ... cascade` follows dependencies across schema boundaries, so a view in `scratch`
that selects from a published table is dropped along with that table. Verified against Postgres
15 by `04_tools/test_team_access.sh`, which asserts the loss and captures the server's own
`NOTICE: drop cascades to view scratch.plans_by_county`.

**Tables in `scratch` survive. Views on published tables do not, wherever they live.** If a
result matters, materialize it:

```sql
-- survives every publish: the rows are copied into your schema
create table scratch.risk_by_county as
select p.county, count(*) as go_no_go
from public.plans p join public.gotchas g on g.plan_id = p.plan_id
where g.decision_class = 'go_no_go' group by 1;

-- does NOT survive: still depends on public.gotchas, so cascade takes it
create view scratch.risk_by_county_v as ...;
```

The source is opened strictly read-only, so the publisher cannot damage the local database.

---

## Related tracking

- **#9** stand up hosted Supabase and publish the structured tables (this work)
- **#12** to **#15** the live-data gap described above
- **#22** hosted vector search
- **#25** the application's local database path is broken on a clean checkout, unrelated to this
  store but relevant if you are running the app yourself
