"""A club signs up on its own: the representative's account and the club, together.

The representative is not an athlete: the account holds no athlete record and no ID,
only the ``club_admin`` grant on the club it registered. The club starts
``unconfirmed`` and reaches an administrator as ``pending_review`` only when the
representative confirms their email (see ``access.confirm_email``), so a club nobody
can be reached about never enters the review queue.

As with athlete registration, the password is hashed before the transaction opens.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

import structlog
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from kafriada.clock import now_utc
from kafriada.contexts.access import phone as phone_mod
from kafriada.contexts.access import service as access
from kafriada.contexts.clubs.profile import OFFICIAL_ROLES, ClubProfile
from kafriada.contexts.clubs.service import Refused, check_club, create_club
from kafriada.db.engine import transaction
from kafriada.security.passwords import get_password_service, password_policy_error

log = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class Representative:
    first_name: str
    surname: str
    role: str
    phone: str
    email: str
    password: str
    consent_notice_version: str


@dataclass(frozen=True, slots=True)
class SignedUp:
    club_id: UUID
    user_id: UUID
    name: str


def sign_up(
    rep: Representative,
    *,
    name: str,
    sport: str,
    lga_id: str,
    contact_phone: str,
    profile: ClubProfile,
    confirm_duplicate: bool = False,
    request_id: str | None = None,
    ip_address: str | None = None,
) -> SignedUp:
    first = " ".join(rep.first_name.split())
    surname = " ".join(rep.surname.split())
    if len(first) < 2:
        raise Refused("Enter your first name.", code="invalid", field="rep_first_name")
    if len(surname) < 2:
        raise Refused("Enter your surname.", code="invalid", field="rep_surname")
    if rep.role not in OFFICIAL_ROLES:
        raise Refused("Choose your role in the club.", code="invalid", field="rep_role")
    try:
        rep_phone = phone_mod.normalise(rep.phone)
    except phone_mod.InvalidPhoneNumberError as exc:
        raise Refused(str(exc), code="invalid", field="rep_phone") from exc
    email = rep.email.strip().lower()
    if not access.EMAIL_RE.match(email):
        raise Refused("Enter a valid email address.", code="invalid", field="rep_email")
    if (problem := password_policy_error(rep.password)) is not None:
        raise Refused(problem, code="invalid", field="password")

    checked = check_club(name=name, sport=sport, contact_phone=contact_phone, profile=profile)
    checked["rep_role"] = rep.role
    if checked["official2_phone"] == rep_phone:
        raise Refused(
            "The second official needs a different number from yours.",
            code="invalid", field="official2_phone",
        )

    full_name = f"{first} {surname}"
    password_hash = get_password_service().hash(rep.password)

    with transaction() as session:
        try:
            user_id: UUID = session.execute(
                text(
                    """
                    INSERT INTO ops.users
                        (full_name, first_name, surname, phone_e164, email, password_hash,
                         consent_notice_version, consent_given_at)
                    VALUES (:full, :first, :surname, :phone, :email, :hash, :consent, :at)
                    RETURNING id
                    """
                ),
                {
                    "full": full_name, "first": first, "surname": surname, "phone": rep_phone,
                    "email": email, "hash": password_hash,
                    "consent": rep.consent_notice_version, "at": now_utc(),
                },
            ).scalar_one()
        except IntegrityError as exc:
            session.rollback()
            violated = getattr(getattr(exc.orig, "diag", None), "constraint_name", None)
            if violated == "users_phone_unique":
                raise Refused(
                    "This number already has a KAFRIADA account. Use a different number "
                    "for the club representative.",
                    code="invalid", field="rep_phone",
                ) from None
            if violated == "users_email_unique":
                raise Refused(
                    "This email already has a KAFRIADA account. Use a different one.",
                    code="invalid", field="rep_email",
                ) from None
            raise

        club_id = create_club(
            session, user_id, full_name, checked, lga_id=lga_id,
            confirm_duplicate=confirm_duplicate, status="unconfirmed",
            request_id=request_id, ip_address=ip_address,
        )
        access.send_email_code_at_registration(session, user_id, email)

    log.info("club_signed_up", club_id=str(club_id), lga=lga_id)
    return SignedUp(club_id=club_id, user_id=user_id, name=str(checked["name"]))
