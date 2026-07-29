#!/usr/bin/env python3
"""Pull client corrections to the competitor name registry back from Supabase into the local CSV.

The push side (`data/push_supabase_bid_data.py --registry`) puts the registry in front of the
client so they can fill in `comp_name` for needs-review rows (blank `comp_name`, appended by
`data/update_name_registry.py`). This script reads their corrections back out.

Row existence stays locally authoritative -- this only overwrites comp_name / source /
top_competitors_tag / suggested_comp on raw_name_variant rows that already exist in the local CSV.
It never adds or removes rows: new raw names only ever get created locally, by
data/update_name_registry.py finding them in real bid data.

Usage:
    export SUPABASE_TEAM_DB_URL='postgresql://...'   # see data/.env.example / data/.env

    python data/pull_registry_corrections.py           # apply corrections
    python data/pull_registry_corrections.py --dry-run  # preview only, write nothing
"""
from __future__ import annotations

import argparse
import os

import pandas as pd
import psycopg

REGISTRY_FILE = (
    "pipelines/ci_model/01_candidates/outputs/"
    "competitor_name_registry - name_variants.csv"
)

REGISTRY_COLUMNS = ["raw_name_variant", "comp_name", "source", "top_competitors_tag", "suggested_comp"]
VALUE_COLUMNS = ["comp_name", "source", "top_competitors_tag", "suggested_comp"]


def connect() -> psycopg.Connection:
    dsn = os.environ.get("SUPABASE_TEAM_DB_URL")
    if not dsn:
        raise SystemExit("SUPABASE_TEAM_DB_URL is not set. export it (see data/.env.example).")
    return psycopg.connect(dsn)


def fetch_remote(conn: psycopg.Connection) -> pd.DataFrame:
    with conn.cursor() as cur:
        cur.execute(
            "select raw_name_variant, comp_name, source, top_competitors_tag, suggested_comp "
            "from scratch.competitor_name_registry"
        )
        rows = cur.fetchall()
    return pd.DataFrame(rows, columns=REGISTRY_COLUMNS)


def _norm(value) -> str:
    return "" if pd.isna(value) else str(value).strip()


def merge_corrections(local: pd.DataFrame, remote: pd.DataFrame) -> tuple[pd.DataFrame, list[dict]]:
    """Overwrite VALUE_COLUMNS on local rows whose raw_name_variant exists in remote and differs.
    Returns (updated_local, list_of_changes). Rows only in remote are reported, not merged in."""
    local = local.copy()
    remote_by_key = remote.set_index("raw_name_variant")

    remote_only = set(remote["raw_name_variant"]) - set(local["raw_name_variant"])
    if remote_only:
        print(f"[warn] {len(remote_only)} raw_name_variant row(s) exist in Supabase but not "
              f"locally -- not merged in (row existence stays locally authoritative):")
        for key in sorted(remote_only)[:20]:
            print(f"    {key}")

    changes: list[dict] = []
    for idx, row in local.iterrows():
        key = row["raw_name_variant"]
        if key not in remote_by_key.index:
            continue
        remote_row = remote_by_key.loc[key]
        changed_cols: dict[str, tuple] = {}
        for col in VALUE_COLUMNS:
            local_val, remote_val = row.get(col), remote_row.get(col)
            if _norm(local_val) != _norm(remote_val):
                changed_cols[col] = (local_val, remote_val)
                local.at[idx, col] = remote_val
        if changed_cols:
            changes.append({"raw_name_variant": key, "cols": changed_cols})

    return local, changes


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--registry", default=REGISTRY_FILE, help="path to the local registry CSV")
    parser.add_argument("--dry-run", action="store_true", help="print the diff, write nothing")
    args = parser.parse_args()

    local = pd.read_csv(args.registry, dtype=str)
    local = local.rename(columns={"Top Competitors Tag": "top_competitors_tag"})

    with connect() as conn:
        remote = fetch_remote(conn)

    updated, changes = merge_corrections(local, remote)

    if not changes:
        print("No corrections found -- local registry already matches Supabase.")
        return

    print(f"{len(changes)} row(s) corrected:")
    for change in changes:
        key = change["raw_name_variant"]
        for col, (old, new) in change["cols"].items():
            old_disp = _norm(old) or "(blank)"
            new_disp = _norm(new) or "(blank)"
            print(f"  {key} [{col}]: {old_disp} -> {new_disp}")

    if args.dry_run:
        print("[dry-run] would write these changes; nothing written.")
        return

    updated = updated.rename(columns={"top_competitors_tag": "Top Competitors Tag"})
    updated.to_csv(args.registry, index=False)
    print(f"Registry saved -> {args.registry}")


if __name__ == "__main__":
    main()
