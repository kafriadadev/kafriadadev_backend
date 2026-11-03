"""The API can run the background jobs itself, for a host with no separate worker.

Found 2026-11-03: the deployed site queued every code and receipt, and nothing sent
them, because the host's free plan runs no background worker. With
``RUN_JOBS_IN_PROCESS`` the API starts the same scheduler on a thread and stops it on
shutdown. On by default when deployed; off locally and in CI, so tests and local
runs never send anything.
"""

from __future__ import annotations

import threading

import pytest
from fastapi.testclient import TestClient

from kafriada import jobs
from kafriada.main import create_app
from kafriada.settings import Environment, get_settings


def _app(monkeypatch: pytest.MonkeyPatch, *, on: bool | None) -> tuple[TestClient, dict[str, object]]:
    seen: dict[str, object] = {}

    def run_forever(jobs_: list[jobs.Job], *, tick: float, stopping: threading.Event) -> None:
        seen["jobs"] = [j.name for j in jobs_]
        seen["stopping"] = stopping
        stopping.wait(5)

    monkeypatch.setattr(jobs, "run_forever", run_forever)
    cfg = get_settings().model_copy(update={"run_jobs_in_process": on})
    return TestClient(create_app(cfg)), seen


def test_the_api_runs_the_jobs_when_asked_and_stops_them_on_shutdown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, seen = _app(monkeypatch, on=True)
    with client:
        assert client.get("/healthz").status_code == 200
        assert "outbox" in seen["jobs"]  # type: ignore[operator]
        stopping = seen["stopping"]
        assert isinstance(stopping, threading.Event) and not stopping.is_set()
    assert stopping.is_set(), "shutdown stops the runner"


def test_deployed_environments_run_the_jobs_unless_told_not_to() -> None:
    cfg = get_settings().model_copy(update={"run_jobs_in_process": None})
    assert cfg.model_copy(update={"environment": Environment.LOCAL}).jobs_in_process is False
    assert cfg.model_copy(update={"environment": Environment.STAGING}).jobs_in_process is True
    assert cfg.model_copy(update={"environment": Environment.PRODUCTION}).jobs_in_process is True
    off = cfg.model_copy(update={"environment": Environment.PRODUCTION, "run_jobs_in_process": False})
    assert off.jobs_in_process is False


def test_the_api_runs_no_jobs_locally_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    client, seen = _app(monkeypatch, on=None)
    with client:
        assert client.get("/healthz").status_code == 200
    assert seen == {}
