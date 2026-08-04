-- Revoke PostgREST write access from the published plan corpus.
-- 2026-08-03. Run in the Supabase SQL editor (which connects as `postgres`).
--
-- WHY THIS CANNOT BE RUN FROM THE REPO
-- -----------------------------------
-- The 8 tables are owned by `postgres`, and every grant on them was issued by `postgres`
-- (`anon=arwdDxtm/postgres` — the part after the slash is the grantor). `csi_team`, the role the
-- application and every script in this repo connects as, is NOT a member of `postgres`.
--
-- A REVOKE issued by a non-grantor does NOT raise. It silently revokes nothing and reports success.
-- Verified 2026-08-03: running the first statement below as `csi_team` returned no error and left
-- `pg_class.relacl` byte-for-byte identical. Do not "confirm" this ran by the absence of an error —
-- confirm it with the verification query at the bottom.
--
-- WHAT THIS FIXES
-- ---------------
-- `anon`, `authenticated` and `service_role` each hold INSERT/UPDATE/DELETE/TRUNCATE on all 8
-- tables of the published plan corpus. Row-level security is OFF on all of them
-- (`relrowsecurity = false`), and `public` is the schema Supabase's PostgREST exposes. So anyone
-- holding the project's anon key can truncate the corpus over HTTPS.
--
-- The grants are Supabase's own defaults (pg_default_acl oid 16492/16496), not something this repo
-- created. They apply to every table created in `public` by `postgres` — which is exactly what
-- `publish_to_supabase.py` does, so **a republish re-creates the tables and re-applies them.**
-- STEP 3 below closes that loop; without it this fix lasts until the next publish.
--
-- `service_role` is deliberately left intact: it is the key the Supabase dashboard itself uses, and
-- revoking it would break the console UI for the team.

-- ------------------------------------------------------------------------------------------------
-- STEP 1 — what the grants look like now. Run this FIRST and keep the output.
-- ------------------------------------------------------------------------------------------------
select relname, relacl::text, relrowsecurity as rls_on
from pg_class
where relnamespace = 'public'::regnamespace
  and relname in ('bucket_hierarchy','gotchas','location_intelligence','material_crosswalk',
                  'materials','plan_metrics','plans','section_taxonomy')
order by relname;

-- ------------------------------------------------------------------------------------------------
-- STEP 2 — revoke write from anon and authenticated. SELECT is left in place.
-- ------------------------------------------------------------------------------------------------
revoke insert, update, delete, truncate, references, trigger
  on all tables in schema public
  from anon, authenticated;

-- ------------------------------------------------------------------------------------------------
-- STEP 3 — stop the next republish from handing the grants straight back.
--
-- REQUIRED. Without it, `publish_to_supabase.py` drops and re-creates all 8 tables, the default ACL
-- re-applies, and this whole fix is undone silently the next time anyone publishes.
-- ------------------------------------------------------------------------------------------------
alter default privileges for role postgres in schema public
  revoke insert, update, delete, truncate, references, trigger on tables
  from anon, authenticated;

-- ------------------------------------------------------------------------------------------------
-- STEP 4 — VERIFY. Do not trust the absence of an error; check the ACL actually changed.
-- Expect `anon` and `authenticated` to read `=r/postgres` (SELECT only), and `service_role` to be
-- unchanged at `arwdDxtm/postgres`.
-- ------------------------------------------------------------------------------------------------
select relname, relacl::text
from pg_class
where relnamespace = 'public'::regnamespace
  and relname in ('bucket_hierarchy','gotchas','location_intelligence','material_crosswalk',
                  'materials','plan_metrics','plans','section_taxonomy')
order by relname;

-- Explicit privilege check — clearer to read than an ACL string.
-- Every row must show writes = false and select = true.
select t.relname,
       has_table_privilege('anon',          'public.'||t.relname, 'SELECT') as anon_select,
       has_table_privilege('anon',          'public.'||t.relname, 'INSERT') as anon_insert,
       has_table_privilege('anon',          'public.'||t.relname, 'DELETE') as anon_delete,
       has_table_privilege('anon',          'public.'||t.relname, 'TRUNCATE') as anon_truncate,
       has_table_privilege('authenticated', 'public.'||t.relname, 'INSERT') as auth_insert,
       has_table_privilege('service_role',  'public.'||t.relname, 'INSERT') as svc_insert
from pg_class t
where t.relnamespace = 'public'::regnamespace
  and t.relkind = 'r'
  and t.relname in ('bucket_hierarchy','gotchas','location_intelligence','material_crosswalk',
                    'materials','plan_metrics','plans','section_taxonomy')
order by t.relname;

-- ------------------------------------------------------------------------------------------------
-- ROLLBACK, if this turns out to break a consumer nobody knew about
-- ------------------------------------------------------------------------------------------------
-- grant insert, update, delete, truncate, references, trigger
--   on all tables in schema public to anon, authenticated;
-- alter default privileges for role postgres in schema public
--   grant insert, update, delete, truncate, references, trigger on tables to anon, authenticated;
