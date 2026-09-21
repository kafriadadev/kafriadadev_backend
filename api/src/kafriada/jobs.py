"""The scheduler: one small process that runs every background job on its own clock.

    python -m kafriada.jobs                      # run forever, each job when it is due
    python -m kafriada.jobs --once               # run every job once now, then exit
    python -m kafriada.jobs --once --only integrity,reconcile

Scheduling is deliberately boring: a loop and a table, no broker. The pilot's whole
workload is a few messages a minute and a handful of hourly sweeps; the honest choice is
the smallest thing that cannot lose work. Every job here is idempotent and safe to run
twice, so the worst a mistake in scheduling can do is a wasted pass — never a doubled
ledger line or a lost message.

**"When did this last run?" lives in the database**, in ``ops.job_runs``, not in memory.
A restart does not repeat an hourly job, and two runners started by mistake do not both
run it: each takes a Postgres advisory lock for the job's name, then looks at the table
*again* under the lock, and skips if someone finished it a moment ago.

**Frequent jobs are not recorded.** Draining the outbox and re-encoding photographs run
every few seconds and are covered by their own row-level locks (``FOR UPDATE SKIP
LOCKED``), so a table row per pass would be noise. Everything that runs on the scale of
hours — reconciliation, expiry, sweeps, the nightly integrity check — writes one row when
it finishes, whether it succeeded or not, so "the integrity check is green" is a query.

**A failing job never stops the others.** Each runs in its own try/except; the failure is
logged at error level and recorded (``ok = false``), and the loop moves on. ``--once``
exits non-zero if any recorded job was not clean, so cron or CI can page on it.
"""

from __future__ import annotations

import argparse
import signal
import sys
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta
from types import FrameType
from typing import Any

import structlog
from sqlalchemy import text

from kafriada import integrity
from kafriada.clock import NIGERIA_TZ, now_utc
from kafriada.contexts.access import ratelimit
from kafriada.contexts.access import service as access
from kafriada.contexts.media import service as media
from kafriada.contexts.media.store import build_store
from kafriada.contexts.payments import reconcile
from kafriada.db.engine import app_engine
from kafriada.main import configure_logging
from kafriada.outbox import service as outbox
from kafriada.outbox.providers import build_sender
from kafriada.settings import MediaStoreKind, SmsProvider, get_settings

log = structlog.get_logger(__name__)

Summary = dict[str, Any]

HOUR = 3_600.0
DAY = 86_400.0


@dataclass(frozen=True, slots=True)
class Job:
    name: str
    run: Callable[[], Summary]
    # How often, in seconds — or, for a nightly job, at what hour (Nigeria time) it
    # first becomes due each day.
    every: float = HOUR
    daily_at_hour: int | None = None
    # Write a row to ops.job_runs. Off for the every-few-seconds workers.
    record: bool = True
    # Decides whether a finished run counts as clean. Default: it did not raise.
    clean: Callable[[Summary], bool] = lambda _summary: True


@dataclass(frozen=True, slots=True)
class Outcome:
    job: str
    ran: bool
    ok: bool = True
    summary: Summary | None = None


# ---------------------------------------------------------------------------
# The jobs
# ---------------------------------------------------------------------------
def _drain_outbox() -> Summary:
    cfg = get_settings()
    if cfg.sms_provider is SmsProvider.NONE:
        return {"skipped": "no SMS provider is configured"}
    result = outbox.drain(limit=20, sender=build_sender(cfg))
    return {"sent": result.sent, "retried": result.retried, "failed": result.failed}


def _process_media() -> Summary:
    if get_settings().media_store is MediaStoreKind.NONE:
        return {"skipped": "no media store is configured"}
    return {"ready": media.process_pending(20, store=build_store())}


def _integrity() -> Summary:
    findings = integrity.run_all()
    return {
        "findings": len(findings),
        "detail": [f"{f.check}: {f.detail}" for f in findings[:20]],  # what a pager needs first
    }


def build_jobs() -> list[Job]:
    return [
        Job("outbox", _drain_outbox, every=5.0, record=False),
        Job("media", _process_media, every=10.0, record=False),
        Job("reconcile", lambda: reconcile.reconcile().summary(), every=10 * 60.0),
        Job("expire", lambda: reconcile.expire_stale().summary(), every=HOUR),
        Job("sessions", lambda: {"removed": access.sweep_sessions()}, every=HOUR),
        Job("rate_counters", lambda: {"removed": ratelimit.prune()}, every=HOUR),
        Job("documents", lambda: {"purged": media.purge_expired_documents(store=build_store())}
            if get_settings().media_store is not MediaStoreKind.NONE
            else {"skipped": "no media store is configured"}, every=HOUR),
        Job("outbox_retention", lambda: {"removed": outbox.prune_delivered()},
            every=DAY, daily_at_hour=3),
        Job("integrity", _integrity, every=DAY, daily_at_hour=2,
            clean=lambda summary: summary.get("findings", 1) == 0),
    ]


# ---------------------------------------------------------------------------
# Scheduling
# ---------------------------------------------------------------------------
def is_due(job: Job, last: datetime | None, now: datetime) -> bool:
    """Is it time? A pure function of the clock and the job's last finish."""
    if job.daily_at_hour is not None:
        local = now.astimezone(NIGERIA_TZ)
        return local.hour >= job.daily_at_hour and (
            last is None or last.astimezone(NIGERIA_TZ).date() < local.date()
        )
    return last is None or (now - last) >= timedelta(seconds=job.every)


def last_finished(name: str) -> datetime | None:
    with app_engine().connect() as conn:
        found = conn.execute(
            text("SELECT max(finished_at) FROM ops.job_runs WHERE job = :j"), {"j": name}
        ).scalar_one()
        conn.rollback()  # a read: nothing to keep, and no transaction left open
    return found  # type: ignore[no-any-return]


@contextmanager
def advisory_lock(name: str) -> Iterator[bool]:
    """Hold a Postgres advisory lock named for the job, or say we could not get it.

    Session-level, so the lock outlives the transaction that took it — which matters,
    because the engine kills a session left idle *in a transaction* after 30 seconds and a
    job can run for longer. The lock is taken, the transaction is committed straight away,
    and the connection then sits idle outside any transaction until the job is done. It must
    be released explicitly before the connection returns to the pool.
    """
    key = {"n": f"kafriada.jobs.{name}"}
    conn = app_engine().connect()
    try:
        got = bool(conn.execute(text("SELECT pg_try_advisory_lock(hashtext(:n))"), key).scalar_one())
        conn.commit()
        try:
            yield got
        finally:
            if got:
                conn.execute(text("SELECT pg_advisory_unlock(hashtext(:n))"), key)
                conn.commit()
    finally:
        conn.close()


def _record(job: Job, started: datetime, ok: bool, summary: Summary) -> None:
    import json

    with app_engine().begin() as conn:
        conn.execute(
            text(
                "INSERT INTO ops.job_runs (job, started_at, ok, summary) "
                "VALUES (:job, :started, :ok, CAST(:summary AS jsonb))"
            ),
            {"job": job.name, "started": started, "ok": ok, "summary": json.dumps(summary, default=str)},
        )


def _execute(job: Job) -> Outcome:
    started = now_utc()
    try:
        summary = job.run()
        ok = job.clean(summary)
    except Exception as exc:
        # One job failing must not stop the rest, and must not be quiet.
        summary = {"error": f"{type(exc).__name__}: {str(exc)[:200]}"}
        ok = False
        log.error("job_failed", job=job.name, error_type=type(exc).__name__, exc_info=True)
    if job.record:
        try:
            _record(job, started, ok, summary)
        except Exception:
            log.error("job_run_not_recorded", job=job.name, exc_info=True)
    if not ok:
        log.error("job_not_clean", job=job.name, summary=summary)
    return Outcome(job.name, True, ok, summary)


def run_job(job: Job, *, force: bool = False, now: datetime | None = None) -> Outcome:
    """Run one job if it is due (or ``force``), exactly once across all runners."""
    now = now or now_utc()
    if not job.record:
        # Every few seconds, and safe to overlap by construction: no lock, no record.
        return _execute(job)

    if not force and not is_due(job, last_finished(job.name), now):
        return Outcome(job.name, False)
    with advisory_lock(job.name) as got:
        if not got:
            return Outcome(job.name, False)
        # Look again under the lock: another runner may have finished it a moment ago.
        if not force and not is_due(job, last_finished(job.name), now_utc()):
            return Outcome(job.name, False)
        return _execute(job)


_stopping = threading.Event()


def _stop(_signum: int, _frame: FrameType | None) -> None:
    _stopping.set()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run KAFRIADA's background jobs.")
    parser.add_argument("--once", action="store_true", help="run every selected job now, then exit")
    parser.add_argument("--only", help="comma-separated job names")
    parser.add_argument("--tick", type=float, default=5.0, help="seconds between passes")
    args = parser.parse_args(argv)

    configure_logging(get_settings())
    jobs = build_jobs()
    if args.only:
        wanted = {n.strip() for n in args.only.split(",")}
        unknown = wanted - {j.name for j in jobs}
        if unknown:
            print(f"unknown job(s): {', '.join(sorted(unknown))}", file=sys.stderr)  # noqa: T201
            return 2
        jobs = [j for j in jobs if j.name in wanted]

    if args.once:
        outcomes = [run_job(j, force=True) for j in jobs]
        for o in outcomes:
            print(f"{'ok  ' if o.ok else 'FAIL'}  {o.job:17} {o.summary}")  # noqa: T201
        return 0 if all(o.ok for o in outcomes) else 1

    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)
    log.info("jobs_started", jobs=[j.name for j in jobs])
    frequent: dict[str, float] = {}  # unrecorded jobs keep their pace in memory
    while not _stopping.is_set():
        for job in jobs:
            if _stopping.is_set():
                break
            if not job.record:
                if time.monotonic() - frequent.get(job.name, -1e9) < job.every:
                    continue
                frequent[job.name] = time.monotonic()
            run_job(job)
        _stopping.wait(args.tick)
    log.info("jobs_stopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
