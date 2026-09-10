"""The KUID — KAFRIADA's permanent athlete identifier.

    KA-NG-JG-BKD-2026-000123
    │  │  │  │   │    └── serial, zero-padded to six digits
    │  │  │  │   └─────── year of registration
    │  │  │  └─────────── LGA of registration — informational only
    │  │  └────────────── state — part of the uniqueness key
    │  └───────────────── country
    └──────────────────── KAFRIADA

**Uniqueness is (state, year, serial).** The LGA segment carries no uniqueness at
all; it is there so a coordinator reading a card can tell where the athlete first
registered. Anyone tempted to change the counter's key later must read this first:
serials are allocated per state per year, and two athletes in different LGAs of the
same state will never share one.

**The KUID records where someone registered, not where they live.** People move,
and the identifier does not. It is a birth-certificate number, not an address. Say
so on the public profile and on the athlete's own edit screen, or the pilot is
spent answering the same question every week and refusing re-issue requests.

**It is immutable and never reused.** There is no update path in this module and
none anywhere else. A KUID cannot exist without its athlete row, because both are
written in one transaction — see the minting service.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final, Self

PREFIX: Final = "KA"
SERIAL_DIGITS: Final = 6
MAX_SERIAL: Final = 10**SERIAL_DIGITS - 1  # 999,999 per state per year

# Anchored, and every segment fixed-width. A KUID is read off a printed card by a
# human and typed into a form by another human, so the format has to be strict
# enough to reject a typo rather than silently accept a different athlete's id.
KUID_PATTERN: Final = re.compile(
    r"^KA"
    r"-(?P<country>[A-Z]{2})"
    r"-(?P<state>[A-Z]{2})"
    r"-(?P<lga>[A-Z]{3})"
    r"-(?P<year>20[0-9]{2})"
    r"-(?P<serial>[0-9]{6})$"
)


class InvalidKuidError(ValueError):
    """The string is not a well-formed KUID."""


@dataclass(frozen=True, slots=True)
class Kuid:
    """A parsed KUID. Frozen: there is no legitimate way to alter one."""

    country: str
    state: str
    lga: str
    year: int
    serial: int

    def __post_init__(self) -> None:
        if not (1 <= self.serial <= MAX_SERIAL):
            raise InvalidKuidError(f"serial out of range: {self.serial}")
        if not (2000 <= self.year <= 2099):
            raise InvalidKuidError(f"year out of range: {self.year}")
        for name, value, length in (
            ("country", self.country, 2),
            ("state", self.state, 2),
            ("lga", self.lga, 3),
        ):
            if len(value) != length or not value.isascii() or not value.isupper():
                raise InvalidKuidError(f"{name} must be {length} uppercase letters: {value!r}")

    def __str__(self) -> str:
        return (
            f"{PREFIX}-{self.country}-{self.state}-{self.lga}"
            f"-{self.year}-{self.serial:0{SERIAL_DIGITS}d}"
        )

    @property
    def counter_key(self) -> tuple[int, str]:
        """The row this KUID's serial was allocated from: (year, state).

        Every registration in a state contends on one counter row, which is why
        the minting transaction is kept as short as it is.
        """
        return (self.year, self.state)

    @classmethod
    def parse(cls, value: str) -> Self:
        """Parse a KUID string. Raises InvalidKuidError on anything malformed.

        Input is normalised first because these arrive from people typing what
        they see on a card: stray spaces, lowercase, and the en dash that a phone
        keyboard substitutes for a hyphen are all ordinary, not hostile.
        """
        if not isinstance(value, str):  # pragma: no cover — defensive at the boundary
            raise InvalidKuidError("KUID must be a string")

        candidate = normalise(value)
        match = KUID_PATTERN.match(candidate)
        if match is None:
            raise InvalidKuidError(f"malformed KUID: {value!r}")

        return cls(
            country=match["country"],
            state=match["state"],
            lga=match["lga"],
            year=int(match["year"]),
            serial=int(match["serial"]),
        )


def normalise(value: str) -> str:
    """Tidy a hand-typed KUID without changing its meaning.

    Uppercases, strips whitespace, and converts the dash characters a phone
    keyboard produces into the plain hyphen the format uses. Nothing here can
    turn one valid KUID into a different valid KUID — it only rescues input that
    was already correct.
    """
    cleaned = value.strip().upper()
    # These lookalike characters are the point of this function, not a mistake in
    # it: phone keyboards and word processors substitute them for a plain hyphen,
    # and a KUID typed on one would otherwise fail to parse. (RUF001 flags them
    # as ambiguous, which is precisely why they are handled here.)
    for dash in ("‐", "‑", "‒", "–", "—", "−", "_"):  # noqa: RUF001
        cleaned = cleaned.replace(dash, "-")
    # Whitespace between segments becomes a separator rather than disappearing:
    # people read a card aloud and type "KA NG JG BKD 2026 000123". Removing the
    # spaces instead would produce one unbroken string that fails to parse.
    cleaned = re.sub(r"\s+", "-", cleaned)
    # "KA - NG" and a stray double hyphen both collapse to a single separator.
    return re.sub(r"-{2,}", "-", cleaned).strip("-")


def build(*, country: str, state: str, lga: str, year: int, serial: int) -> Kuid:
    """Assemble a KUID from its parts.

    Called in exactly one place — inside the minting transaction, immediately
    after the counter returns the next serial. Anywhere else is a mistake.
    """
    return Kuid(
        country=country.upper(),
        state=state.upper(),
        lga=lga.upper(),
        year=year,
        serial=serial,
    )


def prefix(*, country: str, state: str, lga: str, year: int) -> str:
    """Everything in a KUID up to and including the final separator.

    Exists for one reason: the mint appends the serial to this prefix inside the
    same SQL statement that allocates it, so that allocating a number, creating
    the athlete and recording the career event are a single round trip. The
    counter row is locked from that statement until COMMIT, and on a link where
    a round trip costs 150ms the difference between one statement and four is
    the difference between a lock held for milliseconds and one held for most of
    a second.

    The format still belongs to this module — SQL only concatenates the
    zero-padded serial it has just allocated. Two independent guards catch a
    mistake anyway: a CHECK constraint on the column enforces the full shape,
    and a unique index on (state, year, serial) enforces the real rule.
    """
    return f"{PREFIX}-{country.upper()}-{state.upper()}-{lga.upper()}-{year}-"


def is_valid(value: str) -> bool:
    """Cheap check for a form field, before any database work."""
    try:
        Kuid.parse(value)
    except InvalidKuidError:
        return False
    return True


def mask(value: str) -> str:
    """Shorten a KUID for a dense table: KA-…-000123.

    Never used for anything but display. The full value is what identifies a
    person, and a masked one must never be stored, compared or logged as if it
    were the identifier.
    """
    try:
        parsed = Kuid.parse(value)
    except InvalidKuidError:
        return value
    return f"{PREFIX}-…-{parsed.serial:0{SERIAL_DIGITS}d}"
