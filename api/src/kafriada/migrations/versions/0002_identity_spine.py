"""Identity spine: locations, the KUID counter, athletes, career events.

Revision ID: 0002_identity_spine
Revises: 0001_foundation
Create Date: 2026-09-09

Three things here are worth reading before changing anything.

**The counter is one row per (year, state).** In the pilot there is one state, so
every registration in Jigawa contends on a single row. That is fine — the mint is
a single atomic statement and the lock is held for about two milliseconds — but it
is only fine because nothing slow happens inside that transaction. Password
hashing in particular is done before the transaction opens.

**Uniqueness is stated twice, on purpose.** ``athletes.kuid`` is unique, and so is
``(kuid_state, kuid_year, kuid_serial)``. The second index is the rule the counter
actually implements; the first is the rule a human reads off a card. If the
counter were ever changed in a way that could repeat a serial, the second index
would refuse the write rather than let two athletes share an identity.

**Verification state is deliberately not on the athlete row.** The verification
context owns it, and it arrives with that context in Stage 2. Denormalising it
here would give the system two answers to "is this athlete verified", which is
precisely the question the product is sold on.
"""

from __future__ import annotations

from alembic import op

revision = "0002_identity_spine"
down_revision = "0001_foundation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    _locations()
    _seed_jigawa()
    _kuid_counters()
    _athletes()
    _career_events()


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS identity.career_events")
    op.execute("DROP TABLE IF EXISTS identity.athletes")
    op.execute("DROP TABLE IF EXISTS identity.kuid_counters")
    op.execute("DROP TABLE IF EXISTS ops.locations")


# ---------------------------------------------------------------------------
# Locations, and the rollout flag
# ---------------------------------------------------------------------------
def _locations() -> None:
    op.execute(
        """
        CREATE TABLE ops.locations (
            -- Readable, stable ids: 'NG-JG' for the state, 'NG-JG-BKD' for an LGA.
            -- A generated uuid would be correct and useless when reading a log
            -- line or a support query at speed.
            id            text PRIMARY KEY,
            kind          text        NOT NULL,
            code          text        NOT NULL,
            name          text        NOT NULL,
            parent_id     text        REFERENCES ops.locations (id),

            -- Registration is refused in an LGA that is not live. This is the
            -- whole rollout control: opening or closing a wave is an UPDATE, not
            -- a deployment, so a bad wave can be stopped in thirty seconds.
            rollout_wave  smallint,
            is_live       boolean     NOT NULL DEFAULT false,
            went_live_at  timestamptz,

            created_at    timestamptz NOT NULL DEFAULT now(),

            CONSTRAINT locations_kind_valid CHECK (kind IN ('country', 'state', 'lga')),
            CONSTRAINT locations_state_code_shape CHECK (
                kind <> 'state' OR code ~ '^[A-Z]{2}$'
            ),
            -- An LGA code is printed into every KUID issued there and can never
            -- change afterwards. Three uppercase letters, enforced here so a
            -- careless seed cannot introduce a code that breaks the format.
            CONSTRAINT locations_lga_code_shape CHECK (
                kind <> 'lga' OR code ~ '^[A-Z]{3}$'
            ),
            CONSTRAINT locations_live_has_timestamp CHECK (
                is_live = false OR went_live_at IS NOT NULL
            )
        )
        """
    )
    op.execute("CREATE INDEX locations_parent_idx ON ops.locations (parent_id)")
    op.execute(
        "CREATE INDEX locations_live_lgas ON ops.locations (parent_id) WHERE is_live"
    )
    op.execute(
        "COMMENT ON COLUMN ops.locations.code IS "
        "'Permanent. An LGA code is printed into the KUID of every athlete "
        "registered there, and a KUID is never reissued.'"
    )


def _seed_jigawa() -> None:
    """Jigawa State and its 27 LGAs, as at September 2026.

    Written out literally rather than generated from application code. A
    migration records what was inserted at a point in time; if the LGA table in
    the application later changes, this file must still describe what actually
    happened to this database.

    Only Birnin Kudu — wave 1, the anchor LGA — is live. Everything else opens
    behind the rollout flag once its go/no-go gates are met.
    """
    op.execute(
        """
        INSERT INTO ops.locations (id, kind, code, name, parent_id, rollout_wave, is_live, went_live_at)
        VALUES ('NG', 'country', 'NG', 'Nigeria', NULL, NULL, false, NULL)
        """
    )
    op.execute(
        """
        INSERT INTO ops.locations (id, kind, code, name, parent_id, rollout_wave, is_live, went_live_at)
        VALUES ('NG-JG', 'state', 'JG', 'Jigawa', 'NG', NULL, false, NULL)
        """
    )
    op.execute(
        """
        INSERT INTO ops.locations (id, kind, code, name, parent_id, rollout_wave, is_live, went_live_at)
        VALUES
            ('NG-JG-BKD', 'lga', 'BKD', 'Birnin Kudu',    'NG-JG', 1, true,  now()),
            ('NG-JG-DUT', 'lga', 'DUT', 'Dutse',          'NG-JG', 2, false, NULL),
            ('NG-JG-BUJ', 'lga', 'BUJ', 'Buji',           'NG-JG', 2, false, NULL),
            ('NG-JG-GWA', 'lga', 'GWA', 'Gwaram',         'NG-JG', 2, false, NULL),
            ('NG-JG-HAD', 'lga', 'HAD', 'Hadejia',        'NG-JG', 3, false, NULL),
            ('NG-JG-JAH', 'lga', 'JAH', 'Jahun',          'NG-JG', 3, false, NULL),
            ('NG-JG-KIY', 'lga', 'KIY', 'Kiyawa',         'NG-JG', 3, false, NULL),
            ('NG-JG-RIN', 'lga', 'RIN', 'Ringim',         'NG-JG', 3, false, NULL),
            ('NG-JG-TAU', 'lga', 'TAU', 'Taura',          'NG-JG', 3, false, NULL),
            ('NG-JG-MIG', 'lga', 'MIG', 'Miga',           'NG-JG', 3, false, NULL),
            ('NG-JG-KFH', 'lga', 'KFH', 'Kafin Hausa',    'NG-JG', 3, false, NULL),
            ('NG-JG-AUY', 'lga', 'AUY', 'Auyo',           'NG-JG', 3, false, NULL),
            ('NG-JG-GUR', 'lga', 'GUR', 'Guri',           'NG-JG', 3, false, NULL),
            ('NG-JG-KRK', 'lga', 'KRK', 'Kiri Kasama',    'NG-JG', 3, false, NULL),
            ('NG-JG-BRW', 'lga', 'BRW', 'Biriniwa',       'NG-JG', 3, false, NULL),
            ('NG-JG-GUM', 'lga', 'GUM', 'Gumel',          'NG-JG', 4, false, NULL),
            ('NG-JG-KAZ', 'lga', 'KAZ', 'Kazaure',        'NG-JG', 4, false, NULL),
            ('NG-JG-BAB', 'lga', 'BAB', 'Babura',         'NG-JG', 4, false, NULL),
            ('NG-JG-GAG', 'lga', 'GAG', 'Gagarawa',       'NG-JG', 4, false, NULL),
            ('NG-JG-GRK', 'lga', 'GRK', 'Garki',          'NG-JG', 4, false, NULL),
            ('NG-JG-GWI', 'lga', 'GWI', 'Gwiwa',          'NG-JG', 4, false, NULL),
            ('NG-JG-KAU', 'lga', 'KAU', 'Kaugama',        'NG-JG', 4, false, NULL),
            ('NG-JG-MGT', 'lga', 'MGT', 'Maigatari',      'NG-JG', 4, false, NULL),
            ('NG-JG-MLM', 'lga', 'MLM', 'Malam Madori',   'NG-JG', 4, false, NULL),
            ('NG-JG-RON', 'lga', 'RON', 'Roni',           'NG-JG', 4, false, NULL),
            ('NG-JG-SUL', 'lga', 'SUL', 'Sule Tankarkar', 'NG-JG', 4, false, NULL),
            ('NG-JG-YAN', 'lga', 'YAN', 'Yankwashi',      'NG-JG', 4, false, NULL)
        """
    )
    # Jigawa has 27 LGAs. If this migration ever inserts a different number, the
    # rollout plan and the LGA table in the application have diverged, and the
    # right time to find out is now rather than at a registration drive.
    op.execute(
        """
        DO $$
        DECLARE lga_count integer;
        BEGIN
            SELECT count(*) INTO lga_count
              FROM ops.locations WHERE kind = 'lga' AND parent_id = 'NG-JG';
            IF lga_count <> 27 THEN
                RAISE EXCEPTION 'Jigawa must have 27 LGAs, seeded %', lga_count;
            END IF;
        END
        $$
        """
    )


# ---------------------------------------------------------------------------
# The KUID counter
# ---------------------------------------------------------------------------
def _kuid_counters() -> None:
    op.execute(
        """
        CREATE TABLE identity.kuid_counters (
            year        smallint NOT NULL,
            state_code  char(2)  NOT NULL,
            next_serial integer  NOT NULL,
            updated_at  timestamptz NOT NULL DEFAULT now(),

            PRIMARY KEY (year, state_code),
            CONSTRAINT kuid_counter_range CHECK (next_serial BETWEEN 1 AND 999999)
        )
        """
    )
    op.execute(
        "COMMENT ON TABLE identity.kuid_counters IS "
        "'One row per (year, state). Incremented by a single atomic "
        "INSERT ... ON CONFLICT DO UPDATE ... RETURNING, which holds the row lock "
        "for the duration of one statement rather than one transaction. A counter "
        "row is used instead of a sequence because a sequence leaves gaps on "
        "rollback, and an unexplained gap in a public identity number destroys "
        "trust in a register in its first month.'"
    )
    # No row is seeded. The mint upserts, so the first registration of a year
    # creates its own counter — which means adding a state or rolling into a new
    # year needs no migration and no deployment.


# ---------------------------------------------------------------------------
# Athletes
# ---------------------------------------------------------------------------
def _athletes() -> None:
    op.execute(
        """
        CREATE TABLE identity.athletes (
            id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),

            -- One athlete record per user account, and one user account per
            -- verified phone number. Those two constraints together are what
            -- make the phone the identity anchor.
            user_id             uuid        NOT NULL REFERENCES ops.users (id),

            kuid                text        NOT NULL,
            -- The three parts the counter actually allocates, stored separately
            -- so the real uniqueness rule can be an index rather than a promise.
            kuid_state          char(2)     NOT NULL,
            kuid_year           smallint    NOT NULL,
            kuid_serial         integer     NOT NULL,

            -- Where they registered. Permanent, because it is inside the KUID.
            registration_lga_id text        NOT NULL REFERENCES ops.locations (id),
            -- Where they are now. Changeable: people move, the KUID does not.
            current_lga_id      text        NOT NULL REFERENCES ops.locations (id),

            date_of_birth       date        NOT NULL,
            sport               text        NOT NULL,
            playing_position    text,

            created_at          timestamptz NOT NULL DEFAULT now(),
            updated_at          timestamptz NOT NULL DEFAULT now(),

            CONSTRAINT athletes_kuid_format CHECK (
                kuid ~ '^KA-[A-Z]{2}-[A-Z]{2}-[A-Z]{3}-20[0-9]{2}-[0-9]{6}$'
            ),
            CONSTRAINT athletes_serial_range CHECK (kuid_serial BETWEEN 1 AND 999999),
            CONSTRAINT athletes_year_range CHECK (kuid_year BETWEEN 2000 AND 2099),
            -- A sanity bound on typos, not an age check. 18+ is enforced in the
            -- service on registration and checked against a document by a human
            -- at Stage-2 review; a date-based CHECK cannot be used here because
            -- comparing against the current date is not an immutable expression.
            CONSTRAINT athletes_dob_plausible CHECK (
                date_of_birth BETWEEN DATE '1920-01-01' AND DATE '2015-01-01'
            )
        )
        """
    )

    op.execute("CREATE UNIQUE INDEX athletes_user_unique ON identity.athletes (user_id)")
    # What a person reads off a printed card.
    op.execute("CREATE UNIQUE INDEX athletes_kuid_unique ON identity.athletes (kuid)")
    # What the counter actually guarantees. Stated separately so that a future
    # change to the counter cannot silently allow a repeated serial.
    op.execute(
        """
        CREATE UNIQUE INDEX athletes_serial_unique
            ON identity.athletes (kuid_state, kuid_year, kuid_serial)
        """
    )
    op.execute("CREATE INDEX athletes_current_lga_idx ON identity.athletes (current_lga_id)")
    op.execute(
        "CREATE INDEX athletes_registration_lga_idx ON identity.athletes (registration_lga_id)"
    )

    op.execute(
        """
        CREATE TRIGGER athletes_touch_updated_at
            BEFORE UPDATE ON identity.athletes
            FOR EACH ROW EXECUTE FUNCTION ops.touch_updated_at()
        """
    )
    # The KUID is immutable. Nothing in the application offers a way to change it,
    # and this makes that true of the database as well: an UPDATE that alters any
    # part of the identifier is refused, however it was issued.
    op.execute(
        """
        CREATE FUNCTION identity.deny_kuid_change() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            IF NEW.kuid IS DISTINCT FROM OLD.kuid
               OR NEW.kuid_state IS DISTINCT FROM OLD.kuid_state
               OR NEW.kuid_year IS DISTINCT FROM OLD.kuid_year
               OR NEW.kuid_serial IS DISTINCT FROM OLD.kuid_serial
               OR NEW.registration_lga_id IS DISTINCT FROM OLD.registration_lga_id
            THEN
                RAISE EXCEPTION
                    'the KUID and its place of registration are permanent'
                    USING ERRCODE = 'insufficient_privilege';
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER athletes_kuid_is_immutable
            BEFORE UPDATE ON identity.athletes
            FOR EACH ROW EXECUTE FUNCTION identity.deny_kuid_change()
        """
    )
    # An athlete record is never deleted. A person exercising their right to
    # erasure is anonymised — identifying fields cleared, the KUID shell and the
    # financial and audit history retained, exactly as the privacy notice states
    # before anybody registers.
    op.execute("REVOKE DELETE ON identity.athletes FROM PUBLIC, kaf_app, kaf_money")


# ---------------------------------------------------------------------------
# Career events
# ---------------------------------------------------------------------------
def _career_events() -> None:
    op.execute(
        """
        CREATE TABLE identity.career_events (
            id           bigserial PRIMARY KEY,
            athlete_id   uuid        NOT NULL REFERENCES identity.athletes (id),
            event_type   text        NOT NULL,

            -- Set once the clubs context exists. Left without a foreign key here
            -- so this migration does not depend on a table it does not create.
            club_id      uuid,
            club_name    text,       -- captured at the time, so history survives a rename

            occurred_on  date        NOT NULL,
            recorded_at  timestamptz NOT NULL DEFAULT now(),
            metadata     jsonb       NOT NULL DEFAULT '{}'::jsonb,

            CONSTRAINT career_event_type_valid CHECK (event_type IN (
                'registered', 'joined_club', 'left_club', 'transferred',
                'verified', 'verification_revoked'
            ))
        )
        """
    )
    op.execute(
        """
        CREATE INDEX career_events_athlete_idx
            ON identity.career_events (athlete_id, occurred_on DESC, id DESC)
        """
    )

    # Career history is a record of what happened, and records are not edited.
    # A mistake is corrected by adding an event, the way a ledger is corrected —
    # never by rewriting one, which would leave the public profile showing a past
    # that silently differs from what was true at the time.
    op.execute("GRANT SELECT, INSERT ON identity.career_events TO kaf_app, kaf_money")
    op.execute(
        "REVOKE UPDATE, DELETE, TRUNCATE ON identity.career_events "
        "FROM PUBLIC, kaf_app, kaf_money"
    )
    op.execute(
        """
        CREATE TRIGGER career_events_no_update_delete
            BEFORE UPDATE OR DELETE ON identity.career_events
            FOR EACH ROW EXECUTE FUNCTION ops.deny_mutation()
        """
    )
