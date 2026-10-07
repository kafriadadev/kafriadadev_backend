"""Data requests (ADM-07): a record of every export and erasure, and room to erase.

Revision ID: 0016_data_requests
Revises: 0015_club_signup
Create Date: 2026-10-07

A person may ask for a copy of what is held about them, or for it to be erased. Both
are answered by a super administrator, and each answer is a row in `ops.data_requests`:
who asked, how the request arrived, who handled it, when. Insert-only, like every
other record kept as evidence.

Erasure is anonymisation, as the privacy notice says: the person's identifying fields
are cleared and the ID, the ledger and the audit trail are kept. Two columns could not
be cleared while they were NOT NULL — the phone number and the date of birth — so both
become nullable. The phone may be empty only on an anonymised account; the date of
birth is still required at registration, in the service.

Additive: one table, two NOT NULLs relaxed, one CHECK.
"""

from __future__ import annotations

from alembic import op

revision = "0016_data_requests"
down_revision = "0015_club_signup"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE ops.data_requests (
            id            bigserial   PRIMARY KEY,
            user_id       uuid        NOT NULL REFERENCES ops.users (id),
            kind          text        NOT NULL,
            received_via  text        NOT NULL,
            note          text,
            handled_by    uuid        NOT NULL REFERENCES ops.users (id),
            handled_at    timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT data_requests_kind_valid CHECK (kind IN ('export', 'erase')),
            CONSTRAINT data_requests_via_valid CHECK (
                received_via IN ('in_person', 'phone', 'email', 'letter')
            ),
            CONSTRAINT data_requests_erase_has_note CHECK (
                kind <> 'erase' OR (note IS NOT NULL AND length(btrim(note)) > 0)
            )
        )
        """
    )
    op.execute("CREATE INDEX data_requests_user_idx ON ops.data_requests (user_id)")
    _append_only()

    op.execute("ALTER TABLE ops.users ALTER COLUMN phone_e164 DROP NOT NULL")
    op.execute(
        """
        ALTER TABLE ops.users ADD CONSTRAINT users_phone_unless_anonymised
            CHECK (phone_e164 IS NOT NULL OR anonymised_at IS NOT NULL)
        """
    )
    op.execute("ALTER TABLE identity.athletes ALTER COLUMN date_of_birth DROP NOT NULL")


def downgrade() -> None:
    # Fails, deliberately, once anyone has been anonymised: their phone and birth date
    # are gone and cannot be put back.
    op.execute("ALTER TABLE identity.athletes ALTER COLUMN date_of_birth SET NOT NULL")
    op.execute("ALTER TABLE ops.users DROP CONSTRAINT IF EXISTS users_phone_unless_anonymised")
    op.execute("ALTER TABLE ops.users ALTER COLUMN phone_e164 SET NOT NULL")
    op.execute("DROP TABLE IF EXISTS ops.data_requests")


def _append_only() -> None:
    """Insert-only by privilege, then by trigger — the ledger's pattern."""
    op.execute("REVOKE ALL ON ops.data_requests FROM PUBLIC, kaf_app, kaf_money, kaf_reader")
    op.execute("GRANT SELECT, INSERT ON ops.data_requests TO kaf_app")
    op.execute("GRANT SELECT ON ops.data_requests TO kaf_reader")
    op.execute("GRANT USAGE ON SEQUENCE ops.data_requests_id_seq TO kaf_app")
    op.execute(
        """
        CREATE TRIGGER data_requests_no_update_delete
            BEFORE UPDATE OR DELETE ON ops.data_requests
            FOR EACH ROW EXECUTE FUNCTION ops.deny_mutation()
        """
    )
    op.execute(
        """
        CREATE TRIGGER data_requests_no_truncate
            BEFORE TRUNCATE ON ops.data_requests
            FOR EACH STATEMENT EXECUTE FUNCTION ops.deny_mutation()
        """
    )
