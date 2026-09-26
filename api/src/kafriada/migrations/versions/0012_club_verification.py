"""Club verification: a payment that names a club, and a request that follows it.

Revision ID: 0012_club_verification
Revises: 0011_club_approval
Create Date: 2026-09-25

The ₦15,000 badge for a club (CLB-04) uses the athlete money path unchanged — same
initialise, same webhook, same idempotency, same ledger — with a different price and a
different beneficiary. This migration is the beneficiary:

* ``money.payments.org_id`` names the club a ``stage2_org`` payment is for, and a CHECK
  makes the two go together: an org payment names its club, and nothing else may. The
  guard trigger treats it as an agreed field, like the amount: once a payment exists,
  what it is for cannot be edited.
* ``identity.club_verification_requests`` is the state machine, one live request per
  club (a partial unique index — only a revocation frees the slot), and it cannot leave
  ``draft`` without a document and a payment, by CHECK.
* ``identity.club_verification_decisions`` is append-only, exactly as the athlete
  decisions are, and for the same reason: a reviewer's reason is shown to the club
  verbatim and is evidence if a decision is disputed.
* ``media_files`` accepts a third kind, ``club_document``. The club's registration
  document or LGA letter is stored and re-encoded by the same pipeline as an identity
  document; it is owned by the administrator who uploaded it and linked to the club by
  the request.

Additive: new columns, tables and one widened CHECK.
"""

from __future__ import annotations

from alembic import op

revision = "0012_club_verification"
down_revision = "0011_club_approval"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE money.payments ADD COLUMN org_id uuid REFERENCES identity.organizations (id)")
    op.execute(
        "ALTER TABLE money.payments ADD CONSTRAINT payments_org_matches_purpose "
        "CHECK ((purpose = 'stage2_org') = (org_id IS NOT NULL))"
    )
    op.execute("CREATE INDEX payments_org_idx ON money.payments (org_id) WHERE org_id IS NOT NULL")
    op.execute(
        """
        CREATE OR REPLACE FUNCTION money.guard_payment() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            IF NEW.reference     IS DISTINCT FROM OLD.reference
            OR NEW.purpose       IS DISTINCT FROM OLD.purpose
            OR NEW.expected_kobo IS DISTINCT FROM OLD.expected_kobo
            OR NEW.paid_by       IS DISTINCT FROM OLD.paid_by
            OR NEW.on_behalf_of  IS DISTINCT FROM OLD.on_behalf_of
            OR NEW.coordinator_id IS DISTINCT FROM OLD.coordinator_id
            OR NEW.org_id        IS DISTINCT FROM OLD.org_id THEN
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

    op.execute("ALTER TABLE identity.media_files DROP CONSTRAINT media_kind_valid")
    op.execute(
        "ALTER TABLE identity.media_files ADD CONSTRAINT media_kind_valid "
        "CHECK (kind IN ('photo', 'document', 'club_document'))"
    )

    op.execute(
        """
        CREATE TABLE identity.club_verification_requests (
            id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id             uuid        NOT NULL REFERENCES identity.organizations (id),
            status             text        NOT NULL DEFAULT 'draft',
            document_media_id  uuid        REFERENCES identity.media_files (id),
            payment_id         uuid        REFERENCES money.payments (id),
            submitted_at       timestamptz,
            decided_at         timestamptz,
            created_at         timestamptz NOT NULL DEFAULT now(),
            updated_at         timestamptz NOT NULL DEFAULT now(),

            CONSTRAINT club_verification_status_valid CHECK (
                status IN ('draft', 'under_review', 'approved', 'rejected', 'revoked')
            ),
            -- Nothing reaches a reviewer without its document, or without payment.
            CONSTRAINT club_verification_needs_document_and_payment CHECK (
                status = 'draft' OR (document_media_id IS NOT NULL AND payment_id IS NOT NULL)
            )
        )
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX club_verification_one_live_per_club "
        "ON identity.club_verification_requests (org_id) WHERE status <> 'revoked'"
    )
    op.execute(
        "CREATE UNIQUE INDEX club_verification_payment_unique "
        "ON identity.club_verification_requests (payment_id) WHERE payment_id IS NOT NULL"
    )
    op.execute(
        "CREATE INDEX club_verification_queue_idx ON identity.club_verification_requests "
        "(submitted_at) WHERE status = 'under_review'"
    )
    op.execute(
        """
        CREATE TRIGGER club_verification_touch_updated_at
            BEFORE UPDATE ON identity.club_verification_requests
            FOR EACH ROW EXECUTE FUNCTION ops.touch_updated_at()
        """
    )

    op.execute(
        """
        CREATE TABLE identity.club_verification_decisions (
            id           bigserial   PRIMARY KEY,
            request_id   uuid        NOT NULL REFERENCES identity.club_verification_requests (id),
            decision     text        NOT NULL,
            reviewer_id  uuid        NOT NULL REFERENCES ops.users (id),
            reason       text,
            decided_at   timestamptz NOT NULL DEFAULT now(),

            CONSTRAINT club_decision_valid CHECK (decision IN ('approved', 'rejected', 'revoked')),
            CONSTRAINT club_decision_reason_required CHECK (
                decision = 'approved' OR (reason IS NOT NULL AND length(btrim(reason)) > 0)
            )
        )
        """
    )
    op.execute(
        "CREATE INDEX club_decisions_request_idx ON identity.club_verification_decisions "
        "(request_id, decided_at)"
    )
    _append_only("club_verification_decisions")


def downgrade() -> None:
    # Loud and destructive, like the others: for a scratch database only.
    op.execute("DROP TABLE IF EXISTS identity.club_verification_decisions")
    op.execute("DROP TABLE IF EXISTS identity.club_verification_requests")
    op.execute("DELETE FROM identity.media_files WHERE kind = 'club_document'")
    op.execute("ALTER TABLE identity.media_files DROP CONSTRAINT media_kind_valid")
    op.execute(
        "ALTER TABLE identity.media_files ADD CONSTRAINT media_kind_valid "
        "CHECK (kind IN ('photo', 'document'))"
    )
    op.execute("ALTER TABLE money.payments DROP CONSTRAINT IF EXISTS payments_org_matches_purpose")
    op.execute("DROP INDEX IF EXISTS money.payments_org_idx")
    op.execute("ALTER TABLE money.payments DROP COLUMN IF EXISTS org_id")
    op.execute(
        """
        CREATE OR REPLACE FUNCTION money.guard_payment() RETURNS trigger
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


def _append_only(table: str) -> None:
    """Insert-only by privilege, then by trigger — the ledger's pattern."""
    op.execute(f"REVOKE ALL ON identity.{table} FROM PUBLIC, kaf_app, kaf_money, kaf_reader")
    op.execute(f"GRANT SELECT, INSERT ON identity.{table} TO kaf_app, kaf_money")
    op.execute(f"GRANT SELECT ON identity.{table} TO kaf_reader")
    op.execute(f"GRANT USAGE ON SEQUENCE identity.{table}_id_seq TO kaf_app, kaf_money")
    op.execute(
        f"""
        CREATE TRIGGER {table}_no_update_delete
            BEFORE UPDATE OR DELETE ON identity.{table}
            FOR EACH ROW EXECUTE FUNCTION ops.deny_mutation()
        """
    )
    op.execute(
        f"""
        CREATE TRIGGER {table}_no_truncate
            BEFORE TRUNCATE ON identity.{table}
            FOR EACH STATEMENT EXECUTE FUNCTION ops.deny_mutation()
        """
    )
