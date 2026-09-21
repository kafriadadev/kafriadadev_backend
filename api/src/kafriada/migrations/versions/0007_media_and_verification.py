"""Media files, verification requests, and the record of every decision.

Revision ID: 0007_media_verification
Revises: 0006_money_tables
Create Date: 2026-09-20

**What verification is.** An athlete adds a photo of their face and a photo of an
identity document, pays once, and a coordinator in their LGA decides. The badge and
the public photo are what KAFRIADA sells, so the machine below is designed around
the ways that can go wrong.

**The state machine** (``identity.verification_requests.status``):

    draft ──paid──▶ under_review ──approve──▶ approved ──withdraw──▶ revoked
                        │  ▲
                     reject  └── resubmit (against the same payment)
                        ▼
                    rejected ──third rejection──▶ escalated

``revoked`` did not exist in the original specification: it ended at ``approved``
with no way back, and the first forged document would have had no code path.
``escalated`` is where a third rejection lands: resubmission closes and a person
takes over. Resubmission is capped at three attempts because uncapped resubmission
is a free review coupon a solo reviewer cannot absorb.

**One live request per athlete**, as a partial unique index — the database, not the
code, refuses a second. ``revoked`` is the only state that frees the slot.

**Decisions are append-only.** A reviewer's reason is "kept permanently", shown to
the athlete verbatim, and is evidence if a decision is disputed. So it lives in
``verification_decisions``, which no role can update or delete (privileges, then
the same trigger as the audit log and the ledger), rather than in a column that the
next decision overwrites.

**Files are rows, objects are elsewhere.** ``media_files`` holds metadata only; the
bytes are in a private bucket. A row exists first as ``pending`` (a slot was
issued), becomes ``uploaded`` only once the object is confirmed to exist, and
``ready`` once a worker has re-encoded it and stripped its EXIF — phone photos
carry GPS coordinates, and an athlete's home must never reach a public profile.
Nothing is ever DELETEd: a document's *object* is removed 30 days after a decision
and its row records when (``deleted_at``).

Additive and self-contained: creates objects, drops nothing.
"""

from __future__ import annotations

from alembic import op

revision = "0007_media_verification"
down_revision = "0006_money_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE identity.media_files (
            id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            athlete_id    uuid        NOT NULL REFERENCES identity.athletes (id),
            kind          text        NOT NULL,
            status        text        NOT NULL DEFAULT 'pending',

            -- Where the bytes are. The original is never served; only the
            -- re-encoded derivative is, and only after a permission check.
            original_key    text      NOT NULL,
            derivative_key  text,

            -- What the client said it was sending, and what we then measured.
            declared_type   text      NOT NULL,
            declared_bytes  bigint    NOT NULL,
            size_bytes      bigint,

            created_at    timestamptz NOT NULL DEFAULT now(),
            uploaded_at   timestamptz,
            processed_at  timestamptz,
            deleted_at    timestamptz,

            CONSTRAINT media_kind_valid CHECK (kind IN ('photo', 'document')),
            CONSTRAINT media_status_valid CHECK (
                status IN ('pending', 'uploaded', 'ready', 'unreadable', 'deleted')
            ),
            CONSTRAINT media_declared_bytes_positive CHECK (declared_bytes > 0),
            CONSTRAINT media_ready_has_derivative CHECK (
                status <> 'ready' OR derivative_key IS NOT NULL
            )
        )
        """
    )
    op.execute("CREATE UNIQUE INDEX media_original_key_unique ON identity.media_files (original_key)")
    op.execute("CREATE INDEX media_athlete_idx ON identity.media_files (athlete_id, created_at DESC)")
    # The worker's queue: things confirmed to exist that nobody has processed.
    op.execute(
        "CREATE INDEX media_to_process_idx ON identity.media_files (uploaded_at) "
        "WHERE status = 'uploaded'"
    )

    op.execute(
        """
        CREATE TABLE identity.verification_requests (
            id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            athlete_id         uuid        NOT NULL REFERENCES identity.athletes (id),
            status             text        NOT NULL DEFAULT 'draft',

            photo_media_id     uuid        REFERENCES identity.media_files (id),
            document_media_id  uuid        REFERENCES identity.media_files (id),

            -- The one payment that covers every attempt. A rejected athlete does
            -- not pay again.
            payment_id         uuid        REFERENCES money.payments (id),

            attempt            smallint    NOT NULL DEFAULT 1,
            submitted_at       timestamptz,
            decided_at         timestamptz,

            created_at         timestamptz NOT NULL DEFAULT now(),
            updated_at         timestamptz NOT NULL DEFAULT now(),

            CONSTRAINT verification_status_valid CHECK (
                status IN ('draft', 'under_review', 'approved', 'rejected',
                           'escalated', 'revoked')
            ),
            CONSTRAINT verification_attempt_capped CHECK (attempt BETWEEN 1 AND 3),
            -- Nothing reaches a reviewer, or the public, without both files.
            CONSTRAINT verification_needs_files CHECK (
                status = 'draft'
                OR (photo_media_id IS NOT NULL AND document_media_id IS NOT NULL)
            ),
            -- Nothing is under review that was not paid for.
            CONSTRAINT verification_needs_payment CHECK (
                status = 'draft' OR payment_id IS NOT NULL
            )
        )
        """
    )
    # At most one live request per athlete; only a withdrawal frees the slot.
    op.execute(
        "CREATE UNIQUE INDEX verification_one_live_per_athlete "
        "ON identity.verification_requests (athlete_id) WHERE status <> 'revoked'"
    )
    op.execute(
        "CREATE UNIQUE INDEX verification_payment_unique "
        "ON identity.verification_requests (payment_id) WHERE payment_id IS NOT NULL"
    )
    # The review queue: oldest waiting first.
    op.execute(
        "CREATE INDEX verification_queue_idx ON identity.verification_requests (submitted_at) "
        "WHERE status = 'under_review'"
    )
    op.execute(
        """
        CREATE TRIGGER verification_touch_updated_at
            BEFORE UPDATE ON identity.verification_requests
            FOR EACH ROW EXECUTE FUNCTION ops.touch_updated_at()
        """
    )

    op.execute(
        """
        CREATE TABLE identity.verification_decisions (
            id           bigserial   PRIMARY KEY,
            request_id   uuid        NOT NULL REFERENCES identity.verification_requests (id),
            attempt      smallint    NOT NULL,
            decision     text        NOT NULL,
            -- Null only for the automatic escalation, which no person decided.
            reviewer_id  uuid        REFERENCES ops.users (id),
            -- Mandatory for a rejection and a withdrawal, and shown to the
            -- athlete exactly as written.
            reason       text,
            decided_at   timestamptz NOT NULL DEFAULT now(),

            CONSTRAINT decision_valid CHECK (
                decision IN ('approved', 'rejected', 'escalated', 'revoked')
            ),
            CONSTRAINT decision_reason_required CHECK (
                decision NOT IN ('rejected', 'revoked')
                OR (reason IS NOT NULL AND length(btrim(reason)) > 0)
            ),
            CONSTRAINT decision_reviewer_required CHECK (
                decision = 'escalated' OR reviewer_id IS NOT NULL
            )
        )
        """
    )
    op.execute(
        "CREATE INDEX decisions_request_idx ON identity.verification_decisions "
        "(request_id, decided_at)"
    )
    _append_only("verification_decisions")

    # The payment path moves a paid draft to under_review in the same transaction
    # that writes the ledger (0001 already gives kaf_money write access to
    # identity). It has no business with the media table beyond reading it.
    op.execute("REVOKE INSERT, UPDATE ON identity.media_files FROM kaf_money")


def downgrade() -> None:
    # Loud and destructive, like 0001's: for a scratch database only.
    op.execute("DROP TABLE IF EXISTS identity.verification_decisions")
    op.execute("DROP TABLE IF EXISTS identity.verification_requests")
    op.execute("DROP TABLE IF EXISTS identity.media_files")


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
