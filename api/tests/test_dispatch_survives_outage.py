"""The outbox dispatcher outlives a dropped database link.

Found 2026-10-08: one failed DNS lookup for the database host raised out of the loop and
stopped the worker, so every code queued afterwards waited until someone noticed. Nothing
is sent or marked when the database cannot be reached, so the loop waits and tries again.
A run with --once still reports the failure.
"""

from __future__ import annotations

import pytest
from sqlalchemy.exc import InternalError, OperationalError

from kafriada.outbox import dispatch, email_providers, service
from kafriada.settings import EmailProvider, SmsProvider, get_settings


def _unreachable() -> OperationalError:
    return OperationalError("SELECT 1", {}, Exception("failed to resolve host"))


@pytest.fixture
def quiet(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    cfg = get_settings().model_copy(update={"sms_provider": SmsProvider.CONSOLE, "email_provider": EmailProvider.NONE})
    monkeypatch.setattr(dispatch, "get_settings", lambda: cfg)
    monkeypatch.setattr(dispatch, "build_sender", lambda _cfg=None: type("Sms", (), {"name": "test"})())
    monkeypatch.setattr(email_providers, "build_sender", lambda _cfg=None: email_providers.NoSender())
    monkeypatch.setattr(dispatch.ratelimit, "prune", lambda: 0)
    slept: list[float] = []
    monkeypatch.setattr(dispatch.time, "sleep", slept.append)
    monkeypatch.setattr(dispatch, "_stopping", False)
    return slept


def test_the_loop_waits_and_tries_again(monkeypatch: pytest.MonkeyPatch, quiet: list[float]) -> None:
    calls = {"n": 0}

    def drain(**_kw: object) -> service.DrainResult:
        calls["n"] += 1
        if calls["n"] == 1:
            raise _unreachable()
        monkeypatch.setattr(dispatch, "_stopping", True)
        return service.DrainResult(sent=1, retried=0, failed=0)

    monkeypatch.setattr(service, "drain", drain)
    assert dispatch.main([]) == 0
    assert calls["n"] == 2, "the second pass ran after the outage"
    assert quiet and quiet[0] == 15


def test_a_connection_closed_mid_pass_does_not_stop_it(monkeypatch: pytest.MonkeyPatch, quiet: list[float]) -> None:
    """Found 2026-10-09: a slow send outlived the database's idle-transaction timeout."""
    calls = {"n": 0}

    def drain(**_kw: object) -> service.DrainResult:
        calls["n"] += 1
        if calls["n"] == 1:
            raise InternalError("UPDATE ops.outbox", {}, Exception("idle-in-transaction timeout"))
        monkeypatch.setattr(dispatch, "_stopping", True)
        return service.DrainResult(sent=0, retried=0, failed=0)

    monkeypatch.setattr(service, "drain", drain)
    assert dispatch.main([]) == 0
    assert calls["n"] == 2


def test_a_single_pass_still_reports_it(monkeypatch: pytest.MonkeyPatch, quiet: list[float]) -> None:
    def drain(**_kw: object) -> service.DrainResult:
        raise _unreachable()

    monkeypatch.setattr(service, "drain", drain)
    with pytest.raises(OperationalError):
        dispatch.main(["--once"])
