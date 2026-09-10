"""The audit log's immutability, proved against a real database.

The architecture claims audit rows cannot be altered or deleted by anyone,
including a super_admin acting through the application. That is a claim about
PostgreSQL privileges and triggers, so only PostgreSQL can settle it — no amount
of application-level testing proves anything here.

These tests run in CI against a real database and are skipped locally when none
is configured. They are not optional: if this file is deleted or its assertions
weakened, the system's central integrity promise becomes unverified.

    docker compose -f infra/docker-compose.yml up -d
    bash scripts/bootstrap-local-db.sh
    uv run pytest -m db
"""

from __future__ import annotations

import os

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError, ProgrammingError

# A managed database reached over the public internet — an IPv6-only host in
# particular — can take several seconds to accept a first connection. Without an
# explicit budget the first fixture errors out, which reads like a failed
# security assertion when it is really a slow handshake.
_ENGINE_KWARGS = {"connect_args": {"connect_timeout": 30}, "pool_pre_ping": True}

APP_URL = os.environ.get("DATABASE_URL_APP")
MIGRATE_URL = os.environ.get("DATABASE_URL_MIGRATE")

pytestmark = [
    pytest.mark.db,
    pytest.mark.skipif(
        not APP_URL or not MIGRATE_URL,
        reason="needs DATABASE_URL_APP and DATABASE_URL_MIGRATE",
    ),
]


@pytest.fixture(scope="module")
def app_engine():  # type: ignore[no-untyped-def]
    """A connection as kaf_app — the role a running process actually holds."""
    engine = create_engine(APP_URL or "", future=True, **_ENGINE_KWARGS)
    yield engine
    engine.dispose()


@pytest.fixture(scope="module")
def migrate_engine():  # type: ignore[no-untyped-def]
    """A connection as kaf_migrate — the object owner, used only by releases."""
    engine = create_engine(MIGRATE_URL or "", future=True, **_ENGINE_KWARGS)
    yield engine
    engine.dispose()


@pytest.fixture
def an_audit_row(app_engine):  # type: ignore[no-untyped-def]
    with app_engine.begin() as conn:
        row_id = conn.execute(
            text(
                """
                INSERT INTO ops.audit_log
                    (actor_label, action, subject_type, subject_id, request_id)
                VALUES ('test-suite', 'test.written', 'test', :sid, 'test-request')
                RETURNING id
                """
            ),
            {"sid": "immutability-check"},
        ).scalar_one()
    return row_id


class TestApplicationRoleCannotAlterHistory:
    def test_the_application_can_write_an_audit_row(self, an_audit_row: int) -> None:
        # The positive case matters too: a log nothing can write is equally useless.
        assert an_audit_row > 0

    def test_the_application_cannot_update_an_audit_row(
        self, app_engine, an_audit_row: int
    ) -> None:  # type: ignore[no-untyped-def]
        with pytest.raises((ProgrammingError, DBAPIError)) as caught:
            with app_engine.begin() as conn:
                conn.execute(
                    text("UPDATE ops.audit_log SET action = 'tampered' WHERE id = :i"),
                    {"i": an_audit_row},
                )
        assert "permission denied" in str(caught.value).lower()

    def test_the_application_cannot_delete_an_audit_row(
        self, app_engine, an_audit_row: int
    ) -> None:  # type: ignore[no-untyped-def]
        with pytest.raises((ProgrammingError, DBAPIError)) as caught:
            with app_engine.begin() as conn:
                conn.execute(
                    text("DELETE FROM ops.audit_log WHERE id = :i"), {"i": an_audit_row}
                )
        assert "permission denied" in str(caught.value).lower()

    def test_the_application_cannot_truncate_the_audit_log(
        self, app_engine
    ) -> None:  # type: ignore[no-untyped-def]
        with pytest.raises((ProgrammingError, DBAPIError)):
            with app_engine.begin() as conn:
                conn.execute(text("TRUNCATE ops.audit_log"))


class TestEvenTheOwnerIsStopped:
    """Privileges stop the application. The trigger stops the owner too.

    kaf_migrate owns the table, so grants alone would not restrain it. These
    tests cover the case where a migration — or someone who obtained the release
    credential — attempts to rewrite history.
    """

    def test_the_owner_cannot_update_an_audit_row(
        self, migrate_engine, an_audit_row: int
    ) -> None:  # type: ignore[no-untyped-def]
        with pytest.raises((ProgrammingError, DBAPIError)) as caught:
            with migrate_engine.begin() as conn:
                conn.execute(
                    text("UPDATE ops.audit_log SET action = 'tampered' WHERE id = :i"),
                    {"i": an_audit_row},
                )
        assert "append-only" in str(caught.value).lower()

    def test_the_owner_cannot_delete_an_audit_row(
        self, migrate_engine, an_audit_row: int
    ) -> None:  # type: ignore[no-untyped-def]
        with pytest.raises((ProgrammingError, DBAPIError)) as caught:
            with migrate_engine.begin() as conn:
                conn.execute(
                    text("DELETE FROM ops.audit_log WHERE id = :i"), {"i": an_audit_row}
                )
        assert "append-only" in str(caught.value).lower()

    def test_the_owner_cannot_truncate_the_audit_log(
        self, migrate_engine
    ) -> None:  # type: ignore[no-untyped-def]
        with pytest.raises((ProgrammingError, DBAPIError)) as caught:
            with migrate_engine.begin() as conn:
                conn.execute(text("TRUNCATE ops.audit_log"))
        assert "append-only" in str(caught.value).lower()


class TestLedgerPrivilegeBoundary:
    """kaf_app may read money but never write it.

    The ledger tables arrive in a later migration; until then this asserts the
    default privileges that will govern them, which is what actually decides the
    outcome when those tables are created.
    """

    def test_app_role_has_no_default_write_privilege_in_the_money_schema(
        self, app_engine
    ) -> None:  # type: ignore[no-untyped-def]
        with app_engine.connect() as conn:
            grants = conn.execute(
                text(
                    """
                    SELECT DISTINCT a.privilege_type AS privilege
                      FROM pg_default_acl d
                      JOIN pg_namespace n ON n.oid = d.defaclnamespace
                      CROSS JOIN LATERAL aclexplode(d.defaclacl) AS a
                     WHERE n.nspname = 'money'
                       AND a.grantee = 'kaf_app'::regrole
                    """
                )
            ).scalars().all()
        assert set(grants) <= {"SELECT"}, f"kaf_app must not write money: {grants}"

    def test_app_role_is_read_only_on_the_money_schema_in_practice(
        self, app_engine
    ) -> None:  # type: ignore[no-untyped-def]
        with app_engine.connect() as conn:
            can_create = conn.execute(
                text("SELECT has_schema_privilege('kaf_app', 'money', 'CREATE')")
            ).scalar_one()
        assert can_create is False, "kaf_app must not be able to create objects in money"
