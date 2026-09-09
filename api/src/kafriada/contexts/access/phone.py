"""Phone numbers — the identity anchor.

One verified phone, one person, one KUID. That rule is enforced by a unique
constraint on ``ops.users.phone_e164``, and a unique constraint is only as good as
the normalisation in front of it.

**The property this module must hold.** Every way a person can write their own
number must produce exactly one stored value. ``0803 000 0000``,
``+234 803 000 0000``, ``234-803-000-0000`` and ``08030000000`` are the same human
being. If any of them normalised differently, that person could obtain a second
KUID — and a permanent identity register that hands the same person two permanent
identities has failed at its only job.

So this module is deliberately strict: it canonicalises what it can prove, and
**rejects anything ambiguous rather than guessing.** A rejected number costs one
person thirty seconds at a registration desk. A wrongly-guessed number costs a
duplicate identity that cannot be merged, because the KUID is immutable.
"""

from __future__ import annotations

import re
from typing import Final

# Nigeria. The pilot is Jigawa State only, so this is the sole region supported —
# the signature carries a region parameter so adding one later is not a rewrite.
NIGERIA_CC: Final = "234"

# A Nigerian mobile number is ten digits after the country code, beginning 7, 8
# or 9 (the 070x, 080x, 081x, 090x and 091x ranges). Checking the leading digit
# rather than a list of prefixes is deliberate: operators are issued new prefixes
# regularly, and a hardcoded list quietly starts rejecting real customers.
_NG_NATIONAL: Final = re.compile(r"^[789][0-9]{9}$")

# Digits, and a single optional leading plus. Everything else — spaces, dashes,
# brackets, dots — is formatting a person added, and is removed before parsing.
# The class deliberately includes the non-breaking space and the full
# range of dash-like characters (U+2010 to U+2015): people paste numbers out of
# word processors and web pages, which substitute these for a plain hyphen.
# RUF001 flags them as ambiguous — removing that ambiguity is this line's job.
_STRIP: Final = re.compile(r"[\s\-(). ‐-―]")  # noqa: RUF001

E164: Final = re.compile(r"^\+[1-9][0-9]{7,14}$")


class InvalidPhoneNumberError(ValueError):
    """The input is not a phone number we can store with confidence."""


def normalise(raw: str, *, region: str = "NG") -> str:
    """Return the canonical E.164 form, e.g. ``+2348030000000``.

    Raises :class:`InvalidPhoneNumberError` for anything that cannot be resolved
    to exactly one number. Ambiguity is an error, never a guess.
    """
    if region != "NG":
        raise InvalidPhoneNumberError(f"unsupported region: {region}")
    if not isinstance(raw, str):  # pragma: no cover — defensive at the boundary
        raise InvalidPhoneNumberError("phone number must be text")

    cleaned = _STRIP.sub("", raw.strip())
    if not cleaned:
        raise InvalidPhoneNumberError("Enter a phone number.")

    # An international prefix written as 00 is the same as +.
    if cleaned.startswith("00"):
        cleaned = "+" + cleaned[2:]

    if cleaned.startswith("+"):
        digits, had_plus = cleaned[1:], True
    else:
        digits, had_plus = cleaned, False

    if not digits.isdigit():
        raise InvalidPhoneNumberError("A phone number can only contain digits.")

    national = _to_national(digits, had_plus=had_plus)

    if not _NG_NATIONAL.match(national):
        raise InvalidPhoneNumberError(
            "That does not look like a Nigerian mobile number. "
            "It should be 11 digits starting 070, 080, 081, 090 or 091."
        )

    return f"+{NIGERIA_CC}{national}"


def _to_national(digits: str, *, had_plus: bool) -> str:
    """Reduce any accepted form to the ten-digit national number.

    Each branch is a shape a real person actually writes. Anything not matching
    one of them falls through and is rejected — the alternative is inventing a
    number on someone's behalf.
    """
    # -- Forms that state Nigeria's country code explicitly ----------------
    # These are checked first, so that a number carrying both '+234' and the
    # trunk zero is repaired rather than mistaken for a foreign number below.

    # +234 803 000 0000 / 234 803 000 0000
    if digits.startswith(NIGERIA_CC) and len(digits) == len(NIGERIA_CC) + 10:
        return digits[len(NIGERIA_CC):]

    # +2340803… — country code and trunk zero both present. Wrong, but there is
    # only one number it can mean, so it is fixed rather than rejected.
    if digits.startswith(NIGERIA_CC + "0") and len(digits) == len(NIGERIA_CC) + 11:
        return digits[len(NIGERIA_CC) + 1:]

    # -- A stated country code that is not Nigeria's -----------------------
    # Silently dropping the '+1' from a US number and storing the rest as a
    # Nigerian line is the worst outcome available here, so it is refused.
    if had_plus:
        raise InvalidPhoneNumberError(
            "Only Nigerian numbers can be registered in the pilot."
        )

    # -- Local forms, no country code --------------------------------------
    # 0803 000 0000 — as written on a poster and said out loud.
    if digits.startswith("0") and len(digits) == 11:
        return digits[1:]

    # 803 000 0000 — trunk zero omitted, common when copying from a contact list.
    if len(digits) == 10:
        return digits

    raise InvalidPhoneNumberError(
        "That is not the right length for a Nigerian mobile number."
    )


def is_valid(raw: str, *, region: str = "NG") -> bool:
    """Cheap check for a form field, before any database work."""
    try:
        normalise(raw, region=region)
    except InvalidPhoneNumberError:
        return False
    return True


def mask(e164: str) -> str:
    """Obscure the middle digits for logs and support screens: ``+234803***0000``.

    A phone number is the identity anchor here, so it is personal data twice over
    — it identifies the person and it is the key to their account. Logs are read
    by more people, in more places, than the database ever is.

    Never use a masked value as a lookup key or store it as one.
    """
    if not E164.match(e164):
        return "[invalid]"
    return f"{e164[:7]}***{e164[-4:]}"


def display(e164: str) -> str:
    """Group an E.164 number for a person to read back: ``+234 803 000 0000``."""
    if not E164.match(e164) or not e164.startswith(f"+{NIGERIA_CC}"):
        return e164
    national = e164[1 + len(NIGERIA_CC):]
    return f"+{NIGERIA_CC} {national[:3]} {national[3:6]} {national[6:]}"
