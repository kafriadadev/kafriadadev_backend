"""Tests for the ledger lines a settled payment produces.

No database. Two things are being protected: that a payment always produces
*exactly two* lines — gross and provider fee — so the replay test in the
settlement service has a number it can assert, and that nothing which is not whole,
positive, credible kobo can ever become a line at all.
"""

from __future__ import annotations

import dataclasses

import pytest

from kafriada.contexts.ledger.entries import (
    Direction,
    InvalidAmount,
    LedgerLine,
    Source,
    net_kobo,
    plan_settlement,
)

GROSS = 250_000  # 2,500 naira
FEE = 3_750  # 37.50 naira


class TestPlanning:

    def test_a_settled_payment_is_exactly_two_lines(self) -> None:
        lines = plan_settlement(gross_kobo=GROSS, provider_fee_kobo=FEE)
        assert len(lines) == 2

    def test_gross_comes_in_and_the_provider_fee_goes_out(self) -> None:
        gross, fee = plan_settlement(gross_kobo=GROSS, provider_fee_kobo=FEE)
        assert gross == LedgerLine(Direction.CREDIT, Source.PAYSTACK, GROSS)
        assert fee == LedgerLine(Direction.DEBIT, Source.FEE, FEE)

    def test_the_net_is_what_paystack_actually_settles_to_us(self) -> None:
        lines = plan_settlement(gross_kobo=GROSS, provider_fee_kobo=FEE)
        assert net_kobo(lines) == GROSS - FEE == 246_250

    def test_a_waived_fee_is_still_two_lines(self) -> None:
        """Two rows always, so "exactly two" stays true for every payment."""
        lines = plan_settlement(gross_kobo=GROSS, provider_fee_kobo=0)
        assert len(lines) == 2
        assert lines[1].amount_kobo == 0
        assert net_kobo(lines) == GROSS

    def test_planning_is_repeatable(self) -> None:
        """Same figures, same lines — nothing in a plan depends on the clock or on
        how many times it has been asked."""
        first = plan_settlement(gross_kobo=GROSS, provider_fee_kobo=FEE)
        assert all(plan_settlement(gross_kobo=GROSS, provider_fee_kobo=FEE) == first
                   for _ in range(5))

    def test_a_planned_line_cannot_be_edited(self) -> None:
        line, _ = plan_settlement(gross_kobo=GROSS, provider_fee_kobo=FEE)
        with pytest.raises(dataclasses.FrozenInstanceError):
            line.amount_kobo = 1  # type: ignore[misc]


class TestRefusals:

    @pytest.mark.parametrize("gross", [0, -1, -250_000])
    def test_a_payment_must_be_positive(self, gross: int) -> None:
        with pytest.raises(InvalidAmount, match="positive"):
            plan_settlement(gross_kobo=gross, provider_fee_kobo=0)

    def test_a_fee_cannot_be_negative(self) -> None:
        with pytest.raises(InvalidAmount, match="negative"):
            plan_settlement(gross_kobo=GROSS, provider_fee_kobo=-1)

    @pytest.mark.parametrize("fee", [GROSS, GROSS + 1, GROSS * 100])
    def test_a_fee_that_swallows_the_payment_is_a_unit_error_not_a_fee(self, fee: int) -> None:
        with pytest.raises(InvalidAmount, match="credible"):
            plan_settlement(gross_kobo=GROSS, provider_fee_kobo=fee)

    @pytest.mark.parametrize("bad", [250_000.0, 2_500.5, "250000", None, True, False, [1]])
    def test_gross_must_be_an_integer_number_of_kobo(self, bad: object) -> None:
        with pytest.raises(InvalidAmount, match="gross_kobo"):
            plan_settlement(gross_kobo=bad, provider_fee_kobo=0)  # type: ignore[arg-type]

    @pytest.mark.parametrize("bad", [37.5, "3750", None, True, False, [1]])
    def test_the_fee_must_be_an_integer_number_of_kobo(self, bad: object) -> None:
        with pytest.raises(InvalidAmount, match="provider_fee_kobo"):
            plan_settlement(gross_kobo=GROSS, provider_fee_kobo=bad)  # type: ignore[arg-type]

    def test_true_is_not_one_kobo(self) -> None:
        """``bool`` is a subclass of ``int``, so ``True`` passes a naive
        ``isinstance(x, int)`` and would be recorded as a payment of one kobo."""
        with pytest.raises(InvalidAmount):
            plan_settlement(gross_kobo=True, provider_fee_kobo=0)
