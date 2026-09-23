"""Athlete details the spec asks for but registration never collected (ATH-02).

Revision ID: 0009_athlete_details
Revises: 0008_safety_net
Create Date: 2026-09-22

Four columns on ``identity.athletes``, all nullable and all optional at
registration — an athlete who never fills these in is unaffected. Values are
constrained by CHECK rather than a lookup table: none of the four is likely
to grow a fifth option that needs a migration of its own, and a CHECK is one
statement instead of a table, a foreign key and a seed.

**Choices made here that the spec doesn't pin down, flagged for the project
lead to confirm before launch:** the four gender options
(male/female/other/prefer_not_to_say) and the 0–100 bound on years of
experience. Both are easy to widen later; narrowing them after real answers
exist would not be.

Purely additive — four new nullable columns and their CHECKs. No existing
row can violate a CHECK on a column it doesn't have a value for yet.
"""

from __future__ import annotations

from alembic import op

revision = "0009_athlete_details"
down_revision = "0008_safety_net"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE identity.athletes
            ADD COLUMN gender           text,
            ADD COLUMN dominant_side    text,
            ADD COLUMN secondary_sport  text,
            ADD COLUMN years_experience smallint,
            ADD CONSTRAINT athletes_gender_valid CHECK (
                gender IS NULL OR gender IN ('male', 'female', 'other', 'prefer_not_to_say')
            ),
            ADD CONSTRAINT athletes_dominant_side_valid CHECK (
                dominant_side IS NULL OR dominant_side IN ('left', 'right', 'both')
            ),
            ADD CONSTRAINT athletes_years_experience_sane CHECK (
                years_experience IS NULL OR years_experience BETWEEN 0 AND 100
            )
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE identity.athletes
            DROP COLUMN gender,
            DROP COLUMN dominant_side,
            DROP COLUMN secondary_sport,
            DROP COLUMN years_experience
        """
    )
