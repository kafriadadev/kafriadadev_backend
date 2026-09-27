"""A record of which wallet cards a coordinator has printed (CRD-06).

Revision ID: 0013_card_prints
Revises: 0012_club_verification
Create Date: 2026-09-27

Bulk printing turns a registration drive into a stack of cards, and "not yet printed" is
the list that keeps a second coordinator from printing the same hundred again. So each
print is a row: which athlete, who printed it, when. It is insert-only, like every other
record that is later used as evidence: a reprint is a new row, never an edit, and
"not yet printed" simply means no row.

Additive: one table.
"""

from __future__ import annotations

from alembic import op

revision = "0013_card_prints"
down_revision = "0012_club_verification"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE identity.card_prints (
            id          bigserial   PRIMARY KEY,
            athlete_id  uuid        NOT NULL REFERENCES identity.athletes (id),
            printed_by  uuid        NOT NULL REFERENCES ops.users (id),
            printed_at  timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX card_prints_athlete_idx ON identity.card_prints (athlete_id)")
    _append_only("card_prints")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS identity.card_prints")


def _append_only(table: str) -> None:
    """Insert-only by privilege, then by trigger — the ledger's pattern."""
    op.execute(f"REVOKE ALL ON identity.{table} FROM PUBLIC, kaf_app, kaf_money, kaf_reader")
    op.execute(f"GRANT SELECT, INSERT ON identity.{table} TO kaf_app")
    op.execute(f"GRANT SELECT ON identity.{table} TO kaf_reader")
    op.execute(f"GRANT USAGE ON SEQUENCE identity.{table}_id_seq TO kaf_app")
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
