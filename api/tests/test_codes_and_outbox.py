"""One-time codes, and the outbox that carries them.

The code itself is only ever readable in one place — the queued message — which
is what these tests read, exactly as a phone would. Nothing here reaches into
the hash.

What is proved:
  - registering queues one code and leaves the phone unconfirmed
  - the right code confirms the number, signs the person in, and cannot be used twice
  - wrong codes are counted and the fifth kills the code, expired codes are refused,
    and a code for one purpose is useless for the other
  - resending is capped per minute and per day
  - a reset sets the password, ends every session, and answers unknown numbers
    exactly as it answers registered ones
  - the outbox sends once, scrubs the code from the delivered row, retries a
    transient failure with backoff, and gives up on a permanent one
"""

from __future__ import annotations

import os
import re
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from kafriada.contexts.access import otp
from kafriada.contexts.identity.service import register
from kafriada.main import create_app
from kafriada.outbox import service as outbox
from kafriada.outbox.providers import Sent, SmsError
from tests._access_helpers import audit_actions, bearer, make_user, new_phone, sql
from tests._registration import registration

pytestmark = [
    pytest.mark.db,
    pytest.mark.skipif(
        not os.environ.get("DATABASE_URL_APP"),
        reason="needs DATABASE_URL_APP",
    ),
]

PASSWORD = "a long test passphrase"


@pytest.fixture(scope="module")
def client() -> Iterator[TestClient]:
    with TestClient(create_app()) as c:
        yield c


# ---------------------------------------------------------------------------
# Helpers: read the code the way a phone would — out of the queued message
# ---------------------------------------------------------------------------
def queued_code(phone: str) -> str:
    rows = sql(
        """
        SELECT payload ->> 'body' AS body
          FROM ops.outbox
         WHERE payload ->> 'to' = :phone AND payload ? 'body'
         ORDER BY id DESC LIMIT 1
        """,
        phone=phone,
    )
    assert rows, f"no message queued for {phone}"
    found = re.search(r"\b(\d{6})\b", str(rows[0]["body"]))
    assert found, f"no six-digit code in {rows[0]['body']!r}"
    return found.group(1)


def email_of(phone: str) -> str:
    """The address tests._registration derives from a phone."""
    return f"t{phone.lstrip('+')}@example.test"


def register_athlete(name: str = "Code Test") -> tuple[str, str]:
    """Register through the service. Returns (phone, kuid)."""
    phone = new_phone()
    result = register(
        registration(phone, f"{name} Athlete", password=PASSWORD)
    )
    return phone, result.kuid


class Recorder:
    """A sender that records what it was asked to send."""

    name = "recorder"

    def __init__(self, fail: SmsError | None = None) -> None:
        self.sent: list[tuple[str, str]] = []
        self.fail = fail

    def send(self, *, to: str, body: str) -> Sent:
        if self.fail is not None:
            raise self.fail
        self.sent.append((to, body))
        return Sent(provider=self.name, provider_message_id="SM-test")


# ---------------------------------------------------------------------------
# Registration and confirmation
# ---------------------------------------------------------------------------
def test_registering_emails_one_code_and_sends_no_sms(client: TestClient) -> None:
    phone, _ = register_athlete()

    (user,) = sql(
        "SELECT id, email_verified_at FROM ops.users WHERE phone_e164 = :p", p=phone
    )
    assert user["email_verified_at"] is None, "registration must not confirm the email"

    codes = sql(
        "SELECT purpose, consumed_at, sent_to FROM ops.otp_codes WHERE user_id = :id",
        id=user["id"],
    )
    assert codes == [
        {"purpose": "email_verification", "consumed_at": None, "sent_to": email_of(phone)}
    ]

    by_email = sql(
        "SELECT payload ->> 'purpose' AS purpose FROM ops.outbox WHERE payload ->> 'to' = :e",
        e=email_of(phone),
    )
    assert by_email == [{"purpose": "email_verification"}]
    # Phone confirmation is off until an SMS route exists: no text is queued.
    assert not sql("SELECT id FROM ops.outbox WHERE payload ->> 'to' = :p", p=phone)


def test_sign_in_waits_for_the_email_and_sends_a_code(client: TestClient) -> None:
    phone, _ = register_athlete()
    refused = client.post("/v1/sessions", json={"phone": phone, "password": PASSWORD})
    assert refused.status_code == 409, refused.text
    detail = refused.json()["error"]["message"]
    assert detail["reason"] == "email_unconfirmed"
    assert "token" not in refused.text

    code = queued_code(email_of(phone))
    assert client.post(
        "/v1/email/confirm", json={"phone": phone, "code": code}
    ).status_code == 200
    assert client.post(
        "/v1/sessions", json={"phone": phone, "password": PASSWORD}
    ).status_code == 201


def test_a_wrong_password_never_learns_about_the_email(client: TestClient) -> None:
    phone, _ = register_athlete()
    response = client.post("/v1/sessions", json={"phone": phone, "password": "not it at all"})
    assert response.status_code == 401
    assert "email" not in response.text.lower()


def test_an_account_with_no_email_is_asked_for_one(client: TestClient) -> None:
    user_id, phone = make_user("No Email", password=PASSWORD, grants=[("athlete", "global", None)])
    sql("UPDATE ops.users SET email = NULL, email_verified_at = NULL WHERE id = :id", id=user_id)

    asked = client.post("/v1/sessions", json={"phone": phone, "password": PASSWORD})
    assert asked.status_code == 409
    assert asked.json()["error"]["message"]["reason"] == "email_missing"

    address = f"added{phone.lstrip('+')}@example.test"
    sent = client.post(
        "/v1/sessions", json={"phone": phone, "password": PASSWORD, "email": address}
    )
    assert sent.status_code == 409
    assert sent.json()["error"]["message"]["reason"] == "email_unconfirmed"
    assert sql("SELECT email FROM ops.users WHERE id = :id", id=user_id) == [{"email": address}]
    code = queued_code(address)
    assert client.post(
        "/v1/email/confirm", json={"phone": phone, "code": code}
    ).status_code == 200


def test_the_right_code_confirms_signs_in_and_cannot_be_used_twice(
    client: TestClient,
) -> None:
    phone, kuid = register_athlete()
    code = queued_code(email_of(phone))

    confirmed = client.post("/v1/email/confirm", json={"phone": phone, "code": code})
    assert confirmed.status_code == 200, confirmed.text
    body = confirmed.json()
    assert body["kuid"] == kuid

    # The token that comes back is a working session.
    me = client.get("/v1/me", headers=bearer(body["token"]))
    assert me.status_code == 200
    assert me.json()["email_verified"] is True

    (user,) = sql("SELECT id FROM ops.users WHERE phone_e164 = :p", p=phone)
    assert "email.verified" in audit_actions(user["id"])

    # Spent. A second use is refused, however quickly it follows.
    again = client.post("/v1/email/confirm", json={"phone": phone, "code": code})
    assert again.status_code == 422


def test_wrong_codes_are_counted_and_the_fifth_kills_the_code(client: TestClient) -> None:
    phone, _ = register_athlete()
    right = queued_code(email_of(phone))

    for attempt in range(1, 5):
        response = client.post("/v1/email/confirm", json={"phone": phone, "code": "000000"})
        assert response.status_code == 422
        message = response.json()["error"]["message"]["message"]
        assert f"{5 - attempt} tr" in message, message

    # The fifth wrong answer ends the code, and the real one no longer works.
    last = client.post("/v1/email/confirm", json={"phone": phone, "code": "000000"})
    assert last.status_code == 422
    assert client.post(
        "/v1/email/confirm", json={"phone": phone, "code": right}
    ).status_code == 422

    (user,) = sql("SELECT id FROM ops.users WHERE phone_e164 = :p", p=phone)
    assert sql(
        "SELECT email_verified_at FROM ops.users WHERE id = :id", id=user["id"]
    ) == [{"email_verified_at": None}]


def test_an_expired_code_is_refused(client: TestClient) -> None:
    phone, _ = register_athlete()
    code = queued_code(email_of(phone))
    sql(
        """
        UPDATE ops.otp_codes SET expires_at = now() - interval '1 second'
         WHERE user_id = (SELECT id FROM ops.users WHERE phone_e164 = :p)
           AND consumed_at IS NULL AND voided_at IS NULL
        """,
        p=phone,
    )
    response = client.post("/v1/email/confirm", json={"phone": phone, "code": code})
    assert response.status_code == 422
    assert "expired" in response.json()["error"]["message"]["message"]


def test_a_confirmation_code_is_not_a_password_reset_code(client: TestClient) -> None:
    phone, _ = register_athlete()
    code = queued_code(email_of(phone))

    response = client.post(
        "/v1/password-reset/confirm",
        json={"phone": phone, "code": code, "new_password": "another long passphrase"},
    )
    assert response.status_code == 422, "an email code must not reset a password"


# ---------------------------------------------------------------------------
# Resending
# ---------------------------------------------------------------------------
def test_resending_is_capped_per_minute_and_per_day(client: TestClient) -> None:
    phone, _ = register_athlete()
    (user,) = sql("SELECT id FROM ops.users WHERE phone_e164 = :p", p=phone)

    # Straight after registration, another code is refused politely.
    soon = client.post("/v1/email/code", json={"phone": phone})
    assert soon.status_code == 202
    assert soon.json()["resend_in"] > 0
    assert len(sql("SELECT id FROM ops.otp_codes WHERE user_id = :id", id=user["id"])) == 1

    # Move the clock back on the existing code and a resend is allowed. The old
    # code is retired so there is never more than one live code.
    sql(
        "UPDATE ops.otp_codes SET created_at = now() - interval '5 minutes' "
        "WHERE user_id = :id",
        id=user["id"],
    )
    again = client.post("/v1/email/code", json={"phone": phone})
    assert again.status_code == 202
    live = sql(
        "SELECT id FROM ops.otp_codes WHERE user_id = :id "
        "AND consumed_at IS NULL AND voided_at IS NULL",
        id=user["id"],
    )
    assert len(live) == 1

    # Five sends in a day is the cap.
    sql(
        "UPDATE ops.otp_codes SET created_at = now() - interval '5 minutes' "
        "WHERE user_id = :id",
        id=user["id"],
    )
    for _ in range(3):
        client.post("/v1/email/code", json={"phone": phone})
        sql(
            "UPDATE ops.otp_codes SET created_at = now() - interval '5 minutes' "
            "WHERE user_id = :id",
            id=user["id"],
        )
    capped = client.post("/v1/email/code", json={"phone": phone})
    assert capped.json()["daily_limit_reached"] is True
    assert len(sql("SELECT id FROM ops.otp_codes WHERE user_id = :id", id=user["id"])) == 5


# ---------------------------------------------------------------------------
# Password reset
# ---------------------------------------------------------------------------
def test_a_reset_changes_the_password_and_ends_every_session(client: TestClient) -> None:
    user_id, phone = make_user("Resetter", password=PASSWORD, grants=[("athlete", "global", None)])
    token = client.post(
        "/v1/sessions", json={"phone": phone, "password": PASSWORD}
    ).json()["token"]

    assert client.post("/v1/password-reset/code", json={"phone": phone}).status_code == 202
    code = queued_code(phone)

    new_password = "a completely different passphrase"
    done = client.post(
        "/v1/password-reset/confirm",
        json={"phone": phone, "code": code, "new_password": new_password},
    )
    assert done.status_code == 204, done.text

    # Every session ended — including the one open when the reset happened.
    assert client.get("/v1/me", headers=bearer(token)).status_code == 401
    assert client.post(
        "/v1/sessions", json={"phone": phone, "password": PASSWORD}
    ).status_code == 401
    assert client.post(
        "/v1/sessions", json={"phone": phone, "password": new_password}
    ).status_code == 201
    assert "password.reset" in audit_actions(user_id)


def test_unknown_numbers_are_indistinguishable(client: TestClient) -> None:
    """The reset screen must not answer "is this person registered?"."""
    _, known = make_user("Known Reset", password=PASSWORD)
    unknown = new_phone()

    known_response = client.post("/v1/password-reset/code", json={"phone": known})
    unknown_response = client.post("/v1/password-reset/code", json={"phone": unknown})

    assert known_response.status_code == unknown_response.status_code == 202
    assert known_response.json() == unknown_response.json()
    assert not sql("SELECT id FROM ops.outbox WHERE payload ->> 'to' = :p", p=unknown)

    # And a code for a number with no account is refused like any wrong code.
    refused = client.post(
        "/v1/password-reset/confirm",
        json={"phone": unknown, "code": "123456", "new_password": "a long new passphrase"},
    )
    assert refused.status_code == 422


def test_a_weak_new_password_is_refused_before_anything_changes(client: TestClient) -> None:
    _, phone = make_user("Weak Reset", password=PASSWORD)
    client.post("/v1/password-reset/code", json={"phone": phone})
    code = queued_code(phone)

    response = client.post(
        "/v1/password-reset/confirm",
        json={"phone": phone, "code": code, "new_password": "short"},
    )
    assert response.status_code == 422
    assert response.json()["error"]["message"]["field"] == "new_password"
    # The code is untouched, so the person can try again with a better password.
    assert client.post(
        "/v1/password-reset/confirm",
        json={"phone": phone, "code": code, "new_password": "a properly long passphrase"},
    ).status_code == 204


# ---------------------------------------------------------------------------
# The outbox
# ---------------------------------------------------------------------------
def test_a_message_is_sent_once_and_the_code_is_scrubbed_from_the_row() -> None:
    user_id, phone = make_user("Outbox")
    with_code = Recorder()
    message_id = _queue_one(user_id, phone)

    sent = _drain_until(message_id, with_code)
    assert sent >= 1
    assert any(to == phone for to, _ in with_code.sent)

    (row,) = sql("SELECT processed_at, payload FROM ops.outbox WHERE id = :id", id=message_id)
    assert row["processed_at"] is not None
    payload = row["payload"]
    assert payload["scrubbed"] is True
    assert payload["provider"] == "recorder"
    assert "body" not in payload, "the delivered row must not keep the code"

    # A processed row is never picked up again.
    second = Recorder()
    outbox.drain(limit=20, sender=second)
    assert all(to != phone for to, _ in second.sent)


def test_a_transient_failure_is_retried_with_backoff_and_kept() -> None:
    user_id, phone = make_user("Outbox Retry")
    message_id = _queue_one(user_id, phone)

    _drain_until(message_id, Recorder(fail=SmsError("upstream 503", transient=True)))

    (row,) = sql(
        "SELECT attempts, failed_at, last_error, available_at > now() AS waiting "
        "FROM ops.outbox WHERE id = :id",
        id=message_id,
    )
    assert row == {
        "attempts": 1,
        "failed_at": None,
        "last_error": "upstream 503",
        "waiting": True,
    }


def test_a_permanent_failure_gives_up_at_once_and_keeps_the_row() -> None:
    user_id, phone = make_user("Outbox Fail")
    message_id = _queue_one(user_id, phone)

    _drain_until(message_id, Recorder(fail=SmsError("invalid number", transient=False)))

    (row,) = sql(
        "SELECT attempts, failed_at IS NOT NULL AS failed, last_error "
        "FROM ops.outbox WHERE id = :id",
        id=message_id,
    )
    assert row == {"attempts": 1, "failed": True, "last_error": "invalid number"}


def _drain_until(message_id: int, sender: Recorder) -> int:
    """Drain until our message has been dealt with.

    The queue holds whatever the other tests have registered, so a fixed batch
    is not enough to reach a particular row.
    """
    sent = 0
    for _ in range(20):
        sent += outbox.drain(limit=20, sender=sender).sent
        (row,) = sql(
            "SELECT processed_at IS NOT NULL OR failed_at IS NOT NULL "
            "OR available_at > now() AS done FROM ops.outbox WHERE id = :id",
            id=message_id,
        )
        if row["done"]:
            return sent
    raise AssertionError("the outbox never reached the message under test")


def _queue_one(user_id: object, phone: str) -> int:
    """Queue a code the way the application does, and return the message id."""
    from kafriada.db.engine import transaction

    with transaction() as session:
        otp.send_code(
            session,
            user_id=user_id,  # type: ignore[arg-type]
            purpose=otp.PHONE_VERIFICATION,
            phone_e164=phone,
            enforce_limits=False,
        )
    (row,) = sql(
        "SELECT id FROM ops.outbox WHERE payload ->> 'to' = :p ORDER BY id DESC LIMIT 1",
        p=phone,
    )
    return int(row["id"])  # type: ignore[arg-type]
