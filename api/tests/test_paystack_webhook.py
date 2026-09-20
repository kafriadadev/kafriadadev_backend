"""The webhook route: what a signed delivery does, and what an unsigned one cannot.

What is proved here, through the real route and a real database:
  - only a correctly signed body is acted on; a wrong, missing or tampered
    signature changes nothing — no status, no ledger line, no "seen" record
  - the signature is over the exact bytes sent, whatever their whitespace
  - a valid delivery settles; the same delivery five times at once still leaves
    two ledger lines; a wrong amount freezes and alerts
  - every answer a retry cannot improve is 200; a failure to *record* is a 5xx,
    so Paystack redelivers and the rolled-back payment can settle then
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from kafriada.api.v1 import payments
from kafriada.contexts.payments import settlement
from kafriada.contexts.payments.rules import IllegalTransition, new_reference
from kafriada.main import create_app
from tests._payment_helpers import (
    FEE,
    PRICE,
    Athlete,
    charge_success,
    new_athlete,
    pending_payment,
    record_logs,
    sign,
    state,
    use_webhook_key,
)

pytestmark = [
    pytest.mark.db,
    pytest.mark.skipif(
        not (os.environ.get("DATABASE_URL_APP") and os.environ.get("DATABASE_URL_MONEY")),
        reason="needs DATABASE_URL_APP and DATABASE_URL_MONEY",
    ),
]

URL = "/v1/payments/webhook/paystack"
UNTOUCHED = {"status": "pending", "ledger": [], "seen": 0, "audit": []}


@pytest.fixture(scope="module")
def payer() -> Athlete:
    return new_athlete()


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    use_webhook_key(monkeypatch)
    with TestClient(create_app()) as c:
        yield c


class TestNothingHappensWithoutAValidSignature:
    def test_a_wrong_signature_changes_nothing(self, client: TestClient, payer: Athlete) -> None:
        ref = pending_payment(payer)
        raw = charge_success(ref)
        response = client.post(URL, content=raw, headers=sign(raw, key="sk_test_not_the_key_" + "z" * 12))
        assert response.status_code == 400
        assert state(ref) == UNTOUCHED

    def test_a_missing_signature_changes_nothing(self, client: TestClient, payer: Athlete) -> None:
        ref = pending_payment(payer)
        assert client.post(URL, content=charge_success(ref)).status_code == 400
        assert state(ref) == UNTOUCHED

    def test_a_body_altered_after_signing_changes_nothing(
        self, client: TestClient, payer: Athlete
    ) -> None:
        ref = pending_payment(payer)
        honest = charge_success(ref)
        # Signed for the real amount, sent with a different one.
        forged = charge_success(ref, amount=PRICE - 1)
        assert client.post(URL, content=forged, headers=sign(honest)).status_code == 400
        assert state(ref) == UNTOUCHED

    def test_without_a_configured_key_nothing_can_be_verified(
        self, monkeypatch: pytest.MonkeyPatch, payer: Athlete
    ) -> None:
        use_webhook_key(monkeypatch, None)
        ref = pending_payment(payer)
        raw = charge_success(ref)
        logs = record_logs(monkeypatch, payments)
        with TestClient(create_app()) as c:
            assert c.post(URL, content=raw, headers=sign(raw)).status_code == 400
        assert "paystack_webhook_unverifiable" in logs.errors()
        assert state(ref) == UNTOUCHED

    def test_an_enormous_body_is_refused_before_it_is_hashed(self, client: TestClient) -> None:
        assert client.post(URL, content=b"x" * (payments.MAX_WEBHOOK_BYTES + 1)).status_code == 413


class TestSettling:
    def test_a_signed_charge_settles_into_two_ledger_lines(
        self, client: TestClient, payer: Athlete
    ) -> None:
        ref = pending_payment(payer)
        raw = charge_success(ref)
        assert client.post(URL, content=raw, headers=sign(raw)).status_code == 200
        assert state(ref) == {
            "status": "success",
            "ledger": [("debit", "fee", FEE), ("credit", "paystack", PRICE)],
            "seen": 1,
            "audit": ["payment.settled"],
        }

    def test_the_signature_is_over_the_exact_bytes_not_the_parsed_json(
        self, client: TestClient, payer: Athlete
    ) -> None:
        ref = pending_payment(payer)
        # Unusual spacing and key order that json.dumps would never reproduce.
        raw = (
            '{ "data" : {"fees":%d,  "status":"success", "currency":"NGN",'
            ' "amount":%d ,"reference":"%s"},\n "event":"charge.success" }' % (FEE, PRICE, ref)
        ).encode()
        assert client.post(URL, content=raw, headers=sign(raw)).status_code == 200
        assert state(ref)["status"] == "success"

    def test_a_late_payment_on_an_abandoned_attempt_settles(
        self, client: TestClient, payer: Athlete
    ) -> None:
        ref = pending_payment(payer, status="abandoned")
        raw = charge_success(ref)
        assert client.post(URL, content=raw, headers=sign(raw)).status_code == 200
        assert state(ref)["status"] == "success"

    def test_five_identical_deliveries_at_once_leave_exactly_two_ledger_lines(
        self, monkeypatch: pytest.MonkeyPatch, payer: Athlete
    ) -> None:
        use_webhook_key(monkeypatch)
        ref = pending_payment(payer)
        raw = charge_success(ref)

        app = create_app()  # once, here: building it is not safe to race

        def deliver(_: int) -> int:
            return TestClient(app).post(URL, content=raw, headers=sign(raw)).status_code

        with ThreadPoolExecutor(max_workers=5) as pool:
            codes = list(pool.map(deliver, range(5)))

        assert codes == [200] * 5
        found = state(ref)
        assert len(found["ledger"]) == 2  # type: ignore[arg-type]
        assert found["status"] == "success"
        assert found["seen"] == 1
        assert found["audit"] == ["payment.settled"]


class TestFreezing:
    def test_ten_naira_for_a_2500_naira_badge_freezes_and_alerts(
        self, client: TestClient, payer: Athlete, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        ref = pending_payment(payer)
        raw = charge_success(ref, amount=1_000, fees=15)
        logs = record_logs(monkeypatch, settlement)
        assert client.post(URL, content=raw, headers=sign(raw)).status_code == 200
        found = state(ref)
        assert found["status"] == "frozen"
        assert found["ledger"] == []
        assert found["audit"] == ["payment.frozen"]
        assert logs.errors() == ["payment_frozen"]


class TestAnswersARetryCannotImprove:
    def test_a_signed_event_we_do_not_handle_is_a_quiet_200(self, client: TestClient) -> None:
        raw = b'{"event":"transfer.success","data":{"reference":"x"}}'
        assert client.post(URL, content=raw, headers=sign(raw)).status_code == 200

    def test_a_reference_that_is_not_ours_is_ignored(self, client: TestClient) -> None:
        raw = charge_success("order-8841")
        assert client.post(URL, content=raw, headers=sign(raw)).status_code == 200

    def test_a_signed_body_we_cannot_read_is_a_200_and_an_alert(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        logs = record_logs(monkeypatch, payments)
        for raw in (b"not json at all", b'{"event":"charge.success","data":{"amount":"lots"}}'):
            assert client.post(URL, content=raw, headers=sign(raw)).status_code == 200
        assert logs.errors() == ["paystack_webhook_unreadable"] * 2

    def test_a_kaf_reference_we_have_no_row_for_is_a_200_and_an_alert(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        logs = record_logs(monkeypatch, settlement)
        raw = charge_success(new_reference())
        assert client.post(URL, content=raw, headers=sign(raw)).status_code == 200
        assert logs.errors() == ["payment_reference_unknown"]

    def test_an_illegal_transition_is_a_200_and_an_alert(
        self, client: TestClient, payer: Athlete, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def refuse(*_a: object, **_k: object) -> None:
            raise IllegalTransition("a success payment cannot become frozen")

        monkeypatch.setattr(payments, "settle_charge", refuse)
        logs = record_logs(monkeypatch, payments)
        raw = charge_success(pending_payment(payer))
        assert client.post(URL, content=raw, headers=sign(raw)).status_code == 200
        assert logs.errors() == ["paystack_webhook_illegal_transition"]


class TestAFailureToRecordIsNotAnAnswer:
    def test_a_database_failure_is_a_5xx_so_paystack_redelivers(
        self, monkeypatch: pytest.MonkeyPatch, payer: Athlete
    ) -> None:
        use_webhook_key(monkeypatch)
        ref = pending_payment(payer)
        raw = charge_success(ref)
        real = payments.settle_charge

        def down(*_a: object, **_k: object) -> None:
            raise OperationalError("SELECT 1", {}, Exception("connection refused"))

        monkeypatch.setattr(payments, "settle_charge", down)
        with TestClient(create_app(), raise_server_exceptions=False) as c:
            assert c.post(URL, content=raw, headers=sign(raw)).status_code == 500
        assert state(ref) == UNTOUCHED

        # The redelivery, with the database back, settles.
        monkeypatch.setattr(payments, "settle_charge", real)
        with TestClient(create_app()) as c:
            assert c.post(URL, content=raw, headers=sign(raw)).status_code == 200
        assert state(ref)["status"] == "success"
