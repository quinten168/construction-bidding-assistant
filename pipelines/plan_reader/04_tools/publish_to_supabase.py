#!/usr/bin/env python3
"""
Publish the small structured tables from the local csi_v2.db to a hosted Postgres (Supabase),
so the team can read extracted plan data over a connection string instead of needing the
160 MB SQLite file on their own laptop.

This is a PUBLISH, not a migration.
  - Nothing moves. The operational store stays local SQLite and stays authoritative.
  - Nothing is deleted.
  - Per 00_master_plan.md section 4, Supabase is a published analytical snapshot.

  ⚠️ CORRECTED 2026-08-07. This block used to say "The app does not read Supabase. Do not repoint
  it here." THAT IS NO LONGER TRUE, and it is the kind of false that stops someone republishing
  when they need to. P0-B repointed the backend: `apps/api/backend/final_report.py` queries
  `public.gotchas` and `public.plans` through `backend/ci_db.py` (see `:106`, `:147`, `:448`), and
  `config.py::corpus_state` reads Postgres too. **A change to the local SQLite corpus does not
  reach the app until this publisher runs.**

  Note the split, because it is not uniform and it surprised someone already: the report's GOTCHAS
  come from Postgres (so a republish changes them), but the report's QUANTITIES come from the
  content-hashed payload cache in `00_input/_report_payload_cache/`, written at PDF-drop time
  (`final_report.py:312`). Republishing does NOT change quantities on an already-cached plan.
  Retiring that cache is tracked as the cache-to-DB migration.

Five tables are published:  plans, materials, plan_metrics, gotchas, location_intelligence.

Deliberately excluded:
  - `sections` (37,261 rows). It is bulk chunk text and it is RAG fodder. The Chroma store holds
    chunk text AND embeddings, so retrieval never reads this table, and publishing it would hand
    the team text with no embeddings. Hosted vector search is tracked separately as issue #22.
  - `plans.full_markdown` (75.3 MB of the 78.1 MB total, single cells up to 4.68 MB). Excluded
    because it is ~97% of the payload, and for no other reason.

    CORRECTED 2026-08-03. This block used to say full_markdown "lives in the vector store". THAT
    IS FALSE, and it is the kind of false that gets a file deleted. Chroma holds CHUNKS: s2_indexer
    splits with overlap, strips boilerplate paragraphs and drops DROP-sections before indexing (one
    plan alone: 50 DROP-section chunks dropped, 699 boilerplate paragraphs stripped). The vector
    store's text is derived and LOSSY and cannot reconstitute full_markdown. The same caveat applies
    to `sections`.

    So exclusion here is a payload-size decision, NOT a statement that the data is safe elsewhere.
    csi_v2.db is the ONLY copy of both. See docs/DATA_ACCESS.md and #50 before treating either as
    redundant.

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

# The role this publisher MUST connect as. See the pre-flight check in publish() for why:
# ALTER DEFAULT PRIVILEGES is scoped per creating-role, so publishing as anyone else
# silently strips csi_reader's access on every republish.
EXPECTED_PUBLISH_ROLE = "postgres"

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

def find_dependent_objects(cur) -> list[tuple[str, str, str, str]]:
    """Views and materialized views that depend on a table this publish is about to drop.

    `drop table ... cascade` follows dependencies ACROSS SCHEMA BOUNDARIES. A view sitting in the
    team's `scratch` schema that selects from `public.plans` is dropped along with `plans`, even
    though the publisher never names `scratch`. The team's *tables* are safe from us; their
    *views* are not. Nothing warns them, and the object is simply gone next time they look.

    Returns (schema, name, kind, owner) per dependent object, ordered for stable output.
    """
    cur.execute("""
        select distinct dn.nspname, dc.relname, dc.relkind, pg_get_userbyid(dc.relowner)
        from pg_depend d
        join pg_rewrite rw   on rw.oid = d.objid
        join pg_class dc     on dc.oid = rw.ev_class
        join pg_namespace dn on dn.oid = dc.relnamespace
        join pg_class sc     on sc.oid = d.refobjid
        join pg_namespace sn on sn.oid = sc.relnamespace
        where d.classid = 'pg_rewrite'::regclass
          and sn.nspname = 'public'
          and sc.relname = any(%s)
          and dc.relkind in ('v', 'm')
          and dc.oid <> sc.oid
        order by 1, 2
    """, (PUBLISH_TABLES,))
    return cur.fetchall()


def handle_dependents(dependents: list[tuple[str, str, str, str]], force: bool) -> bool:
    """Decide what a publish does when it would destroy someone else's view.

    Called after the dependency scan and before any table is dropped. Returns True to continue,
    False to abort cleanly — nothing has been written at that point, so aborting is free and
    leaves the previous snapshot fully intact.

    Policy, chosen by T on 2026-07-27: refuse by default, allow `--force` to override.

    Refusing by default means nobody's work disappears without a person deciding it should.
    Allowing an override means one forgotten view cannot wedge the refresh permanently, which
    matters because publishing is the only way the team gets current data — and the person a
    hard block would strand is whoever runs this, not whoever left the view behind.

    The alternative of warning and continuing was rejected: a warning that scrolls past in a
    terminal is indistinguishable from silence, and silent failure is this repo's recurring
    wound (CLAUDE.md rough edge 2).
    """
    if force:
        print(f"\n--force given: proceeding anyway. {len(dependents)} object(s) will be "
              f"destroyed and are NOT recoverable from here.")
        return True
    print("\nRefusing to publish, because doing so would destroy the objects listed above.")
    print("Pick one:")
    print("  - ask their owners to re-create them as tables (`create table ... as select ...`),")
    print("    which survives a publish, then re-run;")
    print("  - or re-run with --force if you know they are disposable.")
    return False


def publish(dsn: str, payload: dict, ddl: dict, force: bool = False) -> bool:
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
            # Pre-flight 0: WHO ARE WE CONNECTED AS?
            #
            # This publisher drops and recreates every table (`drop table ... cascade` below), and
            # table-level GRANTs do not survive a DROP -- they are attributes of the object. What
            # keeps csi_reader's access alive across a republish is the DEFAULT PRIVILEGES installed
            # by 04_tools/team_access.sql, and those are scoped to tables created BY THE `postgres`
            # ROLE:
            #
            #     pg_default_acl: schema=public owner=postgres objtype=r
            #                     -> csi_reader=r/postgres, csi_team=r/postgres
            #
            # Connect as any other role and the new tables inherit NOTHING. The publish succeeds,
            # the data is correct, and every teammate silently loses read access until someone
            # re-runs the grants by hand. That is exactly the failure this repo keeps producing:
            # a success that is really a failure, discovered days later by someone else.
            #
            # So: fail here, loudly, before the first drop.
            cur.execute("select current_user")
            current_role = cur.fetchone()[0]
            if current_role != EXPECTED_PUBLISH_ROLE:
                raise SystemExit(
                    f"\nERROR: connected as '{current_role}', expected "
                    f"'{EXPECTED_PUBLISH_ROLE}'.\n"
                    f"  This publisher drops and recreates every table. GRANTs do not survive a\n"
                    f"  DROP; access is restored by the ALTER DEFAULT PRIVILEGES that are scoped to\n"
                    f"  tables created by '{EXPECTED_PUBLISH_ROLE}'. Publishing as '{current_role}'\n"
                    f"  would silently strip csi_reader's SELECT on every table.\n"
                    f"  Fix: point SUPABASE_DB_URL at the {EXPECTED_PUBLISH_ROLE} login, or extend\n"
                    f"  the default privileges to '{current_role}' first (see 04_tools/team_access.sql\n"
                    f"  and docs/DATA_ACCESS.md)."
                )

            # Pre-flight: would this publish destroy anyone's work? Checked before the first
            # drop, so aborting here costs nothing and leaves the previous snapshot whole.
            #
            # `handle_dependents` is only consulted when there is something to lose. With no
            # dependent views — the state today — this is a no-op and the publisher behaves
            # exactly as it always has. The unimplemented policy therefore cannot break a
            # publish now; it forces the decision at the moment it first has consequences.
            dependents = find_dependent_objects(cur)
            if dependents:
                print(f"\nWARNING: {len(dependents)} object(s) depend on tables about to be "
                      f"dropped. `cascade` will destroy them:")
                for schema, name, kind, owner in dependents:
                    label = "matview" if kind == "m" else "view"
                    print(f"    {schema}.{name}  ({label}, owner {owner})")
                if not handle_dependents(dependents, force):
                    print("\nPublish aborted. Nothing was written; the previous snapshot is intact.")
                    return False

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
    return True


# --- main ---------------------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description="Publish structured csi_v2.db tables to Supabase.")
    ap.add_argument("--dry-run", action="store_true",
                    help="Read SQLite, build the payload and DDL, report sizes, write nothing. "
                         "Does not require SUPABASE_DB_URL.")
    ap.add_argument("--force", action="store_true",
                    help="Publish even when it would destroy views that depend on the published "
                         "tables. Without this, such a publish is refused. The destroyed objects "
                         "are not recoverable, so read the list before using it.")
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
        # Exit non-zero on a refusal. A scheduled or scripted caller must be able to tell
        # "published successfully" apart from "declined to publish", and both print plenty of
        # text — the exit status is the only part a cron job actually reads.
        return 0 if publish(dsn, payload, ddl, force=args.force) else 1
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
