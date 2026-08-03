# Data access: the published plan-extraction tables

This describes how to read the structured data that the Plan Reader pipeline extracts from
highway construction plan sets: what is in it, how to connect, and the limits you need to know
before you build on it.

You do not need this repo, a Python environment, or any of the pipeline code to use it. You need
a connection string and anything that speaks Postgres.

**If you want to run the app rather than just query the data, start with the next section.**

---

## Running the app locally — start here

*Added 2026-08-03. This is the section to follow on a fresh machine.*

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

### 4. Python version

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

It is a copy, not the system of record. The local SQLite file remains authoritative and the
application does not read from Postgres.

---

## What is in it

Eight tables, roughly 2.3 MB, covering a curated corpus of 117 plans. Five carry per-plan data,
three are corpus-wide reference/lookup tables.

| table | rows | what it is | grain |
|---|---:|---|---|
| `plans` | 117 | one row per plan set: state, county, year, DOT project and contract id, document type, archetype, source paths, convert status | one plan |
| `materials` | 6,385 | bid-schedule line items: item number, raw description, mapped CSI bucket, spec category, quantity, unit, page, parse confidence | one bid line |
| `plan_metrics` | 100 | per-plan rollup: the seven material buckets, work type, size tier and percentile, bid-item and spec-category counts, gotcha counts, contract duration, extraction cost | one plan |
| `gotchas` | 1,435 | risk flags with verbatim evidence: flag type, family, decision class (`go_no_go` or `pricing`), evidence excerpt, page list, confidence | one flag occurrence |
| `location_intelligence` | 511 | empirical map of where each fact type appears in a document, with prevalence and an authoritative-occurrence rank | one target and section pairing |
| `material_crosswalk` | 2,434 | reference: normalized bid-item description to spec category, per state, with match source and confidence | one description and state pairing |
| `bucket_hierarchy` | 6 | reference: the CSI material bucket hierarchy, units, and the grading-tonnage conversions | one sub-bucket |
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
