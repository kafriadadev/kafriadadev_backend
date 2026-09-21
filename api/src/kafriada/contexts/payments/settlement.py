"""Turning a Paystack ``charge.success`` into ledger lines — or into a freeze.

The one place a stranger's HTTP request can cause money to be recorded, so it is
small and each step is there for a reason that has already cost somebody money.

**One transaction, on the money role.** The idempotency row, the two ledger
lines, the status change and the audit row commit together or not at all. Either
path — settle or freeze — is a single commit; there is no state in which the
ledger says paid and the payment says pending.

**The duplicate check is one statement.** ``INSERT ... ON CONFLICT DO NOTHING
RETURNING``: the delivery that gets a row back is first and may write; every
other copy, however many arrive in the same instant, gets nothing back and
returns without touching anything. A ``SELECT`` followed by an ``INSERT`` would
let all five copies read "not seen" and all five settle.

**A mismatch freezes; it never approves.** The verdict comes from
:func:`~kafriada.contexts.payments.rules.decide`, against the price recorded on
the payment when it was created. Real money moved, so the payment is marked
``frozen``, an audit row is written and an error-level log is raised for a person
to look at. The alert is logged *after* the commit: a log line saying "frozen"
for a transaction that then rolled back would be a lie.

Not here: the HTTP route, signature verification (both run before this) and the
call that creates a payment (after it).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

import structlog
from sqlalchemy import text

from kafriada.contexts.audit.service import Actor, record
from kafriada.contexts.ledger.entries import plan_settlement
from kafriada.contexts.payments.rules import (
    ChargeEvent,
    PaymentStatus,
    Verdict,
    decide,
    is_our_reference,
    transition,
)
from kafriada.contexts.verification import service as verification
from kafriada.db.engine import money_transaction

log = structlog.get_logger(__name__)

PROVIDER = "paystack"


class Outcome(StrEnum):
    SETTLED = "settled"
    FROZEN = "frozen"
    # This delivery was not the first for its reference. Nothing was written.
    DUPLICATE = "duplicate"
    # Not one of ours (another product on the same Paystack account). Ignored.
    IGNORED = "ignored"
    # Ours by shape but no such payment. Nothing was written, deliberately: a
    # redelivery may arrive after the row is visible, and must not be pre-empted.
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class Settlement:
    outcome: Outcome
    payment_id: UUID | None = None
    reason: str | None = None
    # Only for SETTLED: did the payer's verification move to review? False means money
    # arrived for someone with no draft to move, which a person must look at.
    verification_moved: bool = True


def _event_key(event: ChargeEvent) -> str:
    return f"charge.success:{event.reference}"


def settle_charge(event: ChargeEvent, *, request_id: str | None = None) -> Settlement:
    """Act on one delivery of a ``charge.success``. Safe to call any number of times."""
    if not is_our_reference(event.reference):
        return Settlement(Outcome.IGNORED)

    with money_transaction(reason="settle paystack charge") as session:
        found = session.execute(
            text("SELECT id FROM money.payments WHERE reference = :ref"),
            {"ref": event.reference},
        ).first()
        if found is None:
            result = Settlement(Outcome.UNKNOWN)
        else:
            payment_id: UUID = found.id
            first = session.execute(
                text(
                    """
                    INSERT INTO money.webhook_events (provider, event_key, payment_id)
                    VALUES (:provider, :key, :payment_id)
                    ON CONFLICT (provider, event_key) DO NOTHING
                    RETURNING payment_id
                    """
                ),
                {"provider": PROVIDER, "key": _event_key(event), "payment_id": payment_id},
            ).first()
            if first is None:
                return Settlement(Outcome.DUPLICATE, payment_id)

            # Only the first delivery gets here. The lock orders it against any
            # other writer of this payment (the abandon sweep, a reviewer).
            row = session.execute(
                text(
                    "SELECT status, expected_kobo FROM money.payments "
                    "WHERE id = :id FOR UPDATE"
                ),
                {"id": payment_id},
            ).one()
            decision = decide(event, expected_kobo=row.expected_kobo)
            actor = Actor.system("paystack_webhook")
            details = {
                "reference": event.reference,
                "paid_kobo": event.amount_kobo,
                "expected_kobo": row.expected_kobo,
                "fee_kobo": event.fees_kobo,
                "currency": event.currency,
            }

            if decision.verdict is Verdict.SETTLE:
                new_status = transition(PaymentStatus(row.status), PaymentStatus.SUCCESS)
                assert event.fees_kobo is not None  # decide() refuses a missing fee
                for line in plan_settlement(
                    gross_kobo=event.amount_kobo, provider_fee_kobo=event.fees_kobo
                ):
                    session.execute(
                        text(
                            """
                            INSERT INTO money.ledger_entries
                                (payment_id, direction, source, amount_kobo)
                            VALUES (:payment_id, :direction, :source, :amount)
                            """
                        ),
                        {
                            "payment_id": payment_id,
                            "direction": line.direction.value,
                            "source": line.source.value,
                            "amount": line.amount_kobo,
                        },
                    )
                moved = verification.mark_paid(session, payment_id) is not None
                action = "payment.settled"
                result = Settlement(Outcome.SETTLED, payment_id, verification_moved=moved)
            else:
                new_status = transition(PaymentStatus(row.status), PaymentStatus.FROZEN)
                details["reason"] = decision.reason
                action = "payment.frozen"
                result = Settlement(Outcome.FROZEN, payment_id, decision.reason)

            session.execute(
                text("UPDATE money.payments SET status = :status WHERE id = :id"),
                {"status": new_status.value, "id": payment_id},
            )
            record(
                session,
                actor=actor,
                action=action,
                subject_type="payment",
                subject_id=str(payment_id),
                metadata=details,
                request_id=request_id,
            )

    # Past the commit: only now is it true.
    if result.outcome is Outcome.FROZEN:
        log.error(
            "payment_frozen",
            reference=event.reference,
            payment_id=str(result.payment_id),
            paid_kobo=event.amount_kobo,
            reason=result.reason,
        )
    elif result.outcome is Outcome.SETTLED and not result.verification_moved:
        log.error(
            "payment_without_submission",
            reference=event.reference,
            payment_id=str(result.payment_id),
        )
    elif result.outcome is Outcome.UNKNOWN:
        log.error("payment_reference_unknown", reference=event.reference)
    return result
