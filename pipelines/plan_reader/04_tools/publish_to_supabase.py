#!/usr/bin/env python3
"""
Publish the small structured tables from the local csi_v2.db to a hosted Postgres (Supabase),
so the team can read extracted plan data over a connection string instead of needing the
160 MB SQLite file on their own laptop.

This is a PUBLISH, not a migration.
  - Nothing moves. The operational store stays local SQLite and stays authoritative.
  - Nothing is deleted.
  - The app does not read Supabase. Do not repoint it here.
  - Per 00_master_plan.md section 4, Supabase is a published analytical snapshot.

Five tables are published:  plans, materials, plan_metrics, gotchas, location_intelligence.

Deliberately excluded:
  - `sections` (37,261 rows). It is bulk chunk text and it is RAG fodder. Note that the Chroma
    store is self-contained: it holds the chunk text AND the embeddings, so retrieval never
    reads this table. Publishing `sections` would hand the team text with no embeddings, which
    is not RAG, just a large bill. Hosted vector search is tracked separately as issue #22.
  - `plans.full_markdown` (75.8 MB of the 78.1 MB total, single cells up to 4.7 MB). Same
    reasoning: it is the whole converted document, it lives in the vector store, and it is
    the entire reason this publish would otherwise be too large to be useful.

Usage
-----
    # dry run: reads SQLite, builds the payload, prints the DDL and the sizes, writes nothing.
    # works with SUPABASE_DB_URL unset.
    python publish_to_supabase.py --dry-run

    # real publish
    export SUPABASE_DB_URL='postgresql://...'
    export CSI_V2_DB='/path/to/csi_v2.db'
    python publish_to_supabase.py

Configuration is environment-only. No paths and no credentials are baked in or committed.
  CSI_V2_DB        absolute path to the source SQLite file (required)
  SUPABASE_DB_URL  Postgres DSN (required only for a real publish, not for --dry-run)
"""
from __future__ import annotations

import argparse
import os
import sqlite3
import sys
import urllib.parse
from pathlib import Path

# --- what we publish ----------------------------------------------------------------------------

PUBLISH_TABLES = ["plans", "materials", "plan_metrics", "gotchas", "location_intelligence",
                  # reference/lookup tables: small, static, refreshed from local on every publish.
                  "material_crosswalk", "bucket_hierarchy", "section_taxonomy"]
# section_intelligence is held out: its `low_sample_flag` column is declared REAL in csi_v2.db
# but stores boolean text ("Y" / ""), so Postgres rejects it. Retype the source column, then
# add it back here.

# Columns dropped from the publish because they carry bulk document text. Keyed by table.
# `plans.full_markdown` is 97% of the payload on its own.
EXCLUDE_COLUMNS = {
    "plans": {"full_markdown"},
}

# Abort rather than upload if the assembled payload exceeds this. Expected is roughly 2 to 4 MB.
# A blown guard almost certainly means a bulk-text column slipped through, which is the specific
# failure this exists to catch. It is a guard, not a tuning knob.
MAX_PAYLOAD_BYTES = 10 * 1024 * 1024

# SQLite is dynamically typed and its declared types are advisory, so map the declared type by
# prefix (the same rule SQLite's own type-affinity uses) rather than by exact string.
_TYPE_MAP = [
    ("INT", "bigint"),
    ("CHAR", "text"),
    ("CLOB", "text"),
    ("TEXT", "text"),
    ("BLOB", "bytea"),
    ("REAL", "double precision"),
    ("FLOA", "double precision"),
    ("DOUB", "double precision"),
    ("DATETIME", "timestamptz"),
    ("DATE", "timestamptz"),
]


def pg_type(sqlite_decl: str) -> str:
    """Map a SQLite declared type to a Postgres type. Unknown or empty declarations become text,
    which matches SQLite's own fallback to BLOB/TEXT affinity and never loses data."""
    d = (sqlite_decl or "").upper()
    if d.startswith("DATE"):                 # check before INT so DATETIME does not match nothing
        return "timestamptz"
    for prefix, pg in _TYPE_MAP:
        if prefix in d:
            return pg
    return "text"


# --- source access ------------------------------------------------------------------------------

def connect_source(db_path: Path) -> sqlite3.Connection:
    """Open the source strictly read-only.

    The canonical csi_v2.db sits in iCloud Drive and that copy is currently its only backup, so
    this process must not be able to write to it, checkpoint it, or touch its WAL.

    We use `immutable=1` rather than `mode=ro`. The file's header records journal_mode=WAL
    (write/read version byte 2). Opening a WAL database requires SQLite to create the `-shm`
    shared-memory file, which `mode=ro` forbids, so `mode=ro` fails outright with
    "unable to open database file". `immutable=1` promises SQLite the file will not change
    underneath us, which lets it skip the `-shm` entirely and guarantees zero writes.

    The precondition for `immutable=1` is that nothing else is writing the file during the read.
    That holds here: this is an offline publish over a curated corpus, and there are no `-wal`
    or `-shm` sidecars present, so the last writer checkpointed cleanly. Do not run this while
    an extraction pipeline is mid-write.
    """
    if not db_path.exists():
        raise SystemExit(f"ERROR: source database not found: {db_path}\n"
                         f"Set CSI_V2_DB to the csi_v2.db location.")
    uri = "file:" + urllib.parse.quote(str(db_path)) + "?immutable=1"
    con = sqlite3.connect(uri, uri=True)
    con.row_factory = sqlite3.Row
    return con


def table_columns(con: sqlite3.Connection, table: str) -> list[tuple[str, str, bool]]:
    """(name, declared_type, is_pk) for each column we publish, in table order."""
    dropped = EXCLUDE_COLUMNS.get(table, set())
    cols = []
    for r in con.execute(f"PRAGMA table_info({table})"):
        if r["name"] in dropped:
            continue
        cols.append((r["name"], r["type"], bool(r["pk"])))
    if not cols:
        raise SystemExit(f"ERROR: table {table} has no publishable columns.")
    return cols


def verify_schema(con: sqlite3.Connection) -> None:
    """Fail before doing any work if the source is not shaped the way this script expects."""
    present = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    missing = [t for t in PUBLISH_TABLES if t not in present]
    if missing:
        raise SystemExit(f"ERROR: source database is missing expected table(s): {', '.join(missing)}\n"
                         f"Refusing to publish a partial snapshot.")


# --- DDL ----------------------------------------------------------------------------------------

def build_ddl(con: sqlite3.Connection, table: str) -> str:
    """Postgres CREATE TABLE for one published table.

    AUTOINCREMENT surrogate keys become plain `bigint primary key`, not `bigserial`: we are
    copying existing ids verbatim, and a sequence-backed column on a replicated snapshot would
    be a sequence nobody should ever draw from.
    """
    cols = table_columns(con, table)
    lines = [f'  "{name}" {pg_type(decl)}' for name, decl, _ in cols]
    # Emit the primary key as one table-level constraint, not inline per column, so composite
    # keys (e.g. material_crosswalk on normalized_description + state) are valid Postgres.
    # For a single-key table this is identical to the old inline form.
    pk_cols = [name for name, _, is_pk in cols if is_pk]
    if pk_cols:
        lines.append("  primary key (" + ", ".join(f'"{c}"' for c in pk_cols) + ")")
    return f'create table "{table}" (\n' + ",\n".join(lines) + "\n);"


# --- payload ------------------------------------------------------------------------------------

def read_table(con: sqlite3.Connection, table: str) -> tuple[list[str], list[tuple], int]:
    """Return (column names, rows, approximate payload bytes) for one table.

    The byte figure is the sum of the octet length of every published cell, measured in SQL so
    we do not have to materialize the table twice. It is what actually crosses the wire, modulo
    protocol framing, and it is what the size guard is checked against.
    """
    colinfo = table_columns(con, table)
    cols = [c[0] for c in colinfo]
    # SQLite is loosely typed: a column declared numeric can still hold "". Postgres COPY rejects
    # "" for a numeric/timestamp column, so coerce empty strings to NULL for every non-text column.
    # Text columns are left untouched, so a legitimately empty string stays "".
    coerce = {i for i, (_, decl, _) in enumerate(colinfo) if pg_type(decl) != "text"}
    quoted = ", ".join(f'"{c}"' for c in cols)
    size_expr = " + ".join(f'COALESCE(LENGTH(CAST("{c}" AS BLOB)), 0)' for c in cols)
    nbytes = con.execute(f'SELECT COALESCE(SUM({size_expr}), 0) FROM "{table}"').fetchone()[0]
    rows = [
        tuple(None if i in coerce and isinstance(v, str) and v.strip() == "" else v
              for i, v in enumerate(r))
        for r in con.execute(f'SELECT {quoted} FROM "{table}"')
    ]
    return cols, rows, int(nbytes)


def human(n: int) -> str:
    return f"{n / (1024 * 1024):.2f} MB" if n >= 1024 * 1024 else f"{n / 1024:.1f} KB"


# --- publish ------------------------------------------------------------------------------------

def publish(dsn: str, payload: dict, ddl: dict) -> None:
    """Replace all five tables inside ONE transaction.

    Idempotency strategy: full table replacement (drop, create, bulk insert), not upsert.

    Three of the five tables (materials, gotchas, location_intelligence) key on
    `INTEGER PRIMARY KEY AUTOINCREMENT`. That id is a surrogate assigned at insert time by the
    extraction pipeline; it is not a stable identity for the underlying fact. Re-running an
    extraction renumbers rows, so an upsert on id would merge unrelated records and quietly
    corrupt the snapshot. There is no natural key on those tables to upsert against
    (`gotchas` has no unique constraint over plan_id + flag_type + page, and genuinely has
    repeats). Replacement is the only strategy that is correct for all five tables, and it is
    the honest one for a snapshot: what lands is exactly what the source says right now, with
    no residue from a previous run.

    The whole thing runs in a single transaction so a reader either sees the entire previous
    snapshot or the entire new one, never a half-dropped mixture, and so a mid-publish failure
    rolls back rather than leaving the team with empty tables.
    """
    try:
        import psycopg
    except ImportError:
        raise SystemExit("ERROR: psycopg (v3) is required for a real publish.\n"
                         "  pip install 'psycopg[binary]'\n"
                         "Use --dry-run if you only want to inspect the payload.")

    with psycopg.connect(dsn) as conn:
        with conn.cursor() as cur:
            for table in PUBLISH_TABLES:
                cols, rows = payload[table]
                cur.execute(f'drop table if exists "{table}" cascade;')
                cur.execute(ddl[table])
                if rows:
                    collist = ", ".join(f'"{c}"' for c in cols)
                    with cur.copy(f'copy "{table}" ({collist}) from stdin') as cp:
                        for r in rows:
                            cp.write_row(r)
                print(f"  published {table}: {len(rows):,} rows")
        conn.commit()
    print("\nPublish committed.")


# --- main ---------------------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description="Publish structured csi_v2.db tables to Supabase.")
    ap.add_argument("--dry-run", action="store_true",
                    help="Read SQLite, build the payload and DDL, report sizes, write nothing. "
                         "Does not require SUPABASE_DB_URL.")
    args = ap.parse_args()

    src = os.environ.get("CSI_V2_DB", "").strip()
    if not src:
        print("ERROR: CSI_V2_DB is not set. It must be the absolute path to csi_v2.db.",
              file=sys.stderr)
        return 2
    db_path = Path(src).expanduser()

    dsn = os.environ.get("SUPABASE_DB_URL", "").strip()
    if not args.dry_run and not dsn:
        print("ERROR: SUPABASE_DB_URL is not set. Set it, or pass --dry-run.", file=sys.stderr)
        return 2

    mode = "DRY RUN (nothing will be written)" if args.dry_run else "LIVE PUBLISH"
    print("=" * 78)
    print(f"publish_to_supabase  ::  {mode}")
    print("=" * 78)
    print(f"source : {db_path}")
    print(f"target : {'(none, dry run)' if args.dry_run else _redact(dsn)}")
    print()

    con = connect_source(db_path)
    try:
        verify_schema(con)

        payload, ddl, total = {}, {}, 0
        print("per-table:")
        print(f"  {'table':24s} {'rows':>9s} {'cols':>5s} {'bytes':>11s}")
        for t in PUBLISH_TABLES:
            cols, rows, nbytes = read_table(con, t)
            payload[t] = (cols, rows)
            ddl[t] = build_ddl(con, t)
            total += nbytes
            dropped = EXCLUDE_COLUMNS.get(t, set())
            note = f"   (dropped: {', '.join(sorted(dropped))})" if dropped else ""
            print(f"  {t:24s} {len(rows):>9,} {len(cols):>5d} {human(nbytes):>11s}{note}")

        skipped = con.execute("SELECT count(*) FROM sections").fetchone()[0]
        print(f"\n  excluded: sections ({skipped:,} rows), bulk chunk text, lives in Chroma "
              f"with its embeddings; see issue #22")
        print(f"\nTOTAL PAYLOAD: {human(total)}  (guard: {human(MAX_PAYLOAD_BYTES)})")

        if total > MAX_PAYLOAD_BYTES:
            print(f"\nABORT: payload {human(total)} exceeds the {human(MAX_PAYLOAD_BYTES)} guard.\n"
                  f"This almost always means a bulk-text column slipped into the publish.\n"
                  f"Check EXCLUDE_COLUMNS before raising the limit.", file=sys.stderr)
            return 1

        print("\n" + "=" * 78)
        print("generated Postgres DDL")
        print("=" * 78)
        for t in PUBLISH_TABLES:
            print(ddl[t])
            print()

        if args.dry_run:
            print("=" * 78)
            print("DRY RUN complete. Nothing was written to the network.")
            print("Source was opened read-only (immutable=1) and is unmodified.")
            print("=" * 78)
            return 0

        print("=" * 78)
        print("publishing (full table replacement, single transaction)")
        print("=" * 78)
        publish(dsn, payload, ddl)
        return 0
    finally:
        con.close()


def _redact(dsn: str) -> str:
    """Never print the password, even into a local terminal log."""
    try:
        p = urllib.parse.urlsplit(dsn)
        if p.password:
            netloc = f"{p.username}:***@{p.hostname}" + (f":{p.port}" if p.port else "")
            return urllib.parse.urlunsplit((p.scheme, netloc, p.path, "", ""))
    except ValueError:
        pass
    return "(set)"


if __name__ == "__main__":
    raise SystemExit(main())
