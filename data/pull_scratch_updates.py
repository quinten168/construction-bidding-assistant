#!/usr/bin/env python3
"""Pull admin-UI edits back from Supabase's `scratch` schema into the local files ci_model's
training/scoring pipeline actually reads. See docs/DATA_ACCESS_SCRATCH.md and ARCHITECTURE.md §9.

PR #45 gave apps/api its first direct Postgres connection (backend/ci_db.py) for three admin
features -- bid-results entry, pit-list CRUD, competitor-registry CRUD -- but writes from those
pages only ever land in `scratch.*`. Nothing an estimator edits there reaches a report, because
ci_model still reads local CSVs by path. This script is the missing return leg.

Row existence rules differ by table, because the admin UI's capabilities differ by table:
  - competitor_name_registry: update-only, existing rows only (same as the existing
    data/pull_registry_corrections.py, reused here as a library, not duplicated). The admin UI
    can rename/consolidate but new raw_name_variant rows are only ever created locally by
    data/update_name_registry.py finding them in real bid data.
  - bid_projects: update-only, and only the materials columns the admin UI's project-materials
    endpoint can touch. The admin UI never creates or deletes a project.
  - bid_results: upsert (add + update). The admin UI's bid-results-entry feature can add results
    for a project that had none yet, and its inline-edit table can change existing ones.
  - mn_pit_list: full diff (add + update + delete). The admin UI has full pit CRUD.

Usage:
    export SUPABASE_TEAM_DB_URL='postgresql://...'   # see data/.env.example / data/.env

    python data/pull_scratch_updates.py --check-only   # fast staleness check, no pandas, exit 0=fresh 1=stale
    python data/pull_scratch_updates.py --all           # sync all four tables
    python data/pull_scratch_updates.py --all --dry-run # preview only, write nothing
    python data/pull_scratch_updates.py --bid-results --pit-list   # sync just these two
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))

STATE_FILE = _HERE / "processed" / ".scratch_sync_state.json"

# Root-anchored like STATE_FILE above, NOT cwd-relative strings. These were bare relative paths
# until 2026-08-09, which meant the script only worked when invoked from the repo root — and the
# API server invokes it as a subprocess from cwd=apps/api (competitor_live.ensure_fresh_local_data),
# so every server-triggered refresh failed with FileNotFoundError on all four tables since the
# feature shipped, silently (fail-open) leaving reports on stale local data.
_ROOT = _HERE.parent
REGISTRY_FILE = str(_ROOT / "pipelines/ci_model/01_candidates/outputs/"
                            "competitor_name_registry - name_variants.csv")
PROJECTS_FILE = str(_ROOT / "data/processed/projects.csv")
PROJECTS_PARQUET = str(_ROOT / "data/processed/projects.parquet")
BIDDER_RESULTS_FILE = str(_ROOT / "data/processed/bidder_results.csv")
BIDDER_RESULTS_PARQUET = str(_ROOT / "data/processed/bidder_results.parquet")
PIT_LIST_FILE = str(_ROOT / "data/processed/MN_pit_list_cleaned.csv")

MATERIALS_COLUMNS = [
    "mix_tons", "grading_yards", "base_tons", "shldr_tons", "mill_sy", "crush_tons", "stock_tons",
]
BID_RESULTS_COLUMNS = [
    "project_natural_key", "competitor_unit_id", "bid_amount", "bid_rank", "did_win",
    "raw_bidder_name", "mapping_status",
]
PIT_LIST_COLUMNS = [
    "latitude", "longitude", "name", "access", "county", "rating", "state",
    "access_type", "access_company",
]

_TABLES = {"registry", "projects", "bid-results", "pit-list"}


def connect():
    import psycopg
    dsn = os.environ.get("SUPABASE_TEAM_DB_URL")
    if not dsn:
        raise SystemExit("SUPABASE_TEAM_DB_URL is not set. export it (see data/.env.example).")
    return psycopg.connect(dsn)


# ── staleness check (no pandas import on this path -- stays fast) ──────────────────────────────

def _load_state() -> dict:
    if not STATE_FILE.exists():
        return {}
    try:
        return json.loads(STATE_FILE.read_text())
    except (json.JSONDecodeError, OSError):
        return {}


def _save_state(last_synced_at) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps({"last_synced_at": str(last_synced_at)}))


def remote_max_updated_at(conn) -> object:
    with conn.cursor() as cur:
        cur.execute(
            "select greatest("
            "  (select max(updated_at) from scratch.bid_projects),"
            "  (select max(updated_at) from scratch.bid_results),"
            "  (select max(updated_at) from scratch.competitor_name_registry),"
            "  (select max(updated_at) from scratch.mn_pit_list)"
            ")"
        )
        (value,) = cur.fetchone()
        return value


def check_only() -> int:
    """Print fresh/stale and return an exit code (0=fresh, 1=stale) without touching pandas."""
    state = _load_state()
    last_synced_at = state.get("last_synced_at")
    with connect() as conn:
        remote_max = remote_max_updated_at(conn)
    if remote_max is None:
        print("fresh (no rows in scratch.* yet)")
        return 0
    if last_synced_at is None or str(remote_max) > last_synced_at:
        print(f"stale (remote max updated_at={remote_max}, local last_synced_at={last_synced_at})")
        return 1
    print(f"fresh (local last_synced_at={last_synced_at} >= remote max updated_at={remote_max})")
    return 0


# ── value/key normalization ─────────────────────────────────────────────────────────────────────
# psycopg returns native Python types (None, float, int, bool) for remote rows; the local CSVs are
# read with dtype=str. Comparing them naively -- or blanket-casting the remote frame to str before
# comparing -- turns a real SQL NULL into the *string* "nan" or "None", which then looks like a
# change on every blank local cell. _norm() normalizes both sides through the same NaN/float path
# before comparing or displaying, so True/1/"1"/1.0 all compare equal and only genuine differences
# are reported.
#
# Rounded to 9 decimal places (not compared at full float precision): a live pull against
# scratch.mn_pit_list showed every one of 2384 rows differing from its local CSV counterpart by
# ~1e-14 (confirmed via nearest-match distance, not real data drift) -- a round-trip precision
# artifact, most likely from data/push_supabase_bid_data.py's COPY-protocol float formatting.
# Comparing latitude/longitude (this pipeline's only floating-point primary key) at full precision
# turned every real pit into a spurious new+deleted pair. 9 decimal places is ~11cm at these
# latitudes -- far finer than any real distinction between two pit locations -- while safely
# absorbing noise at the 1e-14 (roughly 13th significant digit) level.
_ROUND_DP = 9


def _norm(v) -> str:
    import pandas as pd
    if pd.isna(v):
        return ""
    try:
        return repr(round(float(v), _ROUND_DP))
    except (TypeError, ValueError):
        return str(v).strip()


def _key_str(v) -> str:
    """Canonical string form for a key column (join key or index), so a text/text key like
    project_natural_key round-trips as-is and a numeric key like latitude/longitude (double
    precision in Postgres, string in the CSV) lands on the same value regardless of which side
    it came from. See _ROUND_DP above for why this rounds rather than comparing exactly."""
    try:
        return repr(round(float(v), _ROUND_DP))
    except (TypeError, ValueError):
        return str(v).strip()


def _stringify_remote(remote):
    """Coerce a freshly-fetched remote frame to the same dtype=str-with-NaN-for-blank shape the
    local CSVs already have. psycopg returns native Python types (None/float/int/bool); writing
    those straight into a local frame that's otherwise all `str` produces a column with mixed
    Python types, which pandas' object dtype tolerates in memory but pyarrow's to_parquet cannot
    -- it needs one Arrow type per column and raises ArrowTypeError on the first str/float clash.
    Booleans go to "1"/"0" to match how push_supabase_bid_data.py's BOOL_COLUMNS convention already
    reads back out of these CSVs (see that script's _BOOL_TOKENS)."""
    import numpy as np
    import pandas as pd

    def _cell(v):
        # pd.DataFrame(rows, ...) construction can already upcast a column mixing None with
        # numbers to float64, turning None into np.nan before this function ever sees it -- so
        # `v is None` alone misses that case. pd.isna() catches both.
        if pd.isna(v):
            return np.nan
        if isinstance(v, bool):
            return "1" if v else "0"
        return str(v)

    return remote.apply(lambda col: col.map(_cell))


# ── atomic writes ───────────────────────────────────────────────────────────────────────────────

def _atomic_write_csv(df, path: str) -> None:
    import pandas as pd  # noqa: F401  (typing hint only, df is already a DataFrame)
    tmp = f"{path}.tmp"
    df.to_csv(tmp, index=False)
    os.replace(tmp, path)


def _atomic_write_parquet(df, path: str) -> None:
    tmp = f"{path}.tmp"
    df.to_parquet(tmp, index=False)
    os.replace(tmp, path)


# ── registry: reuse the existing pull script's logic, don't duplicate it ───────────────────────

def sync_registry(conn, dry_run: bool) -> None:
    import pull_registry_corrections as prc
    import pandas as pd

    local = pd.read_csv(REGISTRY_FILE, dtype=str)
    local = local.rename(columns={"Top Competitors Tag": "top_competitors_tag"})
    remote = prc.fetch_remote(conn)
    updated, changes = prc.merge_corrections(local, remote)

    if not changes:
        print("registry: no corrections found -- local already matches Supabase.")
        return

    print(f"registry: {len(changes)} row(s) corrected:")
    for change in changes:
        key = change["raw_name_variant"]
        for col, (old, new) in change["cols"].items():
            print(f"  {key} [{col}]: {prc._norm(old) or '(blank)'} -> {prc._norm(new) or '(blank)'}")

    if dry_run:
        print("[dry-run] registry: would write these changes; nothing written.")
        return

    updated = updated.rename(columns={"top_competitors_tag": "Top Competitors Tag"})
    _atomic_write_csv(updated, REGISTRY_FILE)
    print(f"registry saved -> {REGISTRY_FILE}")


# ── projects: update-only, materials columns only ───────────────────────────────────────────────

def sync_projects(conn, dry_run: bool) -> None:
    import pandas as pd

    local = pd.read_csv(PROJECTS_FILE, dtype=str)
    with conn.cursor() as cur:
        cols = ", ".join(["project_natural_key", *MATERIALS_COLUMNS])
        cur.execute(f"select {cols} from scratch.bid_projects where deleted_at is null")
        rows = cur.fetchall()
    remote = _stringify_remote(pd.DataFrame(rows, columns=["project_natural_key", *MATERIALS_COLUMNS]))
    remote_by_key = remote.set_index(remote["project_natural_key"].map(_key_str))

    changes: list[dict] = []
    for idx, row in local.iterrows():
        key = _key_str(row["project_natural_key"])
        if key not in remote_by_key.index:
            continue
        remote_row = remote_by_key.loc[key]
        changed_cols = {}
        for col in MATERIALS_COLUMNS:
            if col not in local.columns:
                continue
            local_val, remote_val = row.get(col), remote_row.get(col)
            if _norm(local_val) != _norm(remote_val):
                changed_cols[col] = (local_val, remote_val)
                local.at[idx, col] = remote_val
        if changed_cols:
            changes.append({"project_natural_key": key, "cols": changed_cols})

    if not changes:
        print("projects: no materials changes found -- local already matches Supabase.")
        return

    print(f"projects: {len(changes)} row(s) with materials changes:")
    for change in changes:
        key = change["project_natural_key"]
        for col, (old, new) in change["cols"].items():
            print(f"  {key} [{col}]: {_norm(old) or '(blank)'} -> {_norm(new) or '(blank)'}")

    if dry_run:
        print("[dry-run] projects: would write these changes; nothing written.")
        return

    _atomic_write_csv(local, PROJECTS_FILE)
    if Path(PROJECTS_PARQUET).exists():
        _atomic_write_parquet(local, PROJECTS_PARQUET)
    print(f"projects saved -> {PROJECTS_FILE}" + (f" (+ {PROJECTS_PARQUET})" if Path(PROJECTS_PARQUET).exists() else ""))


# ── bid_results: upsert (add new + update existing) ─────────────────────────────────────────────

def sync_bid_results(conn, dry_run: bool) -> None:
    import pandas as pd

    local = pd.read_csv(BIDDER_RESULTS_FILE, dtype=str)
    with conn.cursor() as cur:
        cols = ", ".join(BID_RESULTS_COLUMNS)
        cur.execute(f"select {cols} from scratch.bid_results")
        rows = cur.fetchall()
    remote = _stringify_remote(pd.DataFrame(rows, columns=BID_RESULTS_COLUMNS))

    key_cols = ["project_natural_key", "competitor_unit_id"]

    def _key_index(df):
        return pd.MultiIndex.from_arrays([df[c].map(_key_str) for c in key_cols], names=key_cols)

    local_keyed = local.set_index(_key_index(local), drop=False)
    remote_keyed = remote.set_index(_key_index(remote), drop=False)

    new_keys = remote_keyed.index.difference(local_keyed.index)
    shared_keys = remote_keyed.index.intersection(local_keyed.index)

    updated_rows = 0
    for key in shared_keys:
        remote_row = remote_keyed.loc[key]
        for col in BID_RESULTS_COLUMNS:
            if col in key_cols or col not in local.columns:
                continue
            if _norm(local_keyed.loc[key, col]) != _norm(remote_row.get(col)):
                local_keyed.loc[key, col] = remote_row.get(col)
                updated_rows += 1

    added_rows = len(new_keys)
    if added_rows:
        local_keyed = pd.concat([local_keyed, remote_keyed.loc[new_keys]])

    if not added_rows and not updated_rows:
        print("bid_results: no changes found -- local already matches Supabase.")
        return

    print(f"bid_results: {added_rows} new row(s), {updated_rows} field change(s) on existing rows")

    if dry_run:
        print("[dry-run] bid_results: would write these changes; nothing written.")
        return

    merged = local_keyed.reset_index(drop=True)
    _atomic_write_csv(merged, BIDDER_RESULTS_FILE)
    if Path(BIDDER_RESULTS_PARQUET).exists():
        _atomic_write_parquet(merged, BIDDER_RESULTS_PARQUET)
    print(f"bid_results saved -> {BIDDER_RESULTS_FILE}"
          + (f" (+ {BIDDER_RESULTS_PARQUET})" if Path(BIDDER_RESULTS_PARQUET).exists() else ""))


# ── pit_list: full diff (add + update + delete) ─────────────────────────────────────────────────

def sync_pit_list(conn, dry_run: bool) -> None:
    import pandas as pd

    local = pd.read_csv(PIT_LIST_FILE, dtype=str)
    local.columns = [c.lower() for c in local.columns]
    with conn.cursor() as cur:
        cols = ", ".join(PIT_LIST_COLUMNS)
        cur.execute(f"select {cols} from scratch.mn_pit_list")
        rows = cur.fetchall()
    remote = _stringify_remote(pd.DataFrame(rows, columns=PIT_LIST_COLUMNS))

    # data/clean_mn_pit_list.py's Pass 4 flags rows sharing (latitude, longitude) with an earlier
    # row as 'duplicate_lat_lon'; data/push_supabase_bid_data.py::load_pit_list excludes exactly
    # these before treating (latitude, longitude) as the Supabase primary key (see that script's
    # docstring). Same exclusion here, for the same reason: without it, (latitude, longitude)
    # isn't actually unique locally and .loc[key] below returns a Series instead of a row.
    if "duplicate_flag" in local.columns:
        flagged_dupes = local[local["duplicate_flag"] == "duplicate_lat_lon"]
        local = local[local["duplicate_flag"] != "duplicate_lat_lon"]
    else:
        flagged_dupes = local.iloc[0:0]

    key_cols = ["latitude", "longitude"]

    def _key_index(df):
        return pd.MultiIndex.from_arrays([df[c].map(_key_str) for c in key_cols], names=key_cols)

    local_keyed = local.set_index(_key_index(local), drop=False)
    remote_keyed = remote.set_index(_key_index(remote), drop=False)

    # A (lat, lon) key duplicated on EITHER side breaks every .loc[key] below (returns a frame
    # instead of a row) and used to kill the whole pull with an opaque ValueError -- found live
    # 2026-08-09: two unflagged rows for the same pit whose raw coordinates differed only past the
    # 6th decimal collapsed to one key. Data problems must degrade to a warned no-op for the rows
    # involved, not take down the sync for every other table and row. Collided keys are excluded
    # from the diff entirely (not added, not updated, not deleted) and reported loudly so the
    # underlying data gets fixed rather than silently papered over.
    collided = local_keyed.index[local_keyed.index.duplicated(keep=False)].union(
        remote_keyed.index[remote_keyed.index.duplicated(keep=False)]).unique()
    if len(collided):
        for key in collided:
            for side, frame in (("local", local_keyed), ("remote", remote_keyed)):
                if key in frame.index:
                    rows = frame.loc[[key]]
                    names = ", ".join(repr(n) for n in rows["name"])
                    print(f"pit_list WARNING: key {key} has {len(rows)} {side} row(s): {names}")
        print(f"pit_list WARNING: {len(collided)} colliding (lat, lon) key(s) SKIPPED -- these "
              "rows were left untouched on both sides; fix the duplicate data to resume syncing them.")
        local_keyed = local_keyed[~local_keyed.index.isin(collided)]
        remote_keyed = remote_keyed[~remote_keyed.index.isin(collided)]
        collided_local_rows = local[_key_index(local).isin(collided)]
    else:
        collided_local_rows = local.iloc[0:0]

    new_keys = remote_keyed.index.difference(local_keyed.index)
    deleted_keys = local_keyed.index.difference(remote_keyed.index)
    shared_keys = remote_keyed.index.intersection(local_keyed.index)

    updated_rows = 0
    for key in shared_keys:
        remote_row = remote_keyed.loc[key]
        for col in PIT_LIST_COLUMNS:
            if col in key_cols or col not in local.columns:
                continue
            if _norm(local_keyed.loc[key, col]) != _norm(remote_row.get(col)):
                local_keyed.loc[key, col] = remote_row.get(col)
                updated_rows += 1

    if len(new_keys):
        local_keyed = pd.concat([local_keyed, remote_keyed.loc[new_keys]])
    if len(deleted_keys):
        local_keyed = local_keyed.drop(index=deleted_keys)

    added, deleted = len(new_keys), len(deleted_keys)
    if not added and not deleted and not updated_rows:
        print("pit_list: no changes found -- local already matches Supabase.")
        return

    print(f"pit_list: {added} new, {deleted} deleted, {updated_rows} field change(s) on existing rows"
          + (f" ({len(flagged_dupes)} duplicate_lat_lon row(s) carried through unchanged)" if len(flagged_dupes) else ""))

    if dry_run:
        print("[dry-run] pit_list: would write these changes; nothing written.")
        return

    # collided_local_rows are carried through unchanged, same as flagged_dupes -- excluded from
    # the diff does NOT mean deleted from the file.
    merged = pd.concat([local_keyed.reset_index(drop=True), flagged_dupes, collided_local_rows],
                       ignore_index=True)
    _atomic_write_csv(merged, PIT_LIST_FILE)
    print(f"pit_list saved -> {PIT_LIST_FILE}")


SYNC_FUNCS = {
    "registry": sync_registry,
    "projects": sync_projects,
    "bid-results": sync_bid_results,
    "pit-list": sync_pit_list,
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check-only", action="store_true",
                        help="fast staleness check only, exit 0=fresh 1=stale, writes nothing")
    parser.add_argument("--all", action="store_true", help="sync all four tables")
    parser.add_argument("--registry", action="store_true")
    parser.add_argument("--projects", action="store_true")
    parser.add_argument("--bid-results", action="store_true")
    parser.add_argument("--pit-list", action="store_true")
    parser.add_argument("--dry-run", action="store_true", help="print the diff, write nothing")
    args = parser.parse_args()

    if args.check_only:
        sys.exit(check_only())

    tables = []
    if args.all:
        tables = ["registry", "projects", "bid-results", "pit-list"]
    else:
        if args.registry:
            tables.append("registry")
        if args.projects:
            tables.append("projects")
        if args.bid_results:
            tables.append("bid-results")
        if args.pit_list:
            tables.append("pit-list")
    if not tables:
        raise SystemExit("pass --all, or one or more of --registry/--projects/--bid-results/--pit-list")

    failed = []
    with connect() as conn:
        for table in tables:
            # One table's failure must not block the others -- before this isolation existed, a
            # single duplicate pit-list key killed the whole pull, so admin-UI bid results and
            # registry edits silently never reached local data either (2026-08-09).
            try:
                SYNC_FUNCS[table](conn, args.dry_run)
            except Exception as e:                        # noqa: BLE001 -- degrade per-table, loudly
                failed.append(table)
                print(f"ERROR: {table} sync failed ({type(e).__name__}: {e}) -- continuing with "
                      "the remaining tables.", file=sys.stderr)

        if not args.dry_run and not failed:
            # A failed table means its rows are still stale -- leave the freshness stamp alone so
            # the next --check-only run reports stale and retries, instead of marking a partial
            # sync as fresh.
            remote_max = remote_max_updated_at(conn)
            if remote_max is not None:
                _save_state(remote_max)
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
