"""The money tables: payments, the ledger, and the webhook idempotency record.

Revision ID: 0006_money_tables
Revises: 0005_rate_limits
Create Date: 2026-09-20

**Ledger lines belong to the payment.** There are no per-athlete wallets: a
payment's gross amount and the provider's fee are facts about the platform, not
an athlete's balance. A wallet arrives when something needs a balance.

**Three tables, two of them insert-only.**

  money.payments        one row per attempt to pay. The only one that is edited,
                        and only along the status machine in ``payments.rules``.
  money.ledger_entries  what a settled payment is worth. Exactly two lines per
                        payment, enforced by a unique (payment_id, source) so that
                        "exactly two" is a property of the schema, not a hope.
  money.webhook_events  one row per provider delivery already acted on. Its
                        primary key *is* the duplicate check: the settlement
                        service does ``INSERT ... ON CONFLICT DO NOTHING
                        RETURNING`` and only the delivery that gets a row back
                        may write anything.

**Why the explicit REVOKE.** ``0001`` grants ``kaf_money`` SELECT, INSERT and
UPDATE on every table in ``money`` by default, which is right for ``payments`` and
wrong for a ledger. Privileges stop the application; a trigger stops the object
owner too, which is the same two-layer pattern as ``ops.audit_log``. Correcting a
ledger is done by writing a new line, never by editing an old one.

Self-contained and additive: it creates objects and drops nothing, so applying it
to a database that already holds users and athletes is safe.
"""

from __future__ import annotations

from alembic import op

revision = "0006_money_tables"
down_revision = "0005_rate_limits"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE money.payments (
            id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),

            -- Ours, KAF-{uuid4}. What Paystack echoes back, and the only way a
            -- webhook finds its payment. Shape is checked here as well as in
            -- payments.rules so a hand-written row cannot carry a stranger's id.
            reference       text        NOT NULL,

            purpose         text        NOT NULL,

            -- The price at the moment the intent was created, in kobo. The
            -- webhook is compared against THIS, never against what the provider
            -- says was paid and never against today's configuration.
            expected_kobo   bigint      NOT NULL,

            status          text        NOT NULL DEFAULT 'pending',

            -- Who pressed pay.
            paid_by         uuid        NOT NULL REFERENCES ops.users (id),
            -- The athlete it is for when that is someone other than the payer;
            -- null when a person pays for their own record.
            on_behalf_of    uuid        REFERENCES identity.athletes (id),
            -- Set only for an assisted (cash) payment recorded by a coordinator.
            coordinator_id  uuid        REFERENCES ops.users (id),

            created_at      timestamptz NOT NULL DEFAULT now(),
            updated_at      timestamptz NOT NULL DEFAULT now(),

            CONSTRAINT payments_reference_shape CHECK (
                reference ~ '^KAF-[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
            ),
            CONSTRAINT payments_purpose_valid
                CHECK (purpose IN ('stage2_athlete', 'stage2_org')),
            CONSTRAINT payments_expected_positive CHECK (expected_kobo > 0),
            -- 'frozen' is beyond the specification's four: "freeze and alert"
            -- needs somewhere to put money that is neither settled nor failed.
            CONSTRAINT payments_status_valid CHECK (
                status IN ('pending', 'success', 'failed', 'abandoned', 'frozen')
            )
        )
        """
    )
    op.execute("CREATE UNIQUE INDEX payments_reference_unique ON money.payments (reference)")
    op.execute("CREATE INDEX payments_paid_by_idx ON money.payments (paid_by, created_at DESC)")
    op.execute(
        "CREATE INDEX payments_on_behalf_of_idx ON money.payments (on_behalf_of) "
        "WHERE on_behalf_of IS NOT NULL"
    )
    # The 72-hour abandon sweep looks for old pending rows.
    op.execute("CREATE INDEX payments_pending_idx ON money.payments (created_at) WHERE status = 'pending'")
    op.execute(
        """
        CREATE TRIGGER payments_touch_updated_at
            BEFORE UPDATE ON money.payments
            FOR EACH ROW EXECUTE FUNCTION ops.touch_updated_at()
        """
    )

    # What a payment may not become, whoever asks. The status machine lives in
    # payments.rules; this is the part of it the database can hold on its own.
    op.execute(
        """
        CREATE FUNCTION money.guard_payment() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            IF NEW.reference     IS DISTINCT FROM OLD.reference
            OR NEW.purpose       IS DISTINCT FROM OLD.purpose
            OR NEW.expected_kobo IS DISTINCT FROM OLD.expected_kobo
            OR NEW.paid_by       IS DISTINCT FROM OLD.paid_by
            OR NEW.on_behalf_of  IS DISTINCT FROM OLD.on_behalf_of
            OR NEW.coordinator_id IS DISTINCT FROM OLD.coordinator_id THEN
                RAISE EXCEPTION 'money.payments: what was agreed to be paid is immutable'
                    USING ERRCODE = 'insufficient_privilege';
            END IF;
            IF OLD.status = 'success' AND NEW.status <> 'success' THEN
                RAISE EXCEPTION 'money.payments: a settled payment is final'
                    USING ERRCODE = 'insufficient_privilege';
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER payments_guard
            BEFORE UPDATE ON money.payments
            FOR EACH ROW EXECUTE FUNCTION money.guard_payment()
        """
    )

    op.execute(
        """
        CREATE TABLE money.ledger_entries (
            id            bigserial   PRIMARY KEY,
            payment_id    uuid        NOT NULL REFERENCES money.payments (id),
            direction     text        NOT NULL,
            source        text        NOT NULL,
            amount_kobo   bigint      NOT NULL,
            created_at    timestamptz NOT NULL DEFAULT now(),

            CONSTRAINT ledger_direction_valid CHECK (direction IN ('credit', 'debit')),
            -- 'reward' and 'reversal' arrive with the features that need them.
            CONSTRAINT ledger_source_valid    CHECK (source IN ('paystack', 'fee')),
            -- Zero is allowed: a waived provider fee is real.
            CONSTRAINT ledger_amount_sane     CHECK (amount_kobo >= 0),
            -- "Exactly two lines per payment" as structure: one gross, one fee.
            CONSTRAINT ledger_one_line_per_source UNIQUE (payment_id, source)
        )
        """
    )
    op.execute(
        "COMMENT ON TABLE money.ledger_entries IS "
        "'Insert-only. Only kaf_money may write it, and no role may update or delete: "
        "a correction is a new line. A trigger refuses both even for the object owner.'"
    )

    op.execute(
        """
        CREATE TABLE money.webhook_events (
            provider     text        NOT NULL,
            -- "<event>:<reference>" for Paystack. Its uniqueness is the duplicate
            -- check, so it must be decided by the database, not by a read.
            event_key    text        NOT NULL,
            payment_id   uuid        NOT NULL REFERENCES money.payments (id),
            received_at  timestamptz NOT NULL DEFAULT now(),

            PRIMARY KEY (provider, event_key),
            CONSTRAINT webhook_provider_valid CHECK (provider IN ('paystack'))
        )
        """
    )

    _make_append_only("ledger_entries", "kaf_money")
    _make_append_only("webhook_events", "kaf_money")

    # Only the money role writes payments. kaf_app reads (0001 defaults) and is
    # refused an INSERT by the absence of a grant; say so out loud as well.
    op.execute("REVOKE INSERT, UPDATE ON money.payments FROM PUBLIC, kaf_app, kaf_reader")
    op.execute("GRANT USAGE ON SEQUENCE money.ledger_entries_id_seq TO kaf_money")


def downgrade() -> None:
    # Loud and destructive, like 0001's: for a scratch database only.
    op.execute("DROP TABLE IF EXISTS money.webhook_events")
    op.execute("DROP TABLE IF EXISTS money.ledger_entries")
    op.execute("DROP TABLE IF EXISTS money.payments")
    op.execute("DROP FUNCTION IF EXISTS money.guard_payment()")


def _make_append_only(table: str, writer: str) -> None:
    """Insert-only, twice over: by privilege, then by trigger.

    Written as an explicit allow-list — take everything away, give back SELECT and
    INSERT to the one writer and SELECT to readers — so a privilege added to the
    defaults later cannot leak in. The trigger is what holds against the object
    owner (``kaf_migrate``), which privileges do not.
    """
    op.execute(f"REVOKE ALL ON money.{table} FROM PUBLIC, kaf_app, kaf_money, kaf_reader")
    op.execute(f"GRANT SELECT, INSERT ON money.{table} TO {writer}")
    op.execute(f"GRANT SELECT ON money.{table} TO kaf_app, kaf_reader")
    op.execute(
        f"""
        CREATE TRIGGER {table}_no_update_delete
            BEFORE UPDATE OR DELETE ON money.{table}
            FOR EACH ROW EXECUTE FUNCTION ops.deny_mutation()
        """
    )
    op.execute(
        f"""
        CREATE TRIGGER {table}_no_truncate
            BEFORE TRUNCATE ON money.{table}
            FOR EACH STATEMENT EXECUTE FUNCTION ops.deny_mutation()
        """
    )
