"""Who starts a checkout.

The same shape as the SMS port (ADR 0003): one small interface, so the code that
decides *what* to charge never knows *who* takes the money. Paystack is the real
adapter; the fake lets every test and demo run without an account or a network.

**This is only the front door.** Starting a checkout asks the provider for an
address to send the customer to. It says nothing about whether money moved —
that is decided by the signed webhook, never by anything the browser or this
call reports. An adapter therefore has exactly one job and one way to fail
loudly: it must either return an address we can send someone to, or raise.

**Failures are sorted, as with SMS.** A timeout or a 5xx is *transient*: try
again shortly. A 4xx (a bad key, an amount Paystack refuses) is *permanent*:
retrying does not help and someone should look. The caller marks the payment
failed either way — the customer never received an address, so nothing they do
can complete it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from urllib.parse import quote, urlsplit

import httpx
import structlog

from kafriada.contexts.payments.rules import ChargeEvent, MalformedEvent, parse_charge_event
from kafriada.settings import PaymentProviderKind, Settings, get_settings

log = structlog.get_logger(__name__)


class ProviderError(Exception):
    """A checkout could not be started. ``transient`` says whether to try again."""

    def __init__(self, message: str, *, transient: bool) -> None:
        super().__init__(message)
        self.message = message
        self.transient = transient


class NotConfigured(ProviderError):
    """No provider is configured. Payments are simply not available yet."""

    def __init__(self) -> None:
        super().__init__("no payment provider is configured", transient=True)


@dataclass(frozen=True, slots=True)
class Initialised:
    authorization_url: str
    # Provider's handle for the checkout. Kept out of logs and responses.
    access_code: str | None = None


class PaymentProvider(Protocol):
    name: str

    def initialise(
        self, *, reference: str, amount_kobo: int, email: str, callback_url: str
    ) -> Initialised: ...

    def verify(self, reference: str) -> ChargeEvent | None:
        """What the provider itself says happened to one reference (reconciliation).

        ``None`` means the provider has never heard of it. The returned event carries
        the provider's own status — ``success``, ``abandoned``, ``failed`` — and it is
        the caller's job to act only on ``success``: reconciliation may *confirm* a
        credit, and must never reverse, refund or cancel anything.
        """
        ...


class NoProvider:
    name = "none"

    def initialise(
        self, *, reference: str, amount_kobo: int, email: str, callback_url: str
    ) -> Initialised:
        raise NotConfigured()

    def verify(self, reference: str) -> ChargeEvent | None:
        raise NotConfigured()


class FakeProvider:
    """Sends the customer straight back to the callback. Local development and tests.

    It reports nothing about payment, because no provider ever does: the caller
    still waits for a webhook, and tests deliver one by hand.
    """

    name = "fake"

    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []
        # What verify() answers, per reference. Anything not listed is "never heard of it".
        self.results: dict[str, ChargeEvent | None] = {}
        self.verified: list[str] = []

    def initialise(
        self, *, reference: str, amount_kobo: int, email: str, callback_url: str
    ) -> Initialised:
        self.calls.append(
            {"reference": reference, "amount_kobo": amount_kobo, "email": email}
        )
        return Initialised(
            authorization_url=f"{callback_url}?reference={reference}", access_code="fake"
        )


    def verify(self, reference: str) -> ChargeEvent | None:
        self.verified.append(reference)
        return self.results.get(reference)


class PaystackProvider:
    """Paystack's Initialize Transaction endpoint.

    The secret key comes from the environment and never from an argument. The
    amount is sent in kobo, the currency is pinned to NGN, and the reference is
    ours — Paystack echoes it back on the webhook, which is how a payment finds
    its row.
    """

    name = "paystack"

    def __init__(self, settings: Settings | None = None) -> None:
        cfg = settings or get_settings()
        if cfg.paystack_secret_key is None:
            raise NotConfigured()
        self._key = cfg.paystack_secret_key.get_secret_value()
        self._url = f"{cfg.paystack_base_url.rstrip('/')}/transaction/initialize"
        self._verify_url = f"{cfg.paystack_base_url.rstrip('/')}/transaction/verify"
        self._timeout = cfg.paystack_timeout_seconds

    def initialise(
        self, *, reference: str, amount_kobo: int, email: str, callback_url: str
    ) -> Initialised:
        try:
            response = httpx.post(
                self._url,
                json={
                    "email": email,
                    "amount": amount_kobo,
                    "currency": "NGN",
                    "reference": reference,
                    "callback_url": callback_url,
                },
                headers={"authorization": f"Bearer {self._key}"},
                # A hard deadline: a hung Paystack must not hold a worker thread.
                timeout=self._timeout,
            )
        except httpx.HTTPError as exc:
            raise ProviderError(
                f"paystack unreachable: {type(exc).__name__}", transient=True
            ) from exc

        body = _json_or_empty(response)
        if not response.is_success:
            # 429 is "slow down", 5xx is "not now"; the rest will never work.
            transient = response.status_code == 429 or response.status_code >= 500
            raise ProviderError(
                f"paystack {response.status_code}: {body.get('message') or response.reason_phrase}",
                transient=transient,
            )

        data = body.get("data")
        url = data.get("authorization_url") if isinstance(data, dict) else None
        if body.get("status") is not True or not isinstance(url, str) or not _is_https(url):
            # A 200 that does not carry an address we can send someone to is not
            # a success. Never redirect a customer to whatever a response says.
            raise ProviderError("paystack answered without a usable address", transient=False)
        code = data.get("access_code") if isinstance(data, dict) else None
        return Initialised(authorization_url=url, access_code=code if isinstance(code, str) else None)


    def verify(self, reference: str) -> ChargeEvent | None:
        try:
            response = httpx.get(
                f"{self._verify_url}/{quote(reference, safe='')}",
                headers={"authorization": f"Bearer {self._key}"},
                timeout=self._timeout,
            )
        except httpx.HTTPError as exc:
            raise ProviderError(
                f"paystack unreachable: {type(exc).__name__}", transient=True
            ) from exc

        if response.status_code == 404:
            return None
        body = _json_or_empty(response)
        if not response.is_success:
            transient = response.status_code == 429 or response.status_code >= 500
            raise ProviderError(
                f"paystack {response.status_code}: {body.get('message') or response.reason_phrase}",
                transient=transient,
            )
        data = body.get("data")
        if body.get("status") is not True or not isinstance(data, dict):
            raise ProviderError("paystack answered a verify without a transaction", transient=False)
        try:
            # The same strict reader the webhook uses, so both paths agree on what
            # a well-formed transaction is.
            return parse_charge_event({"event": "charge.success", "data": data})
        except MalformedEvent as exc:
            raise ProviderError(f"paystack verify was not readable: {exc}", transient=False) from exc


def _is_https(url: str) -> bool:
    parts = urlsplit(url)
    return parts.scheme == "https" and bool(parts.netloc)


def _json_or_empty(response: httpx.Response) -> dict[str, object]:
    try:
        payload = response.json()
    except ValueError:
        return {}
    return payload if isinstance(payload, dict) else {}


def build_provider(settings: Settings | None = None) -> PaymentProvider:
    cfg = settings or get_settings()
    match cfg.payment_provider:
        case PaymentProviderKind.PAYSTACK:
            return PaystackProvider(cfg)
        case PaymentProviderKind.FAKE:
            log.warning("payment_fake_provider", note="no money moves")
            return FakeProvider()
        case _:
            return NoProvider()
