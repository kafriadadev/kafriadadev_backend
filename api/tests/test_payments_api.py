"""Starting a payment and reading it back (VER-03), through the real routes.

What is proved here:
  - the price comes from us: whatever amount a caller sends is ignored, and the
    row records our figure
  - starting a checkout writes a pending row *before* the provider is called,
    and hands back only the provider's address
  - a payment can only be read by the person who made it; anyone else's, and one
    that does not exist, look the same
  - a paid or frozen athlete cannot start another
  - a provider that fails leaves the payment failed, the customer with a calm
    message, and no address; an unconfigured environment writes nothing at all
  - only someone holding the payment permission gets in
  - the browser can never make a payment succeed: nothing in these routes does
"""

from __future__ import annotations

import os
import re
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from kafriada.contexts.payments import service
from kafriada.contexts.payments.provider import FakeProvider, NoProvider, ProviderError
from kafriada.main import create_app
from tests._access_helpers import bearer, make_user, sql
from tests._media_helpers import athlete_with_files, use_local_store
from tests._payment_helpers import (
    PRICE,
    charge_success,
    new_athlete,
    pending_payment,
    reference_of,
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

BODY = {"purpose": "stage2_athlete"}


@pytest.fixture(scope="module")
def client() -> Iterator[TestClient]:
    with TestClient(create_app()) as c:
        yield c


@pytest.fixture(autouse=True)
def _store(monkeypatch: pytest.MonkeyPatch, tmp_path):  # type: ignore[no-untyped-def]
    """Paying needs a photo and a document first, so every test has somewhere to put them."""
    return use_local_store(monkeypatch, tmp_path)


@pytest.fixture
def fake(monkeypatch: pytest.MonkeyPatch) -> FakeProvider:
    provider = FakeProvider()
    monkeypatch.setattr(service, "build_provider", lambda _settings=None: provider)
    return provider


class TestQuote:
    def test_it_names_the_record_and_our_price(self, client: TestClient) -> None:
        athlete = athlete_with_files(client)
        body = client.get("/v1/payments/quote", headers=athlete.headers).json()
        assert body == {
            "kuid": athlete.kuid,
            "purpose": "stage2_athlete",
            "amount_kobo": PRICE,
            "already_paid": False,
        }

    def test_someone_with_no_athlete_record_is_told_so(self, client: TestClient) -> None:
        user_id, _ = make_user("Coordinator only", grants=[("athlete", "global", None)])
        from kafriada.contexts.access import service as access

        token = access.issue_session(user_id, method="test").token
        assert client.get("/v1/payments/quote", headers=bearer(token)).status_code == 404


class TestStarting:
    def test_it_records_our_price_first_and_returns_only_the_providers_address(
        self, client: TestClient, fake: FakeProvider
    ) -> None:
        athlete = athlete_with_files(client)
        response = client.post("/v1/payments", json=BODY, headers=athlete.headers)

        assert response.status_code == 201, response.text
        started = response.json()
        ref = started["reference"]
        assert started["amount_kobo"] == PRICE
        assert ref in started["authorization_url"]
        assert set(started) == {"reference", "authorization_url", "amount_kobo"}

        assert state(ref) == {"status": "pending", "ledger": [], "seen": 0, "audit": ["payment.started"]}
        (row,) = sql(
            "SELECT expected_kobo, purpose, paid_by, on_behalf_of FROM money.payments "
            "WHERE reference = :r",
            r=ref,
        )
        assert row["expected_kobo"] == PRICE
        assert row["purpose"] == "stage2_athlete"
        assert row["paid_by"] == athlete.user_id
        assert row["on_behalf_of"] is None

    def test_the_amount_a_caller_sends_is_ignored(
        self, client: TestClient, fake: FakeProvider
    ) -> None:
        athlete = athlete_with_files(client)
        response = client.post(
            "/v1/payments", json={**BODY, "amount_kobo": 1_000, "amount": 10}, headers=athlete.headers
        )
        assert response.status_code == 201
        assert fake.calls[-1]["amount_kobo"] == PRICE
        assert response.json()["amount_kobo"] == PRICE
        (row,) = sql("SELECT expected_kobo FROM money.payments WHERE reference = :r",
                     r=response.json()["reference"])
        assert row["expected_kobo"] == PRICE

    def test_an_athlete_without_an_email_gets_a_placeholder_paystack_will_accept(
        self, client: TestClient, fake: FakeProvider
    ) -> None:
        """The placeholder must be an address Paystack does not refuse.

        This test used to assert the opposite — that the placeholder ended in
        ``.invalid``. RFC 2606 reserves that for exactly this purpose, so it
        read as obviously right, and the fake provider accepted it happily.
        Against the real sandbox Paystack answers
        ``400 "email" must be a valid email`` and refuses the whole checkout,
        which would have left every athlete without an email unable to pay.
        Verified 2026-09-23; see settings.payment_placeholder_email_domain.
        """
        athlete = athlete_with_files(client)
        client.post("/v1/payments", json=BODY, headers=athlete.headers)
        email = str(fake.calls[-1]["email"])

        assert athlete.user_id.hex in email, "the address must identify the athlete"
        assert re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email), email
        # Reserved TLDs read as the careful choice and are the one thing a
        # payment provider will not take.
        assert not email.endswith((".invalid", ".test", ".example", ".localhost")), email

    def test_only_the_athletes_own_price_can_be_started_here(
        self, client: TestClient, fake: FakeProvider
    ) -> None:
        athlete = athlete_with_files(client)
        assert client.post("/v1/payments", json={"purpose": "stage2_org"}, headers=athlete.headers).status_code == 422
        assert client.post("/v1/payments", json={}, headers=athlete.headers).status_code == 422
        assert fake.calls == []

    def test_it_needs_a_session_and_the_permission(self, client: TestClient, fake: FakeProvider) -> None:
        assert client.post("/v1/payments", json=BODY).status_code == 401
        user_id, _ = make_user("No role at all")
        from kafriada.contexts.access import service as access

        token = access.issue_session(user_id, method="test").token
        assert client.post("/v1/payments", json=BODY, headers=bearer(token)).status_code == 403
        assert fake.calls == []


class TestReadingBack:
    def test_the_caller_sees_checking_and_then_confirmed_when_the_webhook_says_so(
        self, client: TestClient, fake: FakeProvider, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        athlete = athlete_with_files(client)
        ref = client.post("/v1/payments", json=BODY, headers=athlete.headers).json()["reference"]

        first = client.get(f"/v1/payments/{ref}", headers=athlete.headers).json()
        assert first["state"] == "checking"
        assert first["amount_kobo"] == PRICE

        # Coming back from Paystack proves nothing; only the signed delivery moves it.
        use_webhook_key(monkeypatch)
        raw = charge_success(ref)
        assert client.post("/v1/payments/webhook/paystack", content=raw, headers=sign(raw)).status_code == 200
        assert client.get(f"/v1/payments/{ref}", headers=athlete.headers).json()["state"] == "confirmed"

    def test_a_frozen_payment_reads_as_under_review_not_as_frozen(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        athlete = athlete_with_files(client)
        ref = pending_payment(athlete)
        use_webhook_key(monkeypatch)
        raw = charge_success(ref, amount=1_000, fees=15)
        client.post("/v1/payments/webhook/paystack", content=raw, headers=sign(raw))
        body = client.get(f"/v1/payments/{ref}", headers=athlete.headers).json()
        assert body["state"] == "review"
        assert "frozen" not in str(body)

    def test_someone_elses_payment_and_a_missing_one_look_the_same(
        self, client: TestClient
    ) -> None:
        owner, stranger = new_athlete("Owner"), new_athlete("Stranger")
        ref = pending_payment(owner)
        theirs = client.get(f"/v1/payments/{ref}", headers=stranger.headers)
        missing = client.get("/v1/payments/KAF-00000000-0000-4000-8000-000000000000", headers=stranger.headers)
        garbage = client.get("/v1/payments/not-a-reference", headers=stranger.headers)
        assert (theirs.status_code, missing.status_code, garbage.status_code) == (404, 404, 404)
        assert theirs.json()["error"]["message"] == missing.json()["error"]["message"]

    @pytest.mark.parametrize(
        ("db_status", "shown"), [("failed", "failed"), ("abandoned", "failed")]
    )
    def test_a_payment_that_was_given_up_on_reads_as_failed(
        self, client: TestClient, db_status: str, shown: str
    ) -> None:
        athlete = athlete_with_files(client)
        ref = pending_payment(athlete, status=db_status)
        assert client.get(f"/v1/payments/{ref}", headers=athlete.headers).json()["state"] == shown


class TestOnceIsEnough:
    def test_a_paid_athlete_cannot_start_another(
        self, client: TestClient, fake: FakeProvider, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        athlete = athlete_with_files(client)
        ref = client.post("/v1/payments", json=BODY, headers=athlete.headers).json()["reference"]
        use_webhook_key(monkeypatch)
        raw = charge_success(ref)
        client.post("/v1/payments/webhook/paystack", content=raw, headers=sign(raw))
        calls = len(fake.calls)

        again = client.post("/v1/payments", json=BODY, headers=athlete.headers)
        assert again.status_code == 409
        assert "already paid" in again.text
        assert len(fake.calls) == calls
        assert client.get("/v1/payments/quote", headers=athlete.headers).json()["already_paid"] is True

    def test_an_athlete_whose_payment_is_frozen_waits_for_a_person(
        self, client: TestClient, fake: FakeProvider, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        athlete = athlete_with_files(client)
        ref = pending_payment(athlete)
        use_webhook_key(monkeypatch)
        raw = charge_success(ref, amount=1_000, fees=15)
        client.post("/v1/payments/webhook/paystack", content=raw, headers=sign(raw))

        again = client.post("/v1/payments", json=BODY, headers=athlete.headers)
        assert again.status_code == 409
        assert "checked by our team" in again.text
        assert fake.calls == []


class TestWhenTheProviderIsNotThere:
    def test_a_failing_provider_marks_the_payment_failed_and_gives_no_address(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        class Broken:
            name = "broken"

            def initialise(self, **_: object) -> None:
                raise ProviderError("paystack unreachable: ConnectTimeout", transient=True)

        monkeypatch.setattr(service, "build_provider", lambda _s=None: Broken())
        athlete = athlete_with_files(client)
        response = client.post("/v1/payments", json=BODY, headers=athlete.headers)

        assert response.status_code == 503
        assert "authorization_url" not in response.text
        assert "Nothing has been charged" in response.text
        assert "ConnectTimeout" not in response.text  # our diagnosis stays in the log
        ref = reference_of(athlete)
        assert state(ref)["status"] == "failed"
        assert state(ref)["audit"] == ["payment.started", "payment.failed"]

        # And the person can simply try again once it is back.
        monkeypatch.setattr(service, "build_provider", lambda _s=None: FakeProvider())
        assert client.post("/v1/payments", json=BODY, headers=athlete.headers).status_code == 201

    def test_an_unconfigured_environment_writes_nothing(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(service, "build_provider", lambda _s=None: NoProvider())
        athlete = athlete_with_files(client)
        assert client.post("/v1/payments", json=BODY, headers=athlete.headers).status_code == 503
        assert sql("SELECT 1 FROM money.payments WHERE paid_by = :u", u=athlete.user_id) == []
