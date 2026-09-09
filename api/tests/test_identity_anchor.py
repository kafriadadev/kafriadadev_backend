"""The two values that identify a person: the phone number and the KUID.

Everything else in KAFRIADA can be corrected. These two cannot. A KUID is
immutable and never reissued, and the phone number is the constraint that stops
one human obtaining two of them. A defect in either is not a bug to fix later —
it is a duplicate identity in a national register, and there is no migration that
undoes it.

The most important test in this file is
``test_every_way_a_person_writes_their_number_gives_one_value``. If that fails,
the unique constraint in the database is silently doing nothing.
"""

from __future__ import annotations

import pytest

from kafriada.contexts.access.phone import (
    InvalidPhoneNumberError,
    display,
    is_valid,
    mask,
    normalise,
)
from kafriada.contexts.geography.jigawa import (
    ANCHOR_LGA_CODE,
    BY_CODE,
    JIGAWA_LGAS,
    STATE_CODE,
)
from kafriada.contexts.identity import kuid as kuid_mod
from kafriada.contexts.identity.kuid import InvalidKuidError, Kuid

# The example carried through every specification document.
CANONICAL = "KA-NG-JG-BKD-2026-000123"


# ---------------------------------------------------------------------------
# Phone numbers
# ---------------------------------------------------------------------------
class TestPhoneNormalisation:
    def test_every_way_a_person_writes_their_number_gives_one_value(self) -> None:
        """The property the whole identity anchor rests on.

        A coordinator types one form, the athlete types another, someone pastes a
        third from their contacts. If any of them stored differently, that person
        could register twice and receive two permanent KUIDs.
        """
        same_person = [
            "08030000000",
            "0803 000 0000",
            "0803-000-0000",
            "+2348030000000",
            "+234 803 000 0000",
            "+234-803-000-0000",
            "2348030000000",
            "234 803 000 0000",
            "008030000000".replace("00", "0", 1),  # 08030000000
            "8030000000",
            "  0803 000 0000  ",
            "(0803) 000-0000",
            "0803.000.0000",
        ]
        results = {normalise(value) for value in same_person}
        assert results == {"+2348030000000"}, f"forms diverged: {results}"

    @pytest.mark.parametrize(
        ("written", "expected"),
        [
            ("08030000000", "+2348030000000"),
            ("07011111111", "+2347011111111"),
            ("09099999999", "+2349099999999"),
            ("08123456789", "+2348123456789"),
        ],
    )
    def test_all_nigerian_mobile_ranges_are_accepted(
        self, written: str, expected: str
    ) -> None:
        # 070x, 080x, 081x, 090x and 091x are all in service. Checking the leading
        # digit rather than a prefix list means a newly issued range keeps working.
        assert normalise(written) == expected

    @pytest.mark.parametrize(
        "rejected",
        [
            "",
            "   ",
            "0803000000",       # ten digits with a trunk zero — one short
            "080300000000",     # one too many
            "06030000000",      # 06 is not a mobile range
            "01030000000",      # a Lagos landline
            "not a number",
            "0803-000-00OO",    # letter O typed for zero
            "+1 555 123 4567",  # a real number, but not Nigerian
            "+447700900000",    # likewise
        ],
    )
    def test_ambiguous_or_wrong_input_is_refused_never_guessed(
        self, rejected: str
    ) -> None:
        """Rejecting costs one person thirty seconds at a desk.

        Guessing costs a duplicate identity that cannot be merged, because the
        KUID it produced is immutable.
        """
        assert is_valid(rejected) is False
        with pytest.raises(InvalidPhoneNumberError):
            normalise(rejected)

    def test_a_foreign_number_is_refused_not_treated_as_nigerian(self) -> None:
        # The dangerous failure would be silently dropping '+1' and storing the
        # remainder as though it were a Nigerian line.
        with pytest.raises(InvalidPhoneNumberError, match="Only Nigerian numbers"):
            normalise("+15551234567")

    def test_country_code_with_trunk_zero_is_repaired(self) -> None:
        # Wrong, but unambiguous — so it is fixed rather than refused.
        assert normalise("+23408030000000") == "+2348030000000"

    def test_error_messages_tell_the_person_what_to_do(self) -> None:
        with pytest.raises(InvalidPhoneNumberError) as caught:
            normalise("0603 000 0000")
        message = str(caught.value)
        assert "070" in message and "080" in message, "should say what a valid number looks like"

    def test_masking_hides_the_middle_and_never_returns_a_usable_key(self) -> None:
        masked = mask("+2348030000000")
        assert masked == "+234803***0000"
        assert "8030000000" not in masked
        assert mask("nonsense") == "[invalid]"

    def test_display_groups_digits_for_reading_aloud(self) -> None:
        assert display("+2348030000000") == "+234 803 000 0000"


# ---------------------------------------------------------------------------
# The KUID
# ---------------------------------------------------------------------------
class TestKuid:
    def test_the_canonical_example_round_trips(self) -> None:
        parsed = Kuid.parse(CANONICAL)
        assert parsed.country == "NG"
        assert parsed.state == "JG"
        assert parsed.lga == "BKD"
        assert parsed.year == 2026
        assert parsed.serial == 123
        assert str(parsed) == CANONICAL

    def test_serial_is_always_six_digits(self) -> None:
        # Cards are read in columns and compared by eye. Variable width would make
        # 12 and 120 look alike at a glance on a printed sheet.
        built = kuid_mod.build(country="NG", state="JG", lga="BKD", year=2026, serial=7)
        assert str(built) == "KA-NG-JG-BKD-2026-000007"

    def test_uniqueness_key_is_state_year_serial_not_the_lga(self) -> None:
        """The LGA segment is informational and carries no uniqueness.

        Anyone changing the counter later must not assume otherwise: serials are
        allocated per state per year, so two athletes in different LGAs of the
        same state never share one.
        """
        a = Kuid.parse("KA-NG-JG-BKD-2026-000123")
        b = Kuid.parse("KA-NG-JG-DUT-2026-000123")
        assert a.counter_key == b.counter_key == (2026, "JG")
        assert a != b  # different strings, because the LGA differs

    @pytest.mark.parametrize(
        "typed",
        [
            "ka-ng-jg-bkd-2026-000123",       # lowercase from a phone keyboard
            "  KA-NG-JG-BKD-2026-000123  ",   # copied with whitespace
            "KA–NG–JG–BKD–2026–000123",  # noqa: RUF001 — en dashes are the test data
            "KA NG JG BKD 2026 000123",       # spaces instead of hyphens
        ],
    )
    def test_hand_typed_variations_are_rescued(self, typed: str) -> None:
        # These arrive from people reading a printed card. None of these repairs
        # can turn one valid KUID into a different valid KUID.
        assert Kuid.parse(typed) == Kuid.parse(CANONICAL)

    @pytest.mark.parametrize(
        "bad",
        [
            "",
            "KA-NG-JG-BKD-2026-00123",     # five digits
            "KA-NG-JG-BKD-2026-0001234",   # seven
            "KA-NG-JG-BK-2026-000123",     # two-letter LGA
            "KA-NG-JG-BKDX-2026-000123",   # four-letter LGA
            "KA-NG-JG-BKD-1999-000123",    # year outside the supported range
            "XX-NG-JG-BKD-2026-000123",    # wrong prefix
            "KA-NG-JG-BKD-2026-000123-1",  # trailing segment
            "PREFIX-KA-NG-JG-BKD-2026-000123",
            "KA-NG-JG-BKD-2026-ABCDEF",
        ],
    )
    def test_malformed_identifiers_are_refused(self, bad: str) -> None:
        assert kuid_mod.is_valid(bad) is False
        with pytest.raises(InvalidKuidError):
            Kuid.parse(bad)

    def test_serial_zero_is_not_a_valid_identity(self) -> None:
        # The counter starts at 1. A zero serial would mean the mint returned
        # before allocating, which must never produce a usable KUID.
        with pytest.raises(InvalidKuidError):
            kuid_mod.build(country="NG", state="JG", lga="BKD", year=2026, serial=0)

    def test_a_kuid_cannot_be_modified_after_it_is_made(self) -> None:
        # Immutability is the product promise. Enforced by the type, by the
        # database trigger, and by there being no code path that tries.
        parsed = Kuid.parse(CANONICAL)
        with pytest.raises(AttributeError):
            parsed.serial = 999  # type: ignore[misc]

    def test_masking_shortens_for_display_only(self) -> None:
        assert kuid_mod.mask(CANONICAL) == "KA-…-000123"
        assert kuid_mod.mask("not a kuid") == "not a kuid"


# ---------------------------------------------------------------------------
# Jigawa
# ---------------------------------------------------------------------------
class TestJigawaLgas:
    def test_there_are_twenty_seven(self) -> None:
        assert len(JIGAWA_LGAS) == 27

    def test_codes_are_unique_because_they_are_printed_into_identifiers(self) -> None:
        codes = [lga.code for lga in JIGAWA_LGAS]
        assert len(set(codes)) == 27, "a duplicate code would make two LGAs indistinguishable"

    def test_every_code_produces_a_valid_kuid(self) -> None:
        # A code that cannot appear in a well-formed KUID would only be discovered
        # when the first athlete in that LGA tried to register.
        for lga in JIGAWA_LGAS:
            built = kuid_mod.build(
                country="NG", state=STATE_CODE, lga=lga.code, year=2026, serial=1
            )
            assert kuid_mod.is_valid(str(built)), f"{lga.name} ({lga.code}) breaks the format"

    def test_the_anchor_lga_is_birnin_kudu(self) -> None:
        assert ANCHOR_LGA_CODE == "BKD"
        assert BY_CODE[ANCHOR_LGA_CODE].name == "Birnin Kudu"
        assert BY_CODE[ANCHOR_LGA_CODE].wave == 1

    def test_only_the_anchor_is_in_wave_one(self) -> None:
        # Wave 1 is the soft launch: one LGA, all attention on it.
        wave_one = [lga for lga in JIGAWA_LGAS if lga.wave == 1]
        assert [lga.code for lga in wave_one] == ["BKD"]

    def test_every_lga_is_assigned_to_a_wave(self) -> None:
        # An unassigned LGA would never open, and nobody would notice until a
        # coordinator asked why their town could not register.
        assert all(lga.wave in {1, 2, 3, 4} for lga in JIGAWA_LGAS)
