"""Deciding what a Paystack event is worth, before anything is written.

Everything here is pure: parsed JSON and numbers in, a verdict out. That is the
point. The webhook is the one place a stranger's HTTP request can cause money to
be recorded, so the *rule* for what earns a ledger entry lives where it can be
tested exhaustively without a database, a network or a Paystack account. The
layer that calls this only has to act on the answer.

**A mismatch freezes; it never approves.** Currency must be NGN, status must be
success, and the amount must equal the expected kobo *exactly*. Anything else is
not settled and is not silently dropped either — real money has moved, so the
payment is frozen and an alert is raised for a person to look at. Exact equality,
not "at least": an overpayment is as much a sign that something upstream is wrong
(a price changed mid-flight, an amount was tampered with) as an underpayment, and
guessing which way to be generous with somebody else's money is not a decision
code should make. The headline case is a ten-naira payment that must never buy a
2,500-naira badge.

**What is deliberately not here: the duplicate check.** Paystack redelivers
webhooks, and five copies can arrive at the same moment. "Have I seen this
before?" cannot be a read followed by a write — two copies both read "no" and
both settle. It is one ``INSERT ... ON CONFLICT DO NOTHING RETURNING`` whose
result says whether *this* delivery was first, and only the database can answer
that atomically. A pure ``already_seen()`` helper here would look safe and be a
race. That check belongs to the settlement service, where the concurrent-replay
test proves it against a real database.

Signature verification is not here either: it already exists, and is tested, in
:func:`kafriada.security.signing.verify_paystack_signature`. It runs first, on
the raw bytes, before anything in this module sees a parsed payload.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum

from kafriada.settings import Settings

CURRENCY = "NGN"

# Our own reference, KAF-{uuid4}. Paystack merchants often run several products
# through one account, so this webhook will receive events for transactions that
# are nothing to do with KAFRIADA. Those are ignored quietly — alerting on them
# would train everyone to ignore the alert that matters.
REFERENCE_PREFIX = "KAF-"
_OUR_REFERENCE = re.compile(
    r"KAF-[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
)


# ---------------------------------------------------------------------------
# What is being bought
# ---------------------------------------------------------------------------
class Purpose(StrEnum):
    STAGE2_ATHLETE = "stage2_athlete"
    STAGE2_ORG = "stage2_org"


def expected_amount_kobo(purpose: Purpose, settings: Settings) -> int:
    """The price, from configuration — never from the payment itself."""
    if purpose is Purpose.STAGE2_ATHLETE:
        return settings.price_athlete_verification_kobo
    return settings.price_club_verification_kobo


def new_reference() -> str:
    """A reference nobody can guess, in a shape we can recognise as ours."""
    return f"{REFERENCE_PREFIX}{uuid.uuid4()}"


def is_our_reference(reference: str) -> bool:
    return _OUR_REFERENCE.fullmatch(reference) is not None


# ---------------------------------------------------------------------------
# Reading the event
# ---------------------------------------------------------------------------
class MalformedEvent(ValueError):
    """Correctly signed, but not shaped like anything we know how to read.

    A valid signature means Paystack sent it, so this is not an attack — it is
    Paystack changing its payload, and it needs a human, not a retry.
    """


@dataclass(frozen=True, slots=True)
class ChargeEvent:
    reference: str
    amount_kobo: int
    currency: str
    status: str
    # None when Paystack did not report one. Not defaulted to zero: a made-up
    # figure in a ledger is worse than a missing one, because it looks right.
    fees_kobo: int | None


def _integer(data: Mapping[str, object], key: str) -> int:
    value = data.get(key)
    # bool is an int in Python; True must not read as one kobo. Floats are refused
    # too — Paystack sends whole kobo, and 5000.0 means something has changed.
    if isinstance(value, bool) or not isinstance(value, int):
        raise MalformedEvent(f"data.{key} must be an integer, got {value!r}")
    return value


def _text(data: Mapping[str, object], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value:
        raise MalformedEvent(f"data.{key} must be a non-empty string, got {value!r}")
    return value


def parse_charge_event(payload: object) -> ChargeEvent | None:
    """Read a webhook body. ``None`` means "not a charge, nothing to do".

    Paystack sends transfer, refund and subscription events to the same URL, and
    the right answer to those is a quiet 200. Only a ``charge.success`` that is
    then unreadable raises, because that one is about money.
    """
    if not isinstance(payload, Mapping):
        raise MalformedEvent("the body is not a JSON object")
    if payload.get("event") != "charge.success":
        return None

    data = payload.get("data")
    if not isinstance(data, Mapping):
        raise MalformedEvent("charge.success without a data object")

    fees = data.get("fees")
    return ChargeEvent(
        reference=_text(data, "reference"),
        amount_kobo=_integer(data, "amount"),
        currency=_text(data, "currency"),
        status=_text(data, "status"),
        fees_kobo=None if fees is None else _integer(data, "fees"),
    )


# ---------------------------------------------------------------------------
# The decision
# ---------------------------------------------------------------------------
class Verdict(StrEnum):
    SETTLE = "settle"
    FREEZE = "freeze"


@dataclass(frozen=True, slots=True)
class Decision:
    verdict: Verdict
    # For the alert and the audit row. Never shown to a customer.
    reason: str


def _freeze(reason: str) -> Decision:
    return Decision(Verdict.FREEZE, reason)


def decide(event: ChargeEvent, *, expected_kobo: int) -> Decision:
    """Settle only when every figure is exactly what was expected.

    A ``SETTLE`` verdict guarantees the fee is a credible whole number smaller
    than the payment, so the ledger planner cannot then reject it halfway through
    a transaction.
    """
    if event.currency != CURRENCY:
        return _freeze(f"currency {event.currency!r}, expected {CURRENCY}")
    if event.status != "success":
        return _freeze(f"charge.success carried status {event.status!r}")
    if event.amount_kobo != expected_kobo:
        return _freeze(f"paid {event.amount_kobo} kobo, expected {expected_kobo}")
    if event.fees_kobo is None:
        return _freeze("the provider fee was not reported")
    if not 0 <= event.fees_kobo < event.amount_kobo:
        return _freeze(
            f"provider fee {event.fees_kobo} kobo is not credible for {event.amount_kobo}"
        )
    return Decision(Verdict.SETTLE, "amount, currency and status match")


# ---------------------------------------------------------------------------
# A payment's life
# ---------------------------------------------------------------------------
class PaymentStatus(StrEnum):
    PENDING = "pending"
    SUCCESS = "success"
    FAILED = "failed"
    ABANDONED = "abandoned"
    # Not in the original status list. It exists because "freeze and alert"
    # needs somewhere to put a payment that is neither settled nor failed.
    FROZEN = "frozen"


# A confirmed payment always beats expiry: if the 72-hour job has already marked
# an intent abandoned and the customer's money then arrives, that is a success,
# not an error. The same goes for a retry after a failed attempt on one reference.
#
# SUCCESS and FROZEN have no exits *here*. A success is final — a second delivery
# is stopped by the idempotency insert, not by re-deciding. A frozen payment is
# resolved by a person through an audited action that does not exist yet, and
# code should not be able to un-freeze money on its own.
_ALLOWED: dict[PaymentStatus, frozenset[PaymentStatus]] = {
    PaymentStatus.PENDING: frozenset(
        {
            PaymentStatus.SUCCESS,
            PaymentStatus.FAILED,
            PaymentStatus.ABANDONED,
            PaymentStatus.FROZEN,
        }
    ),
    PaymentStatus.FAILED: frozenset({PaymentStatus.SUCCESS, PaymentStatus.FROZEN}),
    PaymentStatus.ABANDONED: frozenset({PaymentStatus.SUCCESS, PaymentStatus.FROZEN}),
    PaymentStatus.SUCCESS: frozenset(),
    PaymentStatus.FROZEN: frozenset(),
}


class IllegalTransition(Exception):
    """A payment was asked to move somewhere it may not go."""


def transition(current: PaymentStatus, target: PaymentStatus) -> PaymentStatus:
    if target not in _ALLOWED[current]:
        raise IllegalTransition(f"a {current.value} payment cannot become {target.value}")
    return target
