"""Connect to the client's Supabase database and pull data into data/raw/.

Reads from the `scratch` schema (csi_team's own writable workspace) by default — use --schema
public to read the read-only plan_reader snapshot instead. See docs/DATA_ACCESS.md and the
2026-07-27 team write-access message for what's in each schema and the refresh rules.

Exploratory only — not part of any runtime path, not imported by anything in apps/ or pipelines/.

Usage:
    export SUPABASE_TEAM_DB_URL='postgresql://...'   # see data/.env.example / data/.env

    python data/pull_supabase_table.py                          # list tables in scratch
    python data/pull_supabase_table.py risk_by_county            # -> data/raw/risk_by_county.csv
    python data/pull_supabase_table.py risk_by_county --limit 20
    python data/pull_supabase_table.py risk_by_county other_table   # pull several, one CSV each
    python data/pull_supabase_table.py plans --schema public       # read the public snapshot instead

    # a custom SQL query instead of a plain table dump:
    python data/pull_supabase_table.py --sql "select * from scratch.risk_by_county" --out combined.csv
"""
import argparse
import os

import pandas as pd
import psycopg

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "raw")


def connect():
    dsn = os.environ.get("SUPABASE_TEAM_DB_URL")
    if not dsn:
        raise SystemExit("SUPABASE_TEAM_DB_URL is not set. export it (see data/.env.example).")
    return psycopg.connect(dsn)


def list_tables(conn, schema):
    with conn.cursor() as cur:
        cur.execute(
            "select table_name from information_schema.tables where table_schema = %s order by table_name",
            (schema,),
        )
        names = [row[0] for row in cur.fetchall()]
    if not names:
        print(f"no tables in schema {schema!r}")
        return
    with conn.cursor() as cur:
        for name in names:
            cur.execute(f'select count(*) from "{schema}"."{name}"')
            print(f"{name:<24} {cur.fetchone()[0]} rows")


def fetch_table(conn, schema, table, limit):
    query = f'select * from "{schema}"."{table}"' + (f" limit {int(limit)}" if limit else "")
    return pd.read_sql(query, conn)


def save(df, filename):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    path = os.path.join(OUTPUT_DIR, filename)
    df.to_csv(path, index=False)
    print(f"wrote {path} ({df.shape[0]} rows x {df.shape[1]} cols)")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("tables", nargs="*", help="one or more tables to pull; omit to list tables in the schema")
    parser.add_argument("--schema", default="scratch", help="schema to read from (default: scratch)")
    parser.add_argument("--sql", help="run a raw SQL query instead of dumping whole tables")
    parser.add_argument("--limit", type=int, default=None, help="row limit per table (ignored with --sql)")
    parser.add_argument("--out", help="output CSV filename, written under data/raw/ (required with --sql)")
    args = parser.parse_args()

    with connect() as conn:
        if args.sql:
            if not args.out:
                raise SystemExit("--sql requires --out <filename.csv>")
            df = pd.read_sql(args.sql, conn)
            print(df.head(10).to_string())
            save(df, args.out)
        elif not args.tables:
            list_tables(conn, args.schema)
        else:
            for table in args.tables:
                df = fetch_table(conn, args.schema, table, args.limit)
                save(df, args.out if (args.out and len(args.tables) == 1) else f"{table}.csv")


if __name__ == "__main__":
    main()
