"""The permission to approve or suspend a club.

Revision ID: 0011_club_approval
Revises: 0010_clubs
Create Date: 2026-09-24

A new club starts ``pending_review`` and cannot build a roster until someone with
authority over clubs approves it. That someone is a super administrator, and this
is the permission they act under. Migration 0001 gave ``super_admin`` every
permission that existed *then*; a permission added later is not picked up, so it is
granted here explicitly.

Purely additive: one permission row and one grant.
"""

from __future__ import annotations

from alembic import op

revision = "0011_club_approval"
down_revision = "0010_clubs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "INSERT INTO ops.permissions (code, description) "
        "VALUES ('club.approve', 'Approve or suspend a club')"
    )
    op.execute(
        "INSERT INTO ops.role_permissions (role_code, permission_code) "
        "VALUES ('super_admin', 'club.approve')"
    )


def downgrade() -> None:
    op.execute("DELETE FROM ops.role_permissions WHERE permission_code = 'club.approve'")
    op.execute("DELETE FROM ops.permissions WHERE code = 'club.approve'")
