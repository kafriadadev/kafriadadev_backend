"""Club stage three, stage-two extras, and files a club owns.

Revision ID: 0018_club_stages
Revises: 0017_club_levels
Create Date: 2026-11-03

GDOC 5.10 gives a club three stages: free, stage two (5,000 naira in the pilot) and
stage three (100,000 naira). This migration adds the third:

* ``organizations.stage`` may be 3. A stage-three club is still verified.
* ``organizations.formation`` and ``trophies`` are stage-two details, entered with the
  category, levels and age groups. ``links`` (up to five web addresses) is stage three's.
* ``identity.club_stage3_requests`` is stage three's own state machine, one per club:
  draft -> under_review (paid) -> approved or rejected, and a rejected request goes back
  to review without a second payment. ``club_stage3_decisions`` is append-only, like
  every other decision.
* A media file may belong to a club instead of an athlete (``media_files.org_id``,
  exactly one owner by CHECK), and ``club_photo`` is a new kind. Until now a club's
  document was owned by the athlete account that uploaded it, so a representative who
  signed the club up without an athlete account could not upload anything.
* ``money.payments`` accepts ``stage3_org``, which names its club like ``stage2_org``.

Additive: new columns and tables, two widened CHECKs, one NOT NULL relaxed.
"""

from __future__ import annotations

from alembic import op

revision = "0018_club_stages"
down_revision = "0017_club_levels"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE identity.organizations
            DROP CONSTRAINT organizations_stage_valid,
            ADD CONSTRAINT organizations_stage_valid CHECK (stage IN (1, 2, 3)),
            ADD COLUMN formation text,
            ADD COLUMN trophies  text,
            ADD COLUMN links     text[],
            ADD CONSTRAINT organizations_links_valid CHECK (
                links IS NULL OR cardinality(links) BETWEEN 1 AND 5
            )
        """
    )

    op.execute(
        """
        ALTER TABLE identity.media_files
            ALTER COLUMN athlete_id DROP NOT NULL,
            ADD COLUMN org_id uuid REFERENCES identity.organizations (id),
            ADD CONSTRAINT media_one_owner CHECK ((athlete_id IS NULL) <> (org_id IS NULL)),
            DROP CONSTRAINT media_kind_valid,
            ADD CONSTRAINT media_kind_valid
                CHECK (kind IN ('photo', 'document', 'club_document', 'club_photo'))
        """
    )
    op.execute(
        "CREATE INDEX media_org_idx ON identity.media_files (org_id, created_at) "
        "WHERE org_id IS NOT NULL"
    )

    op.execute(
        """
        ALTER TABLE money.payments
            DROP CONSTRAINT payments_purpose_valid,
            ADD CONSTRAINT payments_purpose_valid
                CHECK (purpose IN ('stage2_athlete', 'stage2_org', 'stage3_org')),
            DROP CONSTRAINT payments_org_matches_purpose,
            ADD CONSTRAINT payments_org_matches_purpose
                CHECK ((purpose IN ('stage2_org', 'stage3_org')) = (org_id IS NOT NULL))
        """
    )

    op.execute(
        """
        CREATE TABLE identity.club_stage3_requests (
            id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id        uuid        NOT NULL UNIQUE REFERENCES identity.organizations (id),
            status        text        NOT NULL DEFAULT 'draft',
            payment_id    uuid        UNIQUE REFERENCES money.payments (id),
            submitted_at  timestamptz,
            decided_at    timestamptz,
            created_at    timestamptz NOT NULL DEFAULT now(),
            updated_at    timestamptz NOT NULL DEFAULT now(),

            CONSTRAINT club_stage3_status_valid CHECK (
                status IN ('draft', 'under_review', 'approved', 'rejected')
            ),
            -- Nothing reaches a reviewer unpaid.
            CONSTRAINT club_stage3_needs_payment CHECK (status = 'draft' OR payment_id IS NOT NULL)
        )
        """
    )
    op.execute(
        "CREATE INDEX club_stage3_queue_idx ON identity.club_stage3_requests "
        "(submitted_at) WHERE status = 'under_review'"
    )
    op.execute(
        """
        CREATE TRIGGER club_stage3_touch_updated_at
            BEFORE UPDATE ON identity.club_stage3_requests
            FOR EACH ROW EXECUTE FUNCTION ops.touch_updated_at()
        """
    )

    op.execute(
        """
        CREATE TABLE identity.club_stage3_decisions (
            id           bigserial   PRIMARY KEY,
            request_id   uuid        NOT NULL REFERENCES identity.club_stage3_requests (id),
            decision     text        NOT NULL,
            reviewer_id  uuid        NOT NULL REFERENCES ops.users (id),
            reason       text,
            decided_at   timestamptz NOT NULL DEFAULT now(),

            CONSTRAINT club_stage3_decision_valid CHECK (decision IN ('approved', 'rejected')),
            CONSTRAINT club_stage3_reason_required CHECK (
                decision = 'approved' OR (reason IS NOT NULL AND length(btrim(reason)) > 0)
            )
        )
        """
    )
    op.execute(
        "CREATE INDEX club_stage3_decisions_request_idx ON identity.club_stage3_decisions "
        "(request_id, decided_at)"
    )
    _append_only("club_stage3_decisions")

def downgrade() -> None:
    # Loud and destructive, like the others: for a scratch database only.
    op.execute("DROP TABLE IF EXISTS identity.club_stage3_decisions")
    op.execute("DROP TABLE IF EXISTS identity.club_stage3_requests")
    # Fails, deliberately, while a stage-three payment exists: the ledger is append-only.
    op.execute(
        """
        ALTER TABLE money.payments
            DROP CONSTRAINT payments_org_matches_purpose,
            ADD CONSTRAINT payments_org_matches_purpose
                CHECK ((purpose = 'stage2_org') = (org_id IS NOT NULL)),
            DROP CONSTRAINT payments_purpose_valid,
            ADD CONSTRAINT payments_purpose_valid
                CHECK (purpose IN ('stage2_athlete', 'stage2_org'))
        """
    )
    op.execute("DELETE FROM identity.media_files WHERE org_id IS NOT NULL")
    op.execute("DROP INDEX IF EXISTS identity.media_org_idx")
    op.execute(
        """
        ALTER TABLE identity.media_files
            DROP CONSTRAINT media_one_owner,
            DROP COLUMN org_id,
            ALTER COLUMN athlete_id SET NOT NULL,
            DROP CONSTRAINT media_kind_valid,
            ADD CONSTRAINT media_kind_valid
                CHECK (kind IN ('photo', 'document', 'club_document'))
        """
    )
    op.execute("UPDATE identity.organizations SET stage = 2 WHERE stage = 3")
    op.execute(
        """
        ALTER TABLE identity.organizations
            DROP CONSTRAINT organizations_links_valid,
            DROP COLUMN links,
            DROP COLUMN trophies,
            DROP COLUMN formation,
            DROP CONSTRAINT organizations_stage_valid,
            ADD CONSTRAINT organizations_stage_valid CHECK (stage IN (1, 2))
        """
    )


def _append_only(table: str) -> None:
    """Insert-only by privilege, then by trigger: the ledger's pattern."""
    op.execute(f"REVOKE ALL ON identity.{table} FROM PUBLIC, kaf_app, kaf_money, kaf_reader")
    op.execute(f"GRANT SELECT, INSERT ON identity.{table} TO kaf_app, kaf_money")
    op.execute(f"GRANT SELECT ON identity.{table} TO kaf_reader")
    op.execute(f"GRANT USAGE ON SEQUENCE identity.{table}_id_seq TO kaf_app, kaf_money")
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

