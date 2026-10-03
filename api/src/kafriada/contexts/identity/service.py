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
      grant the athlete role          (before the lock, so it costs no hold time)
      queue the confirmation code     (likewise — and it commits with the record)
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
import re
from dataclasses import dataclass
from datetime import date
from uuid import UUID

import structlog
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from kafriada.clock import age_on, now_utc, today_in_nigeria
from kafriada.contexts.access import phone as phone_mod
from kafriada.contexts.access import service as access
from kafriada.contexts.audit import service as audit
from kafriada.contexts.identity import kuid as kuid_mod
from kafriada.contexts.identity import profile
from kafriada.db.engine import transaction
from kafriada.security.passwords import get_password_service, password_policy_error
from kafriada.settings import get_settings

log = structlog.get_logger(__name__)

MINIMUM_AGE = 18

# The partial unique indexes on ops.users (migration 0001).
PHONE_UNIQUE_INDEX = "users_phone_unique"
EMAIL_UNIQUE_INDEX = "users_email_unique"
DUPLICATE_PHONE_MESSAGE = (
    "This number is already registered. "
    "Sign in instead, or ask your LGA coordinator for help."
)

# Shape only, same spirit as the phone check: rejects what plainly is not an
# email without pretending to know the full grammar of one.
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class RegistrationError(Exception):
    """Something about the submission is wrong. The message is shown to the user."""

    def __init__(self, message: str, *, field: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.field = field


@dataclass(frozen=True, slots=True)
class RegistrationInput:
    """Everything a registration collects. All of it is required except where noted."""

    first_name: str
    surname: str
    email: str
    phone: str
    password: str
    date_of_birth: date
    gender: str
    nationality: str
    state_of_origin: str          # "Not applicable" for a nationality other than Nigerian
    address_line: str
    town: str
    lga_id: str                   # where they register and live; printed into the ID
    sport: str
    playing_position: str
    dominant_side: str
    height_cm: int
    weight_kg: int
    years_experience: int
    level_played: str
    emergency_name: str
    emergency_relationship: str
    emergency_phone: str
    middle_name: str | None = None          # optional
    secondary_position: str | None = None   # optional
    consent_notice_version: str | None = None

    @property
    def full_name(self) -> str:
        parts = (self.first_name, self.middle_name or "", self.surname)
        return " ".join(" ".join(parts).split())


@dataclass(frozen=True, slots=True)
class RegistrationResult:
    athlete_id: UUID
    user_id: UUID
    kuid: str
    full_name: str
    lga_name: str
    # Masked, for the "we sent a code to 0803 *** 4321" line. The full number
    # never travels back out of the domain tier.
    phone_masked: str = ""


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
    _validate_profile(data)
    full_name = data.full_name

    try:
        phone_e164 = phone_mod.normalise(data.phone)
    except phone_mod.InvalidPhoneNumberError as exc:
        raise RegistrationError(str(exc), field="phone") from exc
    try:
        emergency_e164 = phone_mod.normalise(data.emergency_phone)
    except phone_mod.InvalidPhoneNumberError as exc:
        raise RegistrationError(str(exc), field="emergency_phone") from exc
    if emergency_e164 == phone_e164:
        raise RegistrationError(
            "The emergency contact needs a different number from yours.",
            field="emergency_phone",
        )

    email = data.email.strip().lower()
    cfg = get_settings()
    if not _EMAIL_RE.match(email):
        raise RegistrationError("Enter a valid email address.", field="email")

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
                first_name=data.first_name.strip(),
                middle_name=(data.middle_name or "").strip() or None,
                surname=data.surname.strip(),
                phone_e164=phone_e164,
                email=email,
                password_hash=password_hash,
                consent_version=data.consent_notice_version,
            )
        except IntegrityError as exc:
            # Nothing was minted: the unique index stopped it before the counter
            # was touched. It used to hand back the existing identity, which
            # told anyone who typed a phone number whose it was. The same answer
            # now goes to the owner retrying and to a stranger probing.
            session.rollback()
            violated = _violated_constraint(exc)
            if violated == PHONE_UNIQUE_INDEX:
                log.info("registration_refused_duplicate_phone")
                raise RegistrationError(DUPLICATE_PHONE_MESSAGE, field="phone") from None
            if violated == EMAIL_UNIQUE_INDEX:
                log.info("registration_refused_duplicate_email")
                raise RegistrationError(
                    "This email is already registered. Use a different one.",
                    field="email",
                ) from None
            raise RegistrationError(
                "We could not complete your registration. Please try again."
            ) from None

        access.grant_athlete_role(session, user_id)
        # The confirmation code, queued in this same transaction: a registration
        # that rolls back sends nobody a code, and a code that is queued belongs
        # to a registration that really happened. Before the mint, so it costs
        # no time on the counter lock.
        access.send_email_code_at_registration(session, user_id, email)
        if cfg.require_phone_confirmation:
            access.send_registration_code(session, user_id, phone_e164)

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
                         date_of_birth, sport, playing_position,
                         gender, dominant_side, years_experience,
                         nationality, state_of_origin, address_line, town,
                         height_cm, weight_kg, level_played, secondary_position,
                         emergency_name, emergency_relationship, emergency_phone)
                    SELECT :user_id,
                           :kuid_prefix || lpad(m.next_serial::text, 6, '0'),
                           :state_code, :year, m.next_serial,
                           :lga_id, :lga_id,
                           :dob, :sport, :position,
                           :gender, :side, :years,
                           :nationality, :state_of_origin, :address, :town,
                           :height, :weight, :level, :secondary,
                           :em_name, :em_relationship, :em_phone
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
                "position": data.playing_position.strip(),
                "gender": data.gender,
                "side": data.dominant_side,
                "years": data.years_experience,
                "nationality": data.nationality,
                "state_of_origin": data.state_of_origin,
                "address": " ".join(data.address_line.split()),
                "town": " ".join(data.town.split()),
                "height": data.height_cm,
                "weight": data.weight_kg,
                "level": data.level_played,
                "secondary": (data.secondary_position or "").strip() or None,
                "em_name": " ".join(data.emergency_name.split()),
                "em_relationship": " ".join(data.emergency_relationship.split()),
                "em_phone": emergency_e164,
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
            metadata={"lga": lga["lga_name"], "sport": data.sport, "role_granted": "athlete"},
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
        phone_masked=phone_mod.mask(phone_e164),
    )


def _validate_profile(data: RegistrationInput) -> None:
    """Every required field present and every choice one we offer."""

    def need(value: str | None, field: str, message: str, longest: int = 120) -> None:
        cleaned = " ".join((value or "").split())
        if len(cleaned) < 2:
            raise RegistrationError(message, field=field)
        if len(cleaned) > longest:
            raise RegistrationError(f"Keep this under {longest} characters.", field=field)

    need(data.first_name, "first_name", "Enter your first name.", 60)
    need(data.surname, "surname", "Enter your surname.", 60)
    if data.middle_name and len(data.middle_name.strip()) > 60:
        raise RegistrationError("Keep this under 60 characters.", field="middle_name")
    if data.gender not in profile.GENDERS:
        raise RegistrationError("Choose male or female.", field="gender")
    if data.nationality not in profile.NATIONALITIES:
        raise RegistrationError("Choose your nationality.", field="nationality")
    if data.nationality == profile.NIGERIAN:
        if data.state_of_origin not in profile.NIGERIAN_STATES:
            raise RegistrationError("Choose your state of origin.", field="state_of_origin")
    elif data.state_of_origin not in (*profile.NIGERIAN_STATES, profile.NOT_APPLICABLE):
        raise RegistrationError("Choose your state of origin.", field="state_of_origin")
    need(data.address_line, "address_line", "Enter your house number and street.", 200)
    need(data.town, "town", "Enter your town or city.", 80)
    if data.sport not in profile.SPORTS:
        raise RegistrationError("Choose your sport.", field="sport")
    if data.playing_position not in profile.positions_for(data.sport):
        raise RegistrationError(
            f"Choose a position or event in {data.sport}.", field="playing_position"
        )
    if data.secondary_position and data.secondary_position not in profile.positions_for(
        data.sport
    ):
        raise RegistrationError(
            f"Choose a second position in {data.sport}, or leave it empty.",
            field="secondary_position",
        )
    if data.dominant_side not in profile.DOMINANT_SIDES:
        raise RegistrationError("Choose your stronger side.", field="dominant_side")
    low, high = profile.HEIGHT_CM
    if not low <= data.height_cm <= high:
        raise RegistrationError(f"Height in centimetres, {low} to {high}.", field="height_cm")
    low, high = profile.WEIGHT_KG
    if not low <= data.weight_kg <= high:
        raise RegistrationError(f"Weight in kilograms, {low} to {high}.", field="weight_kg")
    low, high = profile.YEARS_PLAYING
    if not low <= data.years_experience <= high:
        raise RegistrationError("Years playing, as a whole number.", field="years_experience")
    if data.level_played not in profile.LEVELS:
        raise RegistrationError("Choose the highest level you have played.",
                                field="level_played")
    need(data.emergency_name, "emergency_name", "Enter your emergency contact's name.")
    need(data.emergency_relationship, "emergency_relationship",
         "Say how they are related to you.", 40)


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
    first_name: str | None = None,
    middle_name: str | None = None,
    surname: str | None = None,
    phone_e164: str,
    email: str | None,
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
                (full_name, first_name, middle_name, surname, phone_e164, email,
                 password_hash, consent_notice_version, consent_given_at)
            VALUES
                (:full_name, :first_name, :middle_name, :surname, :phone_e164, :email,
                 :password_hash, :consent_version, :consent_given_at)
            RETURNING id
            """
        ),
        {
            "full_name": full_name,
            "first_name": first_name,
            "middle_name": middle_name,
            "surname": surname,
            "phone_e164": phone_e164,
            "email": email,
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
    # An approved badge was later taken back. Shown so nobody trusts a stale card.
    verification_withdrawn: bool = False


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
                       lga.name AS lga_name, st.name AS state_name,
                       EXISTS (SELECT 1 FROM identity.verification_requests v
                                WHERE v.athlete_id = a.id AND v.status = 'approved')
                           AS is_verified,
                       EXISTS (SELECT 1 FROM identity.verification_requests v
                                WHERE v.athlete_id = a.id AND v.status = 'approved'
                                  AND v.photo_media_id IS NOT NULL) AS has_photo,
                       EXISTS (SELECT 1 FROM identity.verification_requests v
                                WHERE v.athlete_id = a.id AND v.status = 'revoked')
                           AS was_revoked
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
        is_verified=row["is_verified"],
        # An address on OUR API that serves the safe copy of an approved photo and
        # nothing else — never a bucket URL, which would be a way round the paywall.
        photo_url=f"/v1/public/athletes/{row['kuid']}/photo" if row["has_photo"] else None,
        verification_withdrawn=row["was_revoked"] and not row["is_verified"],
    )


@dataclass(frozen=True, slots=True)
class AthleteListing:
    kuid: str
    full_name: str
    sport: str
    playing_position: str | None
    registered_on: date


LGA_LISTING_LIMIT = 200


def list_athletes_in_lga(lga_id: str) -> list[AthleteListing] | None:
    """Athletes whose current LGA is this one, newest first. None if no such LGA.

    Who may call this is decided by the route's scope rule, not here.
    """
    with transaction() as session:
        exists = session.execute(
            text("SELECT 1 FROM ops.locations WHERE id = :id AND kind = 'lga'"),
            {"id": lga_id},
        ).scalar_one_or_none()
        if exists is None:
            return None
        rows = session.execute(
            text(
                """
                SELECT a.kuid, u.full_name, a.sport, a.playing_position,
                       (a.created_at AT TIME ZONE 'Africa/Lagos')::date AS registered_on
                  FROM identity.athletes a
                  JOIN ops.users u ON u.id = a.user_id
                 WHERE a.current_lga_id = :id AND u.anonymised_at IS NULL
                 ORDER BY a.created_at DESC
                 LIMIT :limit
                """
            ),
            {"id": lga_id, "limit": LGA_LISTING_LIMIT},
        ).mappings().all()
    return [
        AthleteListing(
            kuid=r["kuid"],
            full_name=r["full_name"],
            sport=r["sport"],
            playing_position=r["playing_position"],
            registered_on=r["registered_on"],
        )
        for r in rows
    ]


@dataclass(frozen=True, slots=True)
class OwnAthlete:
    kuid: str
    lga_name: str


def athlete_for_user(user_id: UUID) -> OwnAthlete | None:
    """The athlete record a signed-in user holds, if they hold one."""
    with transaction() as session:
        row = session.execute(
            text(
                """
                SELECT a.kuid, lga.name AS lga_name
                  FROM identity.athletes a
                  JOIN ops.locations lga ON lga.id = a.current_lga_id
                 WHERE a.user_id = :id
                """
            ),
            {"id": user_id},
        ).mappings().one_or_none()
    if row is None:
        return None
    return OwnAthlete(kuid=row["kuid"], lga_name=row["lga_name"])


# ---------------------------------------------------------------------------
# Athlete details registration never asked for (ATH-02, migration 0009)
# ---------------------------------------------------------------------------


class DetailsError(Exception):
    """A submitted value is not one of the allowed choices."""

    def __init__(self, message: str, *, field: str) -> None:
        super().__init__(message)
        self.message = message
        self.field = field


class NoAthleteRecord(Exception):
    """The signed-in account has no athlete record — a staff-only account."""


@dataclass(frozen=True, slots=True)
class AthleteDetails:
    """The athlete's own record, as the details screen shows it.

    The first group is fixed at registration (identity and eligibility); the
    second is what the athlete keeps up to date.
    """

    kuid: str | None
    full_name: str
    gender: str | None
    date_of_birth: date
    nationality: str | None
    state_of_origin: str | None
    sport: str
    lga_name: str
    email: str | None
    playing_position: str | None
    secondary_position: str | None
    dominant_side: str | None
    secondary_sport: str | None
    years_experience: int | None
    height_cm: int | None
    weight_kg: int | None
    level_played: str | None
    address_line: str | None
    town: str | None
    emergency_name: str | None
    emergency_relationship: str | None
    emergency_phone: str | None


@dataclass(frozen=True, slots=True)
class DetailsUpdate:
    """Everything the athlete may change. All required except the two optional ones."""

    playing_position: str
    dominant_side: str
    years_experience: int
    height_cm: int
    weight_kg: int
    level_played: str
    address_line: str
    town: str
    emergency_name: str
    emergency_relationship: str
    emergency_phone: str
    secondary_position: str | None = None
    secondary_sport: str | None = None


_DETAILS_SELECT = """
    SELECT a.kuid, u.full_name, a.gender, a.date_of_birth, a.nationality, a.state_of_origin,
           a.sport, l.name AS lga_name, u.email, a.playing_position, a.secondary_position,
           a.dominant_side, a.secondary_sport, a.years_experience, a.height_cm, a.weight_kg,
           a.level_played, a.address_line, a.town, a.emergency_name,
           a.emergency_relationship, a.emergency_phone
      FROM identity.athletes a
      JOIN ops.users u ON u.id = a.user_id
      JOIN ops.locations l ON l.id = a.current_lga_id
     WHERE a.user_id = :id
"""


def get_athlete_details(user_id: UUID) -> AthleteDetails | None:
    """The signed-in athlete's own record, for the details screen (ATH-02)."""
    with transaction() as session:
        row = session.execute(text(_DETAILS_SELECT), {"id": user_id}).mappings().one_or_none()
    return AthleteDetails(**row) if row is not None else None


def update_athlete_details(user_id: UUID, update: DetailsUpdate) -> AthleteDetails:
    """Replace what the athlete keeps up to date. The whole form is always sent."""
    existing = get_athlete_details(user_id)
    if existing is None:
        raise NoAthleteRecord()

    def need(value: str, field: str, message: str, longest: int) -> str:
        cleaned = " ".join(value.split())
        if len(cleaned) < 2:
            raise DetailsError(message, field=field)
        if len(cleaned) > longest:
            raise DetailsError(f"Keep this under {longest} characters.", field=field)
        return cleaned

    allowed = profile.positions_for(existing.sport)
    if update.playing_position not in allowed:
        raise DetailsError(f"Choose a position or event in {existing.sport}.",
                           field="playing_position")
    if update.secondary_position and update.secondary_position not in allowed:
        raise DetailsError(f"Choose a second position in {existing.sport}, or none.",
                           field="secondary_position")
    if update.dominant_side not in profile.DOMINANT_SIDES:
        raise DetailsError("Choose one of the listed options.", field="dominant_side")
    secondary_sport = (update.secondary_sport or "").strip() or None
    if secondary_sport is not None and secondary_sport not in profile.SPORTS:
        raise DetailsError("Choose one of the listed sports, or none.", field="secondary_sport")
    for field, (low, high), label in (
        ("height_cm", profile.HEIGHT_CM, "Height in centimetres"),
        ("weight_kg", profile.WEIGHT_KG, "Weight in kilograms"),
        ("years_experience", profile.YEARS_PLAYING, "Years playing"),
    ):
        if not low <= getattr(update, field) <= high:
            raise DetailsError(f"{label}, {low} to {high}.", field=field)
    if update.level_played not in profile.LEVELS:
        raise DetailsError("Choose one of the listed options.", field="level_played")
    address = need(update.address_line, "address_line", "Enter your house number and street.", 200)
    town = need(update.town, "town", "Enter your town or city.", 80)
    em_name = need(update.emergency_name, "emergency_name", "Enter their full name.", 120)
    em_rel = need(update.emergency_relationship, "emergency_relationship",
                  "Say how they are related to you.", 40)
    try:
        em_phone = phone_mod.normalise(update.emergency_phone)
    except phone_mod.InvalidPhoneNumberError as exc:
        raise DetailsError(str(exc), field="emergency_phone") from exc

    with transaction() as session:
        session.execute(
            text(
                """
                UPDATE identity.athletes
                   SET playing_position = :position, secondary_position = :secondary,
                       dominant_side = :side, secondary_sport = :secondary_sport,
                       years_experience = :years, height_cm = :height, weight_kg = :weight,
                       level_played = :level, address_line = :address, town = :town,
                       emergency_name = :em_name, emergency_relationship = :em_rel,
                       emergency_phone = :em_phone, updated_at = now()
                 WHERE user_id = :user_id
                """
            ),
            {
                "user_id": user_id,
                "position": update.playing_position,
                "secondary": update.secondary_position or None,
                "side": update.dominant_side,
                "secondary_sport": secondary_sport,
                "years": update.years_experience,
                "height": update.height_cm,
                "weight": update.weight_kg,
                "level": update.level_played,
                "address": address,
                "town": town,
                "em_name": em_name,
                "em_rel": em_rel,
                "em_phone": em_phone,
            },
        )
    updated = get_athlete_details(user_id)
    assert updated is not None
    return updated
