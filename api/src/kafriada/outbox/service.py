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

import structlog
from sqlalchemy import text
from sqlalchemy.orm import Session

from kafriada.db.engine import transaction
from kafriada.outbox.providers import Sender, SmsError, build_sender

log = structlog.get_logger(__name__)

SMS_REQUESTED = "sms.requested"

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


def drain(*, limit: int = 20, sender: Sender | None = None) -> DrainResult:
    """Send up to ``limit`` due messages. Returns what happened."""
    post = sender or build_sender()
    sent = retried = failed = 0

    for _ in range(limit):
        outcome = _send_one(post)
        if outcome is None:
            return DrainResult(sent=sent, retried=retried, failed=failed, empty=sent == 0)
        sent += outcome == "sent"
        retried += outcome == "retry"
        failed += outcome == "failed"

    return DrainResult(sent=sent, retried=retried, failed=failed)


def _send_one(post: Sender) -> str | None:
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

        if row["event_type"] != SMS_REQUESTED:
            _mark_failed(session, row["id"], attempts, f"unknown event {row['event_type']}")
            log.error("outbox_unknown_event", event_type=row["event_type"])
            return "failed"

        try:
            result = post.send(to=str(payload["to"]), body=str(payload["body"]))
        except SmsError as exc:
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

        # Delivered. The body carried a one-time code, so it does not stay here.
        session.execute(
            text(
                """
                UPDATE ops.outbox
                   SET processed_at = now(),
                       attempts = :attempts,
                       last_error = NULL,
                       payload = jsonb_build_object(
                           'to', payload -> 'to',
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
            },
        )
        log.info("outbox_sent", provider=result.provider, purpose=payload.get("purpose"))
        return "sent"


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
