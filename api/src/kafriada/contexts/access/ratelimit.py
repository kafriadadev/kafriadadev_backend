"""Counting what one source is doing, so bulk attacks stop being free.

Two limits already existed before this module and both are **per person**: an
account locks after repeated wrong passwords, and a phone number may be sent
five codes a day. Neither notices a caller who spreads the load — one password
against ten thousand accounts trips no account's lock, and codes to ten thousand
different numbers trip no number's limit. That is the gap this closes.

**Storage is deliberately boring.** One Postgres table of fixed-window counters.
Redis is the usual answer and is better at this in every way that matters at
scale — in-memory counters, self-expiring keys, shared across servers — but it
is another service to run, secure, pay for and monitor. These limits touch six
endpoints and pilot traffic is a few thousand attempts a day. Everything below
goes through :func:`hit`, so moving to Redis later is one file, not a hundred
call sites.

**Why the numbers are generous.** Nigerian mobile networks put very large
numbers of subscribers behind a handful of public addresses (carrier-grade NAT),
and a coordinator at a registration desk legitimately registers many athletes
from one connection. A tight per-address limit would therefore lock out a whole
carrier or a whole desk. These limits exist to stop ten thousand attempts, not
to police ten. Every one is configurable, because the right value is a thing you
learn from the pilot rather than guess beforehand.

**Counters are not evidence.** The key is hashed before storage, so this table
holds no addresses and answers no question about who did what. The audit log is
where that belongs, and it already records the address for events that matter.
"""

from __future__ import annotations

import hmac
from collections.abc import Sequence
from dataclasses import dataclass
from hashlib import sha256

import structlog
from sqlalchemy import text

from kafriada.db.engine import transaction
from kafriada.settings import get_settings

log = structlog.get_logger(__name__)

HOUR = 3_600
DAY = 86_400


@dataclass(frozen=True, slots=True)
class Limit:
    """At most ``times`` in each ``per_seconds`` window."""

    times: int
    per_seconds: int


class RateLimited(Exception):
    """The caller has spent this window's allowance."""

    def __init__(self, retry_after: int) -> None:
        super().__init__(f"rate limited for another {retry_after}s")
        self.retry_after = retry_after


def _key(bucket: str, subject: str) -> str:
    pepper = get_settings().secret_key.get_secret_value().encode()
    return hmac.new(pepper, f"{bucket}:{subject}".encode(), sha256).hexdigest()


def hit(bucket: str, subject: str | None, limits: Sequence[Limit]) -> None:
    """Count one attempt, and raise :class:`RateLimited` once past a limit.

    Every limit is counted even when an earlier one has already been exceeded,
    so the windows stay consistent with each other rather than depending on
    which limit happened to trip first.

    The counting **commits even when the request is refused** — that is the
    whole point, and it is why this runs in its own transaction rather than the
    caller's, which a raised exception would roll back.
    """
    if not limits:
        return
    if subject is None:
        # No address to count against (a malformed proxy header, say). Refusing
        # everybody would be worse than not counting: the limits are a brake on
        # bulk abuse, not an authentication check.
        log.warning("rate_limit_no_subject", bucket=bucket)
        return

    key_hash = _key(bucket, subject)
    worst = 0

    with transaction() as session:
        for limit in limits:
            row = session.execute(
                text(
                    """
                    INSERT INTO ops.rate_counters (key_hash, window_start, window_secs, hits)
                    VALUES (
                        :key_hash,
                        to_timestamp(
                            floor(extract(epoch FROM now()) / :secs) * :secs
                        ),
                        :secs,
                        1
                    )
                    ON CONFLICT (key_hash, window_start, window_secs)
                        DO UPDATE SET hits = ops.rate_counters.hits + 1
                    RETURNING hits,
                              ceil(extract(epoch FROM (
                                  window_start + CAST(:secs AS integer) * interval '1 second' - now()
                              )))::integer AS retry_after
                    """
                ),
                {"key_hash": key_hash, "secs": limit.per_seconds},
            ).mappings().one()

            if int(row["hits"]) > limit.times:
                worst = max(worst, max(int(row["retry_after"]), 1))
                # Only the crossing is logged, not every attempt after it, so a
                # sustained attack does not itself become the flood.
                if int(row["hits"]) == limit.times + 1:
                    log.warning(
                        "rate_limit_exceeded",
                        bucket=bucket,
                        allowed=limit.times,
                        window_secs=limit.per_seconds,
                    )

    if worst:
        raise RateLimited(worst)


def prune() -> int:
    """Delete windows that have closed. Called by the outbox worker's loop."""
    with transaction() as session:
        result = session.execute(
            text(
                """
                DELETE FROM ops.rate_counters
                 WHERE window_start < now() - interval '1 day'
                """
            )
        )
        # rowcount lives on the cursor result, which the base Result type does
        # not declare.
        deleted = getattr(result, "rowcount", 0)
    return int(deleted or 0)


# ---------------------------------------------------------------------------
# The limits themselves, in one place so they can be read without hunting.
# ---------------------------------------------------------------------------
def limits_for(bucket: str) -> tuple[Limit, ...]:
    cfg = get_settings()
    table: dict[str, tuple[Limit, ...]] = {
        # Password guessing spread across many accounts.
        "sign_in": (Limit(cfg.signins_per_ip_hourly, HOUR),),
        # Sending somebody else's phone a code. The per-number limit already
        # protects one victim; this protects everybody at once, and the bill.
        "send_code": (
            Limit(cfg.code_requests_per_ip_hourly, HOUR),
            Limit(cfg.code_requests_per_ip_daily, DAY),
        ),
        # Guessing six digits against many accounts rather than one.
        "confirm_code": (Limit(cfg.code_attempts_per_ip_hourly, HOUR),),
        # Junk registrations are not merely noise: every one permanently spends
        # a KUID serial for that LGA and year, and KUIDs are never reused.
        "register": (
            Limit(cfg.registrations_per_ip_hourly, HOUR),
            Limit(cfg.registrations_per_ip_daily, DAY),
        ),
    }
    # Look the name up first, so an unknown bucket raises even when limits are
    # switched off — otherwise a typo in a route would read as "no limits" in
    # exactly the configuration where nobody would notice.
    limits = table[bucket]
    return limits if cfg.rate_limits_enabled else ()
