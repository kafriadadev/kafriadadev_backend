"""One-time codes: proving somebody holds the phone they claim.

Six digits is one chance in a million per guess, which is only safe because of
three limits that belong together and are useless apart:

  **five attempts** per code — then the code is dead, not merely wrong
  **ten minutes** of life
  **one send a minute, five a day** per person per purpose

Take any one away and a six-digit code becomes guessable. That is why the limits
live here, beside the code, rather than in whichever route happens to call this.

Codes are stored as an HMAC keyed with a server-held pepper, never as digits and
never as a bare digest — a million-entry lookup table is an afternoon's work.

The purpose is part of every lookup. A code sent to confirm a phone number must
not be accepted as a password reset: same six digits, entirely different
authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

import structlog
from sqlalchemy import text
from sqlalchemy.orm import Session

from kafriada.contexts.access.email_templates import otp_email_html
from kafriada.outbox import service as outbox
from kafriada.security.tokens import OTP_MAX_ATTEMPTS, hash_otp, new_otp, tokens_equal
from kafriada.settings import get_settings

log = structlog.get_logger(__name__)

PHONE_VERIFICATION = "phone_verification"
PASSWORD_RESET = "password_reset"  # noqa: S105 — a purpose name, not a secret
EMAIL_VERIFICATION = "email_verification"

# What the person reads on a locked screen at a registration desk. It says what
# to do with the code and, deliberately, that nobody will ever ask for it.
BODIES = {
    PHONE_VERIFICATION: (
        "{code} is your KAFRIADA code. It confirms your phone number and expires "
        "in {minutes} minutes. KAFRIADA will never ask you for this code."
    ),
    PASSWORD_RESET: (
        "{code} is your KAFRIADA password reset code. It expires in {minutes} "
        "minutes. If you did not ask for it, ignore this message."
    ),
    EMAIL_VERIFICATION: (
        "{code} is your KAFRIADA code. It confirms your email address and expires "
        "in {minutes} minutes. KAFRIADA will never ask you for this code."
    ),
}

EMAIL_SUBJECTS = {
    PHONE_VERIFICATION: "Your KAFRIADA code",
    PASSWORD_RESET: "Your KAFRIADA password reset code",
    EMAIL_VERIFICATION: "Confirm your email for KAFRIADA",
}


class TooSoon(Exception):
    """A code was asked for again before the cooling-off period ended."""

    def __init__(self, seconds: int) -> None:
        super().__init__(f"another code may be requested in {seconds} seconds")
        self.seconds = seconds


class TooMany(Exception):
    """The daily send limit for this person and purpose is used up."""


@dataclass(frozen=True, slots=True)
class CodeCheck:
    ok: bool
    attempts_left: int = 0
    expired: bool = False


def send_code(
    session: Session,
    *,
    user_id: UUID,
    purpose: str,
    phone_e164: str,
    email: str | None = None,
    enforce_limits: bool = True,
) -> None:
    """Issue a code and queue the message, inside the caller's transaction.

    The code row and the outbox row commit with whatever else the caller is
    doing. A registration that rolls back sends nobody a code.
    """
    cfg = get_settings()

    if enforce_limits:
        _guard_rate(session, user_id=user_id, purpose=purpose)

    # One live code per person per purpose: asking for a new one retires the old,
    # so "the code we sent you" is never ambiguous. A unique index enforces it.
    session.execute(
        text(
            """
            UPDATE ops.otp_codes SET voided_at = now()
             WHERE user_id = :user_id AND purpose = :purpose
               AND consumed_at IS NULL AND voided_at IS NULL
            """
        ),
        {"user_id": user_id, "purpose": purpose},
    )

    code = new_otp()
    session.execute(
        text(
            """
            INSERT INTO ops.otp_codes (user_id, purpose, code_hash, expires_at, sent_to)
            VALUES (:user_id, :purpose, :code_hash,
                    now() + CAST(:minutes AS integer) * interval '1 minute', :sent_to)
            """
        ),
        {
            "user_id": user_id,
            "purpose": purpose,
            "code_hash": hash_otp(code, pepper=cfg.secret_key.get_secret_value()),
            "minutes": cfg.otp_minutes_valid,
            "sent_to": email if purpose == EMAIL_VERIFICATION else phone_e164,
        },
    )
    body = BODIES[purpose].format(code=code, minutes=cfg.otp_minutes_valid)
    # 'email' is a pilot stand-in for SMS (see settings.otp_channel). An account
    # with no email on file still gets its code the ordinary way — there is
    # nowhere else to send it. The rule itself lives in outbox.service, so this
    # path and every other notification cannot drift apart.
    if purpose == EMAIL_VERIFICATION:
        # Confirming an email can only be done by sending to it.
        if email is None:
            raise ValueError("an email confirmation code needs an email address")
        html = otp_email_html(code=code, minutes=cfg.otp_minutes_valid, purpose=purpose)
        outbox.queue_email(
            session, to_email=email, subject=EMAIL_SUBJECTS[purpose], body=body,
            html=html, purpose=purpose,
        )
        log.info("otp_queued", purpose=purpose, channel="email")
    elif outbox.prefers_email(email):
        assert email is not None  # prefers_email() only returns true with one
        html = otp_email_html(code=code, minutes=cfg.otp_minutes_valid, purpose=purpose)
        outbox.queue_email(
            session, to_email=email, subject=EMAIL_SUBJECTS[purpose], body=body,
            html=html, purpose=purpose,
        )
        log.info("otp_queued", purpose=purpose, channel="email")
    else:
        outbox.queue_sms(session, to_phone=phone_e164, body=body, purpose=purpose)
        log.info("otp_queued", purpose=purpose, channel="sms")


def _guard_rate(session: Session, *, user_id: UUID, purpose: str) -> None:
    cfg = get_settings()
    row = session.execute(
        text(
            """
            SELECT
              coalesce(ceil(extract(epoch FROM (
                  max(created_at) + CAST(:cooldown AS integer) * interval '1 second' - now()
              ))), 0) AS wait_seconds,
              count(*) FILTER (WHERE created_at > now() - interval '24 hours') AS sent_today
              FROM ops.otp_codes
             WHERE user_id = :user_id AND purpose = :purpose
            """
        ),
        {"user_id": user_id, "purpose": purpose, "cooldown": cfg.otp_resend_seconds},
    ).mappings().one()

    if int(row["sent_today"]) >= cfg.otp_sends_per_day:
        raise TooMany()
    wait = int(row["wait_seconds"])
    if wait > 0:
        raise TooSoon(wait)


def check_code(
    session: Session,
    *,
    user_id: UUID,
    purpose: str,
    code: str,
) -> CodeCheck:
    """Spend one attempt against the live code. A correct code is consumed.

    The row is locked for the check, so two simultaneous guesses cannot each
    spend the same attempt — the cheapest way to turn five guesses into ten.
    """
    cfg = get_settings()
    row = session.execute(
        text(
            """
            SELECT id, code_hash, attempts, expires_at <= now() AS expired
              FROM ops.otp_codes
             WHERE user_id = :user_id AND purpose = :purpose
               AND consumed_at IS NULL AND voided_at IS NULL
             FOR UPDATE
            """
        ),
        {"user_id": user_id, "purpose": purpose},
    ).mappings().one_or_none()

    if row is None:
        return CodeCheck(ok=False)

    if row["expired"]:
        session.execute(
            text("UPDATE ops.otp_codes SET voided_at = now() WHERE id = :id"),
            {"id": row["id"]},
        )
        return CodeCheck(ok=False, expired=True)

    supplied = hash_otp(code.strip(), pepper=cfg.secret_key.get_secret_value())
    if not tokens_equal(supplied, row["code_hash"]):
        attempts = int(row["attempts"]) + 1
        exhausted = attempts >= OTP_MAX_ATTEMPTS
        session.execute(
            text(
                """
                UPDATE ops.otp_codes
                   SET attempts = :attempts,
                       voided_at = CASE WHEN :exhausted THEN now() ELSE voided_at END
                 WHERE id = :id
                """
            ),
            {"id": row["id"], "attempts": attempts, "exhausted": exhausted},
        )
        return CodeCheck(ok=False, attempts_left=max(OTP_MAX_ATTEMPTS - attempts, 0))

    session.execute(
        text("UPDATE ops.otp_codes SET consumed_at = now() WHERE id = :id"),
        {"id": row["id"]},
    )
    return CodeCheck(ok=True)
