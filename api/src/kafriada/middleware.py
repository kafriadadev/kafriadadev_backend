"""HTTP middleware: request identity and security headers."""

from __future__ import annotations

import re
import secrets
import time
from collections.abc import Awaitable, Callable

import structlog
from starlette.datastructures import MutableHeaders
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

from kafriada.settings import Settings

_log = structlog.get_logger(__name__)

REQUEST_ID_HEADER = "x-request-id"

# An inbound request id is attacker-controlled text that ends up in log lines and
# in an audit row. Anything outside this alphabet is discarded and replaced with
# a fresh id — otherwise a caller can inject newlines and forge log entries.
_SAFE_REQUEST_ID = re.compile(r"^[A-Za-z0-9_-]{8,64}$")

Next = Callable[[Request], Awaitable[Response]]


def new_request_id() -> str:
    return secrets.token_urlsafe(12)


def short_reference(request_id: str) -> str:
    """The code shown to a user on an error screen.

    Short enough for a coordinator in Birnin Kudu to read down the phone, and it
    resolves straight to the full trace.
    """
    cleaned = re.sub(r"[^A-Za-z0-9]", "", request_id).upper()
    return f"{cleaned[:4]}-{cleaned[4:8]}" if len(cleaned) >= 8 else cleaned.ljust(4, "0")


class RequestContextMiddleware:
    """Assigns every request an id, binds it to the logger, times it.

    The id travels three ways: into every log line, back to the caller in a
    response header, and into the ``request_id`` column of any audit row written
    while handling the request. One value ties a user's complaint to the exact
    trace.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:  # type: ignore[no-untyped-def]
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope["headers"]}
        candidate = headers.get(REQUEST_ID_HEADER, "")
        request_id = candidate if _SAFE_REQUEST_ID.match(candidate) else new_request_id()

        scope["request_id"] = request_id
        structlog.contextvars.bind_contextvars(
            request_id=request_id,
            path=scope.get("path", ""),
            method=scope.get("method", ""),
        )
        started = time.perf_counter()
        status_holder = {"status": 500}

        async def send_wrapper(message) -> None:  # type: ignore[no-untyped-def]
            if message["type"] == "http.response.start":
                status_holder["status"] = message["status"]
                MutableHeaders(scope=message)[REQUEST_ID_HEADER] = request_id
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            duration_ms = round((time.perf_counter() - started) * 1000, 2)
            _log.info(
                "request",
                status=status_holder["status"],
                duration_ms=duration_ms,
            )
            structlog.contextvars.clear_contextvars()


class SecurityHeadersMiddleware:
    """Response headers that cost nothing and close whole categories of attack.

    This service returns JSON to a server-side caller, never HTML to a browser,
    so the policy can be far stricter than a web application's: deny everything,
    frame nothing, sniff nothing, cache nothing.
    """

    def __init__(self, app: ASGIApp, settings: Settings) -> None:
        self.app = app
        self._headers: list[tuple[bytes, bytes]] = [
            # Never let a browser guess a content type. Stops a JSON response
            # being reinterpreted as HTML and executed.
            (b"x-content-type-options", b"nosniff"),
            (b"x-frame-options", b"DENY"),
            # A JSON API needs no resources at all, so forbid every source.
            (b"content-security-policy", b"default-src 'none'; frame-ancestors 'none'"),
            # Never leak a path containing a KUID into a third party's referer log.
            (b"referrer-policy", b"no-referrer"),
            (b"permissions-policy", b"geolocation=(), camera=(), microphone=(), payment=()"),
            (b"x-permitted-cross-domain-policies", b"none"),
            # Responses carry personal data and payment state. No shared cache,
            # no browser cache, no disk. Endpoints that are genuinely public and
            # cacheable set their own Cache-Control, which overrides this.
            (b"cache-control", b"no-store, no-cache, must-revalidate, private"),
        ]
        if settings.environment.is_production:
            self._headers.append(
                (b"strict-transport-security", b"max-age=31536000; includeSubDomains")
            )

    async def __call__(self, scope, receive, send) -> None:  # type: ignore[no-untyped-def]
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_wrapper(message) -> None:  # type: ignore[no-untyped-def]
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                for key, value in self._headers:
                    name = key.decode("latin-1")
                    # A handler that deliberately set its own value wins — the
                    # public profile endpoint sets a cacheable Cache-Control.
                    if name not in headers:
                        headers[name] = value.decode("latin-1")
                # Advertising the server and its version helps nobody but a
                # scanner looking for a known CVE.
                if "server" in headers:
                    del headers["server"]
            await send(message)

        await self.app(scope, receive, send_wrapper)
