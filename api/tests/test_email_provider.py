"""The Resend adapter and the settings that choose it. No database, no network.

What is proved here:
  - the request carries our from address, recipient, subject and body, and the
    key goes in the Authorization header, never the body
  - a slow or broken Resend is a *transient* failure, a rejection is *permanent*
  - the choice of sender fails loudly when misconfigured: resend without a key,
    console anywhere but local
"""

from __future__ import annotations

import httpx
import pytest
from pydantic import ValidationError

from kafriada.outbox import email_providers
from kafriada.outbox.email_providers import (
    ConsoleSender,
    EmailError,
    NoSender,
    NotConfigured,
    ResendSender,
    build_sender,
)
from tests.test_settings_refuses_insecure_config import build, production

KEY = "re_" + "a" * 30


def settings(**over: object):  # type: ignore[no-untyped-def]
    return build(email_provider="resend", resend_api_key=KEY, **over)


def respond(monkeypatch: pytest.MonkeyPatch, response: httpx.Response | Exception) -> list[dict]:  # type: ignore[type-arg]
    sent: list[dict] = []  # type: ignore[type-arg]

    def post(url: str, **kwargs: object) -> httpx.Response:
        sent.append({"url": url, **kwargs})
        if isinstance(response, Exception):
            raise response
        return response

    monkeypatch.setattr(email_providers.httpx, "post", post)
    return sent


def ok(message_id: str = "abc-123") -> httpx.Response:
    return httpx.Response(200, json={"id": message_id})


class TestResendAdapter:
    def test_it_sends_from_to_subject_and_body_with_the_key_in_the_header(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        sent = respond(monkeypatch, ok())
        result = ResendSender(settings(email_from="alerts@badellafarmandranch.site")).send(
            to="athlete@example.com", subject="You're verified", body="Congratulations."
        )

        assert result.provider == "resend"
        assert result.provider_message_id == "abc-123"
        (call,) = sent
        assert call["url"] == "https://api.resend.com/emails"
        assert call["json"] == {
            "from": "alerts@badellafarmandranch.site",
            "to": ["athlete@example.com"],
            "subject": "You're verified",
            "text": "Congratulations.",
        }
        assert call["headers"] == {"authorization": f"Bearer {KEY}"}

    def test_html_is_included_only_when_given(self, monkeypatch: pytest.MonkeyPatch) -> None:
        sent = respond(monkeypatch, ok())
        ResendSender(settings()).send(
            to="a@b.test", subject="s", body="plain text", html="<p>rich text</p>",
        )
        (call,) = sent
        assert call["json"]["text"] == "plain text"
        assert call["json"]["html"] == "<p>rich text</p>"

    def test_a_network_failure_is_transient(self, monkeypatch: pytest.MonkeyPatch) -> None:
        respond(monkeypatch, httpx.ConnectTimeout("slow"))
        with pytest.raises(EmailError) as exc:
            ResendSender(settings()).send(to="a@b.test", subject="s", body="b")
        assert exc.value.transient

    @pytest.mark.parametrize("status", [500, 502, 429])
    def test_5xx_and_429_are_transient(
        self, monkeypatch: pytest.MonkeyPatch, status: int
    ) -> None:
        respond(monkeypatch, httpx.Response(status, json={"message": "slow down"}))
        with pytest.raises(EmailError) as exc:
            ResendSender(settings()).send(to="a@b.test", subject="s", body="b")
        assert exc.value.transient

    def test_a_rejected_address_is_permanent(self, monkeypatch: pytest.MonkeyPatch) -> None:
        respond(monkeypatch, httpx.Response(422, json={"message": "invalid `to` field"}))
        with pytest.raises(EmailError) as exc:
            ResendSender(settings()).send(to="not-an-email", subject="s", body="b")
        assert not exc.value.transient
        assert "invalid" in exc.value.message

    def test_it_refuses_to_construct_without_a_key(self) -> None:
        cfg = build(email_provider="none")
        with pytest.raises(NotConfigured):
            ResendSender(cfg)


class TestSenderSelection:
    def test_none_queues_without_sending(self) -> None:
        assert isinstance(build_sender(build(email_provider="none")), NoSender)

    def test_console_prints_instead_of_sending(self, capsys: pytest.CaptureFixture[str]) -> None:
        sender = build_sender(build(email_provider="console"))
        assert isinstance(sender, ConsoleSender)
        result = sender.send(to="a@b.test", subject="hi", body="there")
        assert result.provider == "console"
        assert "a@b.test" in capsys.readouterr().out

    def test_resend_is_selected_when_configured(self) -> None:
        assert isinstance(build_sender(settings()), ResendSender)


class TestConfigChoicesFailLoudly:
    def test_resend_without_a_key_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="resend_api_key is required"):
            build(email_provider="resend")

    def test_console_is_refused_in_production(self) -> None:
        with pytest.raises(ValidationError, match="email_provider must not be 'console'"):
            production(email_provider="console")

    def test_resend_is_accepted_in_production(self) -> None:
        assert production(email_provider="resend", resend_api_key=KEY).email_provider == "resend"
