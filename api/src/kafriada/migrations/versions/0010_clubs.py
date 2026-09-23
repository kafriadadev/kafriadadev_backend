"""Clubs: organizations, teams, roster members.

Revision ID: 0010_clubs
Revises: 0009_athlete_details
Create Date: 2026-09-23

**Three tables, one schema, matching the pilot build spec.** ``organizations``
is the club itself (free to register, ``pending_review`` until an admin
approves it, ``stage`` 1 until a ₦15,000 payment moves it to 2 — the same two
gates the wireframes describe, kept as two independent columns because
"approved enough to build a roster" and "paid for the verified badge" are not
the same fact). ``teams`` groups a roster by squad, sport, age category and
gender, exactly as the spec asks — even though Slice 1's screens (CLB-02,
CLB-03) never expose team selection and only ever act on the one team a club
gets at registration. That gap is registration's to close, not this table's:
a single default team is created alongside every organization, so the schema
already supports multiple squads whenever a wireframe needs one.

**The membership rule is stronger than a per-team unique index.** The pilot
build spec sketches ``(team_id, athlete_id)`` uniqueness for an active row;
``docs/TODO.md`` asks for *at-most-one-open-membership*, which is the rule
CLB-03 actually describes — accepting an invitation "moves" a player from
one club to another, so an athlete can be ``active`` on at most one roster in
the whole system, not one per team. That is a partial unique index on
``athlete_id`` alone, enforced by the database rather than a service-layer
check that a second write path could miss. A pending ``invited`` row is
scoped per team instead: nothing stops two different clubs from inviting the
same athlete at once (CLB-03's "currently at another club" state is a warning,
not a refusal), but the same club cannot queue the same invitation twice.

**``club.create`` moves to the ``athlete`` role.** Migration 0001 seeded it
only for ``lga_coordinator``/``state_coordinator``, written before clubs
existed and before the wireframes settled on "any signed-in user may
register a club" (CLB-01). Every account already holds ``athlete`` — it is
the one role registration always grants — so this is the literal reading of
that requirement, not a new global role. Coordinators keep the permission
too: entering a club by hand is CLB-01's own stated fallback if the
self-service screen has to be cut.

**``identity.career_events.club_id`` gets its foreign key.** 0002 left it
bare on purpose, with a comment that it would arrive "once the clubs context
exists" — it does now, so the column is finally checked against something.

Additive and self-contained: creates objects, adds one FK and one permission
grant, drops nothing.
"""

from __future__ import annotations

from alembic import op

revision = "0010_clubs"
down_revision = "0009_athlete_details"
branch_labels = None
depends_on = None


def upgrade() -> None:
    _organizations()
    _teams()
    _roster_members()
    _career_events_fk()
    _club_create_for_athletes()


def downgrade() -> None:
    op.execute(
        "ALTER TABLE identity.career_events DROP CONSTRAINT IF EXISTS career_events_club_fk"
    )
    op.execute(
        "DELETE FROM ops.role_permissions "
        "WHERE role_code = 'athlete' AND permission_code = 'club.create'"
    )
    op.execute("DROP TABLE IF EXISTS identity.roster_members")
    op.execute("DROP TABLE IF EXISTS identity.teams")
    op.execute("DROP TABLE IF EXISTS identity.organizations")


def _organizations() -> None:
    op.execute(
        """
        CREATE TABLE identity.organizations (
            id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),

            name           text        NOT NULL,
            type           text        NOT NULL DEFAULT 'club',
            sport          text        NOT NULL,
            year_founded   smallint,

            state_id       text        NOT NULL REFERENCES ops.locations (id),
            lga_id         text        NOT NULL REFERENCES ops.locations (id),
            contact_phone  text        NOT NULL,

            -- The user who registered the club. Additional admins and coaches
            -- are ordinary ops.user_roles grants scoped to this row's id, the
            -- same shape as an lga_coordinator's grant on an LGA; this column
            -- just names the founder for a quick "administered by" display.
            rep_user_id    uuid        NOT NULL REFERENCES ops.users (id),

            -- Whether the club may build a roster at all. An admin's decision,
            -- separate from the paid badge below.
            status         text        NOT NULL DEFAULT 'pending_review',
            -- 1 until the ₦15,000 verification payment settles; 2 after. Not
            -- a boolean because the spec already calls it a stage, and a
            -- second paid tier is exactly the kind of change a boolean forbids.
            stage          smallint    NOT NULL DEFAULT 1,

            created_at     timestamptz NOT NULL DEFAULT now(),
            updated_at     timestamptz NOT NULL DEFAULT now(),

            CONSTRAINT organizations_type_valid CHECK (
                type IN ('club', 'academy', 'school', 'other')
            ),
            CONSTRAINT organizations_status_valid CHECK (
                status IN ('pending_review', 'approved', 'suspended')
            ),
            CONSTRAINT organizations_stage_valid CHECK (stage IN (1, 2)),
            CONSTRAINT organizations_contact_phone_e164 CHECK (
                contact_phone ~ '^\\+[1-9][0-9]{7,14}$'
            ),
            CONSTRAINT organizations_year_founded_plausible CHECK (
                year_founded IS NULL OR year_founded BETWEEN 1900 AND 2100
            )
        )
        """
    )
    # Duplicate names within one LGA are a warning the registration screen
    # shows, never a refusal — two neighbourhood clubs can genuinely share a
    # name. This index makes that lookup cheap; it enforces nothing.
    op.execute(
        "CREATE INDEX organizations_name_lookup ON identity.organizations (lga_id, lower(name))"
    )
    op.execute("CREATE INDEX organizations_lga_idx ON identity.organizations (lga_id)")
    op.execute("CREATE INDEX organizations_rep_idx ON identity.organizations (rep_user_id)")
    op.execute(
        """
        CREATE TRIGGER organizations_touch_updated_at
            BEFORE UPDATE ON identity.organizations
            FOR EACH ROW EXECUTE FUNCTION ops.touch_updated_at()
        """
    )


def _teams() -> None:
    op.execute(
        """
        CREATE TABLE identity.teams (
            id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id        uuid        NOT NULL REFERENCES identity.organizations (id),

            name          text        NOT NULL,
            sport         text        NOT NULL,
            age_category  text        NOT NULL DEFAULT 'Senior',
            gender        text        NOT NULL DEFAULT 'mixed',

            created_at    timestamptz NOT NULL DEFAULT now(),

            CONSTRAINT teams_gender_valid CHECK (gender IN ('male', 'female', 'mixed'))
        )
        """
    )
    op.execute("CREATE INDEX teams_org_idx ON identity.teams (org_id)")


def _roster_members() -> None:
    op.execute(
        """
        CREATE TABLE identity.roster_members (
            id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            team_id      uuid        NOT NULL REFERENCES identity.teams (id),
            athlete_id   uuid        NOT NULL REFERENCES identity.athletes (id),

            jersey_no    smallint,
            status       text        NOT NULL DEFAULT 'invited',
            invited_by   uuid        NOT NULL REFERENCES ops.users (id),

            invited_at   timestamptz NOT NULL DEFAULT now(),
            decided_at   timestamptz,

            created_at   timestamptz NOT NULL DEFAULT now(),
            updated_at   timestamptz NOT NULL DEFAULT now(),

            CONSTRAINT roster_status_valid CHECK (status IN ('invited', 'active', 'released')),
            CONSTRAINT roster_jersey_no_range CHECK (jersey_no IS NULL OR jersey_no BETWEEN 1 AND 99)
        )
        """
    )
    # The at-most-one-open-membership rule: an athlete is active on at most one
    # roster anywhere, system-wide. Accepting a new invitation is what releases
    # the old one — the service does both writes in one transaction, and this
    # index is what makes "forgot to release the old row" impossible rather
    # than merely unlikely.
    op.execute(
        "CREATE UNIQUE INDEX roster_members_one_active_per_athlete "
        "ON identity.roster_members (athlete_id) WHERE status = 'active'"
    )
    # A club cannot queue the same invitation twice. Different clubs can still
    # invite the same athlete concurrently — CLB-03 warns about that, it does
    # not refuse it.
    op.execute(
        "CREATE UNIQUE INDEX roster_members_one_invite_per_team "
        "ON identity.roster_members (team_id, athlete_id) WHERE status = 'invited'"
    )
    op.execute(
        "CREATE INDEX roster_members_team_idx ON identity.roster_members (team_id, status)"
    )
    op.execute(
        "CREATE INDEX roster_members_athlete_idx ON identity.roster_members (athlete_id, status)"
    )
    op.execute(
        """
        CREATE TRIGGER roster_members_touch_updated_at
            BEFORE UPDATE ON identity.roster_members
            FOR EACH ROW EXECUTE FUNCTION ops.touch_updated_at()
        """
    )


def _career_events_fk() -> None:
    op.execute(
        """
        ALTER TABLE identity.career_events
            ADD CONSTRAINT career_events_club_fk
            FOREIGN KEY (club_id) REFERENCES identity.organizations (id)
        """
    )


def _club_create_for_athletes() -> None:
    op.execute(
        """
        INSERT INTO ops.role_permissions (role_code, permission_code)
        VALUES ('athlete', 'club.create')
        """
    )
