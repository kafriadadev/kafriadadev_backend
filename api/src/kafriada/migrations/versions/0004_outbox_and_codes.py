"""The transactional outbox, and one-time codes.

Revision ID: 0004_outbox_and_codes
Revises: 0003_access
Create Date: 2026-09-12

**Why an outbox and not a queue.** A broker cannot join a database transaction,
which produces the oldest bug in event-driven systems: the record commits and
the send fails, so the thing happened and nobody was told — or the send succeeds
and the transaction rolls back, so the world is told about something that never
happened. A row in this table is written by the same COMMIT as the record it
belongs to. Delivery is then a retry loop over a table that survives every
worker being dead for six hours, and that can be inspected with SQL.

**Why codes are hashed, and keyed.** Six digits is a million possibilities, so a
plain digest of one is reversible with a lookup table anybody can build. The
digest is an HMAC keyed with a server-held pepper, so a stolen copy of this
table does not reveal the codes in flight — the key is not in the database.

**What is deliberately not solved here.** Between the moment a code is queued
and the moment it is sent, the message body — which contains the code — sits in
``ops.outbox.payload``. The worker scrubs it on delivery, and codes live ten
minutes. Encrypting a payload the worker must be able to read would move the
problem, not remove it.
"""

from __future__ import annotations

from alembic import op

revision = "0004_outbox_and_codes"
down_revision = "0003_access"
branch_labels = None
depends_on = None


def upgrade() -> None:
    _outbox()
    _otp_codes()


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS ops.otp_codes")
    op.execute("DROP TABLE IF EXISTS ops.outbox")


def _outbox() -> None:
    op.execute(
        """
        CREATE TABLE ops.outbox (
            id            bigserial PRIMARY KEY,

            -- Past tense, like an audit action: this is a record of something
            -- that happened, which a worker then acts on.
            event_type    text        NOT NULL,
            payload       jsonb       NOT NULL,

            -- The retry clock. A worker only sees rows whose time has come, so
            -- backoff is an UPDATE rather than a sleeping thread.
            available_at  timestamptz NOT NULL DEFAULT now(),
            attempts      smallint    NOT NULL DEFAULT 0,
            last_error    text,

            processed_at  timestamptz,
            -- Set when the attempts are exhausted. A failed row is kept: an
            -- athlete who never received a code is a support case, and the row
            -- is the evidence of what was tried.
            failed_at     timestamptz,

            created_at    timestamptz NOT NULL DEFAULT now(),

            CONSTRAINT outbox_event_type_not_blank CHECK (length(btrim(event_type)) > 0),
            CONSTRAINT outbox_attempts_sane CHECK (attempts >= 0)
        )
        """
    )
    op.execute(
        "COMMENT ON TABLE ops.outbox IS "
        "'Transactional outbox. Written in the same transaction as the record it "
        "belongs to; drained by a worker with FOR UPDATE SKIP LOCKED.'"
    )
    # The worker's query, and nothing else, decides this index.
    op.execute(
        """
        CREATE INDEX outbox_due
            ON ops.outbox (available_at, id)
            WHERE processed_at IS NULL AND failed_at IS NULL
        """
    )
    op.execute("CREATE INDEX outbox_unprocessed ON ops.outbox (created_at DESC)")

    # The worker marks rows done and scrubs delivered payloads, so it needs
    # UPDATE — which the default privileges already grant. DELETE is not granted:
    # rows are evidence, and are pruned by a retention job, not by the app.
    op.execute("GRANT SELECT, INSERT, UPDATE ON ops.outbox TO kaf_app, kaf_money")
    op.execute("GRANT USAGE ON SEQUENCE ops.outbox_id_seq TO kaf_app, kaf_money")


def _otp_codes() -> None:
    op.execute(
        """
        CREATE TABLE ops.otp_codes (
            id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id       uuid        NOT NULL REFERENCES ops.users (id) ON DELETE CASCADE,

            -- What the code lets someone do. A code sent to confirm a phone
            -- must never be accepted as a password reset, so the purpose is
            -- part of the lookup, not a note.
            purpose       text        NOT NULL,

            -- HMAC-SHA256 of the digits, keyed with a server-held pepper.
            code_hash     char(64)    NOT NULL,

            expires_at    timestamptz NOT NULL,
            attempts      smallint    NOT NULL DEFAULT 0,
            consumed_at   timestamptz,
            -- Set when the attempts run out, so a burned code cannot be retried
            -- by waiting; a new one has to be sent.
            voided_at     timestamptz,

            sent_to       text        NOT NULL,     -- E.164 at the time of sending
            ip_address    inet,
            created_at    timestamptz NOT NULL DEFAULT now(),

            CONSTRAINT otp_purpose_valid
                CHECK (purpose IN ('phone_verification', 'password_reset')),
            CONSTRAINT otp_attempts_sane CHECK (attempts >= 0)
        )
        """
    )
    # At most one live code per person per purpose: sending a new one voids the
    # old, so "the last code you were sent" is never ambiguous.
    op.execute(
        """
        CREATE UNIQUE INDEX otp_one_live_per_purpose
            ON ops.otp_codes (user_id, purpose)
            WHERE consumed_at IS NULL AND voided_at IS NULL
        """
    )
    op.execute(
        "CREATE INDEX otp_recent_sends ON ops.otp_codes (user_id, purpose, created_at DESC)"
    )
    op.execute("GRANT SELECT, INSERT, UPDATE ON ops.otp_codes TO kaf_app")
