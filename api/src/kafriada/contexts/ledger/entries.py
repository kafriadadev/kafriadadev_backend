"""The lines a confirmed payment writes to the ledger — planned, not yet written.

A payment that settles produces **exactly two** ledger lines: the gross amount the
customer paid, and the fee Paystack kept out of it. Two lines, from the very first
payment, because a ledger that records only the net figure cannot be reconciled
against a Paystack settlement report — the report is net of fees, the customer's
receipt is gross, and only a ledger holding both can be checked against either.

"Exactly two" is also a testable promise: the replay test sends one webhook five
times at once and asserts two rows, not ten and not four. Anything that could
produce a third line (a rounding adjustment, a "balancing" entry) would make that
test meaningless, so this module refuses to invent one.

This is the pure half. It decides *what* is written and checks the figures are
sane; it does not write anything, choose an account, or open a transaction.
Writing is the ledger service's job, on the money role, and it takes these lines
as given.

**Integers only.** Money is kobo, never naira and never a float. A float that is
off by one part in ten trillion is not visible in a test and is visible in an
audit two years later. ``bool`` is refused explicitly because it is an ``int`` in
Python and ``True`` would otherwise pass as one kobo.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Direction(StrEnum):
    CREDIT = "credit"
    DEBIT = "debit"


class Source(StrEnum):
    # The specification also lists 'reward'. It arrives with the feature that needs
    # it; an unused member is a value nothing has tested.
    PAYSTACK = "paystack"
    FEE = "fee"
    # A refund made by hand in the Paystack dashboard and recorded here afterwards.
    # KAFRIADA never performs one (see contexts/ledger/reversal.py).
    REVERSAL = "reversal"


@dataclass(frozen=True, slots=True)
class LedgerLine:
    direction: Direction
    source: Source
    amount_kobo: int


class InvalidAmount(ValueError):
    """A figure that cannot be money: wrong type, negative, or not credible."""


def _kobo(name: str, value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise InvalidAmount(f"{name} must be an integer number of kobo, got {value!r}")
    return value


def plan_settlement(*, gross_kobo: int, provider_fee_kobo: int) -> tuple[LedgerLine, LedgerLine]:
    """The two lines for one settled payment: gross in, provider fee out.

    A fee equal to or larger than the payment is refused rather than recorded.
    Paystack's fee is a small percentage plus a flat charge and is capped, so a
    fee that swallows the payment is not a fee — it is a unit error (naira read
    as kobo, or the other way round), and the whole point of this ledger is that
    it cannot be quietly wrong. A zero fee is allowed: a waived fee is real, and
    keeping the second line at zero keeps the promise of exactly two rows.
    """
    gross = _kobo("gross_kobo", gross_kobo)
    fee = _kobo("provider_fee_kobo", provider_fee_kobo)

    if gross <= 0:
        raise InvalidAmount(f"gross_kobo must be positive, got {gross}")
    if fee < 0:
        raise InvalidAmount(f"provider_fee_kobo cannot be negative, got {fee}")
    if fee >= gross:
        raise InvalidAmount(
            f"provider fee {fee} kobo is not credible against a payment of {gross} kobo"
        )

    return (
        LedgerLine(Direction.CREDIT, Source.PAYSTACK, gross),
        LedgerLine(Direction.DEBIT, Source.FEE, fee),
    )


def plan_reversal(*, gross_kobo: int, amount_kobo: int) -> LedgerLine:
    """The one debit that records a refund of ``amount_kobo`` against a payment of ``gross_kobo``.

    Never more than was paid: a refund larger than the payment is not a refund, it is a
    mistyped amount (or naira read as kobo), and the ledger exists to refuse exactly that.
    """
    gross = _kobo("gross_kobo", gross_kobo)
    amount = _kobo("amount_kobo", amount_kobo)
    if gross <= 0:
        raise InvalidAmount(f"gross_kobo must be positive, got {gross}")
    if amount <= 0:
        raise InvalidAmount(f"a reversal must be for a positive amount, got {amount}")
    if amount > gross:
        raise InvalidAmount(f"cannot reverse {amount} kobo of a payment of {gross} kobo")
    return LedgerLine(Direction.DEBIT, Source.REVERSAL, amount)


def net_kobo(lines: tuple[LedgerLine, LedgerLine]) -> int:
    """What is left after the fee — credits minus debits."""
    return sum(
        line.amount_kobo if line.direction is Direction.CREDIT else -line.amount_kobo
        for line in lines
    )
