-- ===========================================================================
-- KAFRIADA CORE — cluster bootstrap, Supabase variant
--
-- Same privilege boundary as infra/bootstrap-roles.sql, adapted for a managed
-- Supabase project. Run once, as the project's `postgres` user:
--
--   psql "$ADMIN_URL" -v ON_ERROR_STOP=1 \
--     -v app_password="…" -v money_password="…" \
--     -v reader_password="…" -v migrate_password="…" \
--     -f infra/bootstrap-roles-supabase.sql
--
-- WHY THIS FILE EXISTS SEPARATELY
--
-- The self-hosted script ends with two statements that are correct on a
-- database we own outright and dangerous on Supabase:
--
--     REVOKE ALL ON DATABASE postgres FROM PUBLIC;
--     REVOKE ALL ON SCHEMA public FROM PUBLIC;
--
-- Supabase runs its own services inside this database — PostgREST, the auth
-- service, the dashboard's table editor — and they depend on privileges granted
-- to PUBLIC and on the `public` schema. Revoking those would break the project
-- in ways that are tedious to diagnose and easy to avoid.
--
-- WHAT WE GIVE UP, AND WHY IT DOES NOT MATTER HERE
--
-- Those revokes are defence in depth against a *different* role poking around
-- the database. They are not what creates our isolation. Our isolation comes
-- from the three schemas this application creates — identity, money, ops — which
-- are owned by kaf_migrate and granted only to the roles named below. Nothing is
-- placed in `public`, so leaving `public` at its Supabase defaults costs us
-- nothing.
--
-- The guarantee that actually matters is unchanged: the role serving ordinary
-- requests cannot write the ledger, and no role can delete an audit row.
-- ===========================================================================

\set ON_ERROR_STOP on

-- --------------------------------------------------------------------------
-- Roles. Created only if absent, so the script is safe to re-run, and the
-- password is applied every time so rotation is just a re-run.
-- --------------------------------------------------------------------------
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'kaf_migrate') THEN
        CREATE ROLE kaf_migrate LOGIN;
    END IF;
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'kaf_app') THEN
        CREATE ROLE kaf_app LOGIN;
    END IF;
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'kaf_money') THEN
        CREATE ROLE kaf_money LOGIN;
    END IF;
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'kaf_reader') THEN
        CREATE ROLE kaf_reader LOGIN;
    END IF;
END
$$;

ALTER ROLE kaf_migrate WITH PASSWORD :'migrate_password';
ALTER ROLE kaf_app     WITH PASSWORD :'app_password';
ALTER ROLE kaf_money   WITH PASSWORD :'money_password';
ALTER ROLE kaf_reader  WITH PASSWORD :'reader_password';

-- The self-hosted script sets NOSUPERUSER / NOCREATEDB / NOCREATEROLE
-- explicitly. That is not possible here: PostgreSQL requires the SUPERUSER
-- attribute to alter the SUPERUSER attribute on any role — even to remove it —
-- and Supabase's `postgres` user is deliberately not a superuser.
--
-- It is also unnecessary. CREATE ROLE grants none of those attributes unless
-- asked, so the roles above already lack all of them. What matters is that this
-- is *checked* rather than assumed, so the script verifies and fails loudly if
-- any of our roles ever gains a privilege it should not have.
DO $$
DECLARE offending text;
BEGIN
    SELECT string_agg(rolname, ', ') INTO offending
      FROM pg_roles
     WHERE rolname LIKE 'kaf\_%'
       AND (rolsuper OR rolcreatedb OR rolcreaterole OR rolreplication OR rolbypassrls);

    IF offending IS NOT NULL THEN
        RAISE EXCEPTION
            'these KAFRIADA roles hold privileges they must not have: %', offending;
    END IF;
END
$$;

-- --------------------------------------------------------------------------
-- Per-connection safety limits.
--
-- idle_in_transaction_session_timeout is the important one: an abandoned open
-- transaction holds row locks, and every registration in the state contends on
-- a single KUID counter row. Without this, one stuck client stalls sign-ups
-- for an entire LGA.
-- --------------------------------------------------------------------------
ALTER ROLE kaf_app   SET statement_timeout = '15s';
ALTER ROLE kaf_money SET statement_timeout = '15s';
ALTER ROLE kaf_app   SET idle_in_transaction_session_timeout = '30s';
ALTER ROLE kaf_money SET idle_in_transaction_session_timeout = '30s';

-- Reporting may be slower but must never write. Forcing read-only transactions
-- means a mistyped report cannot modify anything even on a writable connection.
ALTER ROLE kaf_reader SET statement_timeout = '60s';
ALTER ROLE kaf_reader SET default_transaction_read_only = on;

-- --------------------------------------------------------------------------
-- Database access. The migration role needs CREATE to build our three schemas;
-- the others only need to connect.
-- --------------------------------------------------------------------------
GRANT CONNECT ON DATABASE :"DBNAME" TO kaf_migrate, kaf_app, kaf_money, kaf_reader;
GRANT CREATE  ON DATABASE :"DBNAME" TO kaf_migrate;

-- Deliberately NOT run here — see the note at the top of this file:
--   REVOKE ALL ON DATABASE :"DBNAME" FROM PUBLIC;
--   REVOKE ALL ON SCHEMA public FROM PUBLIC;

-- --------------------------------------------------------------------------
-- Report what was created, so the operator sees the boundary rather than
-- trusting that the script did what it says.
-- --------------------------------------------------------------------------
SELECT rolname AS role,
       rolcanlogin AS can_login,
       rolsuper AS is_superuser,
       rolcreaterole AS can_create_roles
  FROM pg_roles
 WHERE rolname LIKE 'kaf\_%'
 ORDER BY rolname;
