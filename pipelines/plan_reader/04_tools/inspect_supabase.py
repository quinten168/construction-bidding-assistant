#!/usr/bin/env python3
"""
Report the current state of the hosted Postgres (Supabase) that carries the published
plan-extraction snapshot: schemas, tables, login roles, who can do what, and which objects
the next publish would destroy.

This is a READ-ONLY tool. It runs no DDL and no DML. Point it at production.

It exists because privileges on this database are invisible from the repo. The publisher
(`publish_to_supabase.py`) writes tables and nothing else; every GRANT, role and schema was
applied by hand through the Supabase SQL editor. There was no way to answer "what can the team
actually do right now" without opening a client and remembering nine catalog queries. Now there
is one command.

Usage
-----
    export SUPABASE_ADMIN_URL='postgresql://postgres.<ref>:<pw>@<host>:5432/postgres'
    python inspect_supabase.py

    # or check what a specific teammate's credentials can reach, by connecting AS them
    export SUPABASE_ADMIN_URL='postgresql://csi_team.<ref>:<pw>@<host>:5432/postgres'
    python inspect_supabase.py

Reading it as a non-admin is allowed and useful: Postgres catalogs are world-readable, so the
privilege picture is the same. Only `--check-writes` differs, since that probes what YOUR role
can do.

    python inspect_supabase.py --check-writes   # harmless probe, see below

Configuration is environment-only. No credentials are baked in or committed.
  SUPABASE_ADMIN_URL   Postgres DSN. Falls back to SUPABASE_DB_URL if unset.
"""
from __future__ import annotations

import argparse
import os
import sys
import urllib.parse

# The tables `publish_to_supabase.py` drops and recreates on every run. Kept in sync by hand;
# a mismatch here only affects which objects get flagged as at-risk, never what is published.
PUBLISHED_TABLES = [
    "plans", "materials", "plan_metrics", "gotchas", "location_intelligence",
    "material_crosswalk", "bucket_hierarchy", "section_taxonomy",
]

# Supabase ships these; they are not ours and listing them buries the signal.
SYSTEM_SCHEMAS = (
    "pg_catalog", "information_schema", "pg_toast",
    "auth", "storage", "realtime", "extensions", "graphql", "graphql_public",
    "supabase_functions", "supabase_migrations", "vault", "pgsodium", "pgsodium_masks",
    "net", "cron", "_realtime", "pgbouncer",
)

# Supabase's own service roles. Real humans and applications are what we want to see.
SYSTEM_ROLES = (
    "postgres", "anon", "authenticated", "service_role", "dashboard_user",
    "supabase_admin", "supabase_auth_admin", "supabase_storage_admin",
    "supabase_replication_admin", "supabase_read_only_user", "supabase_realtime_admin",
    "authenticator", "pgbouncer", "pgsodium_keyholder", "pgsodium_keyiduser",
    "pgsodium_keymaker", "pg_database_owner", "pg_read_all_data", "pg_write_all_data",
    "pg_monitor", "pg_read_all_settings", "pg_read_all_stats", "pg_stat_scan_tables",
    "pg_signal_backend", "pg_checkpoint", "pg_use_reserved_connections",
    "pg_create_subscription", "pg_maintain",
)


def rule(title: str) -> None:
    print("\n" + "=" * 86)
    print(title)
    print("=" * 86)


def redact(dsn: str) -> str:
    """Never print the password, even into a local terminal log."""
    try:
        p = urllib.parse.urlsplit(dsn)
        if p.password:
            netloc = f"{p.username}:***@{p.hostname}" + (f":{p.port}" if p.port else "")
            return urllib.parse.urlunsplit((p.scheme, netloc, p.path, "", ""))
    except ValueError:
        pass
    return "(set)"


def q(cur, sql: str, params: tuple = ()) -> list[tuple]:
    cur.execute(sql, params)
    return cur.fetchall()


# --- sections -----------------------------------------------------------------------------------

def report_identity(cur) -> str:
    rows = q(cur, """
        select current_user, session_user, current_database(),
               version(), current_setting('search_path')
    """)
    cur_user, sess_user, db, ver, sp = rows[0]
    rule("CONNECTION")
    print(f"  connected as   : {cur_user}" + (f"  (session: {sess_user})" if sess_user != cur_user else ""))
    print(f"  database       : {db}")
    print(f"  server         : {ver.split(' on ')[0]}")
    print(f"  search_path    : {sp}")

    su = q(cur, "select rolsuper, rolcreaterole, rolcreatedb from pg_roles where rolname = current_user")
    if su:
        s, cr, cd = su[0]
        caps = [n for n, on in (("superuser", s), ("createrole", cr), ("createdb", cd)) if on]
        print(f"  your role      : {', '.join(caps) if caps else 'ordinary role (no superuser/createrole)'}")
    return cur_user


def report_schemas(cur) -> None:
    rows = q(cur, """
        select n.nspname, pg_get_userbyid(n.nspowner) as owner,
               coalesce(count(c.oid) filter (where c.relkind in ('r','p')), 0) as tables,
               coalesce(count(c.oid) filter (where c.relkind in ('v','m')), 0) as views
        from pg_namespace n
        left join pg_class c on c.relnamespace = n.oid
        where n.nspname <> all(%s) and n.nspname not like 'pg_temp%%'
              and n.nspname not like 'pg_toast%%'
        group by 1, 2
        order by 1
    """, (list(SYSTEM_SCHEMAS),))
    rule("SCHEMAS  (Supabase's own schemas are filtered out)")
    if not rows:
        print("  none beyond the system schemas.")
        return
    print(f"  {'schema':<24} {'owner':<22} {'tables':>7} {'views':>7}")
    for name, owner, tables, views in rows:
        print(f"  {name:<24} {owner:<22} {tables:>7} {views:>7}")


def report_tables(cur) -> None:
    """Exact row counts. The published tables are small (largest is ~6.4k rows), so a real
    count() is cheap and honest; reltuples estimates drift and would undercut the point of
    running this at all."""
    rows = q(cur, """
        select n.nspname, c.relname, c.relkind,
               pg_size_pretty(pg_total_relation_size(c.oid)),
               pg_get_userbyid(c.relowner)
        from pg_class c
        join pg_namespace n on n.oid = c.relnamespace
        where c.relkind in ('r','p','v','m')
          and n.nspname <> all(%s)
          and n.nspname not like 'pg_%%'
        order by n.nspname, c.relname
    """, (list(SYSTEM_SCHEMAS),))
    rule("TABLES AND VIEWS")
    if not rows:
        print("  none.")
        return
    kind_label = {"r": "table", "p": "table", "v": "view", "m": "matview"}
    print(f"  {'schema.name':<44} {'kind':<8} {'rows':>10} {'size':>10}  owner")
    for schema, name, kind, size, owner in rows:
        if kind in ("r", "p", "m"):
            n = q(cur, f'select count(*) from "{schema}"."{name}"')[0][0]
            count = f"{n:,}"
        else:
            count = "-"          # counting a view means executing it; not worth it here
        print(f"  {schema + '.' + name:<44} {kind_label[kind]:<8} {count:>10} {size:>10}  {owner}")


def report_roles(cur) -> None:
    rows = q(cur, """
        select r.rolname, r.rolcanlogin, r.rolsuper, r.rolvaliduntil,
               array_to_string(r.rolconfig, ', ')
        from pg_roles r
        where r.rolname <> all(%s) and r.rolname not like 'pg\\_%%'
        order by r.rolcanlogin desc, r.rolname
    """, (list(SYSTEM_ROLES),))
    rule("ROLES  (Supabase service roles filtered out)")
    if not rows:
        print("  no custom roles. Everyone is connecting as a built-in role.")
        return
    print(f"  {'role':<28} {'login':<7} {'super':<7} {'expires':<12} role-level settings")
    for name, login, super_, valid, config in rows:
        exp = valid.date().isoformat() if valid else "never"
        print(f"  {name:<28} {'yes' if login else 'no':<7} {'YES' if super_ else 'no':<7} "
              f"{exp:<12} {config or '-'}")


def report_schema_privs(cur) -> None:
    """Schema-level USAGE and CREATE. This is the privilege Quinten's CREATE TABLE actually
    failed on (SQLSTATE 42501 names the schema, not the table)."""
    schemas = [r[0] for r in q(cur, """
        select nspname from pg_namespace
        where nspname <> all(%s) and nspname not like 'pg_%%' order by 1
    """, (list(SYSTEM_SCHEMAS),))]
    roles = [r[0] for r in q(cur, """
        select rolname from pg_roles
        where rolname <> all(%s) and rolname not like 'pg\\_%%' and rolcanlogin order by 1
    """, (list(SYSTEM_ROLES),))]
    rule("SCHEMA PRIVILEGES  (can this role create objects here?)")
    if not schemas:
        print("  no non-system schemas.")
        return
    print(f"  {'schema':<24} {'role':<28} {'USAGE':<7} {'CREATE'}")
    for s in schemas:
        for r in roles:
            # has_schema_privilege resolves inherited and role-membership grants, which is what
            # actually decides whether a statement succeeds. It only accepts real roles.
            usage, create = q(cur, """
                select has_schema_privilege(%s, %s, 'USAGE'),
                       has_schema_privilege(%s, %s, 'CREATE')
            """, (r, s, r, s))[0]
            print(f"  {s:<24} {r:<28} {'yes' if usage else 'NO':<7} {'YES' if create else 'no'}")

        # PUBLIC is a pseudo-role, so has_schema_privilege cannot be asked about it. Read the
        # ACL directly instead; grantee 0 is PUBLIC. A NULL nspacl means "built-in default",
        # which since Postgres 15 grants PUBLIC nothing on any schema including `public`.
        pub_usage, pub_create = q(cur, """
            select exists (select 1 from pg_namespace n, aclexplode(n.nspacl) a
                           where n.nspname = %s and a.grantee = 0 and a.privilege_type = 'USAGE'),
                   exists (select 1 from pg_namespace n, aclexplode(n.nspacl) a
                           where n.nspname = %s and a.grantee = 0 and a.privilege_type = 'CREATE')
        """, (s, s))[0]
        print(f"  {s:<24} {'PUBLIC (everyone)':<28} "
              f"{'yes' if pub_usage else 'NO':<7} {'YES' if pub_create else 'no'}")


def report_table_privs(cur) -> None:
    rows = q(cur, """
        select table_schema, grantee, privilege_type, count(*)
        from information_schema.role_table_grants
        where table_schema <> all(%s) and table_schema not like 'pg_%%'
        group by 1, 2, 3
        order by 1, 2, 3
    """, (list(SYSTEM_SCHEMAS),))
    rule("TABLE PRIVILEGES  (granted, by schema and role)")
    if not rows:
        print("  none.")
        return
    print(f"  {'schema':<20} {'role':<28} {'privilege':<12} {'# tables'}")
    for schema, grantee, priv, n in rows:
        print(f"  {schema:<20} {grantee:<28} {priv:<12} {n}")


def report_default_privs(cur) -> None:
    """The publisher DROPs and CREATEs each table, so grants made against the OLD table die
    with it. Only ALTER DEFAULT PRIVILEGES carries a grant onto the replacement. If this
    section is empty, the team loses read access at the next publish."""
    rows = q(cur, """
        select pg_get_userbyid(d.defaclrole), n.nspname, d.defaclobjtype,
               array_to_string(d.defaclacl, ', ')
        from pg_default_acl d
        left join pg_namespace n on n.oid = d.defaclnamespace
        order by 1, 2
    """)
    rule("DEFAULT PRIVILEGES  (do grants survive the publisher's drop-and-recreate?)")
    if not rows:
        print("  NONE SET.")
        print("  Consequence: publish_to_supabase.py drops and recreates every published table,")
        print("  which destroys the grants attached to the old table. Any role reading those")
        print("  tables loses access at the next publish until someone re-grants by hand.")
        return
    objtype = {"r": "tables", "S": "sequences", "f": "functions", "T": "types", "n": "schemas"}
    print(f"  {'when created by':<24} {'in schema':<18} {'on':<11} grants")
    for role, schema, ot, acl in rows:
        print(f"  {role:<24} {(schema or '(all)'):<18} {objtype.get(ot, ot):<11} {acl}")


def report_publish_blast_radius(cur) -> None:
    """Which objects would the next `publish_to_supabase.py` run destroy?

    The publisher issues `drop table if exists "<t>" cascade` per table. CASCADE follows
    dependencies WHEREVER they live: a view in another schema that selects from a published
    table is dropped too. Schema separation protects the team's TABLES; it does not protect
    their VIEWS. That is the single most surprising fact about this database and it is the
    reason this section exists.
    """
    rule("BLAST RADIUS OF THE NEXT PUBLISH")
    print("  publish_to_supabase.py runs `drop table ... cascade` on each published table.")
    print("  CASCADE crosses schema boundaries. Anything listed below is destroyed silently.\n")

    present = [r[0] for r in q(cur, """
        select c.relname from pg_class c join pg_namespace n on n.oid = c.relnamespace
        where n.nspname = 'public' and c.relname = any(%s) and c.relkind in ('r','p')
    """, (PUBLISHED_TABLES,))]
    missing = [t for t in PUBLISHED_TABLES if t not in present]
    print(f"  published tables present : {len(present)} of {len(PUBLISHED_TABLES)}")
    if missing:
        print(f"  MISSING                  : {', '.join(missing)}")

    dependents = q(cur, """
        select distinct dn.nspname, dc.relname, dc.relkind,
               pg_get_userbyid(dc.relowner), sc.relname as depends_on
        from pg_depend d
        join pg_rewrite rw on rw.oid = d.objid
        join pg_class dc   on dc.oid = rw.ev_class
        join pg_namespace dn on dn.oid = dc.relnamespace
        join pg_class sc   on sc.oid = d.refobjid
        join pg_namespace sn on sn.oid = sc.relnamespace
        where d.classid = 'pg_rewrite'::regclass
          and sn.nspname = 'public'
          and sc.relname = any(%s)
          and dc.relkind in ('v','m')
          and dc.oid <> sc.oid
        order by 1, 2
    """, (PUBLISHED_TABLES,))
    if not dependents:
        print("\n  dependent views          : none. Nothing would be lost.")
        return
    print(f"\n  DEPENDENT OBJECTS THAT WOULD BE DROPPED ({len(dependents)}):")
    kind_label = {"v": "view", "m": "matview"}
    for schema, name, kind, owner, source in dependents:
        print(f"    {schema}.{name}  ({kind_label.get(kind, kind)}, owner {owner})  "
              f"-> depends on public.{source}")


def report_write_probe(cur, conn) -> None:
    """Probe what THIS connection can actually write, then roll it all back.

    Privilege catalogs answer "what was granted". This answers "what happens when I try",
    which is the question a teammate is really asking. Everything runs inside a transaction
    that is unconditionally rolled back, so the probe cannot leave an object behind.
    """
    rule("WRITE PROBE  (attempted, then rolled back — nothing persists)")
    schemas = [r[0] for r in q(cur, """
        select nspname from pg_namespace
        where nspname <> all(%s) and nspname not like 'pg_%%' order by 1
    """, (list(SYSTEM_SCHEMAS),))]
    for s in schemas:
        try:
            cur.execute(f'savepoint probe')
            cur.execute(f'create table "{s}"._probe_delete_me (x int)')
            cur.execute(f'rollback to savepoint probe')
            verdict = "CAN CREATE TABLES"
        except Exception as e:
            cur.execute("rollback to savepoint probe")
            verdict = f"cannot create ({type(e).__name__.replace('Error', '')})"
        print(f"  {s:<24} {verdict}")
    conn.rollback()
    print("\n  Transaction rolled back. No objects were created.")


# --- main ---------------------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(
        description="Read-only report on the hosted Postgres snapshot's structure and privileges.")
    ap.add_argument("--check-writes", action="store_true",
                    help="Additionally probe what the connecting role can create, in a "
                         "transaction that is always rolled back.")
    args = ap.parse_args()

    dsn = (os.environ.get("SUPABASE_ADMIN_URL") or os.environ.get("SUPABASE_DB_URL") or "").strip()
    if not dsn:
        print("ERROR: set SUPABASE_ADMIN_URL (or SUPABASE_DB_URL) to a Postgres DSN.",
              file=sys.stderr)
        return 2

    try:
        import psycopg
    except ImportError:
        print("ERROR: psycopg (v3) is required.\n  pip install 'psycopg[binary]'", file=sys.stderr)
        return 2

    print("=" * 86)
    print("inspect_supabase  ::  READ-ONLY REPORT")
    print("=" * 86)
    print(f"target : {redact(dsn)}")

    with psycopg.connect(dsn) as conn:
        with conn.cursor() as cur:
            report_identity(cur)
            report_schemas(cur)
            report_tables(cur)
            report_roles(cur)
            report_schema_privs(cur)
            report_table_privs(cur)
            report_default_privs(cur)
            report_publish_blast_radius(cur)
            if args.check_writes:
                report_write_probe(cur, conn)
        conn.rollback()   # this tool never commits
    print("\n" + "=" * 86)
    print("Report complete. Nothing was written.")
    print("=" * 86)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
