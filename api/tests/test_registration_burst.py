"""Two hundred people register in the same minute, and nobody collides.

This is the concurrency proof for the KUID counter. Every registration in a state
contends on one row, so if the mint were wrong the failure would look like this:
two athletes holding the same permanent identifier, discovered weeks later when
both present a card at the same match.

The test does the real thing — real threads, real transactions, a real database —
and then asserts the properties that matter:

  1. every registration produced a KUID
  2. every KUID is unique
  3. the serials form an unbroken run with no gaps
  4. a duplicate phone number is refused rather than minting a second identity

**On cleanup.** It does not clean up, and that is not an oversight. Career events
are append-only and the application role holds no DELETE on athletes — by design,
because this is a register of people. Rows left by this test are the system
behaving correctly. In CI it runs against a throwaway database; against a shared
staging database it leaves recognisable test athletes behind, which is the price
of testing the real thing rather than a mock of it.

    pytest -m "db and slow" -s
"""

from __future__ import annotations

import itertools
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import pytest
from sqlalchemy import create_engine, text

from kafriada.clock import today_in_nigeria
from kafriada.contexts.identity import kuid as kuid_mod
from kafriada.contexts.identity.service import (
    RegistrationError,
    register,
)
from tests._registration import registration

pytestmark = [
    pytest.mark.db,
    pytest.mark.slow,
    pytest.mark.skipif(
        not os.environ.get("DATABASE_URL_APP"),
        reason="needs DATABASE_URL_APP",
    ),
]

# Lower this when running against a remote database on a slow link; the property
# being proved does not depend on the number, only on there being real contention.
REGISTRATIONS = int(os.environ.get("BURST_SIZE", "200"))
WORKERS = int(os.environ.get("BURST_WORKERS", "25"))

ANCHOR_LGA = "NG-JG-BKD"


def _run_id() -> str:
    """A short marker so this run's rows are identifiable afterwards."""
    return f"{int(time.time()) % 100000:05d}"


def _register_one(index: int, marker: str) -> tuple[int, str | None, str | None]:
    """One registration. Returns (index, kuid, error)."""
    # Nigerian mobile shape, kept inside a range no real subscriber holds so a
    # burst run cannot collide with a genuine registration.
    phone = f"+2349{marker}{index:04d}"
    data = registration(phone, f"Burst Test{marker}{index:04d}", lga_id=ANCHOR_LGA)
    try:
        return index, register(data).kuid, None
    except RegistrationError as exc:
        return index, None, f"rejected: {exc.message}"
    except Exception as exc:  # the test reports failures rather than raising here
        return index, None, f"{type(exc).__name__}: {exc}"


def _measure_round_trip() -> float:
    """Seconds for one trivial query. This governs everything below.

    The mint holds the counter row from its statement until COMMIT, so lock hold
    time is a small multiple of the round trip. In production the application and
    the database share an availability zone and this is under a millisecond. From
    a laptop to a managed database on another continent it is over a hundred
    times that, and the difference decides how many people can register at once.
    """
    engine = create_engine(
        os.environ["DATABASE_URL_APP"],
        connect_args={"connect_timeout": 30},
        future=True,
    )
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))  # pay the connection cost first
        started = time.time()
        for _ in range(5):
            conn.execute(text("SELECT 1"))
        rtt = (time.time() - started) / 5
    engine.dispose()
    return rtt


def test_two_hundred_concurrent_registrations_never_collide() -> None:
    marker = _run_id()

    # Size the test to the environment it is actually running in. The property
    # being proved — that concurrent minting never issues one identity twice —
    # needs genuine contention, not a particular number of threads. Queueing more
    # threads than the link can drain would only prove that PostgreSQL cancels
    # statements after 15 seconds, which is already known and is not the point.
    rtt = _measure_round_trip()
    lock_hold = rtt * 3  # mint statement, audit insert, commit
    safe_workers = max(4, min(WORKERS, int(10.0 / lock_hold)))

    print(f"\n  round trip to database: {rtt * 1000:.0f}ms")
    print(f"  estimated lock hold:     {lock_hold * 1000:.0f}ms")
    print(f"  in-region projection:    ~{1 / (0.001 * 3):.0f} registrations/sec")
    if safe_workers < WORKERS:
        print(f"  reducing {WORKERS} threads to {safe_workers} for this link")
    print(f"  registering {REGISTRATIONS} athletes across {safe_workers} threads...")

    started = time.time()
    results: list[tuple[int, str | None, str | None]] = []
    with ThreadPoolExecutor(max_workers=safe_workers) as pool:
        futures = [pool.submit(_register_one, i, marker) for i in range(REGISTRATIONS)]
        for future in as_completed(futures):
            results.append(future.result())
    elapsed = time.time() - started

    failures = [(i, err) for i, k, err in results if k is None]
    kuids = [k for _, k, _ in results if k is not None]

    print(f"  {len(kuids)} registered, {len(failures)} failed, in {elapsed:.1f}s "
          f"({len(kuids) / elapsed:.1f}/sec)")
    if failures:
        for i, err in failures[:5]:
            print(f"    #{i}: {err}")

    # 1. Everyone got one.
    assert not failures, f"{len(failures)} registrations failed"
    assert len(kuids) == REGISTRATIONS

    # 2. No two people share an identity. This is the assertion the whole
    #    register depends on; if it fails, the product is broken at its core.
    assert len(set(kuids)) == len(kuids), (
        f"DUPLICATE KUID ISSUED — {len(kuids) - len(set(kuids))} collision(s)"
    )

    # 3. Serials form an unbroken run. A gap would mean the counter allocated a
    #    number that never became an athlete — harmless technically, and exactly
    #    the thing that makes a coordinator distrust the register.
    serials = sorted(kuid_mod.Kuid.parse(k).serial for k in kuids)
    assert serials == list(range(serials[0], serials[0] + len(serials))), (
        f"gap in serials: {_first_gap(serials)}"
    )

    # 4. Every KUID is well formed and belongs to the right place.
    for value in kuids:
        parsed = kuid_mod.Kuid.parse(value)
        assert parsed.state == "JG"
        assert parsed.lga == "BKD"
        assert parsed.year == today_in_nigeria().year


def test_a_retried_registration_never_mints_a_second_identity() -> None:
    """The same phone twice must never produce two KUIDs.

    This is what happens in the field: a 2G connection times out after the
    server already committed, and the athlete presses the button again. The
    retry is refused on the phone field — it cannot return the existing KUID,
    because the same answer would go to a stranger who typed the number.
    """
    marker = _run_id()
    data = registration(f"+2349{marker}9999", f"Retry Test{marker}", lga_id=ANCHOR_LGA)

    register(data)
    with pytest.raises(RegistrationError) as caught:
        register(data)
    assert caught.value.field == "phone"

    # And the database agrees there is exactly one.
    engine = create_engine(
        os.environ["DATABASE_URL_APP"],
        connect_args={"connect_timeout": 30},
        future=True,
    )
    with engine.connect() as conn:
        count = conn.execute(
            text(
                """
                SELECT count(*) FROM identity.athletes a
                  JOIN ops.users u ON u.id = a.user_id
                 WHERE u.phone_e164 = :p
                """
            ),
            {"p": data.phone},
        ).scalar_one()
    engine.dispose()
    assert count == 1, "a retry minted a second identity"


def test_registration_is_refused_in_an_lga_that_is_not_open() -> None:
    """Closing a wave must actually stop registrations, not just hide a button."""
    data = registration("+2349880000001", "Too Early", lga_id="NG-JG-GUM")  # Gumel: wave 4
    with pytest.raises(RegistrationError) as caught:
        register(data)
    assert "not opened" in caught.value.message.lower()
    assert caught.value.field == "lga_id"


def _first_gap(serials: list[int]) -> str:
    for a, b in itertools.pairwise(serials):
        if b != a + 1:
            return f"{a} -> {b}"
    return "none"
