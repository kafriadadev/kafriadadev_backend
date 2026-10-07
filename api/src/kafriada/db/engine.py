"""Database engines, one per privilege level.

Three connections, three PostgreSQL roles, three privilege levels. Which engine a
code path uses *is* its authority — there is no application-level check that
decides whether the ledger may be written, because the connection either has the
grant or it does not.

    app     ordinary requests. Reads and writes identity + ops. Reads money.
    money   payment confirmation and reconciliation only. The sole INSERT on the
            ledger. Obtained through ``money_transaction()``, which is
            deliberately awkward to reach by accident.
    read    reporting and the public read surface, pointed at the replica.

Sync engines with ``def`` endpoints, not async. FastAPI runs sync handlers in a
thread pool, which costs a little concurrency and buys a great deal: transaction
boundaries you can see, ``SELECT … FOR UPDATE`` that behaves the way the manual
says, and no risk of an accidental ``await`` inside a held lock. For a system
whose hardest problems are a contended counter row and a ledger that must balance,
that is the right trade. Revisit only with a measurement showing the thread pool
is the bottleneck.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from enum import StrEnum
from functools import lru_cache

import structlog
from sqlalchemy import Engine, create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker

from kafriada.settings import Settings, get_settings

log = structlog.get_logger(__name__)


class Role(StrEnum):
    APP = "kaf_app"
    MONEY = "kaf_money"
    READER = "kaf_reader"


def _build_engine(url: str, settings: Settings, *, role: Role, readonly: bool) -> Engine:
    engine = create_engine(
        url,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        # Recycle before a load balancer or PgBouncer silently drops an idle
        # connection, which otherwise surfaces as a random failure under low
        # traffic — the hardest kind of bug to reproduce.
        # Five minutes, not thirty: Supabase's pooler drops idle connections
        # sooner, and a connection it dropped silently is never reused.
        pool_recycle=300,
        pool_pre_ping=True,
        # Never log a query with its parameters. Those parameters are phone
        # numbers, password hashes and payment references.
        echo=False,
        future=True,
        connect_args={
            "application_name": f"kafriada-{role.value}",
            # Fail rather than hang a worker thread on a dead host. Generous
            # enough for a developer on a remote managed database; production
            # connects in milliseconds and never approaches it.
            "connect_timeout": settings.db_connect_timeout_seconds,
            # A pooled connection whose far end vanished without closing it
            # (an idle drop by the pooler, a network blip) must fail fast, or the
            # pre-ping waits minutes on a dead socket and every request queues
            # behind it. Seen 2026-10-06/07: readiness probes of 40 to 97 s.
            "keepalives": 1,
            "keepalives_idle": 30,
            "keepalives_interval": 10,
            "keepalives_count": 3,
            "tcp_user_timeout": 10_000,
        },
    )

    @event.listens_for(engine, "connect")
    def _set_session_guards(dbapi_connection, _record) -> None:  # type: ignore[no-untyped-def]
        """Belt and braces over the per-role settings applied in bootstrap-roles.sql.

        Those cluster-level settings are the real control; these are set again per
        connection so a database restored without them still behaves safely.
        """
        with dbapi_connection.cursor() as cur:
            cur.execute(f"SET statement_timeout = {settings.db_statement_timeout_ms}")
            cur.execute("SET idle_in_transaction_session_timeout = 30000")
            if readonly:
                cur.execute("SET default_transaction_read_only = on")

    return engine


@lru_cache(maxsize=1)
def app_engine() -> Engine:
    cfg = get_settings()
    return _build_engine(str(cfg.database_url_app), cfg, role=Role.APP, readonly=False)


@lru_cache(maxsize=1)
def money_engine() -> Engine:
    cfg = get_settings()
    return _build_engine(str(cfg.database_url_money), cfg, role=Role.MONEY, readonly=False)


@lru_cache(maxsize=1)
def read_engine() -> Engine:
    cfg = get_settings()
    return _build_engine(str(cfg.read_url), cfg, role=Role.READER, readonly=True)


AppSession = sessionmaker(bind=None, class_=Session, expire_on_commit=False, future=True)


@contextmanager
def transaction() -> Iterator[Session]:
    """A read-write unit of work for ordinary requests.

    Commits on success, rolls back on any exception. Nothing inside should do
    network I/O or password hashing: this may hold the KUID counter row, and
    every registration in the state queues behind it.
    """
    session = Session(bind=app_engine(), expire_on_commit=False, future=True)
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@contextmanager
def money_transaction(*, reason: str) -> Iterator[Session]:
    """A unit of work that may write the ledger.

    ``reason`` is required and logged. It exists so this connection cannot be
    opened absent-mindedly: every use appears in the log with a stated purpose,
    and a grep for ``money_transaction`` lists every place in the codebase that
    can touch money — which should stay small enough to read in one sitting.
    """
    log.info("money_transaction_opened", reason=reason)
    session = Session(bind=money_engine(), expire_on_commit=False, future=True)
    try:
        yield session
        session.commit()
        log.info("money_transaction_committed", reason=reason)
    except Exception:
        session.rollback()
        log.warning("money_transaction_rolled_back", reason=reason)
        raise
    finally:
        session.close()


@contextmanager
def read_only() -> Iterator[Session]:
    """Reporting and public reads, against the replica where one exists.

    A heavy report must never contend with the write path. The connection is
    forced read-only, so a mistyped query cannot modify anything even if it were
    somehow pointed at the primary.
    """
    session = Session(bind=read_engine(), expire_on_commit=False, future=True)
    try:
        yield session
    finally:
        session.close()


def check_connectivity() -> dict[str, bool]:
    """Readiness probe. Internal only — never expose which role failed publicly."""
    results: dict[str, bool] = {}
    for name, engine_factory in (
        ("app", app_engine),
        ("money", money_engine),
        ("read", read_engine),
    ):
        try:
            with engine_factory().connect() as conn:
                conn.execute(text("SELECT 1"))
            results[name] = True
        except Exception as exc:
            # A readiness probe reports, it does not raise. The error type is
            # logged; the message is not, because a connection error can carry
            # the host and user from the DSN.
            log.error("db_unreachable", pool=name, error_type=type(exc).__name__)
            results[name] = False
    return results
