"""Jigawa State and its 27 Local Government Areas.

**These three-letter codes are permanent.** Each one is printed into the KUID of
every athlete who registers in that LGA — ``KA-NG-JG-BKD-2026-000123`` — and the
KUID is immutable and never reissued. Once the first card is handed out in an LGA,
its code is fixed for the life of the register.

Two consequences:

1.  The codes need signing off by the CEO and the state coordinator *before* the
    first registration drive, not after. Changing ``KRK`` to ``KIR`` in week three
    means two athletes in the same LGA hold cards in different formats forever.
2.  A code is never edited and never reused, exactly like the KUID that contains
    it. If an LGA is renamed or split, a new code is added and the old one keeps
    resolving.

Codes are derived from the LGA name and kept visually distinct — ``GWA``/``GWI``
for Gwaram and Gwiwa, ``GAG``/``GRK`` for Gagarawa and Garki. A coordinator reads
these aloud down a phone line, so pairs that sound alike are worth avoiding.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

COUNTRY_CODE: Final = "NG"
STATE_CODE: Final = "JG"
STATE_NAME: Final = "Jigawa"

# The anchor LGA for the pilot: the CEO's home LGA, and the only one live at
# launch. Every other LGA opens later behind the rollout flag.
ANCHOR_LGA_CODE: Final = "BKD"


@dataclass(frozen=True, slots=True)
class Lga:
    code: str  # three letters, permanent, printed into every KUID
    name: str
    wave: int  # rollout wave — see the build plan


# Wave 1 is Birnin Kudu alone. Wave 2 adds the anchor cluster around it. Wave 3
# takes the state to roughly half. Wave 4 completes it. Opening and closing a
# wave is a flag on the row, not a deployment.
JIGAWA_LGAS: Final[tuple[Lga, ...]] = (
    Lga("BKD", "Birnin Kudu", 1),
    Lga("DUT", "Dutse", 2),
    Lga("BUJ", "Buji", 2),
    Lga("GWA", "Gwaram", 2),
    Lga("HAD", "Hadejia", 3),
    Lga("JAH", "Jahun", 3),
    Lga("KIY", "Kiyawa", 3),
    Lga("RIN", "Ringim", 3),
    Lga("TAU", "Taura", 3),
    Lga("MIG", "Miga", 3),
    Lga("KFH", "Kafin Hausa", 3),
    Lga("AUY", "Auyo", 3),
    Lga("GUR", "Guri", 3),
    Lga("KRK", "Kiri Kasama", 3),
    Lga("BRW", "Biriniwa", 3),
    Lga("GUM", "Gumel", 4),
    Lga("KAZ", "Kazaure", 4),
    Lga("BAB", "Babura", 4),
    Lga("GAG", "Gagarawa", 4),
    Lga("GRK", "Garki", 4),
    Lga("GWI", "Gwiwa", 4),
    Lga("KAU", "Kaugama", 4),
    Lga("MGT", "Maigatari", 4),
    Lga("MLM", "Malam Madori", 4),
    Lga("RON", "Roni", 4),
    Lga("SUL", "Sule Tankarkar", 4),
    Lga("YAN", "Yankwashi", 4),
)

BY_CODE: Final[dict[str, Lga]] = {lga.code: lga for lga in JIGAWA_LGAS}


def _check_integrity() -> None:
    """Fail at import if the table is wrong.

    Jigawa has 27 LGAs, and a duplicate code would mean two LGAs minting KUIDs
    that cannot be told apart. Both are cheap to check and catastrophic to miss,
    so they are checked every time the module loads rather than in a test that
    might be skipped.
    """
    if len(JIGAWA_LGAS) != 27:
        raise RuntimeError(f"Jigawa has 27 LGAs, table has {len(JIGAWA_LGAS)}")
    if len(BY_CODE) != len(JIGAWA_LGAS):
        raise RuntimeError("duplicate LGA code — codes are printed into KUIDs")
    for lga in JIGAWA_LGAS:
        if len(lga.code) != 3 or not lga.code.isascii() or not lga.code.isupper():
            raise RuntimeError(f"LGA code must be three uppercase letters: {lga.code!r}")


_check_integrity()
