"""Application configuration.

Every secret is read from the environment and never has a usable default. The
validators below are deliberately unforgiving: a misconfigured production process
must fail to start rather than start insecurely, because a service that boots with
a placeholder signing key is worse than one that does not boot at all.
"""

from __future__ import annotations

import secrets
from enum import StrEnum
from functools import lru_cache
from typing import Annotated, Self

from pydantic import Field, PostgresDsn, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(StrEnum):
    LOCAL = "local"
    STAGING = "staging"
    PRODUCTION = "production"

    @property
    def is_production(self) -> bool:
        return self is Environment.PRODUCTION


# Values that look like a secret but are not. If any of these reaches a deployed
# environment we refuse to start. The list is deliberately blunt — it costs
# nothing and it catches the copy-the-example-file mistake, which is the single
# most common way a real system ends up with a guessable signing key.
_PLACEHOLDER_SECRETS = frozenset(
    {
        "change-me",
        "changeme",
        "secret",
        "password",
        "test",
        "dev",
        "development",
        "placeholder",
        "todo",
        "xxx",
        "generate-me",
        "replace-this",
    }
)

MIN_SECRET_BYTES = 32


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="forbid",  # an unknown variable is a typo, and a typo in config is a defect
        frozen=True,
    )

    # -- Environment ------------------------------------------------------
    environment: Environment = Environment.LOCAL
    service_name: str = "kafriada-api"

    # Interactive API documentation. Off in production: the schema is published
    # deliberately through the versioned contract, not incidentally through /docs.
    enable_docs: bool = False

    # -- Database ---------------------------------------------------------
    # Three connection strings, three PostgreSQL roles, three privilege levels.
    # This is the isolation guarantee from the architecture: the role that serves
    # ordinary requests cannot write the ledger, and no role can delete an audit
    # row. Enforced by GRANT, not by application code.
    database_url_app: PostgresDsn  # kaf_app    — read/write identity + ops
    database_url_money: PostgresDsn  # kaf_money  — the only INSERT on the ledger
    database_url_reader: PostgresDsn | None = None  # kaf_reader — replica, SELECT only
    # kaf_migrate owns every object and holds DDL. It is used by the release step
    # and by the migration tests, and must never be held by a running process —
    # it is the one role that could disable the audit log's protections.
    database_url_migrate: PostgresDsn | None = None

    db_pool_size: int = Field(default=10, ge=1, le=50)
    db_max_overflow: int = Field(default=5, ge=0, le=50)
    db_statement_timeout_ms: int = Field(default=10_000, ge=1_000, le=60_000)
    # In production the application and the database share an availability zone
    # and connect in milliseconds. A developer working against a managed database
    # over the public internet — especially an IPv6-only host — routinely needs
    # several seconds for the first connection, so this is configurable rather
    # than a constant tuned for one of the two situations.
    db_connect_timeout_seconds: int = Field(default=15, ge=2, le=60)

    # -- Signing keys -----------------------------------------------------
    # Session cookies carry an opaque random token; the value below signs
    # nothing user-facing except CSRF tokens. QR_SECRET signs public profile
    # links and is versioned so it can be rotated without invalidating every
    # printed card in Jigawa on the same day.
    secret_key: SecretStr
    qr_secret: SecretStr
    qr_key_version: int = Field(default=1, ge=1, le=99)

    # -- Sessions ---------------------------------------------------------
    # Staff share phones in the field, so their sessions expire on idle far
    # sooner than an athlete's. See the architecture, session policy.
    session_cookie_name: str = "kaf_session"
    session_idle_minutes_staff: int = Field(default=30, ge=5, le=240)
    session_absolute_days_staff: int = Field(default=7, ge=1, le=30)
    session_idle_days_athlete: int = Field(default=30, ge=1, le=90)

    # -- Password hashing -------------------------------------------------
    # OWASP minimum for Argon2id is 19 MiB, t=2, p=1. Raising memory_cost is the
    # strongest lever; do not lower it below the default without measuring on the
    # production instance and recording the reason.
    argon2_memory_kib: int = Field(default=19_456, ge=19_456)
    argon2_time_cost: int = Field(default=2, ge=2)
    argon2_parallelism: int = Field(default=1, ge=1, le=4)
    # Argon2id is intentionally expensive, so it is CPU work. Cap how much of it
    # can run at once or a registration drive starves every other request.
    password_hash_concurrency: int = Field(default=2, ge=1, le=16)

    # -- Money ------------------------------------------------------------
    # Prices in kobo. Never naira, never a float. 250_000 kobo = 2,500 naira.
    price_athlete_verification_kobo: int = Field(default=250_000, ge=1)
    price_club_verification_kobo: int = Field(default=1_500_000, ge=1)

    # -- Paystack ---------------------------------------------------------
    paystack_secret_key: SecretStr | None = None
    paystack_base_url: str = "https://api.paystack.co"
    paystack_timeout_seconds: float = Field(default=8.0, gt=0, le=30)

    # -- Termii (SMS) -----------------------------------------------------
    termii_api_key: SecretStr | None = None
    termii_sender_id: str = "KAFRIADA"

    # -- Redis (rate limits and the idempotency cache only) ---------------
    redis_url: str = "redis://localhost:6379/0"

    # -- Observability ----------------------------------------------------
    sentry_dsn: SecretStr | None = None
    log_level: str = "INFO"

    # -- HTTP -------------------------------------------------------------
    # The browser talks only to the Next.js origin, which calls this service
    # server-side over a private network. So there is no browser origin to allow
    # by default, and CORS stays empty. If this list is ever non-empty in
    # production, someone has exposed the domain tier directly to browsers.
    cors_allow_origins: list[str] = Field(default_factory=list)
    trusted_hosts: list[str] = Field(default_factory=lambda: ["*"])

    # ------------------------------------------------------------------
    # Validators
    # ------------------------------------------------------------------
    @field_validator("secret_key", "qr_secret")
    @classmethod
    def _secret_must_be_strong(cls, value: SecretStr) -> SecretStr:
        raw = value.get_secret_value()
        if raw.strip().lower() in _PLACEHOLDER_SECRETS:
            raise ValueError(
                "refusing a placeholder secret. Generate one with: "
                "python -c \"import secrets; print(secrets.token_urlsafe(32))\""
            )
        if len(raw) < MIN_SECRET_BYTES:
            raise ValueError(
                f"secret must be at least {MIN_SECRET_BYTES} characters, got {len(raw)}"
            )
        return value

    @field_validator("log_level")
    @classmethod
    def _valid_log_level(cls, value: str) -> str:
        allowed = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        upper = value.upper()
        if upper not in allowed:
            raise ValueError(f"log_level must be one of {sorted(allowed)}")
        return upper

    @model_validator(mode="after")
    def _production_is_locked_down(self) -> Self:
        if not self.environment.is_production:
            return self

        problems: list[str] = []

        if self.enable_docs:
            problems.append("enable_docs must be false in production")
        if self.log_level == "DEBUG":
            problems.append("log_level must not be DEBUG in production")
        if "*" in self.trusted_hosts:
            problems.append("trusted_hosts must name real hosts in production, not '*'")
        if self.cors_allow_origins:
            problems.append(
                "cors_allow_origins must be empty in production — the domain tier is "
                "reached server-side by the presentation tier, never by a browser"
            )
        if self.paystack_secret_key is None:
            problems.append("paystack_secret_key is required in production")
        elif self.paystack_secret_key.get_secret_value().startswith("sk_test_"):
            problems.append("refusing a Paystack TEST key in production")
        if self.termii_api_key is None:
            problems.append("termii_api_key is required in production")
        if self.database_url_app == self.database_url_money:
            problems.append(
                "database_url_app and database_url_money must use different roles — "
                "sharing one connection destroys the ledger privilege boundary"
            )

        if problems:
            raise ValueError(
                "refusing to start in production:\n  - " + "\n  - ".join(problems)
            )
        return self

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @property
    def read_url(self) -> PostgresDsn:
        """Replica if configured, primary otherwise.

        Reporting and public reads should never contend with the write path,
        but a missing replica must degrade rather than break.
        """
        return self.database_url_reader or self.database_url_app


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    # Every field is populated from the environment, so no arguments are passed.
    return Settings()


def generate_secret() -> str:
    """Used by scripts and the developer setup flow, never at runtime."""
    return secrets.token_urlsafe(MIN_SECRET_BYTES)


SettingsDep = Annotated[Settings, "injected via dependency in kafriada.deps"]
