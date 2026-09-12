"""Who actually sends an SMS.

One small interface, so the thing that decides *what* to send never knows *who*
sends it. Today that is Twilio; Termii was the original choice and would be
another class in this file, not a change anywhere else.

**Failures come in two kinds and they are not the same.** A network blip, a
429 or a 5xx is *transient*: the message stays queued and is tried again. A
malformed number or a rejected account is *permanent*: retrying it a hundred
times only fills the log, so it fails once and stays failed for a human to look
at. Getting this distinction wrong is how an outbox turns into an outage.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import httpx
import structlog

from kafriada.settings import Settings, SmsProvider, get_settings

log = structlog.get_logger(__name__)


class SmsError(Exception):
    """A send failed. ``transient`` decides whether it will be tried again."""

    def __init__(self, message: str, *, transient: bool) -> None:
        super().__init__(message)
        self.message = message
        self.transient = transient


class NotConfigured(SmsError):
    """No provider is configured. Messages wait rather than fail."""

    def __init__(self) -> None:
        super().__init__("no SMS provider is configured", transient=True)


@dataclass(frozen=True, slots=True)
class Sent:
    provider: str
    provider_message_id: str | None


class Sender(Protocol):
    name: str

    def send(self, *, to: str, body: str) -> Sent: ...


class NoSender:
    """The default. Keeps messages queued until a provider is configured."""

    name = "none"

    def send(self, *, to: str, body: str) -> Sent:
        raise NotConfigured()


class ConsoleSender:
    """Prints the message instead of sending it. Local development only.

    The settings refuse this outside local development, because what it prints
    is a working one-time code and logs are read by more people than a phone is.
    """

    name = "console"

    def send(self, *, to: str, body: str) -> Sent:
        print(f"\n  -- SMS to {to} --\n  {body}\n")  # noqa: T201 — the print IS this sender
        return Sent(provider=self.name, provider_message_id=None)


class TwilioSender:
    """Twilio's Messages API.

    Credentials come from the environment and never from an argument. A
    Messaging Service is preferred over a bare number: it is what holds the
    sender id registration a Nigerian route needs.
    """

    name = "twilio"

    def __init__(self, settings: Settings | None = None) -> None:
        cfg = settings or get_settings()
        if not cfg.twilio_account_sid or cfg.twilio_auth_token is None:
            raise NotConfigured()
        self._sid = cfg.twilio_account_sid
        self._auth = (self._sid, cfg.twilio_auth_token.get_secret_value())
        self._messaging_service = cfg.twilio_messaging_service_sid
        self._from = cfg.twilio_from_number
        if not (self._messaging_service or self._from):
            raise NotConfigured()
        self._url = (
            f"{cfg.twilio_base_url.rstrip('/')}/2010-04-01/Accounts/{self._sid}/Messages.json"
        )
        self._timeout = cfg.sms_timeout_seconds

    def send(self, *, to: str, body: str) -> Sent:
        form = {"To": to, "Body": body}
        if self._messaging_service:
            form["MessagingServiceSid"] = self._messaging_service
        else:
            form["From"] = str(self._from)

        try:
            response = httpx.post(
                self._url, data=form, auth=self._auth, timeout=self._timeout
            )
        except httpx.HTTPError as exc:
            # Unreachable or too slow: the message is still good, the moment is not.
            raise SmsError(f"twilio unreachable: {type(exc).__name__}", transient=True) from exc

        if response.is_success:
            sid = _json_or_empty(response).get("sid")
            return Sent(
                provider=self.name,
                provider_message_id=str(sid) if isinstance(sid, str) else None,
            )

        detail = _json_or_empty(response)
        message = str(detail.get("message") or response.reason_phrase)
        code = detail.get("code")
        # 429 is "slow down", 5xx is "not now". Everything else in the 4xx range
        # says this particular message will never be accepted.
        transient = response.status_code == 429 or response.status_code >= 500
        raise SmsError(f"twilio {response.status_code} ({code}): {message}", transient=transient)


def _json_or_empty(response: httpx.Response) -> dict[str, object]:
    try:
        payload = response.json()
    except ValueError:
        return {}
    return payload if isinstance(payload, dict) else {}


def build_sender(settings: Settings | None = None) -> Sender:
    cfg = settings or get_settings()
    match cfg.sms_provider:
        case SmsProvider.TWILIO:
            return TwilioSender(cfg)
        case SmsProvider.CONSOLE:
            log.warning("sms_console_sender", note="codes are printed, not sent")
            return ConsoleSender()
        case _:
            return NoSender()
