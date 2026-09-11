"""Application entry point.

This service holds every business rule and the only database credentials. It is
not reachable from the internet except for two surfaces — the anonymous public
read endpoints and the Paystack webhook. Everything else is called server-side by
the presentation tier over a private network, which is why there is no CORS
configuration and no browser-facing session handling here.
"""

from __future__ import annotations

import logging
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.trustedhost import TrustedHostMiddleware

from kafriada.middleware import (
    RequestContextMiddleware,
    SecurityHeadersMiddleware,
    short_reference,
)
from kafriada.settings import Settings, get_settings

log = structlog.get_logger(__name__)


def configure_logging(settings: Settings) -> None:
    """Structured JSON logs in deployed environments, readable ones locally.

    The processor chain drops any key whose name suggests a secret. Logs are
    read by more people, in more places, than the database ever is — a token in
    a log line is a token in a support ticket, a screenshot and a backup.
    """
    logging.basicConfig(
        format="%(message)s", stream=sys.stdout, level=settings.log_level
    )

    def redact(_logger: Any, _name: str, event_dict: dict[str, Any]) -> dict[str, Any]:
        blocked = (
            "password",
            "token",
            "secret",
            "authorization",
            "cookie",
            "otp",
            "signature",
            "api_key",
            "card",
        )
        for key in list(event_dict):
            if any(word in key.lower() for word in blocked):
                event_dict[key] = "[redacted]"
        return event_dict

    processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        redact,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]
    processors.append(
        structlog.dev.ConsoleRenderer()
        if settings.environment.value == "local"
        else structlog.processors.JSONRenderer()
    )
    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.getLevelName(settings.log_level)
        ),
        cache_logger_on_first_use=True,
    )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings: Settings = app.state.settings
    log.info(
        "starting",
        service=settings.service_name,
        environment=settings.environment.value,
    )
    yield
    log.info("stopped")


def create_app(settings: Settings | None = None) -> FastAPI:
    cfg = settings or get_settings()
    configure_logging(cfg)

    app = FastAPI(
        title="KAFRIADA CORE API",
        version="0.1.0",
        # The contract is published deliberately as a versioned OpenAPI document,
        # not incidentally from a live endpoint. Off outside development.
        docs_url="/docs" if cfg.enable_docs else None,
        redoc_url=None,
        openapi_url="/openapi.json" if cfg.enable_docs else None,
        lifespan=lifespan,
    )
    app.state.settings = cfg

    # Order matters: the outermost middleware runs first on the way in and last
    # on the way out. Request context is outermost so that every log line and
    # every error response carries an id, including ones raised by middleware
    # below it.
    app.add_middleware(SecurityHeadersMiddleware, settings=cfg)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=cfg.trusted_hosts)
    app.add_middleware(RequestContextMiddleware)

    _install_error_handlers(app)
    _install_health(app)
    _install_routes(app)
    return app


def _install_routes(app: FastAPI) -> None:
    """Mount the versioned contract.

    Everything lives under /v1. The version is in the path because this API is a
    product surface that federations and a future native app will depend on, and
    a breaking change to something other people build against needs a new
    address rather than a quiet redefinition of the old one.
    """
    from kafriada.api.v1 import admin, athletes, sessions

    app.include_router(athletes.router, prefix="/v1")
    app.include_router(sessions.router, prefix="/v1")
    app.include_router(admin.router, prefix="/v1")


def _install_error_handlers(app: FastAPI) -> None:
    """Errors say what went wrong without saying how the system is built.

    Every response carries the short reference from the request id, so a user can
    read it down the phone and it resolves to the exact trace. Unhandled
    exceptions never render a message, a type, or a stack — those go to the log.
    """

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        request_id = request.scope.get("request_id", "")
        if exc.status_code >= 500:
            log.error("http_error", status=exc.status_code, detail=str(exc.detail))
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "message": exc.detail if exc.status_code < 500 else "Something went wrong.",
                    "reference": short_reference(request_id),
                }
            },
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        request_id = request.scope.get("request_id", "")
        # Field names and reasons are safe and useful. The submitted values are
        # not echoed back — they can contain a password or an OTP.
        problems = [
            {"field": ".".join(str(p) for p in err["loc"][1:]), "reason": err["msg"]}
            for err in exc.errors()
        ]
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "message": "Some of the details are not valid.",
                    "reference": short_reference(request_id),
                    "problems": problems,
                }
            },
        )

    @app.exception_handler(Exception)
    async def unhandled(request: Request, exc: Exception) -> JSONResponse:
        request_id = request.scope.get("request_id", "")
        log.exception("unhandled_exception", error_type=type(exc).__name__)
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "message": "Something went wrong at our end.",
                    "reference": short_reference(request_id),
                }
            },
        )


def _install_health(app: FastAPI) -> None:
    from kafriada.api.security import Public

    @app.get(
        "/healthz",
        include_in_schema=False,
        dependencies=[Public("liveness probe; answers only 'ok'")],
    )
    def healthz() -> dict[str, str]:
        """Liveness. Deliberately reveals nothing: version, environment and
        dependency state are all information an unauthenticated caller does not
        need. Readiness, which does check the database, is a separate internal
        endpoint added with the database layer."""
        return {"status": "ok"}


app = create_app()
