#!/usr/bin/env python3
"""Push CSI bid-tab data (projects.csv / bidder_results.csv / the competitor name registry / the
MN pit list) to the CSI Supabase database's `scratch` schema (csi_team's own writable workspace).
See docs/DATA_ACCESS_SCRATCH.md.

scratch.bid_projects, scratch.bid_results, scratch.competitor_name_registry, and
scratch.mn_pit_list are independently appendable: --projects, --bidder-results, --registry, and
--pit-list can each be passed alone or in any combination. Both bid-data source files must already
carry a project_natural_key column -- data/build_project_competitor_panel.py computes it for
today's data; any future source (a plan_reader-driven project loader, a bid-results-entry feature)
must compute and carry it too. (There used to be a job_id column here too -- a sequential row-id
regenerated per-run and not stable across separate runs/appends. Removed entirely in favor of
project_natural_key as the sole identifier, to avoid confusion with plan_reader's own, unrelated
job_id concept.)

The registry table is meant to be read *and edited* by the client in Supabase (filling in
comp_name for needs-review rows) -- see data/pull_registry_corrections.py for reading those edits
back into the local CSV.

The pit list has no stable natural key of its own; (latitude, longitude) is used as one. Rows
data/clean_mn_pit_list.py's Pass 4 flagged 'duplicate_lat_lon' (same coordinates as an earlier row
-- see that script) are excluded from the push rather than silently deduped here, so a real data
conflict (e.g. two different Rating values at the same spot) gets fixed at the source, not masked.

Usage:
    export SUPABASE_TEAM_DB_URL='postgresql://...'   # see data/.env.example / data/.env

    # one-time bulk load (all four tables together)
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
"""
from __future__ import annotations

import argparse
import os

import pandas as pd
import psycopg
from psycopg import sql

SCHEMA = "scratch"

BID_PROJECTS_DDL = """
create table if not exists scratch.bid_projects (
    project_natural_key       text primary key,
    source_project_id         text,
    bid_date                  date,
    bid_time                  text,
    bid_year                  integer,
    state                     text,
    county                    text,
    project_location          text,
    project_name              text,
    project_latitude          double precision,
    project_longitude         double precision,
    mix_tons                  double precision,
    grading_yards             double precision,
    base_tons                 double precision,
    shldr_tons                double precision,
    mill_sy                   double precision,
    crush_tons                double precision,
    stock_tons                double precision,
    project_type              text,
    updated_at                timestamptz not null default now()
)
"""

BID_RESULTS_DDL = """
create table if not exists scratch.bid_results (
    project_natural_key  text not null references scratch.bid_projects(project_natural_key) on delete cascade,
    competitor_unit_id   text not null,
    bid_amount           double precision,
    bid_rank             integer,
    did_win               boolean,
    raw_bidder_name       text,
    mapping_status        text,
    source_batch          text,
    loaded_at             timestamptz not null default now(),
    updated_at            timestamptz not null default now(),
    primary key (project_natural_key, competitor_unit_id)
)
"""

BID_RESULTS_INDEX_DDL = (
    "create index if not exists bid_results_mapping_status_idx "
    "on scratch.bid_results (mapping_status)"
)

REGISTRY_DDL = """
create table if not exists scratch.competitor_name_registry (
    raw_name_variant     text primary key,
    comp_name            text,
    source               text,
    top_competitors_tag  text,
    suggested_comp       text,
    source_batch         text,
    loaded_at            timestamptz not null default now(),
    updated_at           timestamptz not null default now()
)
"""

MN_PIT_LIST_DDL = """
create table if not exists scratch.mn_pit_list (
    latitude            double precision not null,
    longitude           double precision not null,
    name                text,
    access              text,
    county              text,
    rating              integer,
    state               text,
    access_type         text,
    access_company      text,
    updated_at          timestamptz not null default now(),
    primary key (latitude, longitude)
)
"""

PROJECT_COLUMNS = [
    "project_natural_key", "source_project_id", "bid_date", "bid_time", "bid_year",
    "state", "county", "project_location", "project_name",
    "project_latitude", "project_longitude",
    "mix_tons", "grading_yards", "base_tons", "shldr_tons", "mill_sy", "crush_tons", "stock_tons",
    "project_type",
]

RESULT_COLUMNS = [
    "project_natural_key", "competitor_unit_id", "bid_amount", "bid_rank", "did_win",
    "raw_bidder_name", "mapping_status",
]

REGISTRY_COLUMNS = [
    "raw_name_variant", "comp_name", "source", "top_competitors_tag", "suggested_comp",
]

PIT_LIST_COLUMNS = [
    "latitude", "longitude", "name", "access", "county", "rating", "state",
    "access_type", "access_company",
]

DATE_COLUMNS = {"bid_date"}
INT_COLUMNS = {"bid_year", "bid_rank", "rating"}
FLOAT_COLUMNS = {
    "project_latitude", "project_longitude", "mix_tons", "grading_yards", "base_tons",
    "shldr_tons", "mill_sy", "crush_tons", "stock_tons", "bid_amount",
    "latitude", "longitude",
}
BOOL_COLUMNS = {"did_win"}
_BOOL_TOKENS = {"1": True, "1.0": True, "true": True,
                "0": False, "0.0": False, "false": False}


def connect() -> psycopg.Connection:
    dsn = os.environ.get("SUPABASE_TEAM_DB_URL")
    if not dsn:
        raise SystemExit("SUPABASE_TEAM_DB_URL is not set. export it (see data/.env.example).")
    return psycopg.connect(dsn)


def ensure_tables(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        cur.execute(BID_PROJECTS_DDL)
        # bid_time was added after bid_projects already existed in some environments;
        # CREATE TABLE IF NOT EXISTS above won't alter an existing table's columns.
        cur.execute("alter table scratch.bid_projects add column if not exists bid_time text")
        cur.execute(BID_RESULTS_DDL)
        cur.execute(BID_RESULTS_INDEX_DDL)
        cur.execute(REGISTRY_DDL)
        cur.execute(MN_PIT_LIST_DDL)


def _require_columns(df: pd.DataFrame, required: set[str], path: str) -> None:
    missing = required - set(df.columns)
    if missing:
        raise SystemExit(f"{path}: missing required column(s) {sorted(missing)}")


def _typed_value(col: str, value):
    """Convert a raw string cell (or pandas NaN) into the native Python type Postgres expects
    for that column, so psycopg's COPY adapts it correctly instead of writing text like "nan"
    into a numeric/boolean/date column."""
    if pd.isna(value):
        return None
    if col in DATE_COLUMNS:
        return pd.Timestamp(value).date()
    if col in INT_COLUMNS:
        return int(float(value))
    if col in FLOAT_COLUMNS:
        return float(value)
    if col in BOOL_COLUMNS:
        token = str(value).strip().lower()
        if token not in _BOOL_TOKENS:
            raise ValueError(f"column {col!r}: unrecognized boolean value {value!r}")
        return _BOOL_TOKENS[token]
    return str(value)


def load_projects(path: str) -> pd.DataFrame:
    df = pd.read_csv(path, dtype=str)
    # bid_year must come from the CSV as-is (source-file provenance -- see build_projects() in
    # data/build_project_competitor_panel.py), not be recomputed from bid_date here: CSI's fiscal
    # year runs Aug 1-Jul 31, one year ahead of the calendar year for Aug-Dec bids, and plain
    # calendar-year math on bid_date silently mislabeled every Aug-Dec row until this was fixed.
    _require_columns(df, {"project_natural_key", "bid_date", "bid_year", "state", "county"}, path)
    return df


def load_bidder_results(path: str) -> pd.DataFrame:
    df = pd.read_csv(path, dtype=str)
    _require_columns(df, {"project_natural_key", "competitor_unit_id"}, path)
    return df


def load_registry(path: str) -> pd.DataFrame:
    df = pd.read_csv(path, dtype=str)
    df = df.rename(columns={"Top Competitors Tag": "top_competitors_tag"})
    _require_columns(df, {"raw_name_variant", "comp_name"}, path)
    # One exact-duplicate raw_name_variant row exists in the source file as of 2026-07-28
    # ("Anderson Brothers" / pit_list, appears twice, identical in every column) -- dedupe rather
    # than let it hit the primary key on upsert.
    return df.drop_duplicates(subset=["raw_name_variant"], keep="first")


def load_pit_list(path: str) -> pd.DataFrame:
    df = pd.read_csv(path, dtype=str)
    df = df.rename(columns={c: c.lower() for c in df.columns})
    _require_columns(df, {"latitude", "longitude"}, path)
    if "duplicate_flag" in df.columns:
        flagged = df[df["duplicate_flag"] == "duplicate_lat_lon"]
        if len(flagged):
            print(
                f"[skip] {len(flagged)} pit row(s) flagged 'duplicate_lat_lon' by "
                f"data/clean_mn_pit_list.py's Pass 4 -- excluded from the push (fix the source "
                f"file, don't dedupe here):"
            )
            for _, row in flagged.head(20).iterrows():
                print(f"    {row.get('name')}  ({row['latitude']}, {row['longitude']})")
        df = df[df["duplicate_flag"] != "duplicate_lat_lon"]
    return df


def upsert(
    conn: psycopg.Connection,
    table: str,
    df: pd.DataFrame,
    key_cols: list[str],
    all_cols: list[str],
    source_batch: str,
    dry_run: bool,
    write_source_batch: bool = True,
) -> tuple[int, int]:
    payload = df[[c for c in all_cols if c in df.columns]].copy()
    if write_source_batch:
        payload["source_batch"] = source_batch
    write_cols = list(payload.columns)

    if dry_run:
        print(f"[dry-run] {SCHEMA}.{table}: would upsert {len(payload)} row(s), columns={write_cols}")
        return 0, 0

    qualified = sql.Identifier(SCHEMA, table)
    stage = sql.Identifier(f"stage_{table}")

    with conn.cursor() as cur:
        cur.execute(
            sql.SQL("create temporary table {stage} (like {table} including defaults) on commit drop")
            .format(stage=stage, table=qualified)
        )
        col_list = sql.SQL(", ").join(sql.Identifier(c) for c in write_cols)
        with cur.copy(sql.SQL("copy {stage} ({cols}) from stdin").format(stage=stage, cols=col_list)) as copy:
            for row in payload.itertuples(index=False):
                copy.write_row([_typed_value(c, v) for c, v in zip(write_cols, row)])

        update_cols = [c for c in write_cols if c not in key_cols]
        set_clause = sql.SQL(", ").join(
            sql.SQL("{0} = excluded.{0}").format(sql.Identifier(c)) for c in update_cols
        )
        key_list = sql.SQL(", ").join(sql.Identifier(c) for c in key_cols)
        insert_cols = sql.SQL(", ").join(sql.Identifier(c) for c in write_cols)
        cur.execute(
            sql.SQL(
                "insert into {table} ({cols}) select {cols} from {stage} "
                "on conflict ({keys}) do update set {set_clause}, updated_at = now() "
                "returning (xmax = 0) as inserted"
            ).format(table=qualified, cols=insert_cols, stage=stage, keys=key_list, set_clause=set_clause)
        )
        results = cur.fetchall()

    inserted = sum(1 for (is_insert,) in results if is_insert)
    updated = len(results) - inserted
    return inserted, updated


def upsert_projects(conn, df: pd.DataFrame, source_batch: str, dry_run: bool) -> tuple[int, int]:
    return upsert(conn, "bid_projects", df, ["project_natural_key"], PROJECT_COLUMNS, source_batch, dry_run,
                   write_source_batch=False)


def upsert_bidder_results(
    conn,
    df: pd.DataFrame,
    source_batch: str,
    dry_run: bool,
    known_project_keys: set[str] | None,
) -> tuple[int, int]:
    if known_project_keys is not None:
        missing = df[~df["project_natural_key"].isin(known_project_keys)]
        if len(missing):
            print(
                f"[skip] {len(missing)} bid_results row(s) reference a project_natural_key not "
                f"found in {SCHEMA}.bid_projects -- skipped (create the project first):"
            )
            for key in sorted(missing["project_natural_key"].unique())[:20]:
                print(f"    {key}")
            df = df[df["project_natural_key"].isin(known_project_keys)]
    return upsert(
        conn, "bid_results", df, ["project_natural_key", "competitor_unit_id"],
        RESULT_COLUMNS, source_batch, dry_run,
    )


def upsert_registry(conn, df: pd.DataFrame, source_batch: str, dry_run: bool) -> tuple[int, int]:
    return upsert(conn, "competitor_name_registry", df, ["raw_name_variant"],
                  REGISTRY_COLUMNS, source_batch, dry_run)


def upsert_pit_list(conn, df: pd.DataFrame, source_batch: str, dry_run: bool) -> tuple[int, int]:
    return upsert(conn, "mn_pit_list", df, ["latitude", "longitude"],
                  PIT_LIST_COLUMNS, source_batch, dry_run, write_source_batch=False)


def _existing_project_keys(conn: psycopg.Connection) -> set[str]:
    with conn.cursor() as cur:
        cur.execute(f"select project_natural_key from {SCHEMA}.bid_projects")
        return {row[0] for row in cur.fetchall()}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--projects", help="path to a projects.csv-shaped file")
    parser.add_argument("--bidder-results", help="path to a bidder_results.csv-shaped file")
    parser.add_argument("--registry", help="path to the competitor_name_registry CSV")
    parser.add_argument("--pit-list", help="path to the MN_pit_list_cleaned.csv-shaped file")
    parser.add_argument("--source-batch", required=True, help="provenance tag stamped on every upserted row")
    parser.add_argument("--dry-run", action="store_true", help="print what would happen, write nothing")
    args = parser.parse_args()

    if not args.projects and not args.bidder_results and not args.registry and not args.pit_list:
        raise SystemExit(
            "pass --projects and/or --bidder-results and/or --registry and/or --pit-list "
            "(at least one is required)"
        )

    projects_df = load_projects(args.projects) if args.projects else None
    results_df = load_bidder_results(args.bidder_results) if args.bidder_results else None
    registry_df = load_registry(args.registry) if args.registry else None
    pit_list_df = load_pit_list(args.pit_list) if args.pit_list else None

    if args.dry_run:
        print(f"[dry-run] would ensure tables {SCHEMA}.bid_projects, {SCHEMA}.bid_results, "
              f"{SCHEMA}.competitor_name_registry, {SCHEMA}.mn_pit_list exist")
        if projects_df is not None:
            upsert_projects(None, projects_df, args.source_batch, dry_run=True)
        if results_df is not None:
            upsert_bidder_results(None, results_df, args.source_batch, dry_run=True, known_project_keys=None)
        if registry_df is not None:
            upsert_registry(None, registry_df, args.source_batch, dry_run=True)
        if pit_list_df is not None:
            upsert_pit_list(None, pit_list_df, args.source_batch, dry_run=True)
        return

    with connect() as conn:
        ensure_tables(conn)

        if projects_df is not None:
            inserted, updated = upsert_projects(conn, projects_df, args.source_batch, dry_run=False)
            print(f"{SCHEMA}.bid_projects: {inserted} inserted, {updated} updated")

        if results_df is not None:
            known_keys = _existing_project_keys(conn)
            if projects_df is not None:
                known_keys |= set(projects_df["project_natural_key"])
            inserted, updated = upsert_bidder_results(
                conn, results_df, args.source_batch, dry_run=False, known_project_keys=known_keys
            )
            print(f"{SCHEMA}.bid_results: {inserted} inserted, {updated} updated")

        if registry_df is not None:
            inserted, updated = upsert_registry(conn, registry_df, args.source_batch, dry_run=False)
            print(f"{SCHEMA}.competitor_name_registry: {inserted} inserted, {updated} updated")

        if pit_list_df is not None:
            inserted, updated = upsert_pit_list(conn, pit_list_df, args.source_batch, dry_run=False)
            print(f"{SCHEMA}.mn_pit_list: {inserted} inserted, {updated} updated")

        conn.commit()


if __name__ == "__main__":
    main()
