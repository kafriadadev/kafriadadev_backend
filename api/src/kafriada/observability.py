"""Error reporting and tracing.

Wired now, before there is anything to trace, because the alternative is wiring
it during the first incident.

**Inert without a DSN.** No DSN means no initialisation at all: development and
CI carry the dependency and nothing else.

**Nothing identifying leaves this process.** Sentry is a third party, and this
system holds phone numbers — the one field the privacy notice promises is never
public. So:

  - ``send_default_pii`` is off, and request bodies are never captured. A
    registration body holds a name, a phone number and a password.
  - every string in every event is run through :func:`scrub`, which removes
    phone numbers, bearer tokens and database URLs wherever they appear —
    including inside an exception message, which is where they turn up in
    practice. ``psycopg`` puts the connection string in some errors.
  - keys whose names suggest a secret are replaced wholesale, the same rule the
    log processor and the audit log already apply.

What is deliberately *not* scrubbed is the KUID. It is public, it is printed on
a card, and it is the one identifier that makes an error report actionable.
"""

from __future__ import annotations

import re
from typing import Any

import sentry_sdk
import structlog
from sentry_sdk.types import Event, Hint

from kafriada.settings import Settings

log = structlog.get_logger(__name__)

REDACTED = "[redacted]"

# Nigerian numbers, stored and typed. Separators are tolerated because a number
# reaches a log line the way somebody typed it — "0803 000 0000" — not only in
# the normalised form the database holds.
_SEP = r"[\s\-.]?"
_PHONE_E164 = re.compile(r"\+234" + _SEP + r"(?:\d" + _SEP + r"){7,12}")
_PHONE_LOCAL = re.compile(r"0[789]\d" + _SEP + r"(?:\d" + _SEP + r"){7}\d")
# postgresql+psycopg://user:password@host/db
_DB_URL = re.compile(r"(postgresql(?:\+\w+)?://)[^:/\s]+:[^@\s]+@")
_BEARER = re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._\-]{8,}")
# A session token or a signed QR value on its own in a message.
_LONG_TOKEN = re.compile(r"\b[A-Za-z0-9_\-]{40,}\b")

_SECRET_KEYS = (
    "password", "token", "secret", "otp", "code", "pin", "authorization",
    "cookie", "session", "api_key", "dsn", "card", "cvv", "phone",
)

MAX_DEPTH = 12


def scrub_text(value: str) -> str:
    value = _DB_URL.sub(r"\1" + REDACTED + "@", value)
    value = _BEARER.sub(r"\1" + REDACTED, value)
    value = _PHONE_E164.sub("[phone]", value)
    value = _PHONE_LOCAL.sub("[phone]", value)
    return _LONG_TOKEN.sub(REDACTED, value)


def scrub(value: Any, *, depth: int = 0) -> Any:
    """Recursively redact an event. Structure is kept; sensitive values are not."""
    if depth > MAX_DEPTH:
        return REDACTED
    if isinstance(value, str):
        return scrub_text(value)
    if isinstance(value, dict):
        cleaned: dict[Any, Any] = {}
        for key, inner in value.items():
            if isinstance(key, str) and any(word in key.lower() for word in _SECRET_KEYS):
                cleaned[key] = REDACTED
            else:
                cleaned[key] = scrub(inner, depth=depth + 1)
        return cleaned
    if isinstance(value, list):
        return [scrub(item, depth=depth + 1) for item in value]
    if isinstance(value, tuple):
        return tuple(scrub(item, depth=depth + 1) for item in value)
    return value


def _before_send(event: Event, _hint: Hint) -> Event:
    """Every event, on its way out, with the sensitive parts removed."""
    return scrub(event)  # type: ignore[no-any-return]


def configure_sentry(settings: Settings) -> bool:
    """Start Sentry if a DSN is configured. Returns whether it was started."""
    if settings.sentry_dsn is None:
        return False

    sentry_sdk.init(
        dsn=settings.sentry_dsn.get_secret_value(),
        environment=settings.environment.value,
        release=settings.release,
        traces_sample_rate=settings.sentry_traces_sample_rate,
        # Profiling samples stack traces of running code. Not needed to find the
        # first faults, and it is the setting most likely to surprise on cost.
        profiles_sample_rate=0.0,
        send_default_pii=False,
        max_request_body_size="never",
        before_send=_before_send,
        before_send_transaction=_before_send,
    )
    log.info(
        "sentry_enabled",
        environment=settings.environment.value,
        release=settings.release,
        traces_sample_rate=settings.sentry_traces_sample_rate,
    )
    return True


def tag_request(request_id: str) -> None:
    """Put the request id on the Sentry scope.

    It is the same id in the response header, the log lines, the audit row and
    the reference a coordinator reads down the phone. One value ties them
    together, which is the entire point of having it.
    """
    if sentry_sdk.is_initialized():
        sentry_sdk.get_isolation_scope().set_tag("request_id", request_id)
