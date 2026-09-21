"""Access — who is this caller, and what may they do, to what?

Sessions, sign-in, role grants, and every authorisation decision in the system.
Nothing else reads ``ops.sessions`` or decides a permission.

**Sessions are ours, and revocable at once.** The presentation tier holds an
opaque token in an httpOnly cookie and forwards it on every call. This table
holds only its SHA-256, so a leaked backup is not a list of live logins. Ending a
session is an UPDATE that takes effect on the very next request — which is the
reason for this design (ADR 0002): coordinators handle cash on shared phones.

**Two clocks per session.** The idle window slides forward on every request; the
absolute expiry never moves. Staff (anyone holding a role other than athlete)
get 30 minutes idle, athletes 30 days. The window is chosen at sign-in and stored
on the row, and any role change ends the holder's sessions, so it cannot go stale.

**Deny by default, scope always.** :func:`can` answers yes only when an active
grant carries the permission *and* covers the target. A scoped grant — one LGA,
one state — never satisfies a check that names no target, because "may manage a
roster" silently meaning "may manage every roster" is the classic leak.

**Sign-in never says which half was wrong.** Unknown phone, wrong password,
locked or suspended account: one message, one status, and the same Argon2 cost.
A wrong password on a real account also writes its failure counter, so that path
is a database write slower than an unknown phone; registration already answers
"is this number registered?" outright, so this is not the weakest point, but it
is why the timing is kept close rather than claimed identical.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from uuid import UUID

import structlog
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from kafriada.contexts.access import otp
from kafriada.contexts.access import phone as phone_mod
from kafriada.contexts.audit import service as audit
from kafriada.db.engine import transaction
from kafriada.security.passwords import get_password_service, password_policy_error
from kafriada.security.tokens import hash_token, new_token
from kafriada.settings import get_settings

log = structlog.get_logger(__name__)

ATHLETE_ROLE = "athlete"

# Online guessing. Ten consecutive wrong passwords pause the account for an hour.
# The per-IP limit belongs in Redis alongside this and arrives with it; either
# alone is bypassable, so this is half the defence, not all of it.
MAX_FAILED_SIGN_INS = 10
LOCK_MINUTES = 60

SIGN_IN_REFUSED_MESSAGE = (
    "That phone number and password do not match. "
    f"After {MAX_FAILED_SIGN_INS} wrong tries, sign-in pauses for an hour."
)

# A cookie value is 43 characters. Anything much longer is not ours, and is
# refused before it costs a hash or a query.
_MAX_TOKEN_LENGTH = 200

ScopedKind = Literal["state", "lga", "club"]


class SignInRefused(Exception):
    """Sign-in failed. The message is the same whatever the reason."""

    def __init__(self) -> None:
        super().__init__(SIGN_IN_REFUSED_MESSAGE)
        self.message = SIGN_IN_REFUSED_MESSAGE


class AccessError(Exception):
    """A role or session change was refused. The message is shown to the user."""

    def __init__(self, message: str, *, field: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.field = field


class CodeRefused(Exception):
    """A one-time code was wrong, expired, or spent."""

    def __init__(self, message: str, *, attempts_left: int = 0) -> None:
        super().__init__(message)
        self.message = message
        self.attempts_left = attempts_left


@dataclass(frozen=True, slots=True)
class CodeRequested:
    """The answer to "send me a code", shaped so it reveals nothing.

    ``resend_in`` is how long before another can be asked for. For a password
    reset it is the same whether or not the number is registered.
    """

    resend_in: int
    daily_limit_reached: bool = False


@dataclass(frozen=True, slots=True)
class _Found:
    """An account found by phone number, for the code flows."""

    id: UUID
    full_name: str
    phone_e164: str
    password_hash: str | None
    phone_verified_at: datetime | None


@dataclass(frozen=True, slots=True)
class PhoneConfirmed:
    user_id: UUID
    session: IssuedSession


@dataclass(frozen=True, slots=True)
class Scope:
    """The place or organisation a request acts on."""

    kind: ScopedKind
    id: str


@dataclass(frozen=True, slots=True)
class Principal:
    """The signed-in caller, as established from their session token."""

    user_id: UUID
    full_name: str
    session_id: UUID
    idle_expires_at: datetime
    absolute_expires_at: datetime


@dataclass(frozen=True, slots=True)
class IssuedSession:
    # Shown to the caller exactly once. Only its digest is stored.
    token: str
    session_id: UUID
    idle_expires_at: datetime
    absolute_expires_at: datetime
    is_staff: bool
    # Whether the phone behind this account has been confirmed with a code.
    # Signing in does not require it; the confirm screen does.
    phone_verified: bool = False


@dataclass(frozen=True, slots=True)
class RoleGrant:
    grant_id: UUID
    role: str
    scope_kind: str
    scope_id: str | None
    scope_name: str | None


@dataclass(frozen=True, slots=True)
class Account:
    """What a signed-in person may see about their own account."""

    user_id: UUID
    full_name: str
    phone_masked: str
    phone_verified: bool
    roles: tuple[RoleGrant, ...]

    @property
    def is_staff(self) -> bool:
        return any(g.role != ATHLETE_ROLE for g in self.roles)


# ---------------------------------------------------------------------------
# Sign-in
# ---------------------------------------------------------------------------
def sign_in(
    raw_phone: str,
    raw_password: str,
    *,
    ip_address: str | None = None,
    user_agent: str | None = None,
    request_id: str | None = None,
) -> IssuedSession:
    """Check a phone and password and issue a session.

    Raises :class:`SignInRefused` for every kind of failure. Password work
    happens between transactions, never inside one.
    """
    passwords = get_password_service()
    try:
        phone_e164 = phone_mod.normalise(raw_phone)
    except phone_mod.InvalidPhoneNumberError:
        passwords.verify_dummy()
        raise SignInRefused() from None

    with transaction() as session:
        account = session.execute(
            text(
                """
                SELECT id, full_name, password_hash, status,
                       (locked_until IS NOT NULL AND locked_until > now()) AS locked
                  FROM ops.users
                 WHERE phone_e164 = :phone AND anonymised_at IS NULL
                """
            ),
            {"phone": phone_e164},
        ).mappings().one_or_none()

    if (
        account is None
        or account["password_hash"] is None
        or account["status"] != "active"
        or account["locked"]
    ):
        # Same cost as a real check, so timing does not reveal which branch ran.
        passwords.verify_dummy()
        raise SignInRefused()

    user_id: UUID = account["id"]
    checked = passwords.verify(account["password_hash"], raw_password)
    if not checked.ok:
        _record_failed_attempt(user_id, request_id=request_id, ip_address=ip_address)
        raise SignInRefused()

    upgraded_hash = passwords.hash(raw_password) if checked.needs_rehash else None

    with transaction() as session:
        # Conditional, so a lock placed by a concurrent run of wrong guesses
        # between the check above and this line still refuses the sign-in.
        still_allowed = session.execute(
            text(
                """
                UPDATE ops.users
                   SET failed_login_count = 0,
                       locked_until       = NULL,
                       last_login_at      = now(),
                       password_hash      = COALESCE(:upgraded, password_hash)
                 WHERE id = :id
                   AND status = 'active'
                   AND anonymised_at IS NULL
                   AND (locked_until IS NULL OR locked_until <= now())
                RETURNING id
                """
            ),
            {"id": user_id, "upgraded": upgraded_hash},
        ).one_or_none()
        if still_allowed is None:
            raise SignInRefused()

        issued = _issue(session, user_id, ip_address=ip_address, user_agent=user_agent)
        audit.record(
            session,
            actor=audit.Actor(user_id=user_id, label=account["full_name"]),
            action="session.issued",
            subject_type="user",
            subject_id=str(user_id),
            metadata={
                "method": "password",
                "staff": issued.is_staff,
                "hash_upgraded": upgraded_hash is not None,
            },
            request_id=request_id,
            ip_address=ip_address,
        )

    log.info("signed_in", staff=issued.is_staff)
    return issued


def issue_session(
    user_id: UUID,
    *,
    method: str,
    ip_address: str | None = None,
    user_agent: str | None = None,
    request_id: str | None = None,
) -> IssuedSession:
    """Issue a session to someone already authenticated by other means.

    For the one-time-code sign-in and password reset that arrive with OTP, and
    for tests. ``method`` says how they proved who they are and is audited.
    """
    with transaction() as session:
        full_name = session.execute(
            text(
                "SELECT full_name FROM ops.users "
                "WHERE id = :id AND status = 'active' AND anonymised_at IS NULL"
            ),
            {"id": user_id},
        ).scalar_one()
        issued = _issue(session, user_id, ip_address=ip_address, user_agent=user_agent)
        audit.record(
            session,
            actor=audit.Actor(user_id=user_id, label=full_name),
            action="session.issued",
            subject_type="user",
            subject_id=str(user_id),
            metadata={"method": method, "staff": issued.is_staff},
            request_id=request_id,
            ip_address=ip_address,
        )
    return issued


def _issue(
    session: Session,
    user_id: UUID,
    *,
    ip_address: str | None,
    user_agent: str | None,
) -> IssuedSession:
    """Insert a session row. The idle window is decided by the roles held now."""
    cfg = get_settings()
    roles = session.execute(
        text(
            "SELECT DISTINCT role_code FROM ops.user_roles "
            "WHERE user_id = :id AND revoked_at IS NULL"
        ),
        {"id": user_id},
    ).scalars().all()
    is_staff = any(role != ATHLETE_ROLE for role in roles)
    phone_verified = bool(
        session.execute(
            text("SELECT phone_verified_at IS NOT NULL FROM ops.users WHERE id = :id"),
            {"id": user_id},
        ).scalar_one()
    )
    if is_staff:
        idle_seconds = cfg.session_idle_minutes_staff * 60
        absolute_seconds = cfg.session_absolute_days_staff * 86_400
    else:
        idle_seconds = cfg.session_idle_days_athlete * 86_400
        absolute_seconds = cfg.session_absolute_days_athlete * 86_400

    token = new_token()
    row = session.execute(
        text(
            """
            INSERT INTO ops.sessions
                (user_id, token_hash, idle_seconds,
                 idle_expires_at, absolute_expires_at, ip_address, user_agent)
            VALUES
                (:user_id, :token_hash, :idle,
                 now() + LEAST(CAST(:idle AS integer), CAST(:absolute AS integer))
                         * interval '1 second',
                 now() + CAST(:absolute AS integer) * interval '1 second',
                 CAST(:ip AS inet), :user_agent)
            RETURNING id, idle_expires_at, absolute_expires_at
            """
        ),
        {
            "user_id": user_id,
            "token_hash": hash_token(token),
            "idle": idle_seconds,
            "absolute": absolute_seconds,
            "ip": ip_address,
            "user_agent": (user_agent or "")[:300] or None,
        },
    ).mappings().one()

    return IssuedSession(
        token=token,
        session_id=row["id"],
        idle_expires_at=row["idle_expires_at"],
        absolute_expires_at=row["absolute_expires_at"],
        is_staff=is_staff,
        phone_verified=phone_verified,
    )


def _record_failed_attempt(
    user_id: UUID,
    *,
    request_id: str | None,
    ip_address: str | None,
) -> None:
    """Count a wrong password against the account, and lock it at the limit.

    The counter resets when the lock is placed, so the account gets a fresh
    allowance when the hour is up rather than locking again on the next typo.
    """
    with transaction() as session:
        row = session.execute(
            text(
                """
                UPDATE ops.users
                   SET failed_login_count = CASE
                           WHEN failed_login_count + 1 >= :max THEN 0
                           ELSE failed_login_count + 1 END,
                       locked_until = CASE
                           WHEN failed_login_count + 1 >= :max
                               THEN now() + CAST(:lock AS integer) * interval '1 minute'
                           ELSE locked_until END
                 WHERE id = :id
                RETURNING failed_login_count,
                          (locked_until IS NOT NULL AND locked_until > now()) AS locked
                """
            ),
            {"id": user_id, "max": MAX_FAILED_SIGN_INS, "lock": LOCK_MINUTES},
        ).mappings().one()

        # Whoever typed the password is unknown — that is the point — so the
        # actor is anonymous and the account is the subject.
        someone = audit.Actor(user_id=None, label="anonymous sign-in attempt")
        audit.record(
            session,
            actor=someone,
            action="session.sign_in_failed",
            subject_type="user",
            subject_id=str(user_id),
            request_id=request_id,
            ip_address=ip_address,
        )
        if row["locked"] and row["failed_login_count"] == 0:
            audit.record(
                session,
                actor=someone,
                action="account.locked",
                subject_type="user",
                subject_id=str(user_id),
                metadata={"minutes": LOCK_MINUTES, "after_failures": MAX_FAILED_SIGN_INS},
                request_id=request_id,
                ip_address=ip_address,
            )
            log.warning("account_locked")


# ---------------------------------------------------------------------------
# One-time codes: confirming a phone, and resetting a password
# ---------------------------------------------------------------------------
def send_registration_code(session: Session, user_id: UUID, phone_e164: str) -> None:
    """Queue the confirmation code, inside the registration's own transaction.

    Called before the KUID is minted, so it adds nothing to the time the counter
    row is held. The limits are not applied to this one: it is the first code of
    a registration that has just been accepted, and nobody should be told to
    come back in a minute for a code they have not yet been sent once.
    """
    otp.send_code(
        session,
        user_id=user_id,
        purpose=otp.PHONE_VERIFICATION,
        phone_e164=phone_e164,
        enforce_limits=False,
    )


def request_phone_code(
    raw_phone: str,
    *,
    request_id: str | None = None,
    ip_address: str | None = None,
) -> CodeRequested:
    """Send another phone-confirmation code.

    Reached from the confirm screen by someone who has just registered, so a
    "wait 40 seconds" answer tells them nothing registration did not already.
    """
    cfg = get_settings()
    user = _user_for_phone(raw_phone)
    if user is None or user.phone_verified_at is not None:
        # Nothing to confirm. Same shape as success: this screen is public.
        return CodeRequested(resend_in=cfg.otp_resend_seconds)

    with transaction() as session:
        try:
            otp.send_code(
                session,
                user_id=user.id,
                purpose=otp.PHONE_VERIFICATION,
                phone_e164=user.phone_e164,
            )
        except otp.TooSoon as exc:
            return CodeRequested(resend_in=exc.seconds)
        except otp.TooMany:
            return CodeRequested(resend_in=cfg.otp_resend_seconds, daily_limit_reached=True)

        audit.record(
            session,
            actor=audit.Actor(user_id=user.id, label=user.full_name),
            action="phone.code_sent",
            subject_type="user",
            subject_id=str(user.id),
            request_id=request_id,
            ip_address=ip_address,
        )
    return CodeRequested(resend_in=cfg.otp_resend_seconds)


def confirm_phone(
    raw_phone: str,
    code: str,
    *,
    request_id: str | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> PhoneConfirmed:
    """Check the code and mark the phone confirmed, then sign the person in.

    Holding the phone is exactly what a session is meant to prove, so a correct
    code issues one. Raises :class:`CodeRefused` for every kind of failure.
    """
    user = _user_for_phone(raw_phone)
    if user is None:
        # An unknown number gets the answer a wrong code gets.
        raise CodeRefused("That code is wrong or has expired. Ask for a new one.")

    # The attempt is spent in its own transaction, and committed, before any
    # refusal is raised. Counting a wrong guess inside the transaction that the
    # refusal rolls back means the counter never moves — which is five guesses
    # becoming as many as anyone likes.
    _spend_code(user.id, otp.PHONE_VERIFICATION, code)

    with transaction() as session:
        if user.phone_verified_at is None:
            session.execute(
                text("UPDATE ops.users SET phone_verified_at = now() WHERE id = :id"),
                {"id": user.id},
            )
            audit.record(
                session,
                actor=audit.Actor(user_id=user.id, label=user.full_name),
                action="phone.verified",
                subject_type="user",
                subject_id=str(user.id),
                request_id=request_id,
                ip_address=ip_address,
            )

        issued = _issue(session, user.id, ip_address=ip_address, user_agent=user_agent)
        audit.record(
            session,
            actor=audit.Actor(user_id=user.id, label=user.full_name),
            action="session.issued",
            subject_type="user",
            subject_id=str(user.id),
            metadata={"method": "phone_code", "staff": issued.is_staff},
            request_id=request_id,
            ip_address=ip_address,
        )

    return PhoneConfirmed(user_id=user.id, session=issued)


def request_password_reset(
    raw_phone: str,
    *,
    request_id: str | None = None,
    ip_address: str | None = None,
) -> CodeRequested:
    """Send a reset code — or quietly do nothing for an unknown number.

    The answer is identical either way. Anything else turns this screen into a
    way of asking "is this person registered with KAFRIADA?".
    """
    cfg = get_settings()
    user = _user_for_phone(raw_phone)
    if user is None or user.password_hash is None:
        return CodeRequested(resend_in=cfg.otp_resend_seconds)

    with transaction() as session:
        try:
            otp.send_code(
                session,
                user_id=user.id,
                purpose=otp.PASSWORD_RESET,
                phone_e164=user.phone_e164,
            )
        except (otp.TooSoon, otp.TooMany):
            # Also silent: a cooling-off message would answer the same question.
            return CodeRequested(resend_in=cfg.otp_resend_seconds)

        audit.record(
            session,
            actor=audit.Actor(user_id=None, label="anonymous reset request"),
            action="password.reset_requested",
            subject_type="user",
            subject_id=str(user.id),
            request_id=request_id,
            ip_address=ip_address,
        )
    return CodeRequested(resend_in=cfg.otp_resend_seconds)


def reset_password(
    raw_phone: str,
    code: str,
    new_password: str,
    *,
    request_id: str | None = None,
    ip_address: str | None = None,
) -> None:
    """Set a new password with a code, and sign out everywhere.

    Every other session ends: if the reason for the reset was that somebody else
    had the account, leaving their session alive would defeat the exercise.
    """
    if (problem := password_policy_error(new_password)) is not None:
        raise AccessError(problem, field="new_password")

    user = _user_for_phone(raw_phone)
    # Hashing happens here, outside the transaction, as everywhere else.
    password_hash = get_password_service().hash(new_password)

    if user is None:
        raise CodeRefused("That code is wrong or has expired. Ask for a new one.")

    _spend_code(user.id, otp.PASSWORD_RESET, code)

    with transaction() as session:
        session.execute(
            text(
                """
                UPDATE ops.users
                   SET password_hash = :hash, failed_login_count = 0, locked_until = NULL
                 WHERE id = :id
                """
            ),
            {"id": user.id, "hash": password_hash},
        )
        ended = _revoke_sessions(session, user.id, reason="password_reset")
        audit.record(
            session,
            actor=audit.Actor(user_id=user.id, label=user.full_name),
            action="password.reset",
            subject_type="user",
            subject_id=str(user.id),
            metadata={"logins_ended": ended},
            request_id=request_id,
            ip_address=ip_address,
        )
    log.info("password_reset", logins_ended=ended)


def _spend_code(user_id: UUID, purpose: str, code: str) -> None:
    """Check a code and commit the attempt, then refuse if it was wrong.

    Its own transaction, deliberately: a wrong guess has to be *recorded* even
    though the request fails, or the five-attempt limit records nothing.
    """
    with transaction() as session:
        checked = otp.check_code(session, user_id=user_id, purpose=purpose, code=code)
    if not checked.ok:
        raise CodeRefused(_code_message(checked), attempts_left=checked.attempts_left)


def _code_message(checked: otp.CodeCheck) -> str:
    if checked.expired:
        return "That code has expired. Ask for a new one."
    if checked.attempts_left > 0:
        tries = "try" if checked.attempts_left == 1 else "tries"
        return f"That code is not right. {checked.attempts_left} {tries} left."
    return "That code is wrong or has expired. Ask for a new one."


def _user_for_phone(raw_phone: str) -> _Found | None:
    """Look up an account by phone. Returns None for anything unusable."""
    try:
        phone_e164 = phone_mod.normalise(raw_phone)
    except phone_mod.InvalidPhoneNumberError:
        return None

    with transaction() as session:
        row = session.execute(
            text(
                """
                SELECT id, full_name, phone_e164, password_hash, phone_verified_at
                  FROM ops.users
                 WHERE phone_e164 = :phone
                   AND anonymised_at IS NULL
                   AND status = 'active'
                """
            ),
            {"phone": phone_e164},
        ).mappings().one_or_none()
    if row is None:
        return None
    return _Found(
        id=row["id"],
        full_name=row["full_name"],
        phone_e164=row["phone_e164"],
        password_hash=row["password_hash"],
        phone_verified_at=row["phone_verified_at"],
    )


# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------
def authenticate(raw_token: str | None) -> Principal | None:
    """The caller behind a session token, or None.

    One statement: it finds the session, checks both clocks and the account,
    and slides the idle window forward. A revoked, expired or unknown token and
    a suspended account all look the same from outside — None.
    """
    if not raw_token or len(raw_token) > _MAX_TOKEN_LENGTH:
        return None

    with transaction() as session:
        row = session.execute(
            text(
                """
                UPDATE ops.sessions s
                   SET last_seen_at    = now(),
                       idle_expires_at = LEAST(now() + s.idle_seconds * interval '1 second',
                                               s.absolute_expires_at)
                  FROM ops.users u
                 WHERE s.token_hash = :token_hash
                   AND s.revoked_at IS NULL
                   AND s.idle_expires_at > now()
                   AND s.absolute_expires_at > now()
                   AND u.id = s.user_id
                   AND u.status = 'active'
                   AND u.anonymised_at IS NULL
                RETURNING s.id, s.user_id, u.full_name,
                          s.idle_expires_at, s.absolute_expires_at
                """
            ),
            {"token_hash": hash_token(raw_token)},
        ).mappings().one_or_none()

    if row is None:
        return None
    return Principal(
        user_id=row["user_id"],
        full_name=row["full_name"],
        session_id=row["id"],
        idle_expires_at=row["idle_expires_at"],
        absolute_expires_at=row["absolute_expires_at"],
    )


def sign_out(
    principal: Principal,
    *,
    request_id: str | None = None,
    ip_address: str | None = None,
) -> None:
    """End the caller's own session. Effective from the next request."""
    with transaction() as session:
        ended = session.execute(
            text(
                """
                UPDATE ops.sessions
                   SET revoked_at = now(), revoked_reason = 'signed_out'
                 WHERE id = :id AND revoked_at IS NULL
                RETURNING id
                """
            ),
            {"id": principal.session_id},
        ).one_or_none()
        if ended is not None:
            audit.record(
                session,
                actor=audit.Actor(user_id=principal.user_id, label=principal.full_name),
                action="session.revoked",
                subject_type="user",
                subject_id=str(principal.user_id),
                metadata={"reason": "signed_out"},
                request_id=request_id,
                ip_address=ip_address,
            )


def end_all_sessions(
    *,
    actor: Principal,
    user_id: UUID,
    reason: str,
    request_id: str | None = None,
    ip_address: str | None = None,
) -> int:
    """End every session a user holds — a lost phone, a suspected shared login."""
    reason = reason.strip()
    if not reason:
        raise AccessError("Say why these sessions are being ended.", field="reason")

    with transaction() as session:
        _require_user(session, user_id)
        count = _revoke_sessions(session, user_id, reason="ended_by_admin")
        audit.record(
            session,
            actor=audit.Actor(user_id=actor.user_id, label=actor.full_name),
            action="session.revoked_all",
            subject_type="user",
            subject_id=str(user_id),
            metadata={"reason": reason, "logins_ended": count},
            request_id=request_id,
            ip_address=ip_address,
        )
    return count


def _revoke_sessions(session: Session, user_id: UUID, *, reason: str) -> int:
    ended = session.execute(
        text(
            """
            UPDATE ops.sessions
               SET revoked_at = now(), revoked_reason = :reason
             WHERE user_id = :id AND revoked_at IS NULL
            RETURNING id
            """
        ),
        {"id": user_id, "reason": reason},
    ).all()
    return len(ended)


# ---------------------------------------------------------------------------
# Authorisation
# ---------------------------------------------------------------------------
def can(user_id: UUID, permission: str, scope: Scope | None = None) -> bool:
    """Does this user hold ``permission`` over ``scope``?

    A grant covers the target when it is global, when it names exactly the
    target, or when it names the state an LGA target sits in. With no target,
    only a global grant will do. Anything else — including a permission code
    that does not exist — is no.
    """
    with transaction() as session:
        allowed: bool = session.execute(
            text(
                """
                SELECT EXISTS (
                    SELECT 1
                      FROM ops.user_roles ur
                      JOIN ops.role_permissions rp
                        ON rp.role_code = ur.role_code
                       AND rp.permission_code = :permission
                     WHERE ur.user_id = :user_id
                       AND ur.revoked_at IS NULL
                       AND (
                            ur.scope_kind = 'global'
                         OR (ur.scope_kind = :kind AND ur.scope_id = :scope_id)
                         OR (CAST(:kind AS text) = 'lga'
                             AND ur.scope_kind = 'state'
                             AND ur.scope_id = (SELECT parent_id FROM ops.locations
                                                 WHERE id = :scope_id AND kind = 'lga'))
                       )
                )
                """
            ),
            {
                "user_id": user_id,
                "permission": permission,
                "kind": scope.kind if scope else None,
                "scope_id": scope.id if scope else None,
            },
        ).scalar_one()
    return allowed


def describe_account(user_id: UUID) -> Account:
    """The caller's own account: name, masked phone, and the roles they hold."""
    with transaction() as session:
        user = session.execute(
            text(
                "SELECT id, full_name, phone_e164, phone_verified_at "
                "FROM ops.users WHERE id = :id"
            ),
            {"id": user_id},
        ).mappings().one()
        grants = _active_grants(session, user_id)
    return Account(
        user_id=user.id,
        full_name=user.full_name,
        phone_masked=phone_mod.mask(user.phone_e164),
        phone_verified=user.phone_verified_at is not None,
        roles=grants,
    )


def _active_grants(session: Session, user_id: UUID) -> tuple[RoleGrant, ...]:
    rows = session.execute(
        text(
            """
            SELECT ur.id, ur.role_code, ur.scope_kind, ur.scope_id, loc.name AS scope_name
              FROM ops.user_roles ur
              LEFT JOIN ops.locations loc ON loc.id = ur.scope_id
             WHERE ur.user_id = :id AND ur.revoked_at IS NULL
             ORDER BY ur.granted_at
            """
        ),
        {"id": user_id},
    ).mappings().all()
    return tuple(
        RoleGrant(
            grant_id=r["id"],
            role=r["role_code"],
            scope_kind=r["scope_kind"],
            scope_id=r["scope_id"],
            scope_name=r["scope_name"],
        )
        for r in rows
    )


# ---------------------------------------------------------------------------
# Role grants
# ---------------------------------------------------------------------------
def grant_athlete_role(session: Session, user_id: UUID) -> None:
    """Called by registration, inside its transaction, before the KUID mint.

    Audited by the ``athlete.registered`` row that transaction writes rather
    than by a row of its own: every statement in that transaction adds to how
    long registrations queue, and the registration record already says it.
    """
    session.execute(
        text(
            """
            INSERT INTO ops.user_roles (user_id, role_code, scope_kind, scope_id, reason)
            VALUES (:id, 'athlete', 'global', NULL, 'registration')
            """
        ),
        {"id": user_id},
    )


def grant_role(
    *,
    actor: Principal,
    current_password: str,
    user_id: UUID,
    role: str,
    scope_id: str | None,
    reason: str,
    request_id: str | None = None,
    ip_address: str | None = None,
) -> UUID:
    """Grant a role, and its scope, as one action.

    The actor re-enters their password first. A scoped role without a scope is
    refused here, not only by the form: an LGA coordinator with no LGA would be
    a coordinator over every LGA. The grantee's sessions end, so the new
    permissions and session length apply from their next sign-in.
    """
    reason = reason.strip()
    scope_id = (scope_id or "").strip() or None
    if not reason:
        raise AccessError("Say why this role is being granted.", field="reason")

    _reauthenticate(actor, current_password, request_id=request_id, ip_address=ip_address)

    with transaction() as session:
        role_row = session.execute(
            text("SELECT code, scope_kind FROM ops.roles WHERE code = :code"),
            {"code": role},
        ).mappings().one_or_none()
        if role_row is None:
            raise AccessError("Choose a role.", field="role")
        scope_kind: str = role_row["scope_kind"]

        if scope_kind == "global":
            if scope_id is not None:
                raise AccessError(
                    "This role is not tied to a place. Leave the scope empty.",
                    field="scope_id",
                )
        elif scope_id is None:
            raise AccessError(f"Choose the {scope_kind} this role covers.", field="scope_id")
        elif scope_kind == "club":
            # Clubs arrive with their context in Stage 2. Until a club can be
            # looked up, a club id cannot be checked, and an unchecked scope is
            # how a grant ends up covering something nobody intended.
            raise AccessError(
                "Club roles can be granted once clubs are registered in KAFRIADA.",
                field="role",
            )
        else:
            place = session.execute(
                text("SELECT name FROM ops.locations WHERE id = :id AND kind = :kind"),
                {"id": scope_id, "kind": scope_kind},
            ).scalar_one_or_none()
            if place is None:
                raise AccessError(f"There is no {scope_kind} with that id.", field="scope_id")

        grantee = _require_user(session, user_id)

        try:
            with session.begin_nested():
                grant_id: UUID = session.execute(
                    text(
                        """
                        INSERT INTO ops.user_roles
                            (user_id, role_code, scope_kind, scope_id, granted_by, reason)
                        VALUES (:user_id, :role, :kind, :scope_id, :actor, :reason)
                        RETURNING id
                        """
                    ),
                    {
                        "user_id": user_id,
                        "role": role,
                        "kind": scope_kind,
                        "scope_id": scope_id,
                        "actor": actor.user_id,
                        "reason": reason[:300],
                    },
                ).scalar_one()
        except IntegrityError:
            raise AccessError(
                f"{grantee} already holds this role there.", field="role"
            ) from None

        _mark_reauthenticated(session, actor)
        ended = _revoke_sessions(session, user_id, reason="role_changed")
        audit.record(
            session,
            actor=audit.Actor(user_id=actor.user_id, label=actor.full_name),
            action="role.granted",
            subject_type="user",
            subject_id=str(user_id),
            metadata={
                "grant_id": str(grant_id),
                "role": role,
                "scope_kind": scope_kind,
                "scope_id": scope_id,
                "reason": reason,
                "logins_ended": ended,
            },
            request_id=request_id,
            ip_address=ip_address,
        )

    log.info("role_granted", role=role, scope_kind=scope_kind, scope_id=scope_id)
    return grant_id


def revoke_role(
    *,
    actor: Principal,
    current_password: str,
    grant_id: UUID,
    reason: str,
    request_id: str | None = None,
    ip_address: str | None = None,
) -> None:
    """Revoke one grant. The row stays, marked revoked: history is kept."""
    reason = reason.strip()
    if not reason:
        raise AccessError("Say why this role is being removed.", field="reason")

    _reauthenticate(actor, current_password, request_id=request_id, ip_address=ip_address)

    with transaction() as session:
        grant = session.execute(
            text(
                """
                UPDATE ops.user_roles
                   SET revoked_at = now(), revoked_by = :actor
                 WHERE id = :id AND revoked_at IS NULL
                RETURNING user_id, role_code, scope_kind, scope_id
                """
            ),
            {"id": grant_id, "actor": actor.user_id},
        ).mappings().one_or_none()
        if grant is None:
            raise AccessError("That role grant does not exist or was already removed.")

        _mark_reauthenticated(session, actor)
        ended = _revoke_sessions(session, grant["user_id"], reason="role_changed")
        audit.record(
            session,
            actor=audit.Actor(user_id=actor.user_id, label=actor.full_name),
            action="role.revoked",
            subject_type="user",
            subject_id=str(grant["user_id"]),
            metadata={
                "grant_id": str(grant_id),
                "role": grant["role_code"],
                "scope_kind": grant["scope_kind"],
                "scope_id": grant["scope_id"],
                "reason": reason,
                "logins_ended": ended,
            },
            request_id=request_id,
            ip_address=ip_address,
        )

    log.info("role_revoked", role=grant["role_code"])


def _reauthenticate(
    actor: Principal,
    raw_password: str,
    *,
    request_id: str | None,
    ip_address: str | None,
) -> None:
    """The actor proves it is still them. Wrong answers count towards the lock."""
    passwords = get_password_service()
    with transaction() as session:
        stored = session.execute(
            text("SELECT password_hash FROM ops.users WHERE id = :id"),
            {"id": actor.user_id},
        ).scalar_one_or_none()
    if stored is None:
        passwords.verify_dummy()
        raise AccessError("That password is not right.", field="current_password")
    if not passwords.verify(stored, raw_password).ok:
        _record_failed_attempt(actor.user_id, request_id=request_id, ip_address=ip_address)
        raise AccessError("That password is not right.", field="current_password")


def reauthenticate(
    actor: Principal,
    raw_password: str,
    *,
    request_id: str | None = None,
    ip_address: str | None = None,
) -> None:
    """The actor proves it is still them, for an action that asks for it.

    Public so other contexts (withdrawing a verification) use the same check, with
    the same lockout accounting, rather than growing their own.
    """
    _reauthenticate(actor, raw_password, request_id=request_id, ip_address=ip_address)


def _mark_reauthenticated(session: Session, actor: Principal) -> None:
    session.execute(
        text("UPDATE ops.sessions SET reauthenticated_at = now() WHERE id = :id"),
        {"id": actor.session_id},
    )


def _require_user(session: Session, user_id: UUID) -> str:
    name = session.execute(
        text("SELECT full_name FROM ops.users WHERE id = :id AND anonymised_at IS NULL"),
        {"id": user_id},
    ).scalar_one_or_none()
    if name is None:
        raise AccessError("There is no such user.", field="user_id")
    return str(name)
