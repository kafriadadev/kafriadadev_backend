"""Identity — registering an athlete and minting their KUID.

This is the most correctness-critical path in the system, and the ordering of the
statements below *is* the design. Two properties have to hold at once:

**Nobody ever gets two identities.** One phone means one KUID, enforced by a
unique index rather than by a check in this file. A retried request — a timeout
on a 2G connection, a double-tapped Submit button, a load balancer retrying —
must never mint a second one. It is refused, and refused *without saying whose
number it is*: until a code sent to the phone proves the caller owns it, the
refusal must not carry the holder's name, KUID or card.

**Two hundred people can register in the same minute.** Every registration in the
state contends on a single counter row, so the row lock has to be held for
milliseconds. Everything expensive happens before the transaction opens, and the
mint is the last blocking statement inside it.

    hash the password        ~80ms   <-- OUTSIDE. This is the whole trick.
    BEGIN
      insert the user account         (unique phone; a duplicate ends it here)
      mint the serial                 <-- lock acquired
      insert the athlete
      insert the career event
      insert the audit row
    COMMIT                            <-- lock released, ~3 statements later

With the hash inside the transaction the lock would be held for ~80ms and the
ceiling would be about twelve registrations a second. With it outside, the
ceiling is the round-trip time to the database.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from uuid import UUID

import structlog
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from kafriada.clock import age_on, now_utc, today_in_nigeria
from kafriada.contexts.access import phone as phone_mod
from kafriada.contexts.audit import service as audit
from kafriada.contexts.identity import kuid as kuid_mod
from kafriada.db.engine import transaction
from kafriada.security.passwords import get_password_service, password_policy_error

log = structlog.get_logger(__name__)

MINIMUM_AGE = 18

# The partial unique index on ops.users (migration 0001).
PHONE_UNIQUE_INDEX = "users_phone_unique"
DUPLICATE_PHONE_MESSAGE = (
    "This number is already registered. "
    "Sign in instead, or ask your LGA coordinator for help."
)


class RegistrationError(Exception):
    """Something about the submission is wrong. The message is shown to the user."""

    def __init__(self, message: str, *, field: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.field = field


@dataclass(frozen=True, slots=True)
class RegistrationInput:
    full_name: str
    phone: str
    password: str
    date_of_birth: date
    lga_id: str
    sport: str
    playing_position: str | None = None
    consent_notice_version: str | None = None


@dataclass(frozen=True, slots=True)
class RegistrationResult:
    athlete_id: UUID
    user_id: UUID
    kuid: str
    full_name: str
    lga_name: str


def register(
    data: RegistrationInput,
    *,
    request_id: str | None = None,
    ip_address: str | None = None,
) -> RegistrationResult:
    """Register an athlete and issue their permanent KUID."""
    # ---------------------------------------------------------------
    # Everything that can be rejected, rejected before any database work.
    # ---------------------------------------------------------------
    full_name = " ".join(data.full_name.split())
    if len(full_name) < 3:
        raise RegistrationError("Enter your full name.", field="full_name")

    try:
        phone_e164 = phone_mod.normalise(data.phone)
    except phone_mod.InvalidPhoneNumberError as exc:
        raise RegistrationError(str(exc), field="phone") from exc

    if (problem := password_policy_error(data.password)) is not None:
        raise RegistrationError(problem, field="password")

    age = age_on(data.date_of_birth)
    if age < MINIMUM_AGE:
        # Self-declared, and only checked against a document at Stage-2 review.
        # Stating the rule plainly here is the honest thing to do.
        raise RegistrationError(
            f"You must be {MINIMUM_AGE} or older to register during the pilot.",
            field="date_of_birth",
        )
    if age > 120:
        raise RegistrationError("Check the date of birth.", field="date_of_birth")

    if not data.sport.strip():
        raise RegistrationError("Choose your sport.", field="sport")

    # ---------------------------------------------------------------
    # The expensive part, deliberately before BEGIN. See the module docstring:
    # doing this inside the transaction would hold the KUID counter row for the
    # duration and collapse throughput for the whole state.
    # ---------------------------------------------------------------
    password_hash = get_password_service().hash(data.password)

    with transaction() as session:
        lga = _load_open_lga(session, data.lga_id)

        try:
            user_id = _insert_user(
                session,
                full_name=full_name,
                phone_e164=phone_e164,
                password_hash=password_hash,
                consent_version=data.consent_notice_version,
            )
        except IntegrityError as exc:
            # Nothing was minted: the unique index stopped it before the counter
            # was touched. It used to hand back the existing identity, which
            # told anyone who typed a phone number whose it was. The same answer
            # now goes to the owner retrying and to a stranger probing.
            session.rollback()
            if _violated_constraint(exc) == PHONE_UNIQUE_INDEX:
                log.info("registration_refused_duplicate_phone")
                raise RegistrationError(DUPLICATE_PHONE_MESSAGE, field="phone") from None
            raise RegistrationError(
                "We could not complete your registration. Please try again."
            ) from None

        # -- the mint ----------------------------------------------------
        # One statement allocates the serial, creates the athlete and records
        # the career event. The counter row is locked from here until COMMIT, so
        # collapsing three statements into one takes the hold time from four
        # network round trips to one. On a link where a round trip costs 150ms
        # that is the difference between a lock held for milliseconds and one
        # held for most of a second — and every registration in the state queues
        # behind it.
        # The year is printed permanently into the KUID, so it is Nigeria's year,
        # not the server's. See kafriada.clock.
        year = today_in_nigeria().year
        kuid_prefix = kuid_mod.prefix(
            country=lga["country_code"],
            state=lga["state_code"],
            lga=lga["lga_code"],
            year=year,
        )
        minted = session.execute(
            text(
                """
                WITH minted AS (
                    INSERT INTO identity.kuid_counters (year, state_code, next_serial)
                    VALUES (:year, :state_code, 1)
                    ON CONFLICT (year, state_code) DO UPDATE
                        SET next_serial = identity.kuid_counters.next_serial + 1,
                            updated_at  = now()
                    RETURNING next_serial
                ),
                created AS (
                    INSERT INTO identity.athletes
                        (user_id, kuid, kuid_state, kuid_year, kuid_serial,
                         registration_lga_id, current_lga_id,
                         date_of_birth, sport, playing_position)
                    SELECT :user_id,
                           :kuid_prefix || lpad(m.next_serial::text, 6, '0'),
                           :state_code, :year, m.next_serial,
                           :lga_id, :lga_id,
                           :dob, :sport, :position
                      FROM minted m
                    RETURNING id, kuid
                )
                INSERT INTO identity.career_events
                    (athlete_id, event_type, occurred_on, metadata)
                SELECT c.id, 'registered', CURRENT_DATE, CAST(:meta AS jsonb)
                  FROM created c
                RETURNING athlete_id,
                          (SELECT kuid FROM created) AS kuid
                """
            ),
            {
                "year": year,
                "state_code": lga["state_code"],
                "kuid_prefix": kuid_prefix,
                "user_id": user_id,
                "lga_id": lga["id"],
                "dob": data.date_of_birth,
                "sport": data.sport.strip(),
                "position": (data.playing_position or "").strip() or None,
                "meta": json.dumps({"lga": lga["lga_name"]}),
            },
        ).mappings().one()

        athlete_id = minted["athlete_id"]
        # Parse what the database actually stored rather than trusting what we
        # think it built. If the concatenation above were ever wrong, this is
        # where it surfaces — before anybody is told their permanent number.
        kuid = kuid_mod.Kuid.parse(minted["kuid"])

        audit.record(
            session,
            actor=audit.Actor(user_id=user_id, label=full_name, role="athlete"),
            action="athlete.registered",
            subject_type="athlete",
            subject_id=str(kuid),
            metadata={"lga": lga["lga_name"], "sport": data.sport},
            request_id=request_id,
            ip_address=ip_address,
        )

    log.info("athlete_registered", kuid=str(kuid), lga=lga["lga_name"])
    return RegistrationResult(
        athlete_id=athlete_id,
        user_id=user_id,
        kuid=str(kuid),
        full_name=full_name,
        lga_name=lga["lga_name"],
    )


# ---------------------------------------------------------------------------
# The mint
# ---------------------------------------------------------------------------
def _load_open_lga(session: Session, lga_id: str) -> dict[str, str]:
    """Resolve the LGA and refuse if registration is not open there.

    The rollout flag is checked here, in the service, rather than only being
    hidden in the UI — closing a wave has to actually stop registrations, not
    merely remove a button.
    """
    row = session.execute(
        text(
            """
            SELECT lga.id       AS id,
                   lga.code     AS lga_code,
                   lga.name     AS lga_name,
                   lga.is_live  AS is_live,
                   st.code      AS state_code,
                   country.code AS country_code
              FROM ops.locations lga
              JOIN ops.locations st      ON st.id = lga.parent_id
              JOIN ops.locations country ON country.id = st.parent_id
             WHERE lga.id = :lga_id AND lga.kind = 'lga'
            """
        ),
        {"lga_id": lga_id},
    ).mappings().one_or_none()

    if row is None:
        raise RegistrationError("Choose your Local Government Area.", field="lga_id")
    if not row["is_live"]:
        raise RegistrationError(
            f"Registration has not opened in {row['lga_name']} yet. "
            "Your LGA coordinator will announce the date.",
            field="lga_id",
        )
    return dict(row)


def _insert_user(
    session: Session,
    *,
    full_name: str,
    phone_e164: str,
    password_hash: str,
    consent_version: str | None,
) -> UUID:
    """Create the account. The unique index on the phone is the identity anchor."""
    # Decided here rather than with a CASE in the statement: PostgreSQL cannot
    # infer a parameter's type inside a CASE without an explicit cast, and the
    # rule — a consent timestamp exists exactly when a notice version does — is
    # clearer stated once in Python than repeated in SQL.
    consent_given_at = now_utc() if consent_version else None

    user_id: UUID = session.execute(
        text(
            """
            INSERT INTO ops.users
                (full_name, phone_e164, password_hash,
                 consent_notice_version, consent_given_at)
            VALUES
                (:full_name, :phone_e164, :password_hash,
                 :consent_version, :consent_given_at)
            RETURNING id
            """
        ),
        {
            "full_name": full_name,
            "phone_e164": phone_e164,
            "password_hash": password_hash,
            "consent_version": consent_version,
            "consent_given_at": consent_given_at,
        },
    ).scalar_one()
    return user_id


def _violated_constraint(exc: IntegrityError) -> str | None:
    """Name of the constraint or index PostgreSQL reported, if any."""
    diag = getattr(exc.orig, "diag", None)
    return getattr(diag, "constraint_name", None)


# ---------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class PublicProfile:
    """Exactly what a stranger scanning a QR code is allowed to see.

    Note what is absent: the phone number, the date of birth, the identity
    document. Only the age is derived, never the birth date itself. If a field
    is not on this class it cannot reach the public page by accident.
    """

    kuid: str
    full_name: str
    sport: str
    playing_position: str | None
    lga_name: str
    state_name: str
    registered_year: int
    age: int
    is_verified: bool
    photo_url: str | None


def get_public_profile(kuid_text: str) -> PublicProfile | None:
    """Read a public profile by KUID. Returns None when there is no such athlete."""
    try:
        parsed = kuid_mod.Kuid.parse(kuid_text)
    except kuid_mod.InvalidKuidError:
        return None

    with transaction() as session:
        row = session.execute(
            text(
                """
                SELECT a.kuid, a.sport, a.playing_position, a.date_of_birth,
                       a.kuid_year, u.full_name,
                       lga.name AS lga_name, st.name AS state_name
                  FROM identity.athletes a
                  JOIN ops.users u       ON u.id = a.user_id
                  JOIN ops.locations lga ON lga.id = a.current_lga_id
                  JOIN ops.locations st  ON st.id = lga.parent_id
                 WHERE a.kuid = :kuid
                """
            ),
            {"kuid": str(parsed)},
        ).mappings().one_or_none()

    if row is None:
        return None

    return PublicProfile(
        kuid=row["kuid"],
        full_name=row["full_name"],
        sport=row["sport"],
        playing_position=row["playing_position"],
        lga_name=row["lga_name"],
        state_name=row["state_name"],
        registered_year=row["kuid_year"],
        age=age_on(row["date_of_birth"]),
        # Verification arrives in Stage 2 with its own context, which owns this
        # answer. Until then nobody is verified, which is truthful rather than
        # a placeholder — no athlete has paid yet.
        is_verified=False,
        photo_url=None,
    )
