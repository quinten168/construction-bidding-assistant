#!/usr/bin/env python3
"""
Phase 1 of the Postgres migration (docs/2026-07-27_postgres_migration_plan.md): find every value
in csi_v2.db that Postgres would refuse to accept.

This is a READ-ONLY audit. It opens the source read-only, writes nothing anywhere, and makes no
network calls. Run it as often as you like.

WHY THIS EXISTS
---------------
SQLite does not enforce declared column types. A column declared REAL will happily store the
string "Y" forever, and nothing complains. Postgres enforces types on every row, so the moment
those values are copied across, the load fails — in bulk, at the worst time, with an error that
names one row out of thousands.

Two instances are already known and both were found by accident:
  - `section_intelligence.low_sample_flag` is declared REAL and stores "Y"/"". This is why that
    table is still held out of the publish (publish_to_supabase.py:53-55).
  - Empty strings in numeric columns, which `publish_to_supabase.py:180` works around by
    coercing "" to NULL for every non-text column.

Two found in the 8 tables anyone has examined closely. The other 4 tables, and the 75.8 MB of
document text in `plans.full_markdown`, have never been checked at all. This finds the rest
before the migration does.

WHAT IT CHECKS
--------------
  1. Storage-class violations — a value whose SQLite storage class cannot become the mapped
     Postgres type (text in a bigint column, etc). These are hard failures.
  2. Empty strings in non-text columns — the known workaround case. Survivable (the publisher
     already coerces) but each one is a column whose declared type is a lie.
  3. Embedded NUL bytes in text — Postgres `text` cannot contain \\x00 at all, and COPY rejects
     the row outright. Converted PDF text is exactly where these come from, so the columns most
     at risk are the ones never yet published.
  4. Non-integral values in integer columns — 1.5 in a bigint column.
  5. NULLs in primary-key columns — SQLite permits NULL in a PRIMARY KEY unless the column is
     INTEGER PRIMARY KEY or explicitly NOT NULL. Postgres never does.
  6. Duplicate primary keys — same reason; SQLite's leniency around PKs it did not make a
     rowid alias for.
  7. Unparseable timestamps in date/datetime columns.

Usage
-----
    export CSI_V2_DB='/path/to/csi_v2.db'
    python audit_types_for_postgres.py             # all tables
    python audit_types_for_postgres.py --table plans
    python audit_types_for_postgres.py --skip-text-scan   # faster; skips the 75.8 MB NUL scan
"""
from __future__ import annotations

import argparse
import os
import sqlite3
import sys
import urllib.parse
from pathlib import Path

# Mirrors publish_to_supabase.py. Kept as a copy rather than an import because `04_tools` is not
# a package and CLAUDE.md invariant 2 says the numbered directories must stay unimportable.
_TYPE_MAP = [
    ("INT", "bigint"), ("CHAR", "text"), ("CLOB", "text"), ("TEXT", "text"),
    ("BLOB", "bytea"), ("REAL", "double precision"), ("FLOA", "double precision"),
    ("DOUB", "double precision"), ("DATETIME", "timestamptz"), ("DATE", "timestamptz"),
]

# Storage classes SQLite may return from typeof(), and which of them can legally become each
# mapped Postgres type. 'null' is always allowed (unless the column is a primary key).
COMPATIBLE = {
    "bigint":           {"integer"},
    "double precision": {"integer", "real"},
    "text":             {"text", "integer", "real"},   # numbers stringify losslessly enough
    "bytea":            {"blob", "text"},
    "timestamptz":      {"text", "integer"},           # ISO strings or epochs; validated below
}

BLOCKING = "BLOCKING"     # migration fails here
ADVISORY = "advisory"     # survivable, but the declared type is wrong


def pg_type(decl: str) -> str:
    d = (decl or "").upper()
    if d.startswith("DATE"):
        return "timestamptz"
    for prefix, pg in _TYPE_MAP:
        if prefix in d:
            return pg
    return "text"


def connect_source(db_path: Path) -> sqlite3.Connection:
    """Open strictly read-only, preferring the mode that respects the write-ahead log.

    `publish_to_supabase.py` uses `immutable=1`, and documents as its precondition that no `-wal`
    or `-shm` sidecars exist. As of 2026-07-27 they DO exist (`-shm` is 32 KB), so that
    precondition is no longer literally true. `immutable=1` tells SQLite the file cannot change
    and lets it skip the WAL entirely — which is fast and guarantees zero writes, but would
    silently miss any committed-but-not-checkpointed data.

    So try `mode=ro` first: it reads the WAL and cannot write. Fall back to `immutable=1` only if
    the shared-memory file cannot be opened, and say so out loud when that happens, because it
    changes what the answer means.
    """
    if not db_path.exists():
        raise SystemExit(f"ERROR: source database not found: {db_path}\n"
                         f"Set CSI_V2_DB to the csi_v2.db location.")
    quoted = "file:" + urllib.parse.quote(str(db_path))
    try:
        con = sqlite3.connect(f"{quoted}?mode=ro", uri=True)
        con.execute("select count(*) from sqlite_master").fetchone()
        print("  opened read-only (mode=ro; write-ahead log honoured)")
    except sqlite3.OperationalError as e:
        con = sqlite3.connect(f"{quoted}?immutable=1", uri=True)
        print(f"  opened read-only (immutable=1; mode=ro failed: {e})")
        print("  NOTE: immutable=1 ignores the -wal file. Any committed-but-uncheckpointed")
        print("        rows are invisible to this audit.")
    con.row_factory = sqlite3.Row
    return con


def all_tables(con: sqlite3.Connection) -> list[str]:
    return [r[0] for r in con.execute(
        "select name from sqlite_master where type='table' "
        "and name not like 'sqlite_%' order by name")]


def columns(con: sqlite3.Connection, table: str) -> list[sqlite3.Row]:
    return list(con.execute(f"PRAGMA table_info({table})"))


def scan_primary_key(con: sqlite3.Connection,
                     table: str, cols: list[sqlite3.Row]) -> list[tuple[str, str, int, str]]:
    """Check the primary key as a whole, which is the only way it is meaningful.

    A composite key (`material_crosswalk` keys on normalized_description + state) is one
    constraint over a tuple. Duplicates within a single member column are completely legal —
    'MOBILIZATION' appears once per state and that is the point. Checking members individually
    reports 132 fake violations on this database, so do not do it.

    SQLite also permits NULL in a PRIMARY KEY unless the column is an INTEGER PRIMARY KEY rowid
    alias or explicitly NOT NULL. Postgres never permits it, in any key column.
    """
    pk = [c for c in cols if c["pk"]]
    if not pk:
        return []
    pk.sort(key=lambda c: c["pk"])          # pk is the 1-based position within the key
    names = [c["name"] for c in pk]
    quoted = ", ".join(f'"{n}"' for n in names)
    label = " + ".join(names)
    qt = f'"{table}"'
    out: list[tuple[str, str, int, str]] = []

    for c in pk:
        if c["notnull"]:
            continue
        n = con.execute(f'select count(*) from {qt} where "{c["name"]}" is null').fetchone()[0]
        if n:
            out.append((BLOCKING, f"NULL in key column {c['name']} (key: {label})", n, "NULL"))

    dupes = con.execute(
        f"select count(*) from (select {quoted} from {qt} group by {quoted} having count(*) > 1)"
    ).fetchone()[0]
    if dupes:
        ex = con.execute(
            f"select {quoted} from {qt} group by {quoted} having count(*) > 1 limit 1").fetchone()
        out.append((BLOCKING, f"duplicate primary key ({label})", dupes,
                    repr(tuple(ex))[:60]))
    return out


def scan_column(con: sqlite3.Connection, table: str, col: str, decl: str,
                skip_text_scan: bool) -> list[tuple[str, str, int, str]]:
    """Return (severity, issue, count, example) for one column. Empty list means clean."""
    pg = pg_type(decl)
    ok = COMPATIBLE[pg]
    found: list[tuple[str, str, int, str]] = []
    qc, qt = f'"{col}"', f'"{table}"'

    classes = {r[0]: r[1] for r in con.execute(
        f"select typeof({qc}), count(*) from {qt} group by 1")}

    # 1 & 2. storage classes that cannot become the mapped type.
    #
    # Empty strings are split out rather than counted as hard failures: publish_to_supabase.py:180
    # already coerces "" to NULL for every non-text column, so they load fine. They still mean the
    # declared type is a lie, so they are reported — just not as blockers. A column whose only
    # offending values are empty strings needs no migration work at all, and saying otherwise
    # sends someone chasing a non-problem.
    for cls, n in classes.items():
        if cls == "null" or cls in ok:
            continue
        if cls == "text" and pg != "text":
            empties = con.execute(
                f"select count(*) from {qt} where typeof({qc})='text' and trim({qc})=''"
            ).fetchone()[0]
            if empties:
                found.append((ADVISORY,
                              f"empty string in a {pg} column (publisher coerces to NULL)",
                              empties, "''"))
            real = n - empties
            if real:
                ex = con.execute(
                    f"select {qc} from {qt} where typeof({qc})='text' and trim({qc}) <> '' limit 1"
                ).fetchone()
                found.append((BLOCKING, f"non-empty text in a {pg} column", real,
                              repr(ex[0])[:60]))
            continue
        ex = con.execute(
            f"select {qc} from {qt} where typeof({qc}) = ? limit 1", (cls,)).fetchone()
        found.append((BLOCKING, f"{cls} value in a {pg} column", n, repr(ex[0])[:60]))

    # 3. non-integral floats in an integer column
    if pg == "bigint" and classes.get("real"):
        n = con.execute(
            f"select count(*) from {qt} where typeof({qc})='real' and {qc} <> cast({qc} as integer)"
        ).fetchone()[0]
        if n:
            ex = con.execute(
                f"select {qc} from {qt} where typeof({qc})='real' "
                f"and {qc} <> cast({qc} as integer) limit 1").fetchone()
            found.append((BLOCKING, "fractional value in a bigint column", n, repr(ex[0])[:60]))

    # 4. embedded NUL bytes — Postgres text cannot hold \x00 and COPY rejects the row.
    #    Compared as BLOB because SQLite's own text functions truncate at the first NUL.
    if pg == "text" and classes.get("text") and not skip_text_scan:
        n = con.execute(
            f"select count(*) from {qt} where typeof({qc})='text' "
            f"and instr(cast({qc} as blob), x'00') > 0").fetchone()[0]
        if n:
            found.append((BLOCKING, "embedded NUL byte (\\x00) in text", n, "<binary>"))

    # timestamps Postgres cannot parse
    if pg == "timestamptz" and classes.get("text"):
        n = con.execute(
            f"select count(*) from {qt} where typeof({qc})='text' "
            f"and trim({qc}) <> '' and date({qc}) is null").fetchone()[0]
        if n:
            ex = con.execute(
                f"select {qc} from {qt} where typeof({qc})='text' and trim({qc}) <> '' "
                f"and date({qc}) is null limit 1").fetchone()
            found.append((BLOCKING, "unparseable value in a timestamptz column", n,
                          repr(ex[0])[:60]))

    return found


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Read-only audit: find values Postgres would reject. Writes nothing.")
    ap.add_argument("--table", action="append",
                    help="Audit only this table. Repeatable. Default: every table.")
    ap.add_argument("--skip-text-scan", action="store_true",
                    help="Skip the embedded-NUL scan over text columns. Much faster, but "
                         "plans.full_markdown (75.8 MB) is exactly where NULs would hide.")
    args = ap.parse_args()

    src = os.environ.get("CSI_V2_DB", "").strip()
    if not src:
        print("ERROR: CSI_V2_DB is not set (absolute path to csi_v2.db).", file=sys.stderr)
        return 2
    db_path = Path(src).expanduser()

    print("=" * 88)
    print("audit_types_for_postgres  ::  READ-ONLY")
    print("=" * 88)
    print(f"source : {db_path}")
    con = connect_source(db_path)

    try:
        tables = args.table or all_tables(con)
        missing = [t for t in tables if t not in set(all_tables(con))]
        if missing:
            print(f"ERROR: no such table(s): {', '.join(missing)}", file=sys.stderr)
            return 2
        if args.skip_text_scan:
            print("  --skip-text-scan: embedded-NUL detection is DISABLED")
        print(f"  auditing {len(tables)} table(s)\n")

        blocking, advisory, clean = [], [], []
        for t in tables:
            rows = con.execute(f'select count(*) from "{t}"').fetchone()[0]
            cols = columns(con, t)
            print(f"{t}  ({rows:,} rows, {len(cols)} columns)")
            issues_here = 0

            def report(label: str, findings: list[tuple[str, str, int, str]], detail: str) -> None:
                nonlocal issues_here
                for sev, issue, n, example in findings:
                    issues_here += 1
                    tag = ("\033[31mBLOCKING\033[0m" if sev == BLOCKING
                           else "\033[33madvisory\033[0m")
                    print(f"    {tag}  {label} ({detail})")
                    print(f"              {issue}: {n:,} row(s), e.g. {example}")
                    (blocking if sev == BLOCKING else advisory).append((t, label, issue, n))

            # The key is checked once, as a whole. Checking its member columns separately treats
            # a composite key as several single-column keys and invents violations that are not
            # real -- on this database that alone produced 137 phantom findings.
            report("<primary key>", scan_primary_key(con, t, cols), "table constraint")
            for c in cols:
                report(c["name"],
                       scan_column(con, t, c["name"], c["type"], args.skip_text_scan),
                       f"{c['type'] or 'untyped'} -> {pg_type(c['type'])}")
            if issues_here == 0:
                print("    clean")
                clean.append(t)
            print()

        print("=" * 88)
        print("SUMMARY")
        print("=" * 88)
        print(f"  tables audited      : {len(tables)}")
        print(f"  tables clean        : {len(clean)}")
        print(f"  BLOCKING issues     : {len(blocking)}   (migration fails on these)")
        print(f"  advisory issues     : {len(advisory)}   (survivable; declared type is wrong)")
        if blocking:
            print("\n  Fix these at the SQLite source while it is still authoritative:")
            for t, c, issue, n in blocking:
                print(f"    {t}.{c:28s} {issue} ({n:,})")
        if not blocking and not advisory:
            print("\n  No type violations found. The schema is Postgres-clean.")
        print("\n" + "=" * 88)
        print("Audit complete. Nothing was written; the source is unmodified.")
        print("=" * 88)
        return 1 if blocking else 0
    finally:
        con.close()


if __name__ == "__main__":
    raise SystemExit(main())
