# Data access: the CSI bid-tab tables in `scratch`

This describes the tables that hold CSI's historical competitor-bid data in Supabase's `scratch`
schema — csi_team's own writable workspace, separate from `public` (a read-only snapshot owned by
the plan_reader pipeline; see `docs/DATA_ACCESS.md`, which this file does not duplicate or
modify).

---

## What is in it

Four tables, populated from `data/processed/projects.csv`, `data/processed/bidder_results.csv`,
the competitor name registry, and the MN pit list, all by `data/push_supabase_bid_data.py`.

| table | grain | rows (as of the last load) |
|---|---|---|
| `scratch.bid_projects` | one row per historical letting | 1,591 |
| `scratch.bid_results` | one row per bidder per project | 6,838 |
| `scratch.competitor_name_registry` | one row per raw bidder-name variant | 897 |
| `scratch.mn_pit_list` | one row per pit/quarry location | 2,384 |

`bid_results.project_natural_key` is a foreign key to `bid_projects.project_natural_key` (cascade
on delete). `competitor_name_registry` and `mn_pit_list` are independent of the other tables — no
foreign keys.

```sql
create table scratch.bid_projects (
    project_natural_key       text primary key,
    job_id                    text,               -- informational only, see below
    source_project_id         text,
    bid_date                  date,
    bid_year                  integer,
    state                     text,
    county                    text,
    project_location          text,
    project_name              text,
    project_latitude          double precision,
    project_longitude         double precision,
    mix_tons                  double precision,
    grading_yards              double precision,
    base_tons                  double precision,
    shldr_tons                 double precision,
    mill_sy                    double precision,
    crush_tons                 double precision,
    stock_tons                 double precision,
    low_bid_amount               double precision,  -- min(bid_amount) across bidders on this project
    project_type                text,
    project_type_source         text,
    project_type_rule           text,
    source_batch                 text,              -- provenance tag of the load/append that last touched the row
    loaded_at, updated_at                            timestamptz
);

create table scratch.bid_results (
    project_natural_key  text references scratch.bid_projects(project_natural_key) on delete cascade,
    competitor_unit_id   text,
    bid_amount           double precision,
    bid_rank             integer,
    did_win              boolean,
    raw_bidder_name      text,
    mapping_status       text,      -- registry_mapped | needs_review | unmapped (may be "; "-joined)
    source_batch         text,
    loaded_at, updated_at timestamptz,
    primary key (project_natural_key, competitor_unit_id)
);

create table scratch.competitor_name_registry (
    raw_name_variant     text primary key,
    comp_name            text,      -- blank = needs a human (the client) to fill in the canonical name
    source               text,      -- bid_data | pit_list | both | unknown
    top_competitors_tag  text,
    suggested_comp       text,      -- fuzzy-match hint for a blank comp_name, from update_name_registry.py
    source_batch         text,
    loaded_at, updated_at timestamptz
);

create table scratch.mn_pit_list (
    latitude, longitude   double precision,  -- composite key, see below
    name                  text,
    access                text,              -- raw owner/access text, feeds update_name_registry.py
    county                text,              -- already corrected by clean_mn_pit_list.py Pass 2
    rating                integer,
    state                 text,
    access_type           text,              -- open | unknown | client | competitor | closed | knife_river_pending
    access_company        text,
    source_batch          text,
    loaded_at, updated_at timestamptz,
    primary key (latitude, longitude)
);
```

---

## Key design: `project_natural_key`, not `job_id`

`job_id` (e.g. `P000123`) is CSI's local CSV row id, regenerated sequentially by date-sort every
time `data/build_project_competitor_panel.py` runs. It is **not stable** across separate runs —
do not join or key on it. It is carried into `bid_projects` purely for traceability back to a
specific local CSV generation.

The real key is `project_natural_key`, a deterministic, human-readable string built from fields
that don't change run to run:

```
{state}_{county}_{city}_{bid_date:%Y-%m-%d}[_N]
```

e.g. `MN_STEARNS_CO_MELROSE_2023-08-03`. Built by `build_project_natural_key()` in
`data/build_project_competitor_panel.py`. State+county+city+date alone isn't always unique — some
DOTs (e.g. Iowa's `CALL` lettings) bundle multiple distinct projects under one county/city/date —
so `disambiguate_natural_keys()` appends a numeric suffix (`_2`, `_3`, ...), but **only** to the
rows that actually collide (287 of 1,591 projects, 18%, as of the last regeneration). The other
82% get a clean, suffix-free key.

---

## How to load or append

`data/push_supabase_bid_data.py`. `--projects`, `--bidder-results`, `--registry`, and `--pit-list`
are each optional and independent — pass any one alone, or any combination together. Every row is
upserted (`INSERT ... ON CONFLICT DO UPDATE`) on the table's natural key (`project_natural_key` for
`bid_projects`; `(project_natural_key, competitor_unit_id)` for `bid_results`; `raw_name_variant`
for `competitor_name_registry`; `(latitude, longitude)` for `mn_pit_list`), so re-running with the
same data is a no-op, and appending new data never wipes what's already there.

Both bid-data source files must already carry a `project_natural_key` column — the script does not
compute it or resolve it from `job_id`. `data/build_project_competitor_panel.py` computes it for
today's data. Any future source (e.g. a plan_reader-driven project loader, or a bid-results-entry
feature) must compute and carry it too before calling this script.

`bid_results` rows whose `project_natural_key` doesn't already exist in `bid_projects` are reported
and skipped rather than raising a raw foreign-key error, since `bid_results` can be pushed on its
own, without a paired projects file in the same run — the project must already exist.

```bash
export SUPABASE_TEAM_DB_URL='postgresql://...'   # see data/.env.example / data/.env

# bulk load (all four tables together)
python data/push_supabase_bid_data.py \
    --projects data/processed/projects.csv \
    --bidder-results data/processed/bidder_results.csv \
    --registry "pipelines/ci_model/01_candidates/outputs/competitor_name_registry - name_variants.csv" \
    --pit-list data/processed/MN_pit_list_cleaned.csv \
    --source-batch initial_bulk_load

# append/update just one table later, independently
python data/push_supabase_bid_data.py --bidder-results new_results.csv --source-batch 2026_update

# inspect without writing (works without SUPABASE_TEAM_DB_URL)
python data/push_supabase_bid_data.py --projects ... --bidder-results ... --registry ... --pit-list ... --dry-run
```

---

## The name registry's review loop

`competitor_name_registry` exists to be edited by the client, not just read. When
`data/update_name_registry.py` finds a raw bidder name it doesn't recognize (from either bid data
or the pit list), it appends a new row with `comp_name` left **blank** — that's the signal for a
human to fill in the correct canonical name. Pushing the registry to Supabase is what lets the
client actually see and act on those blank rows.

`data/pull_registry_corrections.py` is the other half of the loop: it reads
`scratch.competitor_name_registry` back out and overwrites `comp_name` / `source` /
`top_competitors_tag` / `suggested_comp` on matching local rows wherever Supabase's value differs
— i.e. it pulls the client's corrections into the local CSV. It never adds or removes rows; row
existence stays locally authoritative (rows are only ever created by `update_name_registry.py`
finding a real raw name in the data). A row present in Supabase but not locally is reported as a
warning, not merged in.

```
update_name_registry.py        (finds new raw names, appends blank-comp_name rows locally)
        ↓
push_supabase_bid_data.py --registry ...   (push; client sees new/blank rows in Supabase)
        ↓
   [client fills in comp_name for needs-review rows, directly in Supabase]
        ↓
pull_registry_corrections.py    (pulls the client's corrections back into the local CSV)
        ↓
build_project_competitor_panel.py   (entity resolution now uses the corrected registry)
```

```bash
export SUPABASE_TEAM_DB_URL='postgresql://...'

python data/pull_registry_corrections.py             # apply corrections into the local CSV
python data/pull_registry_corrections.py --dry-run     # preview the diff, write nothing
```

Note: `raw_name_variant` had one exact-duplicate row as of 2026-07-28 ("Anderson Brothers" /
pit_list). `push_supabase_bid_data.py`'s `load_registry()` dedupes on push
(`keep="first"`); the local CSV itself is left untouched by the push.

---

## The pit list's `(latitude, longitude)` key

`mn_pit_list` has no natural key of its own — `Name` repeats (multiple pits share a name at
different locations) and isn't reliable. `(latitude, longitude)` is used instead, per explicit
direction. That's mostly clean, but not perfectly: as of 2026-07-28, 14 of 2,398 rows in
`MN_pit_list_cleaned.csv` shared coordinates with an earlier row.

Rather than silently dedupe those in the push script, `data/clean_mn_pit_list.py`'s **Pass 4**
(`pass4_lat_lon_duplicates()`) flags every row after the first at a given coordinate pair
`duplicate_flag = 'duplicate_lat_lon'` and sinks it to the bottom of the file, for a human to
resolve. Most are exact full-row duplicates (harmless), but 2 pairs ("Langaas pit", "Lois Cater")
carry a genuinely different `Rating` at the same spot — a real conflict, not just noise.
`push_supabase_bid_data.py`'s `load_pit_list()` excludes flagged rows from the push entirely
(reported, not silently kept-first) — fix the source file to get a flagged row into Supabase, not
the push.

`county_from_coords`, `county_match`, `county_flag`, and `county_original` were dropped as of
2026-07-29 — they're Pass 1-2 QA/audit intermediates (spatial-join verification that `County` is
correct), not used by anything downstream once `County` itself is corrected
(`build_pit_features.py`, the only real consumer, derives its own key straight from `County`).
`clean_mn_pit_list.py` still computes them internally — Pass 2's correction logic needs them — it
just no longer writes them to the saved CSV.

---

## Out of scope here

- No join or reconciliation with `public.plans` or any other plan_reader table. These two tables
  are self-contained.
- No ingestion path from `pipelines/plan_reader/` or from a bid-results-entry feature — both are
  future work, not built yet. When they exist, they should write `project_natural_key`-bearing
  rows and call `push_supabase_bid_data.py`'s `upsert_projects()` / `upsert_bidder_results()`
  directly (or a CSV shaped like `projects.csv` / `bidder_results.csv`).
