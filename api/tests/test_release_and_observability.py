"""The deploy gates: what leaves the process, and what a migration may do.

No database and no network. These are the two checks that would otherwise only
be exercised during an incident or a release, which is the worst time to find
out they were wrong.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

import pytest
import sentry_sdk
from fastapi.testclient import TestClient

from kafriada.main import create_app
from kafriada.observability import _before_send, configure_sentry, scrub, scrub_text
from kafriada.settings import Settings

REPO = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------------------
# Nothing identifying reaches Sentry
# ---------------------------------------------------------------------------
class TestScrubbing:
    @pytest.mark.parametrize(
        ("text", "must_not_contain"),
        [
            ("registration failed for +2348030000000", "8030000000"),
            ("phone=08030000000 not found", "08030000000"),
            # As typed at a registration desk, separators and all.
            ("no such user 0803 000 0000", "0803 000 0000"),
            ("no such user 0803-000-0000", "0803-000-0000"),
            ("phone=+234 803 000 0000 rejected", "803 000 0000"),
        ],
    )
    def test_phone_numbers_never_survive(self, text: str, must_not_contain: str) -> None:
        cleaned = scrub_text(text)
        assert must_not_contain not in cleaned
        assert "[phone]" in cleaned

    def test_the_kuid_is_kept_because_it_is_public_and_useful(self) -> None:
        cleaned = scrub_text("phone=+2349441944242 kuid=KA-NG-JG-BKD-2026-000610")
        assert "KA-NG-JG-BKD-2026-000610" in cleaned
        assert "[phone]" in cleaned

    def test_a_database_url_loses_its_password(self) -> None:
        cleaned = scrub_text(
            "(psycopg.OperationalError) connection to "
            "postgresql+psycopg://kaf_app:s3cr3tpassword@db.example.co:5432/postgres failed"
        )
        assert "s3cr3tpassword" not in cleaned
        assert "postgresql+psycopg://[redacted]@" in cleaned

    def test_a_bearer_token_loses_its_value(self) -> None:
        cleaned = scrub_text("authorization: Bearer I02Pdgk3vYncqg6ftDQirVAp7o10Sy80Dr4NJ7FPkTk")
        assert "I02Pdgk3" not in cleaned

    def test_keys_that_sound_like_secrets_are_replaced_whole(self) -> None:
        event: dict[str, Any] = {
            "request": {
                "headers": {"authorization": "Bearer abc", "user-agent": "Opera Mini"},
                "cookies": {"kaf_session": "abcdef"},
            },
            "extra": {"password": "hunter2", "otp_code": "123456", "kuid": "KA-NG-JG-BKD-2026-1"},
        }
        cleaned = scrub(event)
        assert cleaned["request"]["headers"]["authorization"] == "[redacted]"
        assert cleaned["request"]["headers"]["user-agent"] == "Opera Mini"
        assert cleaned["request"]["cookies"] == "[redacted]"
        assert cleaned["extra"]["password"] == "[redacted]"
        assert cleaned["extra"]["otp_code"] == "[redacted]"
        assert cleaned["extra"]["kuid"] == "KA-NG-JG-BKD-2026-1"

    def test_nested_structures_are_walked(self) -> None:
        event = {"exception": {"values": [{"value": "failed for +2348030000000"}]}}
        cleaned = scrub(event)
        assert "+2348030000000" not in str(cleaned)

    def test_a_cycle_or_a_deep_nest_cannot_hang_the_reporter(self) -> None:
        deep: dict[str, Any] = {}
        node = deep
        for _ in range(50):
            node["next"] = {}
            node = node["next"]
        node["value"] = "+2348030000000"
        assert "+2348030000000" not in str(scrub(deep))


def _settings(**overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "database_url_app": "postgresql+psycopg://kaf_app:pw@localhost:5432/kafriada",
        "database_url_money": "postgresql+psycopg://kaf_money:pw@localhost:5432/kafriada",
        "secret_key": "x" * 40,
        "qr_secret": "y" * 40,
    }
    values.update(overrides)
    return Settings(**values)


class TestSentryStartup:
    def test_an_event_that_really_goes_through_sentry_is_scrubbed(self) -> None:
        """Proves the scrubber is attached, not merely correct on its own.

        A fake transport stands in for the network, so this sends nothing
        anywhere and still exercises the path a real error takes.
        """
        captured: list[dict[str, Any]] = []
        settings = _settings(sentry_dsn="https://public@localhost/1", release="abc123")
        try:
            assert configure_sentry(settings) is True
            # Replace the client's transport with one that keeps the event.
            sentry_sdk.init(
                dsn="https://public@localhost/1",
                environment="local",
                release="abc123",
                send_default_pii=False,
                max_request_body_size="never",
                before_send=_before_send,
                transport=captured.append,
            )
            try:
                raise RuntimeError(
                    "could not register +234 803 000 0000 via "
                    "postgresql+psycopg://kaf_app:s3cr3t@db.example.co:5432/postgres"
                )
            except RuntimeError:
                sentry_sdk.capture_exception()
            sentry_sdk.flush(timeout=5)
        finally:
            sentry_sdk.init(dsn=None)  # leave the process as it was found

        assert captured, "no event reached the transport"
        body = str(captured[0])
        assert "803 000 0000" not in body
        assert "s3cr3t" not in body
        assert "[phone]" in body
        assert captured[0]["release"] == "abc123"

    def test_without_a_dsn_nothing_is_started(self) -> None:
        assert configure_sentry(_settings(sentry_dsn=None)) is False


# ---------------------------------------------------------------------------
# The probes
# ---------------------------------------------------------------------------
class TestProbes:
    def test_liveness_answers_without_touching_the_database(self) -> None:
        with TestClient(create_app()) as client:
            response = client.get("/healthz")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

    def test_readiness_reports_not_ready_without_saying_which_role_failed(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import kafriada.db.engine as engine

        monkeypatch.setattr(
            engine, "check_connectivity", lambda: {"app": True, "money": False, "read": True}
        )
        with TestClient(create_app()) as client:
            response = client.get("/readyz")
        assert response.status_code == 503
        assert response.json() == {"status": "not ready"}
        assert "money" not in response.text

    def test_readiness_is_ready_when_every_role_answers(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import kafriada.db.engine as engine

        monkeypatch.setattr(
            engine, "check_connectivity", lambda: {"app": True, "money": True, "read": True}
        )
        with TestClient(create_app()) as client:
            response = client.get("/readyz")
        assert response.status_code == 200
        assert response.json() == {"status": "ready"}


# ---------------------------------------------------------------------------
# The destructive-migration gate
# ---------------------------------------------------------------------------
def _load_gate() -> Any:
    """Import scripts/check_migration_safety.py, which is not a package."""
    path = REPO / "scripts/check_migration_safety.py"
    spec = importlib.util.spec_from_file_location("check_migration_safety", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["check_migration_safety"] = module
    spec.loader.exec_module(module)
    return module


class TestMigrationGate:
    gate = _load_gate()

    def test_the_real_migrations_pass(self) -> None:
        assert self.gate.main() == 0

    def test_a_dropped_column_in_an_upgrade_is_caught(self, tmp_path: Path) -> None:
        self._write(tmp_path, "0099_bad.py", 'def upgrade():\n    op.execute("ALTER TABLE ops.users DROP COLUMN phone_e164")\n')
        assert self.gate.main() == 1

    def test_the_same_statement_in_a_downgrade_is_allowed(self, tmp_path: Path) -> None:
        self._write(
            tmp_path,
            "0099_ok.py",
            'def upgrade():\n    op.execute("CREATE TABLE ops.x (id int)")\n\n\n'
            'def downgrade():\n    op.execute("DROP TABLE ops.x")\n',
        )
        assert self.gate.main() == 0

    def test_a_written_justification_lets_it_through(self, tmp_path: Path) -> None:
        self._write(
            tmp_path,
            "0099_approved.py",
            'DESTRUCTIVE_MIGRATION_APPROVED = "the column was never written to"\n\n'
            'def upgrade():\n    op.execute("ALTER TABLE ops.users DROP COLUMN unused")\n',
        )
        assert self.gate.main() == 0

    def _write(self, tmp_path: Path, name: str, body: str) -> None:
        """Point the gate at a throwaway directory holding one migration."""
        versions = tmp_path / "versions"
        versions.mkdir(exist_ok=True)
        (versions / name).write_text(body, encoding="utf-8")
        self.gate.VERSIONS = versions
