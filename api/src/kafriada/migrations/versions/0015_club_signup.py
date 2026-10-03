"""A club's full record, and its own sign-up.

Revision ID: 0015_club_signup
Revises: 0014_full_registration
Create Date: 2026-10-03

A club now signs up through its own public form: the representative's account and the
club are created together, and the club waits as ``unconfirmed`` until the
representative confirms their email. Only then does it reach an administrator as
``pending_review``.

``identity.organizations`` gains what a sports body records about a club: short name,
category, age groups, level, home ground, official email, registration number,
affiliation, colours, website, the representative's role, and a second official.
Nullable in the database for clubs registered before today; the service requires them
for every new club.

Athlete accounts lose ``club.create``, granted to them in 0010: a club is no longer
registered from inside an athlete's account. Coordinators and administrators keep it.
"""

from __future__ import annotations

from alembic import op

revision = "0015_club_signup"
down_revision = "0014_full_registration"
branch_labels = None
depends_on = None

# The one row deleted is the athlete role's club.create permission, granted in 0010. No
# user data is removed; the project lead asked on 2026-10-03 that clubs sign up separately.
DESTRUCTIVE_MIGRATION_APPROVED = (
    "removes one role_permissions row (athlete, club.create); project lead, 2026-10-03"
)


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE identity.organizations
            ADD COLUMN short_name      text,
            ADD COLUMN category        text,
            ADD COLUMN age_groups      text[],
            ADD COLUMN level           text,
            ADD COLUMN ground_name     text,
            ADD COLUMN ground_address  text,
            ADD COLUMN town            text,
            ADD COLUMN club_email      text,
            ADD COLUMN cac_number      text,
            ADD COLUMN affiliation     text,
            ADD COLUMN colours         text,
            ADD COLUMN website         text,
            ADD COLUMN rep_role        text,
            ADD COLUMN official2_name  text,
            ADD COLUMN official2_role  text,
            ADD COLUMN official2_phone text,
            ADD CONSTRAINT organizations_category_valid CHECK (
                category IS NULL OR category IN ('men', 'women', 'mixed')
            ),
            ADD CONSTRAINT organizations_age_groups_valid CHECK (
                age_groups IS NULL OR (
                    cardinality(age_groups) > 0
                    AND age_groups <@ ARRAY['senior', 'u20', 'u17', 'u15', 'u13']::text[]
                )
            ),
            ADD CONSTRAINT organizations_level_valid CHECK (
                level IS NULL OR level IN ('grassroots', 'amateur', 'semi_pro', 'professional')
            ),
            ADD CONSTRAINT organizations_official2_phone_e164 CHECK (
                official2_phone IS NULL OR official2_phone ~ '^\\+[1-9][0-9]{7,14}$'
            )
        """
    )
    op.execute("ALTER TABLE identity.organizations DROP CONSTRAINT organizations_status_valid")
    op.execute(
        """
        ALTER TABLE identity.organizations ADD CONSTRAINT organizations_status_valid
            CHECK (status IN ('unconfirmed', 'pending_review', 'approved', 'suspended'))
        """
    )
    op.execute(
        "DELETE FROM ops.role_permissions "
        "WHERE role_code = 'athlete' AND permission_code = 'club.create'"
    )


def downgrade() -> None:
    op.execute(
        """
        INSERT INTO ops.role_permissions (role_code, permission_code)
        VALUES ('athlete', 'club.create') ON CONFLICT DO NOTHING
        """
    )
    op.execute(
        "UPDATE identity.organizations SET status = 'pending_review' WHERE status = 'unconfirmed'"
    )
    op.execute("ALTER TABLE identity.organizations DROP CONSTRAINT organizations_status_valid")
    op.execute(
        """
        ALTER TABLE identity.organizations ADD CONSTRAINT organizations_status_valid
            CHECK (status IN ('pending_review', 'approved', 'suspended'))
        """
    )
    op.execute(
        """
        ALTER TABLE identity.organizations
            DROP COLUMN short_name, DROP COLUMN category, DROP COLUMN age_groups,
            DROP COLUMN level, DROP COLUMN ground_name, DROP COLUMN ground_address,
            DROP COLUMN town, DROP COLUMN club_email, DROP COLUMN cac_number,
            DROP COLUMN affiliation, DROP COLUMN colours, DROP COLUMN website,
            DROP COLUMN rep_role, DROP COLUMN official2_name, DROP COLUMN official2_role,
            DROP COLUMN official2_phone
        """
    )
