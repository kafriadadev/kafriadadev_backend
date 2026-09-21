"""The safety net: a record of what the background jobs did, and refunds in the ledger.

Revision ID: 0008_safety_net
Revises: 0007_media_verification
Create Date: 2026-09-21

**``ops.job_runs``.** Every job that matters (reconciling payments against Paystack,
expiring stale ones, the nightly integrity check, retention sweeps) writes one row
when it finishes: which job, when, whether it was clean, and a small summary. Two
reasons. The runner asks it "when did this last run?" so a restart, or two runners,
never doubles a job or skips one. And Stage 2's exit criterion — "the nightly
integrity check is green" — needs *evidence*, not a log line somebody once saw.
Insert-only, like every record that is later used as proof.

**Refunds are recorded, never performed.** KAFRIADA cannot send money, by design.
When someone is refunded in the Paystack dashboard, the books must still match, so a
super administrator records it here as a ``reversal`` — a debit against the original
payment. The ledger's source check gains ``reversal``; the existing unique
``(payment_id, source)`` then allows exactly one reversal per payment, which is a
deliberate limit (a second refund on the same payment is a conversation, not a
button). A reversal must say who recorded it and why, by CHECK, so a hand-written row
cannot skip either.

**Outbox retention.** Delivered messages are scrubbed of their body already; the rows
are kept only as evidence a message went out. ``kaf_app`` is granted DELETE on this
one table so the retention job can remove them after 30 days (90 for failures).
Nothing else about the outbox changes.

Additive except one constraint swap on the ledger (``ledger_source_valid``): the new
constraint accepts everything the old one did, so no existing row can violate it.
"""

from __future__ import annotations

from alembic import op

revision = "0008_safety_net"
down_revision = "0007_media_verification"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE ops.job_runs (
            id           bigserial   PRIMARY KEY,
            job          text        NOT NULL,
            started_at   timestamptz NOT NULL,
            finished_at  timestamptz NOT NULL DEFAULT now(),
            ok           boolean     NOT NULL,
            summary      jsonb       NOT NULL DEFAULT '{}'::jsonb,
            CONSTRAINT job_runs_job_not_blank CHECK (length(btrim(job)) > 0)
        )
        """
    )
    op.execute("CREATE INDEX job_runs_latest_idx ON ops.job_runs (job, finished_at DESC)")
    _append_only("job_runs")

    op.execute("GRANT DELETE ON ops.outbox TO kaf_app")

    # -- a refund recorded against its payment ------------------------------
    op.execute("ALTER TABLE money.ledger_entries ADD COLUMN note text")
    op.execute(
        "ALTER TABLE money.ledger_entries "
        "ADD COLUMN recorded_by uuid REFERENCES ops.users (id)"
    )
    op.execute("ALTER TABLE money.ledger_entries DROP CONSTRAINT ledger_source_valid")
    op.execute(
        "ALTER TABLE money.ledger_entries ADD CONSTRAINT ledger_source_valid "
        "CHECK (source IN ('paystack', 'fee', 'reversal'))"
    )
    op.execute(
        """
        ALTER TABLE money.ledger_entries ADD CONSTRAINT ledger_reversal_is_accountable
            CHECK (
                source <> 'reversal'
                OR (direction = 'debit'
                    AND amount_kobo > 0
                    AND recorded_by IS NOT NULL
                    AND note IS NOT NULL AND length(btrim(note)) > 0)
            )
        """
    )


def downgrade() -> None:
    # Loud and destructive, like 0001's: for a scratch database only.
    op.execute("DROP TABLE IF EXISTS ops.job_runs")
    op.execute("REVOKE DELETE ON ops.outbox FROM kaf_app")
    op.execute("ALTER TABLE money.ledger_entries DROP CONSTRAINT IF EXISTS ledger_reversal_is_accountable")
    op.execute("ALTER TABLE money.ledger_entries DROP CONSTRAINT IF EXISTS ledger_source_valid")
    op.execute(
        "ALTER TABLE money.ledger_entries ADD CONSTRAINT ledger_source_valid "
        "CHECK (source IN ('paystack', 'fee'))"
    )
    op.execute("ALTER TABLE money.ledger_entries DROP COLUMN IF EXISTS recorded_by")
    op.execute("ALTER TABLE money.ledger_entries DROP COLUMN IF EXISTS note")


def _append_only(table: str) -> None:
    """Insert-only by privilege, then by trigger — the ledger's pattern."""
    op.execute(f"REVOKE ALL ON ops.{table} FROM PUBLIC, kaf_app, kaf_money, kaf_reader")
    op.execute(f"GRANT SELECT, INSERT ON ops.{table} TO kaf_app")
    op.execute(f"GRANT SELECT ON ops.{table} TO kaf_reader")
    op.execute(f"GRANT USAGE ON SEQUENCE ops.{table}_id_seq TO kaf_app")
    op.execute(
        f"""
        CREATE TRIGGER {table}_no_update_delete
            BEFORE UPDATE OR DELETE ON ops.{table}
            FOR EACH ROW EXECUTE FUNCTION ops.deny_mutation()
        """
    )
    op.execute(
        f"""
        CREATE TRIGGER {table}_no_truncate
            BEFORE TRUNCATE ON ops.{table}
            FOR EACH STATEMENT EXECUTE FUNCTION ops.deny_mutation()
        """
    )
