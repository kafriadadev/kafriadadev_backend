"""Queueing a message, and draining the queue.

Writing is trivial and belongs to whoever is writing the record: one INSERT, in
their transaction. Draining is where the care is.

**One message per transaction.** The row is locked while the provider call is in
flight — that lock is what stops two workers sending the same code twice. The
engine sets ``idle_in_transaction_session_timeout`` to 30 seconds, and an HTTP
call counts as idle time, so a batch of sends inside one transaction would be
killed mid-drain. One row, one transaction, one send.

**FOR UPDATE SKIP LOCKED.** Any number of workers can run at once with no
coordination and no broker: each takes rows nobody else holds.

**Backoff, then give up.** A transient failure comes back in seconds, then
minutes. After the last attempt the row is marked failed and kept, because an
athlete who never got a code is a support case and this row is the evidence.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import structlog
from sqlalchemy import text
from sqlalchemy.orm import Session

from kafriada.db.engine import transaction
from kafriada.outbox import email_providers
from kafriada.outbox.email_providers import EmailError
from kafriada.outbox.email_providers import Sender as EmailSender
from kafriada.outbox.providers import Sender, SmsError, build_sender
from kafriada.outbox.providers import Sent as SmsSent
from kafriada.settings import OtpChannel, get_settings

log = structlog.get_logger(__name__)

SMS_REQUESTED = "sms.requested"
EMAIL_REQUESTED = "email.requested"
# Addressed to a *person*, not to a phone or an inbox: the worker looks up how to
# reach them at send time. Two reasons, and the second is the load-bearing one:
# a recipient who changes their number between queueing and sending still gets the
# message, and a caller that cannot read ops.users can still notify someone —
# settlement runs as kaf_money, which by design has no grant on that table at all.
NOTIFICATION_REQUESTED = "notification.requested"

MAX_ATTEMPTS = 5
# Seconds before each retry. A one-time code is worth nothing in an hour, so the
# first retries are quick and the tail is short.
BACKOFF_SECONDS = (30, 120, 600, 1_800)


@dataclass(frozen=True, slots=True)
class DrainResult:
    sent: int = 0
    retried: int = 0
    failed: int = 0
    # True when there was nothing due. Lets a worker loop idle politely.
    empty: bool = False


def prefers_email(email: str | None) -> bool:
    """Whether a message to this person should go by email rather than SMS.

    The one place the pilot's channel rule lives, so the OTP path and every
    other notification cannot drift apart. 'email' is a stand-in while Twilio
    has no Nigerian sender id (settings.otp_channel); somebody with no email on
    file still gets SMS, because there is nowhere else to send it.
    """
    return bool(email) and get_settings().otp_channel is OtpChannel.EMAIL


def queue_notification(
    session: Session,
    *,
    user_id: UUID,
    sms: str,
    subject: str,
    email: str,
    purpose: str,
) -> int:
    """Queue one message to a person, inside the caller's transaction.

    Both wordings are stored: which one is used depends on how that person can
    be reached, and that is not known until the worker sends it. No phone
    number or address is written here — only who to tell.
    """
    message_id: int = session.execute(
        text(
            """
            INSERT INTO ops.outbox (event_type, payload)
            VALUES (:event_type, CAST(:payload AS jsonb))
            RETURNING id
            """
        ),
        {
            "event_type": NOTIFICATION_REQUESTED,
            "payload": json.dumps(
                {
                    "user_id": str(user_id),
                    "sms": sms,
                    "subject": subject,
                    "email": email,
                    "purpose": purpose,
                }
            ),
        },
    ).scalar_one()
    return message_id


def queue_sms(
    session: Session,
    *,
    to_phone: str,
    body: str,
    purpose: str,
) -> int:
    """Queue one SMS inside the caller's transaction.

    If that transaction rolls back, so does the message — which is the whole
    point: no code is ever sent for a registration that did not happen.
    """
    message_id: int = session.execute(
        text(
            """
            INSERT INTO ops.outbox (event_type, payload)
            VALUES (:event_type, CAST(:payload AS jsonb))
            RETURNING id
            """
        ),
        {
            "event_type": SMS_REQUESTED,
            "payload": json.dumps({"to": to_phone, "body": body, "purpose": purpose}),
        },
    ).scalar_one()
    return message_id


def queue_email(
    session: Session,
    *,
    to_email: str,
    subject: str,
    body: str,
    purpose: str,
    html: str | None = None,
) -> int:
    """Queue one email inside the caller's transaction. See ``queue_sms``."""
    message_id: int = session.execute(
        text(
            """
            INSERT INTO ops.outbox (event_type, payload)
            VALUES (:event_type, CAST(:payload AS jsonb))
            RETURNING id
            """
        ),
        {
            "event_type": EMAIL_REQUESTED,
            "payload": json.dumps(
                {"to": to_email, "subject": subject, "body": body, "html": html,
                 "purpose": purpose}
            ),
        },
    ).scalar_one()
    return message_id


def drain(
    *,
    limit: int = 20,
    sender: Sender | None = None,
    email_sender: EmailSender | None = None,
) -> DrainResult:
    """Send up to ``limit`` due messages, of either channel. Returns what happened."""
    post = sender or build_sender()
    email_post = email_sender or email_providers.build_sender()
    sent = retried = failed = 0

    for _ in range(limit):
        outcome = _send_one(post, email_post)
        if outcome is None:
            return DrainResult(sent=sent, retried=retried, failed=failed, empty=sent == 0)
        sent += outcome == "sent"
        retried += outcome == "retry"
        failed += outcome == "failed"

    return DrainResult(sent=sent, retried=retried, failed=failed)


def _send_one(post: Sender, email_post: EmailSender) -> str | None:
    """Take one due row, send it, and record the outcome. None if none is due."""
    with transaction() as session:
        row = session.execute(
            text(
                """
                SELECT id, event_type, payload, attempts
                  FROM ops.outbox
                 WHERE processed_at IS NULL
                   AND failed_at IS NULL
                   AND available_at <= now()
                 ORDER BY id
                 FOR UPDATE SKIP LOCKED
                 LIMIT 1
                """
            )
        ).mappings().one_or_none()
        if row is None:
            return None

        payload: dict[str, Any] = row["payload"]
        attempts = int(row["attempts"]) + 1
        event_type = row["event_type"]

        if event_type not in (SMS_REQUESTED, EMAIL_REQUESTED, NOTIFICATION_REQUESTED):
            _mark_failed(session, row["id"], attempts, f"unknown event {event_type}")
            log.error("outbox_unknown_event", event_type=event_type)
            return "failed"

        # Addressed to a person: find out how to reach them, now rather than when
        # it was queued. Someone with no way to be reached is a permanent failure,
        # not a retry — the row is kept as the evidence that nobody was told.
        sent_to: str | None = None
        if event_type == NOTIFICATION_REQUESTED:
            reach = _reach(session, payload["user_id"])
            if reach is None:
                _mark_failed(session, row["id"], attempts, "no phone or email on file")
                log.error("outbox_unreachable", purpose=payload.get("purpose"))
                return "failed"
            sent_to, by_email = reach

        result: SmsSent | email_providers.Sent
        try:
            if event_type == SMS_REQUESTED:
                result = post.send(to=str(payload["to"]), body=str(payload["body"]))
            elif event_type == NOTIFICATION_REQUESTED:
                assert sent_to is not None
                result = (
                    email_post.send(
                        to=sent_to, subject=str(payload["subject"]), body=str(payload["email"])
                    )
                    if by_email
                    else post.send(to=sent_to, body=str(payload["sms"]))
                )
            else:
                html = payload.get("html")
                result = email_post.send(
                    to=str(payload["to"]),
                    subject=str(payload["subject"]),
                    body=str(payload["body"]),
                    html=str(html) if html is not None else None,
                )
        except (SmsError, EmailError) as exc:
            if exc.transient and attempts < MAX_ATTEMPTS:
                delay = BACKOFF_SECONDS[min(attempts, len(BACKOFF_SECONDS)) - 1]
                session.execute(
                    text(
                        """
                        UPDATE ops.outbox
                           SET attempts = :attempts,
                               last_error = :error,
                               available_at = now() + CAST(:delay AS integer) * interval '1 second'
                         WHERE id = :id
                        """
                    ),
                    {"id": row["id"], "attempts": attempts, "error": exc.message[:500],
                     "delay": delay},
                )
                log.warning("outbox_retry", attempts=attempts, in_seconds=delay)
                return "retry"
            _mark_failed(session, row["id"], attempts, exc.message)
            log.error("outbox_gave_up", attempts=attempts, transient=exc.transient)
            return "failed"

        # Delivered. The body may have carried a one-time code, so it does not stay here.
        # The subject line is kept for email — it holds nothing a code or password would.
        session.execute(
            text(
                """
                UPDATE ops.outbox
                   SET processed_at = now(),
                       attempts = :attempts,
                       last_error = NULL,
                       payload = jsonb_build_object(
                           'to', coalesce(payload -> 'to', to_jsonb(CAST(:sent_to AS text))),
                           -- Kept for a notification: it is the only thing tying a
                           -- delivered row back to the person who was told.
                           'user_id', payload -> 'user_id',
                           'subject', payload -> 'subject',
                           'purpose', payload -> 'purpose',
                           'provider', CAST(:provider AS text),
                           'provider_message_id', CAST(:message_id AS text),
                           'scrubbed', true)
                 WHERE id = :id
                """
            ),
            {
                "id": row["id"],
                "attempts": attempts,
                "provider": result.provider,
                "message_id": result.provider_message_id,
                # A notification carried no address; record the one it reached, so a
                # delivered row is still evidence of where the message went.
                "sent_to": sent_to,
            },
        )
        log.info("outbox_sent", provider=result.provider, purpose=payload.get("purpose"))
        return "sent"


def _reach(session: Session, user_id: str) -> tuple[str, bool] | None:
    """How to reach this person, and whether that is by email. None if neither.

    Read here, on the worker's own connection, rather than carried in the
    payload: the roles that queue a notification do not all have a grant on
    ``ops.users`` — settlement runs as ``kaf_money``, which has none.
    """
    row = session.execute(
        text(
            "SELECT phone_e164, email FROM ops.users "
            "WHERE id = CAST(:id AS uuid) AND anonymised_at IS NULL"
        ),
        {"id": user_id},
    ).mappings().one_or_none()
    if row is None:
        return None
    if prefers_email(row["email"]):
        return str(row["email"]), True
    return (str(row["phone_e164"]), False) if row["phone_e164"] else None


def _mark_failed(session: Session, message_id: int, attempts: int, error: str) -> None:
    session.execute(
        text(
            """
            UPDATE ops.outbox
               SET failed_at = now(), attempts = :attempts, last_error = :error
             WHERE id = :id
            """
        ),
        {"id": message_id, "attempts": attempts, "error": error[:500]},
    )


def prune_delivered(*, keep_days: int = 30, keep_failed_days: int = 90) -> int:
    """Delete delivered messages after ``keep_days`` and given-up ones after ``keep_failed_days``.

    A delivered row was already scrubbed of its body; what remains is only the evidence
    that a message went out, which stops being useful within a month. Failed rows are kept
    longer because each one is a support case. Rows still waiting to be sent are never
    touched, however old.
    """
    with transaction() as session:
        result = session.execute(
            text(
                """
                DELETE FROM ops.outbox
                 WHERE (processed_at IS NOT NULL AND processed_at < now() - make_interval(days => :ok))
                    OR (failed_at IS NOT NULL AND failed_at < now() - make_interval(days => :bad))
                """
            ),
            {"ok": keep_days, "bad": keep_failed_days},
        )
        return int(getattr(result, "rowcount", 0) or 0)


def pending_count() -> int:
    """How many messages are waiting. For the dispatcher and for support."""
    with transaction() as session:
        return int(
            session.execute(
                text(
                    "SELECT count(*) FROM ops.outbox "
                    "WHERE processed_at IS NULL AND failed_at IS NULL"
                )
            ).scalar_one()
        )
