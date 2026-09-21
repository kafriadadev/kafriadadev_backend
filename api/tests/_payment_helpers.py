"""Shared fixtures for the payment route tests: an athlete with a session, a
signed Paystack delivery, and reads of what the money path wrote.

Rows are left behind, like every other DB test here: users cannot be deleted and
the ledger is append-only.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import date
from types import SimpleNamespace
from uuid import UUID

import pytest
from pydantic import SecretStr
from sqlalchemy import text

from kafriada.contexts.access import service as access
from kafriada.contexts.identity import service as identity
from kafriada.contexts.payments.rules import Purpose
from kafriada.db.engine import money_transaction
from tests._access_helpers import new_phone, sql

PRICE = 250_000
FEE = 3_750
WEBHOOK_KEY = "sk_test_" + "k" * 30


@dataclass(frozen=True)
class Athlete:
    user_id: UUID
    kuid: str
    token: str

    @property
    def headers(self) -> dict[str, str]:
        return {"authorization": f"Bearer {self.token}"}


def new_athlete(name: str = "Payer") -> Athlete:
    phone = new_phone()
    result = identity.register(
        identity.RegistrationInput(
            full_name=f"{name} Test",
            phone=phone,
            password="a long test passphrase",
            date_of_birth=date(1996, 4, 20),
            lga_id="NG-JG-BKD",
            sport="Football",
        )
    )
    token = access.issue_session(result.user_id, method="test").token
    return Athlete(user_id=result.user_id, kuid=result.kuid, token=token)


def use_webhook_key(monkeypatch: pytest.MonkeyPatch, key: str | None = WEBHOOK_KEY) -> None:
    """Give the route a Paystack secret without touching the environment."""
    from kafriada.api.v1 import payments

    monkeypatch.setattr(
        payments,
        "get_settings",
        lambda: SimpleNamespace(paystack_secret_key=SecretStr(key) if key else None),
    )


class LogRecorder:
    """Stands in for a module's structlog logger and keeps what it was told.

    ``structlog.testing.capture_logs`` cannot be used once ``create_app()`` has
    configured structlog with ``cache_logger_on_first_use``: loggers already
    bound ignore the swap, and the test then passes or fails for reasons that
    have nothing to do with the code under test.
    """

    def __init__(self) -> None:
        self.events: list[dict[str, object]] = []

    def _add(self, level: str, event: str, **kw: object) -> None:
        self.events.append({"event": event, "log_level": level, **kw})

    def info(self, event: str, **kw: object) -> None:
        self._add("info", event, **kw)

    def warning(self, event: str, **kw: object) -> None:
        self._add("warning", event, **kw)

    def error(self, event: str, **kw: object) -> None:
        self._add("error", event, **kw)

    def errors(self) -> list[str]:
        return [str(e["event"]) for e in self.events if e["log_level"] == "error"]


def record_logs(monkeypatch: pytest.MonkeyPatch, *modules: object) -> LogRecorder:
    recorder = LogRecorder()
    for module in modules:
        monkeypatch.setattr(module, "log", recorder)
    return recorder


def sign(raw: bytes, key: str = WEBHOOK_KEY) -> dict[str, str]:
    return {"x-paystack-signature": hmac.new(key.encode(), raw, hashlib.sha512).hexdigest()}


def charge_success(reference: str, **data: object) -> bytes:
    body: dict[str, object] = {
        "reference": reference,
        "amount": PRICE,
        "currency": "NGN",
        "status": "success",
        "fees": FEE,
    }
    body.update(data)
    return json.dumps({"event": "charge.success", "data": body}).encode()


def reference_of(athlete: Athlete) -> str:
    """The reference of the athlete's most recent payment."""
    rows = sql(
        "SELECT reference FROM money.payments WHERE paid_by = :u ORDER BY created_at DESC LIMIT 1",
        u=athlete.user_id,
    )
    return str(rows[0]["reference"])


def pending_payment(athlete: Athlete, *, status: str = "pending") -> str:
    from kafriada.contexts.payments.rules import new_reference

    ref = new_reference()
    with money_transaction(reason="test fixture: create payment") as session:
        session.execute(
            text(
                "INSERT INTO money.payments (reference, purpose, expected_kobo, status, paid_by) "
                "VALUES (:r, :p, :e, :s, :u)"
            ),
            {"r": ref, "p": Purpose.STAGE2_ATHLETE.value, "e": PRICE, "s": status, "u": athlete.user_id},
        )
    return ref


def state(reference: str) -> dict[str, object]:
    """Status, ledger lines and 'seen' records for one payment, read as kaf_app."""
    (payment,) = sql(
        "SELECT id, status FROM money.payments WHERE reference = :r", r=reference
    )
    ledger = sql(
        "SELECT direction, source, amount_kobo FROM money.ledger_entries "
        "WHERE payment_id = :p ORDER BY source",
        p=payment["id"],
    )
    seen = sql("SELECT 1 FROM money.webhook_events WHERE payment_id = :p", p=payment["id"])
    actions = sql(
        "SELECT action FROM ops.audit_log WHERE subject_type = 'payment' "
        "AND subject_id = :s ORDER BY id",
        s=str(payment["id"]),
    )
    return {
        "status": payment["status"],
        "ledger": [(r["direction"], r["source"], r["amount_kobo"]) for r in ledger],
        "seen": len(seen),
        "audit": [str(a["action"]) for a in actions],
    }


def charge_success_event(reference: str, **overrides: object):  # type: ignore[no-untyped-def]
    """The parsed ChargeEvent for a matching delivery (settle_charge's input)."""
    from kafriada.contexts.payments.rules import ChargeEvent

    fields: dict[str, object] = {
        "reference": reference,
        "amount_kobo": PRICE,
        "currency": "NGN",
        "status": "success",
        "fees_kobo": FEE,
    }
    fields.update(overrides)
    return ChargeEvent(**fields)  # type: ignore[arg-type]
