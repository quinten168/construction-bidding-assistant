#!/usr/bin/env bash
# ================================================================================================
# Validate team_access.sql against a throwaway Postgres before it is run against production.
#
# The privilege model this sets up has a failure mode that is invisible on the day you apply it:
# grants look correct, every verification query passes, and then the next publish silently
# removes the team's access because the default-privileges policy named the wrong creating-role.
# You would not find out until someone reports a permission error days later.
#
# So this does not merely run the SQL and check it parses. It reproduces the snapshot, applies
# the grants, and then SIMULATES A PUBLISH — the same drop-and-recreate publish_to_supabase.py
# performs — and re-checks every privilege afterwards. That is the only test that actually
# exercises the risk.
#
# Requires: docker. Uses a disposable container on port 55432 and removes it on exit.
#
#   ./test_team_access.sh
# ================================================================================================
set -euo pipefail

CONTAINER="csi-team-access-test"
PORT=55432
PGPW="testpw"
TEAMPW="team-test-pw"
SBPW="sb-admin-pw"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Supabase's `postgres` is NOT a superuser. It has CREATEROLE and CREATEDB and owns the data,
# but it cannot do everything, and the difference is not academic: running this file as a real
# container superuser passed 20/20 while production failed with
#   42501: permission denied to change default privileges
# because `alter default privileges FOR ROLE <other>` requires membership in that role.
#
# So every privileged action below runs as `sb_admin`, a deliberately non-superuser stand-in.
# Testing as the container superuser tests a database we do not have.

# Supabase runs Postgres 15+. Pinning 15 tests the oldest version we could be talking to, which
# is where the "public schema is not world-writable by default" behaviour we rely on begins.
IMAGE="postgres:15-alpine"

pass=0; fail=0
cleanup() { docker rm -f "$CONTAINER" >/dev/null 2>&1 || true; }
trap cleanup EXIT

# Superuser. Used ONLY to bootstrap sb_admin and to read catalogs; never to apply the grants.
psql_su()  { docker exec -i -e PGPASSWORD="$PGPW" "$CONTAINER" psql -U postgres -d postgres -v ON_ERROR_STOP=1 "$@"; }
# Query as an arbitrary role, to test what that role can really do rather than what a catalog says.
psql_as()  { local role="$1" pw="$2"; shift 2
             docker exec -i -e PGPASSWORD="$pw" "$CONTAINER" psql -U "$role" -d postgres -h 127.0.0.1 -v ON_ERROR_STOP=1 "$@"; }
# The Supabase stand-in: owns the published tables and applies team_access.sql, exactly as the
# real `postgres` role does. Everything a human would run in the Supabase SQL editor goes here.
psql_run() { psql_as sb_admin "$SBPW" "$@"; }

check() { # check <description> <expected> <actual>
  if [[ "$2" == "$3" ]]; then printf '  \033[32mPASS\033[0m  %s\n' "$1"; pass=$((pass+1))
  else printf '  \033[31mFAIL\033[0m  %s\n        expected [%s] got [%s]\n' "$1" "$2" "$3"; fail=$((fail+1)); fi
}

echo "=============================================================================="
echo "team_access.sql :: validation against a disposable $IMAGE"
echo "=============================================================================="

cleanup
docker run -d --name "$CONTAINER" -e POSTGRES_PASSWORD="$PGPW" -p "$PORT:5432" "$IMAGE" >/dev/null
printf 'waiting for postgres'
for _ in $(seq 1 40); do
  if docker exec "$CONTAINER" pg_isready -U postgres -q 2>/dev/null; then break; fi
  printf '.'; sleep 1
done
echo " ready"

# --- reproduce Supabase's privilege level -------------------------------------------------------
echo
echo "-- creating sb_admin: NOSUPERUSER + CREATEROLE + CREATEDB, as Supabase's postgres is"
psql_su -q <<SQL
create role sb_admin with login password '$SBPW' nosuperuser createrole createdb;
-- Supabase's postgres owns the database and the public schema, which is what lets it CREATE
-- SCHEMA (a database-level privilege) and REVOKE on public (an ownership-level one). Grant the
-- same, and no more: the point of this role is that it is not a superuser.
grant create on database postgres to sb_admin;
alter schema public owner to sb_admin;
SQL
r=$(psql_su -qtAc "select rolsuper from pg_roles where rolname='sb_admin'")
check "sb_admin is NOT a superuser (matches Supabase)" "f" "$r"

# --- reproduce the production shape ------------------------------------------------------------
# Owned by sb_admin, exactly as publish_to_supabase.py leaves them. The DO block detects the
# publisher role by reading public.plans' owner, so this is what it will find.
echo
echo "-- seeding a stand-in snapshot (8 tables owned by sb_admin, as the publisher leaves them)"
psql_run -q <<'SQL'
create table public.plans                 (plan_id text primary key, county text, state text);
create table public.materials             (id bigint primary key, plan_id text, quantity double precision);
create table public.plan_metrics          (plan_id text primary key, work_type text);
create table public.gotchas               (id bigint primary key, plan_id text, decision_class text);
create table public.location_intelligence (id bigint primary key, target text);
create table public.material_crosswalk    (normalized_description text, state text, primary key (normalized_description, state));
create table public.bucket_hierarchy      (sub_bucket text primary key);
create table public.section_taxonomy      (section_type text primary key);
insert into public.plans values ('P0001','Hennepin','MN'), ('P0002','Ramsey','MN');
SQL

# --- apply the real file, unmodified except for the password placeholder -----------------------
echo "-- applying team_access.sql"
# The file is a sequence of independent steps, not one transaction, and STEP 7 is explicitly
# allowed to fail. So apply with ON_ERROR_STOP=0 and assert on OUTCOMES below rather than on the
# exit status. Errors are still printed: filtering to NOTICE only, once, hid a hard failure and
# made the next assertion report "role does not exist" -- a symptom three steps from its cause.
apply() {
  sed "s/REPLACE_ME/$TEAMPW/" "$HERE/team_access.sql" \
    | docker exec -i -e PGPASSWORD="$SBPW" "$CONTAINER" \
        psql -U sb_admin -d postgres -h 127.0.0.1 -q -v ON_ERROR_STOP=0 2>&1
}
apply | grep -iE 'notice|error' | sed 's/^/    /' || true

echo
echo "-- privileges as granted"
r=$(psql_run -tAc "select has_schema_privilege('csi_team','public','CREATE')")
check "csi_team CANNOT create in public"           "f" "$r"
r=$(psql_run -tAc "select has_schema_privilege('csi_team','public','USAGE')")
check "csi_team can use public"                    "t" "$r"
r=$(psql_run -tAc "select has_schema_privilege('csi_team','scratch','CREATE')")
check "csi_team CAN create in scratch"             "t" "$r"
r=$(psql_run -tAc "select count(*) from information_schema.role_table_grants where grantee='csi_team' and table_schema='public' and privilege_type='SELECT'")
check "csi_team has SELECT on all 8 snapshot tables" "8" "$r"
r=$(psql_run -tAc "select count(*) from information_schema.role_table_grants where grantee='csi_team' and table_schema='public' and privilege_type<>'SELECT'")
check "csi_team has NO write grants in public"     "0" "$r"
r=$(psql_run -tAc "select array_to_string(rolconfig,',') from pg_roles where rolname='csi_team'")
check "search_path puts scratch first"             "search_path=scratch, public" "$r"

# The single most failure-prone line in the file, and the one whose absence is invisible until a
# publish silently removes the team's access. It must be recorded against the role that OWNS the
# published tables, which the DO block detects rather than assumes.
r=$(psql_run -tAc "select count(*) from pg_default_acl d join pg_namespace n on n.oid=d.defaclnamespace where pg_get_userbyid(d.defaclrole)='sb_admin' and n.nspname='public' and array_to_string(d.defaclacl,',') like '%csi_team=r%'")
check "default SELECT recorded against sb_admin"   "1" "$r"

# --- behaviour, not catalogs -------------------------------------------------------------------
echo
echo "-- what the role can actually DO (connecting as csi_team)"
r=$(psql_as csi_team "$TEAMPW" -tAc "select count(*) from plans" 2>/dev/null || echo ERR)
check "csi_team can read public.plans unqualified" "2" "$r"

# Quinten's exact failing statement, minus the explicit public. qualifier.
# -q suppresses psql's per-statement command tags ("CREATE TABLE", "INSERT 0 1"), which would
# otherwise be interleaved with the value we are asserting on.
r=$(psql_as csi_team "$TEAMPW" -qtAc "create table if not exists test_table (id serial primary key, name text, created_at timestamp default now()); select 'created'" 2>/dev/null || echo ERR)
check "Quinten's CREATE TABLE now succeeds"        "created" "$r"
r=$(psql_as csi_team "$TEAMPW" -qtAc "select table_schema from information_schema.tables where table_name='test_table'")
check "...and it landed in scratch, not public"    "scratch" "$r"
r=$(psql_as csi_team "$TEAMPW" -qtAc "insert into test_table (name) values ('x'); select count(*) from test_table" 2>/dev/null || echo ERR)
check "SERIAL insert works (sequence granted)"     "1" "$r"

# The refusals still have to hold.
r=$(psql_as csi_team "$TEAMPW" -tAc "create table public.nope (x int)" 2>&1 >/dev/null | grep -c "permission denied for schema public" || true)
check "explicit CREATE in public still refused"    "1" "$r"
r=$(psql_as csi_team "$TEAMPW" -tAc "drop table public.plans" 2>&1 >/dev/null | grep -c "must be owner" || true)
check "csi_team cannot DROP the snapshot"          "1" "$r"
r=$(psql_as csi_team "$TEAMPW" -tAc "delete from public.plans" 2>&1 >/dev/null | grep -c "permission denied" || true)
check "csi_team cannot DELETE from the snapshot"   "1" "$r"

# --- the test that matters: survive a publish --------------------------------------------------
echo
echo "-- simulating a publish (drop + recreate, as publish_to_supabase.py does)"
psql_as csi_team "$TEAMPW" -qc "create view scratch.plans_by_county as select county, count(*) from public.plans group by 1" >/dev/null
r=$(psql_run -tAc "select count(*) from pg_class c join pg_namespace n on n.oid=c.relnamespace where n.nspname='scratch' and c.relname='plans_by_county'")
check "team view exists before the publish"        "1" "$r"

psql_run -q <<'SQL'
drop table if exists public.plans cascade;
create table public.plans (plan_id text primary key, county text, state text);
insert into public.plans values ('P0001','Hennepin','MN'), ('P0002','Ramsey','MN'), ('P0003','Anoka','MN');
SQL

r=$(psql_run -tAc "select count(*) from information_schema.role_table_grants where grantee='csi_team' and table_schema='public' and table_name='plans' and privilege_type='SELECT'")
check "SELECT SURVIVED the republish (default privs)" "1" "$r"
r=$(psql_as csi_team "$TEAMPW" -tAc "select count(*) from plans" 2>/dev/null || echo ERR)
check "csi_team still reads plans after republish" "3" "$r"
r=$(psql_as csi_team "$TEAMPW" -tAc "select count(*) from scratch.test_table" 2>/dev/null || echo ERR)
check "team's TABLE survived the republish"        "1" "$r"

# The documented hazard. This asserts the loss is real, so the claim in DATA_ACCESS.md is
# measured rather than assumed. If this ever starts passing as 1, the hazard is gone and the
# docs should change.
r=$(psql_run -tAc "select count(*) from pg_class c join pg_namespace n on n.oid=c.relnamespace where n.nspname='scratch' and c.relname='plans_by_county'")
check "team's VIEW was destroyed (the known hazard)" "0" "$r"

# --- idempotency -------------------------------------------------------------------------------
echo
echo "-- re-running the whole file (must be safe to repeat)"
# STEP 2's `create role` is EXPECTED to fail the second time; the file documents running the
# commented ALTER instead. Every other step must still be a clean no-op, so assert that the only
# error is that one -- not merely that "some errors happened", which would hide a regression.
errs=$(apply | grep -ci '^ERROR' || true)
check "re-apply produces exactly 1 error (role exists)" "1" "$errs"
r=$(apply | grep -i '^ERROR' | grep -ci 'already exists' || true)
check "...and it is the expected already-exists error"  "1" "$r"
r=$(psql_as csi_team "$TEAMPW" -qtAc "select count(*) from scratch.test_table" 2>/dev/null || echo ERR)
check "re-apply did not disturb team data"         "1" "$r"
r=$(psql_run -tAc "select has_schema_privilege('csi_team','public','CREATE')")
check "re-apply did not loosen public"             "f" "$r"

echo
echo "=============================================================================="
printf 'passed %d, failed %d\n' "$pass" "$fail"
echo "=============================================================================="
[[ $fail -eq 0 ]]
