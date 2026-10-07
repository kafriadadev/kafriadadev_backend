"""Mail to a reserved test domain never reaches the provider.

The test suite and the end-to-end scripts register people at example.com and
*.test addresses. On 2026-10-07 a dispatcher run against the dev database sent
107 of them through Resend and used up the account's daily quota. Nothing at
those domains can receive mail, so the Resend sender now refuses to try.
"""

from __future__ import annotations

import pytest
from pydantic import SecretStr

from kafriada.outbox import email_providers
from kafriada.settings import get_settings


@pytest.mark.parametrize(
    "address",
    ["t2348031234567@example.test", "e2e.1@example.com", "a@mail.example.org",
     "x@payments.kafriada.invalid", "dev@localhost", "Someone@EXAMPLE.NET"],
)
def test_reserved_addresses_are_recognised(address: str) -> None:
    assert email_providers.reserved(address)


@pytest.mark.parametrize("address", ["someone@gmail.com", "coach@kafriada.ng", "x@examples.com", "y@test.ng"])
def test_real_addresses_are_not(address: str) -> None:
    assert not email_providers.reserved(address)


def test_resend_is_never_called_for_a_reserved_address(monkeypatch: pytest.MonkeyPatch) -> None:
    def no_network(*_a: object, **_k: object) -> None:
        raise AssertionError("Resend was called for a reserved address")

    monkeypatch.setattr(email_providers.httpx, "post", no_network)
    settings = get_settings().model_copy(update={"resend_api_key": SecretStr("re_test")})
    sent = email_providers.ResendSender(settings).send(to="t1@example.test", subject="Code", body="123456")
    assert sent.provider == "suppressed" and sent.provider_message_id is None
