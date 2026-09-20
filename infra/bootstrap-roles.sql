-- ===========================================================================
-- KAFRIADA CORE — cluster bootstrap
--
-- Creates the four PostgreSQL login roles that carry the privilege boundary
-- described in the architecture. Run ONCE per environment, by a database
-- administrator, before the first migration.
--
--   psql "$ADMIN_URL" \
--     -v app_password="$KAF_APP_PASSWORD" \
--     -v money_password="$KAF_MONEY_PASSWORD" \
--     -v reader_password="$KAF_READER_PASSWORD" \
--     -v migrate_password="$KAF_MIGRATE_PASSWORD" \
--     -f infra/bootstrap-roles.sql
--
-- Role creation is deliberately NOT part of an Alembic migration. Roles are
-- cluster-level objects with credentials attached; putting passwords in a
-- migration would put them in git history forever.
--
-- WHY FOUR ROLES
--
--   kaf_migrate  Owns every object. Holds DDL. Used only by the release step,
--                never by a running process. This is the role an attacker
--                would need, and it is not present in any running container.
--   kaf_app      Serves ordinary requests. Reads and writes identity + ops.
--                Can READ money but cannot write it.
--   kaf_money    The only role that may write the ledger. Used exclusively by
--                the payment confirmation and reconciliation code paths.
--   kaf_reader   Reporting, analytics, and the public read surface. SELECT
--                only, and pointed at the replica, so a heavy report can never
--                contend with the write path.
--
-- The guarantee this buys: a compromised application process holding the
-- kaf_app connection cannot insert a ledger row or delete an audit row,
-- because the role it is using does not have permission. That is a property of
-- the database, not a promise in the code.
-- ===========================================================================

\set ON_ERROR_STOP on

-- --------------------------------------------------------------------------
-- Roles. Created only if absent, so this script is safe to re-run.
-- ALTER ROLE ... PASSWORD is applied every time so credential rotation is just
-- a re-run with new values.
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

-- No role here needs to create databases, bypass row security, or replicate.
-- Being explicit means an accidental grant elsewhere shows up as a diff.
ALTER ROLE kaf_migrate WITH NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
ALTER ROLE kaf_app     WITH NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
ALTER ROLE kaf_money   WITH NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
ALTER ROLE kaf_reader  WITH NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;

-- --------------------------------------------------------------------------
-- Per-connection safety limits.
--
-- statement_timeout: a query that has run for 15 seconds in this system is a
-- bug or an attack, not slow work. Without it, one pathological query can hold
-- a connection and a lock indefinitely.
--
-- idle_in_transaction_session_timeout: an abandoned open transaction holds row
-- locks and blocks VACUUM. In a system whose registration path contends on a
-- single counter row, this one setting prevents a stuck client stalling every
-- registration in the state.
-- --------------------------------------------------------------------------
ALTER ROLE kaf_app   SET statement_timeout = '15s';
ALTER ROLE kaf_money SET statement_timeout = '15s';
ALTER ROLE kaf_app   SET idle_in_transaction_session_timeout = '30s';
ALTER ROLE kaf_money SET idle_in_transaction_session_timeout = '30s';

-- Reporting is allowed to be slower, but never unbounded, and it must never
-- write. Forcing the transaction to read-only means a mistyped report cannot
-- modify anything even if it somehow reached a writable connection.
ALTER ROLE kaf_reader SET statement_timeout = '60s';
ALTER ROLE kaf_reader SET default_transaction_read_only = on;

-- --------------------------------------------------------------------------
-- Lock down the database itself.
--
-- By default PostgreSQL lets every role connect to a database and create
-- objects in the public schema. Both defaults are wrong for an application
-- database and both are revoked here.
-- --------------------------------------------------------------------------
REVOKE ALL ON DATABASE :"DBNAME" FROM PUBLIC;
GRANT CONNECT ON DATABASE :"DBNAME" TO kaf_migrate, kaf_app, kaf_money, kaf_reader;

-- Migration 0001 creates the identity, ops and money schemas, and creating a
-- schema needs CREATE on the database. bootstrap-roles-supabase.sql has always
-- granted this; this file did not, so a local database built from it failed on
-- its very first migration. It went unnoticed because nobody had run the local
-- path — found the first time it was, on a machine without Docker.
GRANT CREATE ON DATABASE :"DBNAME" TO kaf_migrate;

REVOKE ALL ON SCHEMA public FROM PUBLIC;
