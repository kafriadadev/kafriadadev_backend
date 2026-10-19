"""A club may play at up to two levels.

Revision ID: 0017_club_levels
Revises: 0016_data_requests
Create Date: 2026-10-19

A club often fields a grassroots side and an amateur-league side at once, so the
single `level` becomes `levels`, one or two of the same four values. Existing rows are
copied across. `level` is left in place, unread, so this upgrade loses nothing; a
later migration may drop it.

Category, levels and age groups are no longer asked at sign-up: they are collected
before the stage-two verification. All three columns were already nullable.

Additive: one column, one CHECK, one backfill.
"""

from __future__ import annotations

from alembic import op

revision = "0017_club_levels"
down_revision = "0016_data_requests"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE identity.organizations
            ADD COLUMN levels text[],
            ADD CONSTRAINT organizations_levels_valid CHECK (
                levels IS NULL OR (
                    cardinality(levels) BETWEEN 1 AND 2
                    AND levels <@ ARRAY['grassroots', 'amateur', 'semi_pro', 'professional']::text[]
                )
            )
        """
    )
    op.execute("UPDATE identity.organizations SET levels = ARRAY[level] WHERE level IS NOT NULL")


def downgrade() -> None:
    op.execute(
        "UPDATE identity.organizations SET level = levels[1] "
        "WHERE level IS NULL AND levels IS NOT NULL"
    )
    op.execute(
        """
        ALTER TABLE identity.organizations
            DROP CONSTRAINT organizations_levels_valid,
            DROP COLUMN levels
        """
    )
