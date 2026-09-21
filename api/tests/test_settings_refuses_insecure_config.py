"""Configuration must fail loudly rather than boot insecurely.

Every case here is a real way production systems get deployed wrong: the example
file copied unchanged, debug docs left on, a test payment key promoted, CORS
opened to make a browser call work. A service that starts with any of these is
worse than one that refuses to start, because nobody finds out until it matters.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from kafriada.settings import Environment, Settings

APP_URL = "postgresql+psycopg://kaf_app:pw@db:5432/kafriada"
MONEY_URL = "postgresql+psycopg://kaf_money:pw@db:5432/kafriada"


def build(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "database_url_app": APP_URL,
        "database_url_money": MONEY_URL,
        "secret_key": "s" * 40,
        "qr_secret": "q" * 40,
    }
    values.update(overrides)
    # _env_file=None keeps the developer's local .env out of the test run. A test
    # whose result depends on an untracked file on one machine is not a test —
    # it passes locally, fails in CI, and tells you nothing either way.
    return Settings(_env_file=None, **values)  # type: ignore[arg-type]


def production(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "environment": Environment.PRODUCTION,
        "enable_docs": False,
        "trusted_hosts": ["api.kafriada.ng"],
        "cors_allow_origins": [],
        "paystack_secret_key": "sk_live_" + "z" * 30,
        "payment_provider": "paystack",
        "media_store": "r2",
        "r2_account_id": "acct",
        "r2_access_key_id": "AKIAEXAMPLE",
        "r2_secret_access_key": "r" * 30,
        "r2_bucket": "kafriada-media",
        "sms_provider": "twilio",
        "twilio_account_sid": "AC" + "1" * 30,
        "twilio_auth_token": "t" * 30,
        "twilio_messaging_service_sid": "MG" + "2" * 30,
    }
    values.update(overrides)
    return build(**values)


class TestSecretStrength:
    def test_local_defaults_are_accepted(self) -> None:
        assert build().environment is Environment.LOCAL

    @pytest.mark.parametrize("placeholder", ["change-me", "CHANGEME", "secret", "TODO"])
    def test_placeholder_secrets_are_refused(self, placeholder: str) -> None:
        with pytest.raises(ValidationError, match="placeholder secret"):
            build(secret_key=placeholder)

    def test_short_secrets_are_refused(self) -> None:
        with pytest.raises(ValidationError, match="at least 32 characters"):
            build(qr_secret="only-24-characters-here")

    def test_unknown_variable_is_an_error_not_a_silent_ignore(self) -> None:
        # A typo'd variable name means a setting silently keeps its default.
        # For a setting like session lifetime, that is a security defect.
        with pytest.raises(ValidationError):
            build(sesion_idle_days_athlete=1)


class TestProductionLockdown:
    def test_a_correct_production_config_is_accepted(self) -> None:
        assert production().environment.is_production

    def test_interactive_docs_are_refused(self) -> None:
        with pytest.raises(ValidationError, match="enable_docs must be false"):
            production(enable_docs=True)

    def test_debug_logging_is_refused(self) -> None:
        # DEBUG logging in this codebase emits request bodies and query
        # parameters, which include phone numbers and payment references.
        with pytest.raises(ValidationError, match="must not be DEBUG"):
            production(log_level="DEBUG")

    def test_wildcard_host_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="trusted_hosts"):
            production(trusted_hosts=["*"])

    def test_open_cors_is_refused(self) -> None:
        # A browser origin in this list means the domain tier has been exposed
        # directly to browsers, which defeats the whole point of the BFF.
        with pytest.raises(ValidationError, match="cors_allow_origins must be empty"):
            production(cors_allow_origins=["https://kafriada.ng"])

    def test_paystack_test_key_is_refused_in_production(self) -> None:
        with pytest.raises(ValidationError, match="Paystack TEST key"):
            production(paystack_secret_key="sk_test_" + "z" * 30)

    def test_missing_payment_or_sms_credentials_are_refused(self) -> None:
        with pytest.raises(ValidationError, match="paystack_secret_key is required"):
            production(paystack_secret_key=None)
        with pytest.raises(ValidationError, match="twilio_auth_token is required"):
            production(twilio_auth_token=None)
        with pytest.raises(ValidationError, match="messaging_service_sid or"):
            production(twilio_messaging_service_sid=None, twilio_from_number=None)

    def test_an_unconfigured_or_printing_sms_provider_is_refused(self) -> None:
        """A queue nobody drains, and codes in a log file, are both production bugs."""
        with pytest.raises(ValidationError, match="sms_provider must be configured"):
            production(sms_provider="none")
        with pytest.raises(ValidationError, match="must not be 'console'"):
            production(sms_provider="console")

    def test_sharing_one_database_role_for_app_and_money_is_refused(self) -> None:
        """The ledger privilege boundary, checked at startup.

        If both connection strings use the same role, the role serving ordinary
        requests can write the ledger — and the isolation described in the
        architecture silently does not exist.
        """
        with pytest.raises(ValidationError, match="different roles"):
            production(database_url_money=APP_URL)

    def test_all_problems_are_reported_together(self) -> None:
        # Fixing a misconfiguration one restart at a time is how a deploy window
        # gets used up. Report everything wrong at once.
        with pytest.raises(ValidationError) as caught:
            production(enable_docs=True, trusted_hosts=["*"], twilio_auth_token=None)
        message = str(caught.value)
        assert "enable_docs" in message
        assert "trusted_hosts" in message
        assert "twilio_auth_token" in message


class TestReadRouting:
    def test_reads_prefer_the_replica_when_configured(self) -> None:
        replica = "postgresql+psycopg://kaf_reader:pw@replica:5432/kafriada"
        assert str(build(database_url_reader=replica).read_url) == replica

    def test_reads_fall_back_to_the_primary_rather_than_failing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # A missing replica should degrade performance, never availability.
        #
        # An exported DATABASE_URL_READER *is* a configured replica, and reaches
        # Settings through the process environment even with _env_file=None. So
        # this test would fail for anyone running the database tests against a
        # local database with all four URLs set — clear it rather than depend on
        # what the shell happens to hold.
        monkeypatch.delenv("DATABASE_URL_READER", raising=False)
        assert str(build().read_url) == APP_URL
