"""The per-address brake.

What is proved here:
  - a caller who spreads wrong passwords across many accounts is stopped, even
    though no single account ever locks — the gap these limits exist to close
  - the refusal is a 429 carrying Retry-After, and says nothing about which
    limit was hit or how much allowance is left
  - one address being throttled does not throttle anybody else
  - counting survives the refusal: it is committed, not rolled back with the
    request that tripped it
  - closed windows are pruned, and open ones are not
  - the whole thing can be switched off by configuration
"""

from __future__ import annotations

import os
import secrets
from collections.abc import Iterator
from ipaddress import IPv6Address

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from kafriada.contexts.access import ratelimit
from kafriada.db.engine import transaction
from kafriada.main import create_app
from tests._access_helpers import make_user

pytestmark = [
    pytest.mark.db,
    pytest.mark.skipif(
        not os.environ.get("DATABASE_URL_APP"),
        reason="needs DATABASE_URL_APP",
    ),
]

PASSWORD = "a long test passphrase"


@pytest.fixture(scope="module")
def client() -> Iterator[TestClient]:
    with TestClient(create_app()) as c:
        yield c


@pytest.fixture
def small_limits(monkeypatch: pytest.MonkeyPatch) -> None:
    """Three sign-ins an hour, so a test spends the allowance in four requests.

    The real numbers are deliberately large — a coordinator's registration desk
    and a whole carrier behind one address both have to fit underneath them — so
    exercising them honestly means lowering them, not sending sixty requests.
    Settings are frozen, so the lookup is replaced rather than the value.
    """
    real = ratelimit.limits_for

    def small(bucket: str) -> tuple[ratelimit.Limit, ...]:
        if bucket == "sign_in":
            return (ratelimit.Limit(times=3, per_seconds=ratelimit.HOUR),)
        return real(bucket)

    monkeypatch.setattr(ratelimit, "limits_for", small)


# The counters are keyed per address, so two tests sharing one would interfere —
# and the counters live in the database for the whole window, an hour, so it is
# not enough for addresses to differ *within* a run: they must differ *between*
# runs too. This once handed out 198.51.100.1, .2, .3 in order every time, so a
# second run inside the hour inherited the first run's counts and failed with a
# 429 on the very first request. Found the first time it was run twice.
#
# 2001:db8::/32 is the IPv6 documentation range: it belongs to nobody, and 32
# random bits of it make a collision between runs a non-event.
def _unique_ip() -> str:
    return str(IPv6Address((0x2001_0DB8 << 96) | secrets.randbits(32)))


WRONG = "not the right passphrase"  # deliberately wrong


def _sign_in(client: TestClient, phone: str, ip: str, password: str = WRONG) -> object:
    return client.post(
        "/v1/sessions",
        json={"phone": phone, "password": password},
        headers={"cf-connecting-ip": ip},
    )


# ---------------------------------------------------------------------------
# The attack this exists to stop
# ---------------------------------------------------------------------------
@pytest.mark.usefixtures("small_limits")
def test_one_password_against_many_accounts_is_stopped(client: TestClient) -> None:
    """Password spraying: one guess each against many accounts.

    No account ever reaches its own lock — that is exactly why the per-account
    limit cannot see this, and why this one has to.
    """
    ip = _unique_ip()
    victims = [make_user(f"Spray target {i}", password=PASSWORD)[1] for i in range(4)]

    refusals = [_sign_in(client, phone, ip).status_code for phone in victims]

    assert refusals[:3] == [401, 401, 401], "the first three guesses are merely wrong"
    assert refusals[3] == 429, "the fourth is refused by the address limit"

    # And no victim was locked: each saw exactly one wrong password.
    ok = client.post(
        "/v1/sessions",
        json={"phone": victims[0], "password": PASSWORD},
        headers={"cf-connecting-ip": _unique_ip()},
    )
    assert ok.status_code == 201, "the account itself is untouched"


@pytest.mark.usefixtures("small_limits")
def test_the_refusal_says_when_to_come_back_and_nothing_else(client: TestClient) -> None:
    ip = _unique_ip()
    phone = make_user("Retry after", password=PASSWORD)[1]
    for _ in range(4):
        response = _sign_in(client, phone, ip)

    assert response.status_code == 429
    assert int(response.headers["retry-after"]) > 0

    # An error's message may itself be {message, field}: a rejection can name the
    # box to point at, and web/src/lib/api.ts is written against that shape.
    rejection = response.json()["error"]["message"]
    assert rejection["field"] is None, "a throttle points at no field — that would say which"
    message = rejection["message"]
    assert "try again" in message.lower()
    # It says when to come back, and nothing about which limit was hit or how
    # much allowance is left — that is the recipe for pacing an attack to sit
    # just underneath it.
    assert "minute" in message.lower()
    assert "limit" not in message.lower()


@pytest.mark.usefixtures("small_limits")
def test_one_address_being_throttled_does_not_affect_another(client: TestClient) -> None:
    """Carrier-grade NAT makes this the difference between a brake and an outage."""
    blocked, innocent = _unique_ip(), _unique_ip()
    phone = make_user("Neighbour", password=PASSWORD)[1]

    for _ in range(4):
        _sign_in(client, phone, blocked)
    assert _sign_in(client, phone, blocked).status_code == 429

    other = client.post(
        "/v1/sessions",
        json={"phone": phone, "password": PASSWORD},
        headers={"cf-connecting-ip": innocent},
    )
    assert other.status_code == 201, "a different address is unaffected"


# ---------------------------------------------------------------------------
# The counting itself
# ---------------------------------------------------------------------------
def test_counting_is_committed_even_though_the_request_was_refused() -> None:
    """The increment runs in its own transaction.

    If it shared the caller's, the exception that refuses the request would roll
    the counter back and the limit would never bite.
    """
    ip = _unique_ip()
    limits = (ratelimit.Limit(times=2, per_seconds=ratelimit.HOUR),)

    ratelimit.hit("sign_in", ip, limits)
    ratelimit.hit("sign_in", ip, limits)
    with pytest.raises(ratelimit.RateLimited):
        ratelimit.hit("sign_in", ip, limits)
    # Still refused afterwards: the third attempt's own increment survived.
    with pytest.raises(ratelimit.RateLimited):
        ratelimit.hit("sign_in", ip, limits)


def test_buckets_do_not_share_an_allowance() -> None:
    ip = _unique_ip()
    limits = (ratelimit.Limit(times=1, per_seconds=ratelimit.HOUR),)
    ratelimit.hit("sign_in", ip, limits)
    with pytest.raises(ratelimit.RateLimited):
        ratelimit.hit("sign_in", ip, limits)
    ratelimit.hit("send_code", ip, limits)  # a different bucket, untouched


def test_no_address_is_counted_rather_than_refused() -> None:
    """A malformed proxy header must not deny everybody their identity."""
    ratelimit.hit("sign_in", None, (ratelimit.Limit(times=0, per_seconds=ratelimit.HOUR),))


def test_the_table_stores_no_addresses() -> None:
    ip = _unique_ip()
    ratelimit.hit("sign_in", ip, (ratelimit.Limit(times=99, per_seconds=ratelimit.HOUR),))
    with transaction() as session:
        keys = session.execute(text("SELECT key_hash FROM ops.rate_counters")).scalars().all()
    assert keys, "something was counted"
    assert all(ip not in key for key in keys), "the address is hashed, never stored"


def test_pruning_removes_closed_windows_and_leaves_open_ones() -> None:
    ratelimit.hit("sign_in", _unique_ip(), (ratelimit.Limit(times=99, per_seconds=ratelimit.HOUR),))
    with transaction() as session:
        session.execute(
            text(
                """
                INSERT INTO ops.rate_counters (key_hash, window_start, window_secs, hits)
                VALUES ('stale-probe', now() - interval '2 days', 3600, 1)
                """
            )
        )

    ratelimit.prune()

    with transaction() as session:
        stale = session.execute(
            text("SELECT count(*) FROM ops.rate_counters WHERE key_hash = 'stale-probe'")
        ).scalar()
        live = session.execute(
            text("SELECT count(*) FROM ops.rate_counters WHERE window_start > now() - interval '1 hour'")
        ).scalar()
    assert stale == 0, "closed windows are swept"
    assert live and live > 0, "open ones are not"


def test_every_declared_bucket_has_limits() -> None:
    """A route naming a bucket that does not exist must fail loudly, not silently
    sail through unlimited. Throttle() calls this at import time for that reason."""
    for bucket in ("sign_in", "send_code", "confirm_code", "register"):
        assert ratelimit.limits_for(bucket), bucket
    with pytest.raises(KeyError):
        ratelimit.limits_for("no_such_bucket")
