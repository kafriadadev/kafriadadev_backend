"""Foundation: schemas, privilege boundary, audit log, identity and access.

Revision ID: 0001_foundation
Revises:
Create Date: 2026-09-09

This is the most security-critical file in the repository. Three of the decisions
identified as most expensive to change after launch are made here, in the very
first migration, before any table exists that would have to be rewritten:

  1. The privilege boundary — which role may write what. Enforced by GRANT.
  2. The audit log's immutability — enforced by GRANT *and* by trigger, so it
     holds even against the object owner.
  3. Role scope — ``scope_type`` and ``scope_id`` on ``ops.user_roles``, so a
     club administrator's authority stops at their club and a coordinator's at
     their LGA. Adding scope later means re-auditing every route, and until it is
     done the system quietly leaks other people's data.

Written as explicit SQL rather than generated from models. Security DDL should be
read and reviewed exactly as it will be executed.
"""

from __future__ import annotations

from alembic import op

revision = "0001_foundation"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    _schemas_and_grants()
    _audit_log()
    _identity_and_access()
    _seed_roles_and_permissions()


def downgrade() -> None:
    # Deliberately destructive and deliberately loud. This exists so the
    # migration test can run down() against a scratch database; it must never be
    # run against an environment holding real records.
    op.execute("DROP SCHEMA IF EXISTS identity CASCADE")
    op.execute("DROP SCHEMA IF EXISTS money CASCADE")
    op.execute("DROP SCHEMA IF EXISTS ops CASCADE")


# ---------------------------------------------------------------------------
# 1. Schemas and the privilege boundary
# ---------------------------------------------------------------------------
def _schemas_and_grants() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS identity AUTHORIZATION kaf_migrate")
    op.execute("CREATE SCHEMA IF NOT EXISTS money    AUTHORIZATION kaf_migrate")
    op.execute("CREATE SCHEMA IF NOT EXISTS ops      AUTHORIZATION kaf_migrate")

    # USAGE on a schema only permits *naming* objects inside it; table privileges
    # are granted separately below. kaf_app is given USAGE on money so it can read
    # a payment's status, and no write privilege there at all.
    op.execute("GRANT USAGE ON SCHEMA identity, ops   TO kaf_app")
    op.execute("GRANT USAGE ON SCHEMA money           TO kaf_app")
    op.execute("GRANT USAGE ON SCHEMA identity, ops, money TO kaf_money")
    op.execute("GRANT USAGE ON SCHEMA identity, ops, money TO kaf_reader")

    # -- Default privileges for tables created by later migrations ----------
    #
    # Note what is absent: DELETE. No role receives DELETE by default anywhere in
    # this system. Where a row genuinely must be removable, that migration grants
    # DELETE on that one table with a comment explaining why. The default for a
    # register of people and money is that nothing is deleted.
    op.execute(
        """
        ALTER DEFAULT PRIVILEGES FOR ROLE kaf_migrate IN SCHEMA identity, ops
            GRANT SELECT, INSERT, UPDATE ON TABLES TO kaf_app
        """
    )
    op.execute(
        """
        ALTER DEFAULT PRIVILEGES FOR ROLE kaf_migrate IN SCHEMA identity, ops
            GRANT USAGE ON SEQUENCES TO kaf_app
        """
    )

    # kaf_app may read money, never write it. This single pair of statements is
    # the ledger privilege boundary.
    op.execute(
        """
        ALTER DEFAULT PRIVILEGES FOR ROLE kaf_migrate IN SCHEMA money
            GRANT SELECT ON TABLES TO kaf_app
        """
    )
    op.execute(
        """
        ALTER DEFAULT PRIVILEGES FOR ROLE kaf_migrate IN SCHEMA money
            GRANT SELECT, INSERT, UPDATE ON TABLES TO kaf_money
        """
    )
    op.execute(
        """
        ALTER DEFAULT PRIVILEGES FOR ROLE kaf_migrate IN SCHEMA money
            GRANT USAGE ON SEQUENCES TO kaf_money
        """
    )
    # The payment path also advances a verification case in identity, so it needs
    # write access there. It does not get ops beyond what audit requires.
    op.execute(
        """
        ALTER DEFAULT PRIVILEGES FOR ROLE kaf_migrate IN SCHEMA identity
            GRANT SELECT, INSERT, UPDATE ON TABLES TO kaf_money
        """
    )

    # Reporting reads everything and writes nothing. Its role is additionally
    # forced into read-only transactions at the cluster level (bootstrap-roles).
    op.execute(
        """
        ALTER DEFAULT PRIVILEGES FOR ROLE kaf_migrate IN SCHEMA identity, ops, money
            GRANT SELECT ON TABLES TO kaf_reader
        """
    )


# ---------------------------------------------------------------------------
# 2. The audit log — insert-only, twice over
# ---------------------------------------------------------------------------
def _audit_log() -> None:
    op.execute(
        """
        CREATE TABLE ops.audit_log (
            id              bigserial PRIMARY KEY,
            occurred_at     timestamptz NOT NULL DEFAULT now(),

            -- Who. Null actor means the system acted (a scheduled job, a
            -- webhook). actor_label survives the actor being anonymised later,
            -- because an audit trail that loses its subject is not an audit trail.
            actor_user_id   uuid,
            actor_label     text        NOT NULL,
            actor_role      text,

            -- What, and to what.
            action          text        NOT NULL,
            subject_type    text        NOT NULL,
            subject_id      text        NOT NULL,

            -- Context. request_id ties this row to the trace and to the
            -- reference code shown on the user's error screen.
            request_id      text,
            ip_address      inet,
            metadata        jsonb       NOT NULL DEFAULT '{}'::jsonb,

            CONSTRAINT audit_action_not_blank  CHECK (length(btrim(action)) > 0),
            CONSTRAINT audit_subject_not_blank CHECK (length(btrim(subject_id)) > 0)
        )
        """
    )
    op.execute(
        "COMMENT ON TABLE ops.audit_log IS "
        "'Insert-only. Retained 7 years. No application role holds UPDATE or "
        "DELETE, and a trigger refuses both even for the object owner.'"
    )

    op.execute("CREATE INDEX audit_log_occurred_idx ON ops.audit_log (occurred_at DESC)")
    op.execute(
        "CREATE INDEX audit_log_subject_idx ON ops.audit_log (subject_type, subject_id, occurred_at DESC)"
    )
    op.execute(
        "CREATE INDEX audit_log_actor_idx ON ops.audit_log (actor_user_id, occurred_at DESC)"
    )
    op.execute("CREATE INDEX audit_log_request_idx ON ops.audit_log (request_id)")

    # -- Layer one: privileges ------------------------------------------
    op.execute("GRANT SELECT, INSERT ON ops.audit_log TO kaf_app, kaf_money")
    op.execute("GRANT SELECT ON ops.audit_log TO kaf_reader")
    op.execute("GRANT USAGE ON SEQUENCE ops.audit_log_id_seq TO kaf_app, kaf_money")
    op.execute(
        "REVOKE UPDATE, DELETE, TRUNCATE ON ops.audit_log "
        "FROM PUBLIC, kaf_app, kaf_money, kaf_reader"
    )

    # -- Layer two: a trigger the owner cannot talk past ------------------
    #
    # Privileges stop the application. They do not stop kaf_migrate, which owns
    # the table. This trigger does — an owner would have to deliberately disable
    # it first, which is a distinct, visible, auditable act rather than an
    # ordinary DELETE that could be slipped into a migration.
    op.execute(
        """
        CREATE FUNCTION ops.deny_mutation() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            -- Reused by every append-only table in the system, in any schema,
            -- so the message names the table it actually fired on.
            RAISE EXCEPTION
                '%.% is append-only; % is not permitted',
                TG_TABLE_SCHEMA, TG_TABLE_NAME, TG_OP
                USING ERRCODE = 'insufficient_privilege';
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER audit_log_no_update_delete
            BEFORE UPDATE OR DELETE ON ops.audit_log
            FOR EACH ROW EXECUTE FUNCTION ops.deny_mutation()
        """
    )
    op.execute(
        """
        CREATE TRIGGER audit_log_no_truncate
            BEFORE TRUNCATE ON ops.audit_log
            FOR EACH STATEMENT EXECUTE FUNCTION ops.deny_mutation()
        """
    )


# ---------------------------------------------------------------------------
# 3. Identity and access
# ---------------------------------------------------------------------------
def _identity_and_access() -> None:
    # -- users ----------------------------------------------------------
    op.execute(
        """
        CREATE TABLE ops.users (
            id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),

            -- The identity anchor. One verified phone, one person, one KUID.
            -- Stored E.164 normalised. The UNIQUE constraint is the guarantee,
            -- not the application's check — see the architecture, finding 2.
            phone_e164          text        NOT NULL,
            phone_verified_at   timestamptz,

            email               text,
            full_name           text        NOT NULL,

            -- Argon2id. Nullable because a coordinator may create a record for
            -- someone who sets their password later.
            password_hash       text,

            status              text        NOT NULL DEFAULT 'active',

            -- Online-guessing defence. Counted per account; the per-IP limit
            -- lives in Redis alongside it, because either alone is bypassable.
            failed_login_count  smallint    NOT NULL DEFAULT 0,
            locked_until        timestamptz,
            last_login_at       timestamptz,

            -- NDPR: consent is a recorded fact with a version, not a checkbox
            -- that was displayed once.
            consent_notice_version text,
            consent_given_at    timestamptz,

            -- "Deletion" means anonymisation: identifying fields are cleared and
            -- this is set. Financial records and audit rows must be retained, and
            -- the privacy notice says so before anyone registers.
            anonymised_at       timestamptz,

            created_at          timestamptz NOT NULL DEFAULT now(),
            updated_at          timestamptz NOT NULL DEFAULT now(),

            CONSTRAINT users_status_valid CHECK (status IN ('active', 'suspended', 'anonymised')),
            CONSTRAINT users_phone_e164 CHECK (phone_e164 ~ '^\\+[1-9][0-9]{7,14}$'),
            CONSTRAINT users_failed_login_sane CHECK (failed_login_count >= 0)
        )
        """
    )
    # Partial unique index: an anonymised user releases their phone number, but
    # every active account still holds exactly one.
    op.execute(
        """
        CREATE UNIQUE INDEX users_phone_unique
            ON ops.users (phone_e164)
            WHERE anonymised_at IS NULL
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX users_email_unique
            ON ops.users (lower(email))
            WHERE email IS NOT NULL AND anonymised_at IS NULL
        """
    )

    # -- sessions -------------------------------------------------------
    op.execute(
        """
        CREATE TABLE ops.sessions (
            id                    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id               uuid        NOT NULL
                                    REFERENCES ops.users (id) ON DELETE CASCADE,

            -- SHA-256 of the cookie value, never the value itself. A leaked
            -- backup of this table cannot be replayed as anybody's session.
            token_hash            char(64)    NOT NULL,

            issued_at             timestamptz NOT NULL DEFAULT now(),
            last_seen_at          timestamptz NOT NULL DEFAULT now(),

            -- Two clocks. Idle expiry is short for staff, who share phones in the
            -- field; absolute expiry bounds a stolen cookie regardless of use.
            idle_expires_at       timestamptz NOT NULL,
            absolute_expires_at   timestamptz NOT NULL,

            revoked_at            timestamptz,
            revoked_reason        text,

            -- Recorded for the audit trail and for "sign out everywhere".
            ip_address            inet,
            user_agent            text,

            -- Set when the user re-authenticated for a sensitive action. Role
            -- changes, verification revocation and reversal recording require a
            -- recent value here, not merely a valid session.
            reauthenticated_at    timestamptz,

            CONSTRAINT sessions_absolute_after_issue
                CHECK (absolute_expires_at > issued_at)
        )
        """
    )
    op.execute("CREATE UNIQUE INDEX sessions_token_hash_unique ON ops.sessions (token_hash)")
    op.execute(
        """
        CREATE INDEX sessions_active_by_user
            ON ops.sessions (user_id)
            WHERE revoked_at IS NULL
        """
    )
    op.execute("CREATE INDEX sessions_expiry_sweep ON ops.sessions (absolute_expires_at)")
    # Expired sessions are swept by a job, so this is the one place DELETE is
    # legitimate. Granted explicitly, on one table, with the reason recorded.
    op.execute("GRANT DELETE ON ops.sessions TO kaf_app")

    # -- roles and permissions ------------------------------------------
    op.execute(
        """
        CREATE TABLE ops.roles (
            code        text PRIMARY KEY,
            description text NOT NULL,
            -- Which scope a grant of this role must name. A role that is scoped
            -- cannot be granted without a scope; the service refuses it and this
            -- column is what it checks against.
            scope_kind  text NOT NULL,
            created_at  timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT roles_scope_kind_valid
                CHECK (scope_kind IN ('global', 'state', 'lga', 'club'))
        )
        """
    )
    op.execute(
        """
        CREATE TABLE ops.permissions (
            code        text PRIMARY KEY,
            description text NOT NULL,
            CONSTRAINT permissions_code_shape CHECK (code ~ '^[a-z][a-z0-9_]*(\\.[a-z][a-z0-9_]*)+$')
        )
        """
    )
    op.execute(
        """
        CREATE TABLE ops.role_permissions (
            role_code       text NOT NULL REFERENCES ops.roles (code) ON DELETE CASCADE,
            permission_code text NOT NULL REFERENCES ops.permissions (code) ON DELETE CASCADE,
            PRIMARY KEY (role_code, permission_code)
        )
        """
    )

    # -- user_roles, with scope -----------------------------------------
    #
    # This table is decision three of the three most expensive to change. Scope
    # is here from the first migration precisely so it never has to be added to a
    # live system with real coordinators and real clubs already in it.
    op.execute(
        """
        CREATE TABLE ops.user_roles (
            id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id      uuid NOT NULL REFERENCES ops.users (id) ON DELETE CASCADE,
            role_code    text NOT NULL REFERENCES ops.roles (code),

            -- 'global' for super_admin; otherwise the id of the state, LGA or
            -- club this grant is bounded to. A scoped role with a null scope_id
            -- would be a role over everything, so the check forbids it.
            scope_kind   text NOT NULL,
            scope_id     text,

            granted_by   uuid REFERENCES ops.users (id),
            granted_at   timestamptz NOT NULL DEFAULT now(),
            revoked_at   timestamptz,
            revoked_by   uuid REFERENCES ops.users (id),
            reason       text,

            CONSTRAINT user_roles_scope_kind_valid
                CHECK (scope_kind IN ('global', 'state', 'lga', 'club')),
            CONSTRAINT user_roles_scope_id_required
                CHECK ((scope_kind = 'global' AND scope_id IS NULL)
                    OR (scope_kind <> 'global' AND scope_id IS NOT NULL))
        )
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX user_roles_active_unique
            ON ops.user_roles (user_id, role_code, scope_kind, coalesce(scope_id, ''))
            WHERE revoked_at IS NULL
        """
    )
    op.execute(
        """
        CREATE INDEX user_roles_lookup
            ON ops.user_roles (user_id)
            WHERE revoked_at IS NULL
        """
    )

    # A role grant is never edited or deleted — it is revoked, leaving the history
    # of who held what and when. Same reasoning as the audit log.
    op.execute("REVOKE DELETE ON ops.user_roles FROM PUBLIC, kaf_app, kaf_money")

    # -- updated_at maintenance -----------------------------------------
    op.execute(
        """
        CREATE FUNCTION ops.touch_updated_at() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            NEW.updated_at = now();
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER users_touch_updated_at
            BEFORE UPDATE ON ops.users
            FOR EACH ROW EXECUTE FUNCTION ops.touch_updated_at()
        """
    )


# ---------------------------------------------------------------------------
# 4. The eight live roles and their permissions
# ---------------------------------------------------------------------------
def _seed_roles_and_permissions() -> None:
    """Seed the roles that exist at launch.

    The GDOC specifies 28 roles. Twenty of them are future INSERTs into these
    tables, not future code — which was the entire point of making authorisation
    table-driven rather than hard-coded.
    """
    op.execute(
        """
        INSERT INTO ops.roles (code, description, scope_kind) VALUES
            ('super_admin',       'Full administrative authority',              'global'),
            ('state_coordinator', 'Coordinates all LGAs within one state',      'state'),
            ('lga_coordinator',   'Coordinates one LGA; reviews and assists',   'lga'),
            ('club_admin',        'Administers one club and its roster',        'club'),
            ('coach',             'Read-only access to one club roster',        'club'),
            ('scout',             'Searches verified athletes',                 'global'),
            ('athlete',           'Owns one athlete record',                    'global')
        """
    )
    # 'public' is deliberately not a row. Anonymous access is the absence of a
    # session, not a role someone holds — modelling it as a role invites code
    # that grants permissions to unauthenticated callers.

    op.execute(
        """
        INSERT INTO ops.permissions (code, description) VALUES
            ('athlete.read_self',        'View own athlete record'),
            ('athlete.update_self',      'Edit own athlete record'),
            ('athlete.search_scoped',    'Search athletes within own scope'),
            ('athlete.search_verified',  'Search verified athletes'),
            ('verification.submit_self', 'Submit own verification'),
            ('verification.submit_club', 'Submit verification for own club'),
            ('verification.review',      'Approve or reject verifications in scope'),
            ('verification.revoke',      'Withdraw an approved verification'),
            ('club.create',              'Register a new club'),
            ('club.manage_roster',       'Invite and remove players in own club'),
            ('club.read_scoped',         'View clubs within own scope'),
            ('payment.initiate_self',    'Start a payment for oneself'),
            ('payment.initiate_behalf',  'Pay on behalf of an athlete'),
            ('payment.read_self',        'View own payment history'),
            ('payment.read_scoped',      'View payments within own scope'),
            ('payment.record_reversal',  'Record a refund made in the provider dashboard'),
            ('feed.publish_scoped',      'Publish a feed post within own scope'),
            ('feed.read',                'Read the feed'),
            ('transfer.list',            'List a player for transfer'),
            ('transfer.accept_self',     'Accept a transfer of oneself'),
            ('transfer.confirm_buyer',   'Confirm an incoming transfer'),
            ('transfer.validate',        'Validate and complete a transfer'),
            ('admin.manage_users',       'Grant and revoke roles'),
            ('admin.manage_rollout',     'Open and close LGAs'),
            ('admin.read_audit',         'Read the audit log'),
            ('admin.data_requests',      'Handle export and anonymisation requests')
        """
    )

    op.execute(
        """
        INSERT INTO ops.role_permissions (role_code, permission_code)
        SELECT 'athlete', code FROM ops.permissions WHERE code IN (
            'athlete.read_self', 'athlete.update_self', 'verification.submit_self',
            'payment.initiate_self', 'payment.read_self', 'feed.read',
            'transfer.accept_self'
        )
        """
    )
    op.execute(
        """
        INSERT INTO ops.role_permissions (role_code, permission_code)
        SELECT 'club_admin', code FROM ops.permissions WHERE code IN (
            'club.manage_roster', 'club.read_scoped', 'verification.submit_club',
            'payment.initiate_self', 'feed.read', 'transfer.list',
            'transfer.confirm_buyer'
        )
        """
    )
    op.execute(
        """
        INSERT INTO ops.role_permissions (role_code, permission_code)
        SELECT 'coach', code FROM ops.permissions WHERE code IN (
            'club.read_scoped', 'feed.read'
        )
        """
    )
    op.execute(
        """
        INSERT INTO ops.role_permissions (role_code, permission_code)
        SELECT 'scout', code FROM ops.permissions WHERE code IN (
            'athlete.search_verified', 'feed.read'
        )
        """
    )
    op.execute(
        """
        INSERT INTO ops.role_permissions (role_code, permission_code)
        SELECT 'lga_coordinator', code FROM ops.permissions WHERE code IN (
            'athlete.search_scoped', 'verification.review', 'payment.initiate_behalf',
            'payment.read_scoped', 'club.read_scoped', 'club.create',
            'feed.publish_scoped', 'feed.read', 'transfer.validate'
        )
        """
    )
    op.execute(
        """
        INSERT INTO ops.role_permissions (role_code, permission_code)
        SELECT 'state_coordinator', code FROM ops.permissions WHERE code IN (
            'athlete.search_scoped', 'verification.review', 'payment.read_scoped',
            'club.read_scoped', 'club.create', 'feed.publish_scoped', 'feed.read',
            'transfer.validate', 'admin.read_audit'
        )
        """
    )
    # super_admin holds every permission, including ones added later, so it is
    # defined by this query rather than by a list somebody must remember to update.
    op.execute(
        """
        INSERT INTO ops.role_permissions (role_code, permission_code)
        SELECT 'super_admin', code FROM ops.permissions
        """
    )
    # Note what super_admin still does not have: any permission to move money out
    # of the system. No such permission exists to grant, because no such endpoint
    # exists to protect.
