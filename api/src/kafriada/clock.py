"""Time, decided explicitly.

``date.today()`` reads the clock of whatever machine happens to be running the
code. That is fine in most systems and wrong in this one, because **the year of
registration is printed permanently into the KUID.**

The failure it prevents: an athlete registers at 11:30pm on 31 December in Birnin
Kudu. The application runs in Frankfurt, where it is already 00:30 on 1 January.
``date.today()`` would give the server's year, and that person's permanent
identifier would say they registered in a year they did not — on a card that can
never be reissued.

So dates that a *person* would recognise are computed in Nigeria's timezone, and
instants recorded for machines are UTC. Never mix the two.

Nigeria (West Africa Time) is UTC+1 and has never observed daylight saving, so a
fixed offset is exactly correct here and avoids depending on a timezone database
being installed — which on Windows it is not, by default.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta, timezone

# West Africa Time. No daylight saving, so a fixed offset is not an
# approximation — it is the definition.
NIGERIA_TZ = timezone(timedelta(hours=1), name="WAT")


def now_utc() -> datetime:
    """The current instant, for anything a machine will compare or order.

    Audit timestamps, session expiry, payment records. Always UTC, always
    timezone-aware — a naive datetime in a system that records money is a bug
    waiting for a daylight-saving boundary.
    """
    return datetime.now(UTC)


def today_in_nigeria() -> date:
    """Today's date as the person standing in Jigawa would give it.

    Use this for anything a human states or reads: the year in a KUID, the date
    a career event occurred, the day a coordinator's cash total covers.
    """
    return datetime.now(NIGERIA_TZ).date()


def age_on(born: date, today: date | None = None) -> int:
    """Whole years completed, in Nigeria's date.

    The comparison is on (month, day) rather than any day-count arithmetic, so
    someone born on 29 February is treated as having their birthday on 1 March in
    a common year rather than being a day out.
    """
    reference = today or today_in_nigeria()
    return (
        reference.year
        - born.year
        - ((reference.month, reference.day) < (born.month, born.day))
    )
