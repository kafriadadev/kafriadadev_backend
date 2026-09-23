"""Notifications addressed to a person rather than to a number.

A caller says *who* to tell and what to say in each wording; the worker works
out how to reach them when it sends. What that buys, and what is proved here:

  - the message follows the person: whichever way they can be reached, and
    resolved at send time, so a number changed after queueing is still used
  - **a role with no grant on ``ops.users`` can still notify somebody.**
    Settlement runs as ``kaf_money``, which by design cannot read that table at
    all. If the address had to be resolved by the caller, a payment could not
    send its own receipt — which is a Stage 2 exit criterion
  - somebody unreachable fails once and is kept as evidence, rather than
    retrying until the attempts run out
  - a delivered row still records where the message actually went
"""

from __future__ import annotations

import os
from uuid import UUID

import pytest
from sqlalchemy import text

import uuid

from kafriada.db.engine import money_transaction, transaction
from kafriada.outbox import service as outbox
from kafriada.outbox.email_providers import Sent as EmailSent
from kafriada.outbox.providers import Sent as SmsSent
from tests._access_helpers import make_user, new_phone, sql

pytestmark = [
    pytest.mark.db,
    pytest.mark.skipif(
        not (os.environ.get("DATABASE_URL_APP") and os.environ.get("DATABASE_URL_MONEY")),
        reason="needs the app and money database URLs",
    ),
]


class Recorder:
    """Stands in for a provider and remembers what it was handed."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.sent: list[tuple[str, str]] = []

    def send(self, *, to: str, body: str, **kw: object):  # type: ignore[no-untyped-def]
        self.sent.append((to, body))
        return SmsSent(provider=self.name, provider_message_id="x")


class EmailRecorder(Recorder):
    def send(self, *, to: str, subject: str = "", body: str = "", html: str | None = None):  # type: ignore[no-untyped-def,override]
        self.sent.append((to, body))
        self.subjects = getattr(self, "subjects", [])
        self.subjects.append(subject)
        return EmailSent(provider=self.name, provider_message_id="x")


def set_email(user_id: UUID, email: str | None) -> None:
    with transaction() as session:
        session.execute(
            text("UPDATE ops.users SET email = :e WHERE id = :u"), {"e": email, "u": user_id}
        )


def queued(user_id: UUID) -> list[dict[str, object]]:
    return sql(
        "SELECT payload, processed_at, failed_at, last_error FROM ops.outbox "
        "WHERE payload ->> 'user_id' = :u ORDER BY id",
        u=str(user_id),
    )


def drain_one(sms: Recorder, email: Recorder) -> str | None:
    return outbox.drain(limit=1, sender=sms, email_sender=email).sent and "sent" or None


def test_it_reaches_someone_by_sms_when_that_is_all_they_have() -> None:
    user_id, phone = make_user("Notify SMS")
    set_email(user_id, None)
    with transaction() as session:
        outbox.queue_notification(
            session, user_id=user_id, sms="by sms", subject="s", email="by email",
            purpose="test_notification",
        )

    sms, email = Recorder("sms"), EmailRecorder("email")
    outbox.drain(limit=50, sender=sms, email_sender=email)

    assert (phone, "by sms") in sms.sent
    assert email.sent == []


def test_the_same_message_goes_by_email_when_the_pilot_channel_is_on(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id, _ = make_user("Notify email")
    address = f"notify-{uuid.uuid4().hex[:12]}@example.test"
    set_email(user_id, address)
    monkeypatch.setattr(outbox, "prefers_email", lambda e: bool(e))

    with transaction() as session:
        outbox.queue_notification(
            session, user_id=user_id, sms="by sms", subject="the subject",
            email="by email", purpose="test_notification",
        )

    sms, email = Recorder("sms"), EmailRecorder("email")
    outbox.drain(limit=50, sender=sms, email_sender=email)

    assert (address, "by email") in email.sent
    assert "the subject" in email.subjects
    assert sms.sent == []


def test_the_address_is_resolved_when_it_is_sent_not_when_it_is_queued() -> None:
    user_id, _ = make_user("Notify moved")
    set_email(user_id, None)
    with transaction() as session:
        outbox.queue_notification(
            session, user_id=user_id, sms="body", subject="s", email="body",
            purpose="test_notification",
        )
    # Nothing in the row points at a person's number or inbox...
    (row,) = queued(user_id)
    payload = row["payload"]
    assert "to" not in payload and payload["user_id"] == str(user_id)

    # ...so changing it before the send is what the message follows.
    moved = new_phone()
    with transaction() as session:
        session.execute(
            text("UPDATE ops.users SET phone_e164 = :p WHERE id = :u"),
            {"p": moved, "u": user_id},
        )

    sms, email = Recorder("sms"), EmailRecorder("email")
    outbox.drain(limit=50, sender=sms, email_sender=email)
    assert (moved, "body") in sms.sent


def test_a_delivered_row_still_says_where_it_went() -> None:
    user_id, phone = make_user("Notify evidence")
    set_email(user_id, None)
    with transaction() as session:
        outbox.queue_notification(
            session, user_id=user_id, sms="body", subject="s", email="body",
            purpose="test_notification",
        )

    outbox.drain(limit=50, sender=Recorder("sms"), email_sender=EmailRecorder("email"))

    (row,) = queued(user_id)
    assert row["processed_at"] is not None
    payload = row["payload"]
    assert payload["to"] == phone
    assert payload["scrubbed"] is True
    # The wording is gone; the evidence that it went is not.
    assert "sms" not in payload and "email" not in payload


def test_somebody_unreachable_fails_once_rather_than_retrying() -> None:
    """Anonymised between queueing and sending — there is no longer anyone to tell.

    ``phone_e164`` is NOT NULL, so this is what unreachable actually looks like
    in this schema: the row is still there and must not be written to again.
    """
    user_id, _ = make_user("Notify unreachable")
    with transaction() as session:
        session.execute(
            text("UPDATE ops.users SET email = NULL, anonymised_at = now() WHERE id = :u"),
            {"u": user_id},
        )
        outbox.queue_notification(
            session, user_id=user_id, sms="body", subject="s", email="body",
            purpose="test_notification",
        )

    outbox.drain(limit=50, sender=Recorder("sms"), email_sender=EmailRecorder("email"))

    (row,) = queued(user_id)
    assert row["failed_at"] is not None, "an unreachable person is not a transient failure"
    assert row["processed_at"] is None
    assert "no phone or email" in str(row["last_error"])


def test_the_money_role_can_notify_somebody_it_cannot_look_up() -> None:
    """The privilege point, and the reason the payload holds a user id.

    ``kaf_money`` has no grant on ``ops.users``. It must still be able to send a
    receipt, so queueing must not require reading that table.
    """
    user_id, phone = make_user("Notify from money role")
    set_email(user_id, None)

    with money_transaction(reason="test: receipt from the money role") as session:
        with pytest.raises(Exception) as refused:
            session.execute(text("SELECT phone_e164 FROM ops.users WHERE id = :u"), {"u": user_id})
        assert "permission denied" in str(refused.value).lower()

    with money_transaction(reason="test: receipt from the money role") as session:
        outbox.queue_notification(
            session, user_id=user_id, sms="receipt", subject="s", email="receipt",
            purpose="payment_received",
        )

    sms = Recorder("sms")
    outbox.drain(limit=50, sender=sms, email_sender=EmailRecorder("email"))
    assert (phone, "receipt") in sms.sent
