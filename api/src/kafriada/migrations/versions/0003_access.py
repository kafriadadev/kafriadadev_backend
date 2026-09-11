"""Access: each session remembers its idle window; athletes hold the athlete role.

Revision ID: 0003_access
Revises: 0002_identity_spine
Create Date: 2026-09-11

**Why a session stores its own idle window.** Staff get 30 minutes, athletes 30
days, decided by the roles held when the session was issued. Every request slides
the idle expiry forward by that window, so the window has to be on the row — the
alternative is re-deriving it from the user's roles on every request, which is a
second query per request to answer a question that was settled at sign-in. A
role change revokes the holder's sessions, so the stored window cannot go stale.

**Why athletes now hold a role.** Authorisation is table-driven: a permission is
held through a row in ``ops.user_roles`` or not at all. Registration grants the
athlete role from now on; this backfills everyone registered before it did.
"""

from __future__ import annotations

from alembic import op

revision = "0003_access"
down_revision = "0002_identity_spine"
branch_labels = None
depends_on = None

# The backfilled grants are marked with reason = 'backfill: 0003', written
# literally in each statement so the SQL reads exactly as it executes.


def upgrade() -> None:
    # Added with a default so the statement cannot fail on a table with rows in
    # it, then the default is dropped: every new session must state its window.
    op.execute(
        """
        ALTER TABLE ops.sessions
            ADD COLUMN idle_seconds integer NOT NULL DEFAULT 1800
                CONSTRAINT sessions_idle_positive CHECK (idle_seconds > 0)
        """
    )
    op.execute("ALTER TABLE ops.sessions ALTER COLUMN idle_seconds DROP DEFAULT")

    op.execute(
        """
        INSERT INTO ops.user_roles (user_id, role_code, scope_kind, scope_id, reason)
        SELECT a.user_id, 'athlete', 'global', NULL, 'backfill: 0003'
          FROM identity.athletes a
         WHERE NOT EXISTS (
                SELECT 1 FROM ops.user_roles ur
                 WHERE ur.user_id = a.user_id
                   AND ur.role_code = 'athlete'
                   AND ur.revoked_at IS NULL
         )
        """
    )
    # A grant is a state change, and every state change is audited — including
    # the ones a migration makes. One row for the batch, with the count.
    op.execute(
        """
        INSERT INTO ops.audit_log
            (actor_label, actor_role, action, subject_type, subject_id, metadata)
        SELECT 'system:migration', 'system', 'role.backfilled', 'migration', '0003_access',
               jsonb_build_object('role', 'athlete', 'grants', count(*))
          FROM ops.user_roles
         WHERE reason = 'backfill: 0003'
        """
    )


def downgrade() -> None:
    op.execute("DELETE FROM ops.user_roles WHERE reason = 'backfill: 0003'")
    op.execute("ALTER TABLE ops.sessions DROP COLUMN IF EXISTS idle_seconds")
