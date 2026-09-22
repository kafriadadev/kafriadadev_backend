"""Who actually sends an email. The email twin of ``providers.py`` (SMS).

Same shape, same reasoning: the outbox decides *what* to send and *when*;
this file is the only place that knows *who* sends it. Today that is Resend.

**Transient vs permanent, same as SMS.** A network blip, a 429 or a 5xx is
tried again. A rejected address or a bad request is not — no amount of
retrying fixes a malformed email, so it fails once and stays failed.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import httpx
import structlog

from kafriada.settings import EmailProvider, Settings, get_settings

log = structlog.get_logger(__name__)


class EmailError(Exception):
    """A send failed. ``transient`` decides whether it will be tried again."""

    def __init__(self, message: str, *, transient: bool) -> None:
        super().__init__(message)
        self.message = message
        self.transient = transient


class NotConfigured(EmailError):
    """No provider is configured. Messages wait rather than fail."""

    def __init__(self) -> None:
        super().__init__("no email provider is configured", transient=True)


@dataclass(frozen=True, slots=True)
class Sent:
    provider: str
    provider_message_id: str | None


class Sender(Protocol):
    name: str

    def send(self, *, to: str, subject: str, body: str, html: str | None = None) -> Sent: ...


class NoSender:
    """The default. Keeps messages queued until a provider is configured."""

    name = "none"

    def send(self, *, to: str, subject: str, body: str, html: str | None = None) -> Sent:
        raise NotConfigured()


class ConsoleSender:
    """Prints the message instead of sending it. Local development only.

    Refused outside local by the settings validator, same as the SMS console
    sender — a body meant for one athlete does not belong in a shared log.
    """

    name = "console"

    def send(self, *, to: str, subject: str, body: str, html: str | None = None) -> Sent:
        print(f"\n  -- email to {to} --\n  subject: {subject}\n\n  {body}\n")  # noqa: T201
        return Sent(provider=self.name, provider_message_id=None)


class ResendSender:
    """Resend's Emails API (https://resend.com/docs/api-reference/emails/send-email)."""

    name = "resend"

    def __init__(self, settings: Settings | None = None) -> None:
        cfg = settings or get_settings()
        if cfg.resend_api_key is None:
            raise NotConfigured()
        self._key = cfg.resend_api_key.get_secret_value()
        self._from = cfg.email_from
        self._url = f"{cfg.resend_base_url.rstrip('/')}/emails"
        self._timeout = cfg.email_timeout_seconds

    def send(self, *, to: str, subject: str, body: str, html: str | None = None) -> Sent:
        payload: dict[str, object] = {
            "from": self._from, "to": [to], "subject": subject, "text": body,
        }
        if html is not None:
            payload["html"] = html
        try:
            response = httpx.post(
                self._url,
                json=payload,
                headers={"authorization": f"Bearer {self._key}"},
                timeout=self._timeout,
            )
        except httpx.HTTPError as exc:
            # Unreachable or too slow: the message is still good, the moment is not.
            raise EmailError(f"resend unreachable: {type(exc).__name__}", transient=True) from exc

        if response.is_success:
            message_id = _json_or_empty(response).get("id")
            return Sent(
                provider=self.name,
                provider_message_id=str(message_id) if isinstance(message_id, str) else None,
            )

        detail = _json_or_empty(response)
        message = str(detail.get("message") or response.reason_phrase)
        # 429 is "slow down", 5xx is "not now". Everything else in the 4xx range
        # says this particular message will never be accepted.
        transient = response.status_code == 429 or response.status_code >= 500
        raise EmailError(f"resend {response.status_code}: {message}", transient=transient)


def _json_or_empty(response: httpx.Response) -> dict[str, object]:
    try:
        payload = response.json()
    except ValueError:
        return {}
    return payload if isinstance(payload, dict) else {}


def build_sender(settings: Settings | None = None) -> Sender:
    cfg = settings or get_settings()
    match cfg.email_provider:
        case EmailProvider.RESEND:
            return ResendSender(cfg)
        case EmailProvider.CONSOLE:
            log.warning("email_console_sender", note="message bodies are printed, not sent")
            return ConsoleSender()
        case _:
            return NoSender()
