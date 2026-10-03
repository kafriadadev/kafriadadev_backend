"""A complete athlete record, and a confirmed email on every account.

Revision ID: 0014_full_registration
Revises: 0013_card_prints
Create Date: 2026-10-03

Registration now collects what a sports body keeps on a registered player: the name
in its parts, nationality and state of origin, a residential address, height, weight,
the highest level played, and an emergency contact. Every account also confirms its
email with a code before it can sign in, so ``ops.users`` gains ``email_verified_at``
and the code table accepts a third purpose.

The new columns are nullable in the database because rows registered before today
have no values for them. The registration service requires them for every new
athlete; the database constrains the shape of whatever is stored.

Additive: new columns, new CHECKs, and one CHECK widened.
"""

from __future__ import annotations

from alembic import op

revision = "0014_full_registration"
down_revision = "0013_card_prints"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE ops.users
            ADD COLUMN email_verified_at timestamptz,
            ADD COLUMN first_name        text,
            ADD COLUMN middle_name       text,
            ADD COLUMN surname           text
        """
    )
    op.execute(
        """
        ALTER TABLE identity.athletes
            ADD COLUMN nationality            text,
            ADD COLUMN state_of_origin        text,
            ADD COLUMN address_line           text,
            ADD COLUMN town                   text,
            ADD COLUMN height_cm              smallint,
            ADD COLUMN weight_kg              smallint,
            ADD COLUMN level_played           text,
            ADD COLUMN secondary_position     text,
            ADD COLUMN emergency_name         text,
            ADD COLUMN emergency_relationship text,
            ADD COLUMN emergency_phone        text,
            ADD CONSTRAINT athletes_height_sane CHECK (
                height_cm IS NULL OR height_cm BETWEEN 120 AND 230
            ),
            ADD CONSTRAINT athletes_weight_sane CHECK (
                weight_kg IS NULL OR weight_kg BETWEEN 35 AND 200
            ),
            ADD CONSTRAINT athletes_level_valid CHECK (
                level_played IS NULL OR level_played IN
                    ('school', 'community', 'lga', 'state', 'national', 'international')
            ),
            ADD CONSTRAINT athletes_emergency_phone_e164 CHECK (
                emergency_phone IS NULL OR emergency_phone ~ '^\\+[1-9][0-9]{7,14}$'
            )
        """
    )
    op.execute("ALTER TABLE ops.otp_codes DROP CONSTRAINT otp_purpose_valid")
    op.execute(
        """
        ALTER TABLE ops.otp_codes ADD CONSTRAINT otp_purpose_valid
            CHECK (purpose IN ('phone_verification', 'password_reset', 'email_verification'))
        """
    )


def downgrade() -> None:
    op.execute("DELETE FROM ops.otp_codes WHERE purpose = 'email_verification'")
    op.execute("ALTER TABLE ops.otp_codes DROP CONSTRAINT otp_purpose_valid")
    op.execute(
        """
        ALTER TABLE ops.otp_codes ADD CONSTRAINT otp_purpose_valid
            CHECK (purpose IN ('phone_verification', 'password_reset'))
        """
    )
    op.execute(
        """
        ALTER TABLE identity.athletes
            DROP COLUMN nationality, DROP COLUMN state_of_origin,
            DROP COLUMN address_line, DROP COLUMN town,
            DROP COLUMN height_cm, DROP COLUMN weight_kg, DROP COLUMN level_played,
            DROP COLUMN secondary_position, DROP COLUMN emergency_name,
            DROP COLUMN emergency_relationship, DROP COLUMN emergency_phone
        """
    )
    op.execute(
        """
        ALTER TABLE ops.users
            DROP COLUMN email_verified_at, DROP COLUMN first_name,
            DROP COLUMN middle_name, DROP COLUMN surname
        """
    )
