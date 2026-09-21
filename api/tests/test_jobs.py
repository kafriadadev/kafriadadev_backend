# ruff: noqa: S608  (the SQL below interpolates the test's own interval literals, never input)
"""The scheduler and the housekeeping it runs.

What is proved here:
  - when a job is due is a pure function of the clock and its last finish — including the
    nightly ones, which fire at their Nigeria-time hour, once a day, and not before
  - a recorded job leaves exactly one row, clean or not; asked again inside its interval
    it does nothing; a second runner holding the same job's lock skips it
  - a job that raises is recorded as failed, logged at error, and does not stop the rest
  - the record of runs cannot be edited or deleted by anyone, the owner included
  - the sweeps remove only what is dead long enough and never anything still live or waiting
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError

from kafriada import jobs
from kafriada.clock import NIGERIA_TZ
from kafriada.contexts.access import service as access
from kafriada.jobs import Job, is_due, run_job
from kafriada.outbox import service as outbox
from tests._access_helpers import make_user, sql
from tests._payment_helpers import LogRecorder, record_logs

pytestmark = [
    pytest.mark.db,
    pytest.mark.skipif(
        not (os.environ.get("DATABASE_URL_APP") and os.environ.get("DATABASE_URL_MIGRATE")),
        reason="needs DATABASE_URL_APP and DATABASE_URL_MIGRATE",
    ),
]


def unique_job(**kw: object) -> Job:
    name = f"test-{uuid4().hex[:10]}"
    return Job(name, kw.pop("run", lambda: {"did": "it"}), **kw)  # type: ignore[arg-type]


def runs_of(job: Job) -> list[dict[str, object]]:
    return sql("SELECT ok, summary FROM ops.job_runs WHERE job = :j ORDER BY id", j=job.name)


class TestWhenAJobIsDue:
    NOW = datetime(2026, 9, 21, 12, 0, tzinfo=UTC)

    def test_a_job_that_never_ran_is_due(self) -> None:
        assert is_due(Job("x", dict), None, self.NOW)

    def test_an_interval_job_is_due_exactly_when_the_interval_has_passed(self) -> None:
        job = Job("x", dict, every=3_600)
        assert not is_due(job, self.NOW - timedelta(seconds=3_599), self.NOW)
        assert is_due(job, self.NOW - timedelta(seconds=3_600), self.NOW)

    def test_a_nightly_job_waits_for_its_hour_in_nigeria_not_utc(self) -> None:
        job = Job("x", dict, every=86_400, daily_at_hour=2)
        yesterday = datetime(2026, 9, 20, 2, 5, tzinfo=NIGERIA_TZ)
        # 00:59 in Nigeria is 23:59 UTC the day before: not yet.
        assert not is_due(job, yesterday, datetime(2026, 9, 21, 0, 59, tzinfo=NIGERIA_TZ))
        assert not is_due(job, yesterday, datetime(2026, 9, 21, 1, 59, tzinfo=NIGERIA_TZ))
        assert is_due(job, yesterday, datetime(2026, 9, 21, 2, 0, tzinfo=NIGERIA_TZ))
        assert is_due(job, None, datetime(2026, 9, 21, 2, 0, tzinfo=NIGERIA_TZ))

    def test_a_nightly_job_runs_once_a_day_however_late_it_is(self) -> None:
        job = Job("x", dict, every=86_400, daily_at_hour=2)
        ran = datetime(2026, 9, 21, 2, 3, tzinfo=NIGERIA_TZ)
        assert not is_due(job, ran, datetime(2026, 9, 21, 23, 59, tzinfo=NIGERIA_TZ))
        assert is_due(job, ran, datetime(2026, 9, 22, 2, 0, tzinfo=NIGERIA_TZ))

    def test_a_restart_late_at_night_still_catches_up_the_missed_run(self) -> None:
        job = Job("x", dict, every=86_400, daily_at_hour=2)
        last_night = datetime(2026, 9, 20, 2, 3, tzinfo=NIGERIA_TZ)
        assert is_due(job, last_night, datetime(2026, 9, 21, 15, 0, tzinfo=NIGERIA_TZ))


class TestRunningJobs:
    def test_a_recorded_job_leaves_one_row_and_is_not_repeated_inside_its_interval(self) -> None:
        job = unique_job(every=3_600)
        first = run_job(job)
        again = run_job(job)
        assert first.ran and first.ok and not again.ran
        assert runs_of(job) == [{"ok": True, "summary": {"did": "it"}}]

    def test_force_runs_it_anyway(self) -> None:
        job = unique_job(every=3_600)
        run_job(job)
        run_job(job, force=True)
        assert len(runs_of(job)) == 2

    def test_a_job_that_raises_is_recorded_as_failed_logged_and_contained(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        logs = record_logs(monkeypatch, jobs)

        def boom() -> dict[str, object]:
            raise RuntimeError("the sky fell")

        job = unique_job(run=boom)
        outcome = run_job(job)  # does not raise

        assert outcome.ran and not outcome.ok
        (row,) = runs_of(job)
        assert row["ok"] is False and "RuntimeError: the sky fell" in str(row["summary"])
        assert "job_failed" in logs.errors() and "job_not_clean" in logs.errors()

    def test_a_run_that_finishes_but_is_not_clean_is_recorded_and_alarmed(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        logs = record_logs(monkeypatch, jobs)
        job = unique_job(run=lambda: {"findings": 3}, clean=lambda s: s["findings"] == 0)
        assert not run_job(job).ok
        assert runs_of(job) == [{"ok": False, "summary": {"findings": 3}}]
        assert logs.errors() == ["job_not_clean"]

    def test_a_second_runner_holding_the_lock_makes_this_one_skip(self) -> None:
        job = unique_job()
        with jobs.advisory_lock(job.name) as got:
            assert got is True
            outcome = run_job(job)  # another runner is mid-job
            assert not outcome.ran
        assert runs_of(job) == []
        assert run_job(job).ran  # released, so it runs now

    def test_the_lock_is_released_even_when_the_job_raises(self) -> None:
        def boom() -> dict[str, object]:
            raise RuntimeError("x")

        job = unique_job(run=boom)
        run_job(job)
        with jobs.advisory_lock(job.name) as got:
            assert got is True

    def test_two_runners_started_together_run_a_job_once(self) -> None:
        from concurrent.futures import ThreadPoolExecutor

        counter = {"n": 0}

        def slow() -> dict[str, object]:
            import time

            counter["n"] += 1
            time.sleep(0.3)
            return {}

        job = unique_job(run=slow, every=3_600)
        with ThreadPoolExecutor(max_workers=4) as pool:
            outcomes = list(pool.map(lambda _: run_job(job), range(4)))
        assert sum(o.ran for o in outcomes) == 1 and counter["n"] == 1
        assert len(runs_of(job)) == 1

    def test_the_every_few_seconds_jobs_are_not_recorded(self) -> None:
        before = sql("SELECT count(*) AS n FROM ops.job_runs")[0]["n"]
        job = unique_job(record=False, every=5)
        assert run_job(job).ran and run_job(job).ran
        assert sql("SELECT count(*) AS n FROM ops.job_runs")[0]["n"] == before

    def test_the_real_job_list_is_what_the_build_plan_asks_for(self) -> None:
        names = {j.name for j in jobs.build_jobs()}
        assert {"reconcile", "expire", "integrity", "sessions", "outbox_retention", "outbox",
                "media", "documents", "rate_counters"} <= names
        by_name = {j.name: j for j in jobs.build_jobs()}
        assert by_name["integrity"].daily_at_hour == 2 and by_name["reconcile"].every == 600
        assert by_name["outbox"].record is False and by_name["integrity"].record is True

    def test_once_with_an_unknown_job_name_is_refused(self, capsys: pytest.CaptureFixture[str]) -> None:
        assert jobs.main(["--once", "--only", "no-such-job"]) == 2
        assert "no-such-job" in capsys.readouterr().err

    def test_once_reports_a_dirty_run_with_a_non_zero_exit_for_cron_to_page_on(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        dirty = unique_job(run=lambda: {"findings": 1}, clean=lambda s: False)
        monkeypatch.setattr(jobs, "build_jobs", lambda: [dirty])
        assert jobs.main(["--once"]) == 1
        clean = unique_job()
        monkeypatch.setattr(jobs, "build_jobs", lambda: [clean])
        assert jobs.main(["--once"]) == 0


class TestTheRecordOfRunsIsEvidence:
    @pytest.mark.parametrize("role", ["APP", "MIGRATE"])
    @pytest.mark.parametrize(
        "statement",
        ["UPDATE ops.job_runs SET ok = true", "DELETE FROM ops.job_runs"],
    )
    def test_nobody_can_edit_or_delete_a_run(self, role: str, statement: str) -> None:
        run_job(unique_job())
        engine = create_engine(os.environ[f"DATABASE_URL_{role}"], future=True)
        try:
            with pytest.raises(DBAPIError) as caught, engine.begin() as conn:
                conn.execute(text(statement))
        finally:
            engine.dispose()
        assert "permission denied" in str(caught.value) or "append-only" in str(caught.value)


class TestSweeps:
    def _session(self, user_id: object, **times: str) -> str:
        sid = str(uuid4())
        sql(
            "INSERT INTO ops.sessions (id, user_id, token_hash, issued_at, idle_expires_at, "
            "absolute_expires_at, revoked_at, idle_seconds) VALUES (:id, :u, :h, now() - interval '200 days', "
            f"now() + interval '{times['idle']}', now() + interval '{times['absolute']}', "
            f"{times.get('revoked', 'NULL')}, 86400)",
            id=sid, u=user_id, h=uuid4().hex + uuid4().hex,
        )
        return sid

    def test_only_long_dead_sessions_are_swept(self) -> None:
        user_id, _ = make_user("Sweep")
        live = self._session(user_id, idle="1 day", absolute="30 days")
        just_expired = self._session(user_id, idle="-1 day", absolute="30 days")
        long_dead_idle = self._session(user_id, idle="-40 days", absolute="30 days")
        long_dead_absolute = self._session(user_id, idle="10 days", absolute="-40 days")
        revoked_long_ago = self._session(user_id, idle="1 day", absolute="30 days",
                                         revoked="now() - interval '40 days'")
        revoked_just_now = self._session(user_id, idle="1 day", absolute="30 days", revoked="now()")

        access.sweep_sessions()

        left = {str(r["id"]) for r in sql("SELECT id FROM ops.sessions WHERE user_id = :u", u=user_id)}
        assert left == {live, just_expired, revoked_just_now}
        assert not left & {long_dead_idle, long_dead_absolute, revoked_long_ago}

    def test_a_swept_session_was_already_refused(self) -> None:
        user_id, _ = make_user("Dead")
        token = access.issue_session(user_id, method="test").token
        sql("UPDATE ops.sessions SET idle_expires_at = now() - interval '40 days' WHERE user_id = :u", u=user_id)
        assert access.authenticate(token) is None  # dead before the sweep...
        access.sweep_sessions()
        assert sql("SELECT 1 FROM ops.sessions WHERE user_id = :u", u=user_id) == []
        assert access.authenticate(token) is None  # ...and after

    def _outbox(self, **cols: str) -> int:
        row = sql(
            "INSERT INTO ops.outbox (event_type, payload, processed_at, failed_at, created_at) "
            "VALUES ('sms.requested', '{\"to\": \"+2340000000000\", \"body\": \"x\", \"purpose\": \"test\"}'::jsonb, "
            f"{cols.get('processed', 'NULL')}, {cols.get('failed', 'NULL')}, now() - interval '200 days') "
            "RETURNING id"
        )
        return int(row[0]["id"])  # type: ignore[call-overload]

    def test_outbox_retention_keeps_what_is_waiting_and_what_is_recent(self) -> None:
        old_sent = self._outbox(processed="now() - interval '40 days'")
        recent_sent = self._outbox(processed="now() - interval '5 days'")
        old_failed = self._outbox(failed="now() - interval '100 days'")
        recent_failed = self._outbox(failed="now() - interval '40 days'")
        ancient_waiting = self._outbox()  # never sent, however old: it is still owed

        outbox.prune_delivered()

        ids = [old_sent, recent_sent, old_failed, recent_failed, ancient_waiting]
        left = {int(r["id"]) for r in sql("SELECT id FROM ops.outbox WHERE id = ANY(:ids)", ids=ids)}  # type: ignore[call-overload]
        # The row still waiting is a real message as far as the worker is concerned; take
        # it out of the queue so it cannot be picked up by the outbox tests that share it.
        sql("DELETE FROM ops.outbox WHERE id = :i", i=ancient_waiting)
        assert left == {recent_sent, recent_failed, ancient_waiting}


def test_the_recorder_used_for_logs_is_a_logger() -> None:
    assert isinstance(LogRecorder().errors(), list)
