"""The Paystack adapter and the settings that choose it. No database, no network.

What is proved here:
  - the request carries our reference, whole kobo, NGN and the key — and the
    response is trusted only when it holds an https address to send someone to
  - a slow or broken Paystack is a *transient* failure, a refusal is *permanent*,
    and neither ever yields an address
  - the choice of provider fails loudly when misconfigured: paystack without a key,
    the fake anywhere but local, anything but paystack in production
"""

from __future__ import annotations

import httpx
import pytest
from pydantic import ValidationError

from kafriada.contexts.payments import provider as provider_mod
from kafriada.contexts.payments.provider import (
    FakeProvider,
    NoProvider,
    NotConfigured,
    PaystackProvider,
    ProviderError,
    build_provider,
)
from kafriada.settings import Environment
from tests.test_settings_refuses_insecure_config import build, production

REF = "KAF-6f1c1f8e-2b7a-4e0b-9d47-0a4c1a1b2c3d"
KEY = "sk_test_" + "a" * 30
CALL = {"reference": REF, "amount_kobo": 250_000, "email": "a@b.test", "callback_url": "https://x.test/pay"}


def settings(**over: object):  # type: ignore[no-untyped-def]
    return build(paystack_secret_key=KEY, payment_provider="paystack", **over)


def respond(monkeypatch: pytest.MonkeyPatch, response: httpx.Response | Exception) -> list[dict]:  # type: ignore[type-arg]
    sent: list[dict] = []  # type: ignore[type-arg]

    def post(url: str, **kwargs: object) -> httpx.Response:
        sent.append({"url": url, **kwargs})
        if isinstance(response, Exception):
            raise response
        return response

    monkeypatch.setattr(provider_mod.httpx, "post", post)
    return sent


def ok(url: object = "https://checkout.paystack.com/abc") -> httpx.Response:
    return httpx.Response(200, json={"status": True, "data": {"authorization_url": url, "access_code": "abc"}})


class TestPaystackAdapter:
    def test_it_sends_our_reference_whole_kobo_naira_currency_and_the_key(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        sent = respond(monkeypatch, ok())
        result = PaystackProvider(settings()).initialise(**CALL)

        assert result.authorization_url == "https://checkout.paystack.com/abc"
        (call,) = sent
        assert call["url"] == "https://api.paystack.co/transaction/initialize"
        assert call["json"] == {
            "email": "a@b.test", "amount": 250_000, "currency": "NGN",
            "reference": REF, "callback_url": "https://x.test/pay",
        }
        assert call["headers"] == {"authorization": f"Bearer {KEY}"}
        assert call["timeout"] == 8.0  # a hard deadline, always

    @pytest.mark.parametrize(
        "failure",
        [httpx.ConnectTimeout("slow"), httpx.ConnectError("down")],
    )
    def test_an_unreachable_paystack_is_transient(
        self, monkeypatch: pytest.MonkeyPatch, failure: Exception
    ) -> None:
        respond(monkeypatch, failure)
        with pytest.raises(ProviderError) as caught:
            PaystackProvider(settings()).initialise(**CALL)
        assert caught.value.transient is True

    @pytest.mark.parametrize(("status", "transient"), [(500, True), (503, True), (429, True), (400, False), (401, False)])
    def test_refusals_are_sorted_by_whether_trying_again_can_help(
        self, monkeypatch: pytest.MonkeyPatch, status: int, transient: bool
    ) -> None:
        respond(monkeypatch, httpx.Response(status, json={"status": False, "message": "no"}))
        with pytest.raises(ProviderError) as caught:
            PaystackProvider(settings()).initialise(**CALL)
        assert caught.value.transient is transient
        assert KEY not in str(caught.value)

    @pytest.mark.parametrize(
        "response",
        [
            httpx.Response(200, json={"status": False, "data": {}}),
            httpx.Response(200, json={"status": True, "data": {}}),
            httpx.Response(200, json={"status": True, "data": {"authorization_url": "http://plain.test/x"}}),
            httpx.Response(200, json={"status": True, "data": {"authorization_url": "javascript:alert(1)"}}),
            httpx.Response(200, json={"status": True, "data": {"authorization_url": 5}}),
            httpx.Response(200, text="<html>not json</html>"),
        ],
    )
    def test_a_success_without_a_usable_address_is_not_a_success(
        self, monkeypatch: pytest.MonkeyPatch, response: httpx.Response
    ) -> None:
        respond(monkeypatch, response)
        with pytest.raises(ProviderError) as caught:
            PaystackProvider(settings()).initialise(**CALL)
        assert caught.value.transient is False

    def test_without_a_key_there_is_no_adapter(self) -> None:
        with pytest.raises(NotConfigured):
            PaystackProvider(build())


class TestChoosingAProvider:
    def test_none_is_the_default_and_takes_no_money(self) -> None:
        chosen = build_provider(build())
        assert isinstance(chosen, NoProvider)
        with pytest.raises(NotConfigured):
            chosen.initialise(**CALL)

    def test_the_fake_sends_the_customer_back_and_records_the_call(self) -> None:
        chosen = build_provider(build(payment_provider="fake"))
        assert isinstance(chosen, FakeProvider)
        assert chosen.initialise(**CALL).authorization_url == f"https://x.test/pay?reference={REF}"

    def test_paystack_is_chosen_by_configuration(self) -> None:
        assert isinstance(build_provider(settings()), PaystackProvider)

    def test_paystack_without_its_key_will_not_start(self) -> None:
        with pytest.raises(ValidationError, match="paystack_secret_key is required"):
            build(payment_provider="paystack")

    def test_the_fake_is_refused_outside_local_development(self) -> None:
        with pytest.raises(ValidationError, match="local development only"):
            build(payment_provider="fake", environment=Environment.STAGING)

    @pytest.mark.parametrize("kind", ["none", "fake"])
    def test_production_will_not_start_on_a_provider_that_takes_no_money(self, kind: str) -> None:
        with pytest.raises(ValidationError, match="payment_provider"):
            production(payment_provider=kind)

    def test_production_with_paystack_starts(self) -> None:
        assert production().payment_provider.value == "paystack"
