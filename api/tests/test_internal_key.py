"""Only the web tier may use the API.

With INTERNAL_API_KEY set, a request without the right x-kafriada-internal header is
refused before any route runs, so someone who finds the API's address can neither use
it nor forge the visitor-address header the rate limits trust. The platform's probes
and the Paystack webhook (which proves itself with its own signature) stay open.
Production refusing to start without a key is in test_settings_refuses_insecure_config.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr, ValidationError

from kafriada.main import create_app
from kafriada.settings import Settings, get_settings

KEY = "k" * 40


@pytest.fixture(scope="module")
def client() -> TestClient:
    cfg = get_settings().model_copy(update={"internal_api_key": SecretStr(KEY)})
    return TestClient(create_app(cfg))


def test_a_request_without_the_key_is_refused_as_if_nothing_were_there(client: TestClient) -> None:
    for headers in ({}, {"x-kafriada-internal": "wrong"}, {"x-kafriada-internal": KEY[:-1]}):
        got = client.get("/v1/public/lgas", headers=headers)
        assert got.status_code == 404, headers
        assert got.json() == {"error": {"message": "Not found."}}


def test_the_web_tier_with_the_key_gets_through(client: TestClient) -> None:
    got = client.get("/v1/me", headers={"x-kafriada-internal": KEY})
    assert got.status_code == 401, "past the key check, the route's own sign-in check answers"


def test_the_probes_and_the_paystack_webhook_stay_open(client: TestClient) -> None:
    assert client.get("/healthz").status_code == 200
    # The webhook answers for itself: an unsigned delivery is refused by its own check.
    assert client.post("/v1/payments/webhook/paystack", content=b"{}").status_code == 400


def test_without_a_key_nothing_is_checked() -> None:
    cfg = get_settings().model_copy(update={"internal_api_key": None})
    assert TestClient(create_app(cfg)).get("/v1/me").status_code == 401


def test_a_short_key_is_refused() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, secret_key="s" * 40, qr_secret="q" * 40, internal_api_key="short",
                 database_url_app="postgresql+psycopg://a:b@h/d", database_url_money="postgresql+psycopg://c:d@h/d")
