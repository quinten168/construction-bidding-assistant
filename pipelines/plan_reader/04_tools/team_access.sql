-- ================================================================================================
-- Team write access to the hosted Postgres snapshot.
--
-- Gives the team a place to create their own tables WITHOUT letting them damage, drop or shadow
-- the published snapshot that `publish_to_supabase.py` maintains.
--
-- RUN THESE ONE STEP AT A TIME, IN ORDER, in the Supabase SQL editor.
--
-- Deliberately NOT one big transaction. An earlier version wrapped everything in a single
-- `do $$ ... $$` block, which was atomic but had two problems against the real dashboard:
--   1. the password was interpolated INSIDE the dollar-quoted block, so a password containing
--      `$$` or a quote broke the block delimiter and produced malformed SQL;
--   2. when the editor dropped the connection, there was no way to tell which statement had
--      been reached.
-- Every step below is independently re-runnable and safe to repeat, so if one fails you fix that
-- step and continue from there rather than starting over.
--
-- WHY A SEPARATE SCHEMA, rather than granting CREATE on `public`
-- ---------------------------------------------------------------
-- `publish_to_supabase.py:228` runs `drop table if exists "<table>" cascade` on all eight
-- published tables, every publish. Working inside `public` means: tables silently destroyed,
-- the snapshot itself droppable, and name collisions between teammates. A schema the publisher
-- never names avoids all three.
--
-- WHAT THIS DOES NOT PROTECT
-- ---------------------------------------------------------------
-- `drop table ... cascade` follows dependencies ACROSS SCHEMAS. A VIEW in `scratch` that selects
-- from `public.plans` is still dropped when `plans` is. Tables are protected; views are not.
-- `publish_to_supabase.py` now refuses to publish when it would destroy one (override: --force).
-- ================================================================================================


-- ── STEP 0 ─────────────────────────────────────────────────────────────────────────────────────
-- Read-only. Run this FIRST, and again after any failure, to see the actual state.
-- A dropped connection leaves it ambiguous whether the work committed; this removes the guess.

select 'role csi_team exists' as check,
       coalesce((select 'yes'::text from pg_roles where rolname = 'csi_team'), 'no') as result
union all
select 'schema scratch exists',
       coalesce((select 'yes'::text from pg_namespace where nspname = 'scratch'), 'no')
union all
select 'owner of public.plans (the publisher role)',
       coalesce((select pg_get_userbyid(c.relowner)::text from pg_class c
                 join pg_namespace n on n.oid = c.relnamespace
                 where n.nspname = 'public' and c.relname = 'plans'), 'public.plans NOT FOUND')
union all
select 'csi_team can create in scratch',
       case when not exists (select 1 from pg_roles where rolname = 'csi_team') then 'n/a'
            when not exists (select 1 from pg_namespace where nspname = 'scratch') then 'n/a'
            when has_schema_privilege('csi_team', 'scratch', 'CREATE') then 'yes' else 'no' end
union all
select 'csi_team SELECT grants in public (want 8)',
       coalesce((select count(*)::text from information_schema.role_table_grants
                 where grantee = 'csi_team' and table_schema = 'public'
                   and privilege_type = 'SELECT'), '0');


-- ── STEP 1 ─────────────────────────────────────────────────────────────────────────────────────
-- The writable schema. The publisher never references this name.

create schema if not exists scratch;


-- ── STEP 2 ─────────────────────────────────────────────────────────────────────────────────────
-- The team login. Replace the password below, then run.
--
-- The password sits in a plain statement, NOT inside a dollar-quoted block, so any character is
-- safe except a single quote. If your password contains a single quote, double it (' becomes '').
-- Easier: generate one without quotes or backslashes.
--
-- If STEP 0 said the role already exists, run the ALTER line instead of the CREATE line.

create role csi_team with login password 'REPLACE_ME';
-- alter role csi_team with login password 'REPLACE_ME';


-- ── STEP 3 ─────────────────────────────────────────────────────────────────────────────────────
-- Read-only access to the published snapshot.

grant usage on schema public to csi_team;
grant select on all tables in schema public to csi_team;

-- Explicitly deny object creation in public. Postgres 15+ withholds this by default; stating it
-- means a later `grant all on schema public` cannot silently re-open it.
revoke create on schema public from csi_team;


-- ── STEP 4 ─────────────────────────────────────────────────────────────────────────────────────
-- THE IMPORTANT ONE. Grants live on the table, so the publisher's drop-and-recreate destroys
-- them. Only a default-privileges policy carries SELECT onto the replacement table. Without
-- this, the team loses all read access at the next publish, with no error to explain it.
--
-- The policy is recorded PER CREATING-ROLE, so it must name the role that owns the published
-- tables. STEP 0 printed it. This block reads it rather than trusting a guess.

do $step4$
declare
  publisher_role text;
begin
  select pg_get_userbyid(c.relowner) into publisher_role
  from pg_class c join pg_namespace n on n.oid = c.relnamespace
  where n.nspname = 'public' and c.relname = 'plans' and c.relkind = 'r';

  if publisher_role is null then
    raise exception 'public.plans not found; cannot determine the publisher role';
  end if;

  execute format(
    'alter default privileges for role %I in schema public grant select on tables to csi_team',
    publisher_role);
  raise notice 'default SELECT policy recorded against %', publisher_role;
end
$step4$;


-- ── STEP 5 ─────────────────────────────────────────────────────────────────────────────────────
-- Read-write in the team schema. The sequence grant matters: a SERIAL column creates a
-- sequence, and without it an INSERT fails on a table the role owns.

grant usage, create on schema scratch to csi_team;
grant all privileges on all tables in schema scratch to csi_team;
grant all privileges on all sequences in schema scratch to csi_team;


-- ── STEP 6 ─────────────────────────────────────────────────────────────────────────────────────
-- Make the safe thing the default thing. An unqualified `create table foo (...)` lands in
-- `scratch`, while `select * from plans` still resolves to `public.plans`.
--
-- This does NOT rescue a statement that says `public.` explicitly, and should not:
-- `create table public.foo` still fails with 42501, because it asked for something we refuse.

alter role csi_team set search_path = scratch, public;


-- ── STEP 7 (OPTIONAL — skip if it errors) ──────────────────────────────────────────────────────
-- Lets teammates read and build on each other's objects in `scratch`.
--
-- `alter default privileges FOR ROLE <other>` requires membership in that role, and Supabase's
-- `postgres` is NOT a superuser — this is what failed with 42501 on the first attempt. The GRANT
-- below supplies that membership.
--
-- Genuinely optional: while `csi_team` is a single shared login, these are a no-op, because
-- csi_team creates the object and therefore already owns it and holds every privilege on it.
-- They only matter if per-person roles are added to `scratch` later. If either line errors,
-- skip both and move on -- nothing about the team's access depends on them.

grant csi_team to current_user;
alter default privileges for role csi_team in schema scratch grant all on tables to csi_team;
alter default privileges for role csi_team in schema scratch grant all on sequences to csi_team;


-- ── STEP 8 ─────────────────────────────────────────────────────────────────────────────────────
-- Verify. Re-run STEP 0 as well; it should now report yes / yes / <publisher> / yes / 8.

-- Expect: public -> can_use true, can_create FALSE.  scratch -> both true.
select s.nspname                                             as schema,
       has_schema_privilege('csi_team', s.nspname, 'USAGE')  as can_use,
       has_schema_privilege('csi_team', s.nspname, 'CREATE') as can_create
from pg_namespace s
where s.nspname in ('public', 'scratch')
order by 1;

-- Expect: 8 rows, all SELECT, nothing else.
select table_name, privilege_type
from information_schema.role_table_grants
where grantee = 'csi_team' and table_schema = 'public'
order by 1, 2;

-- Expect: at least one row, for the publisher role in schema public, granting r (SELECT) to
-- csi_team. An empty result means grants will NOT survive the next publish -- redo STEP 4.
select pg_get_userbyid(defaclrole)  as applies_to_objects_created_by,
       coalesce(n.nspname, '(all)') as in_schema,
       defaclacl                    as policy
from pg_default_acl d
left join pg_namespace n on n.oid = d.defaclnamespace
order by 1, 2;
