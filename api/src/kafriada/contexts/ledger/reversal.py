"""Recording a refund that was made by hand in the Paystack dashboard (ADM-04).

**KAFRIADA cannot send money, and this does not change that.** There is no payout path
and no code here that asks Paystack to do anything. A refund happens in Paystack's own
dashboard, by a person with access to it; afterwards a super administrator records that
it happened, so the ledger matches the bank. The verb is *record*, not *refund*.

Because it is the one place a person types an amount into the ledger, it is guarded more
heavily than anything around it:

* the actor re-enters their **password** (the same check, and the same lockout accounting,
  as granting a role);
* a **reason** is mandatory and is kept with the ledger line itself, permanently;
* it can only be recorded against a **settled** payment, **once** (a second refund on the
  same payment is a conversation, not a button — the ledger's unique key refuses it), and
  never for **more than the payment**;
* it writes an **audit** row in the same transaction, on the money role — the only role
  that may write the ledger — and the line can never be edited or deleted afterwards.

A reversal does not withdraw the athlete's verification. Taking back a badge is its own
decision with its own screen (ADM-03); refunding money and revoking a badge are separate
things that sometimes happen together and sometimes do not.
"""

from __future__ import annotations

from dataclasses import dataclass

import structlog
from sqlalchemy import text

from kafriada.contexts.access import service as access
from kafriada.contexts.access.service import Principal
from kafriada.contexts.audit.service import Actor, record
from kafriada.contexts.ledger.entries import InvalidAmount, plan_reversal
from kafriada.db.engine import money_transaction

log = structlog.get_logger(__name__)

MAX_REASON_CHARS = 1_000


class Refused(Exception):
    """The reversal cannot be recorded, and the person can be told why."""

    def __init__(self, message: str, *, code: str) -> None:
        super().__init__(message)
        self.message = message
        self.code = code


class NotFound(Exception):
    """No such payment."""


@dataclass(frozen=True, slots=True)
class Recorded:
    reference: str
    amount_kobo: int
    gross_kobo: int


def record_reversal(
    actor: Principal,
    reference: str,
    amount_kobo: int,
    reason: str,
    current_password: str,
    *,
    request_id: str | None = None,
    ip_address: str | None = None,
) -> Recorded:
    reason = reason.strip()
    if not reason:
        raise Refused("Say why the refund was made. It is kept permanently.", code="reason")
    if len(reason) > MAX_REASON_CHARS:
        raise Refused(f"Keep the reason under {MAX_REASON_CHARS} characters.", code="reason")
    if isinstance(amount_kobo, bool) or not isinstance(amount_kobo, int) or amount_kobo <= 0:
        raise Refused("Enter the amount refunded, in kobo, as a whole number.", code="amount")

    try:
        access.reauthenticate(actor, current_password, request_id=request_id, ip_address=ip_address)
    except access.AccessError as exc:
        raise Refused(exc.message, code="password") from exc

    with money_transaction(reason="record a refund made in the provider dashboard") as session:
        payment = session.execute(
            text("SELECT id, status FROM money.payments WHERE reference = :ref FOR UPDATE"),
            {"ref": reference},
        ).one_or_none()
        if payment is None:
            raise NotFound()
        if payment.status != "success":
            raise Refused("Only a settled payment can have a refund recorded.", code="not_settled")

        gross = session.execute(
            text(
                "SELECT amount_kobo FROM money.ledger_entries "
                "WHERE payment_id = :p AND source = 'paystack'"
            ),
            {"p": payment.id},
        ).scalar_one()
        already = session.execute(
            text(
                "SELECT 1 FROM money.ledger_entries WHERE payment_id = :p AND source = 'reversal'"
            ),
            {"p": payment.id},
        ).first()
        if already:
            raise Refused("A refund is already recorded against this payment.", code="already")
        try:
            line = plan_reversal(gross_kobo=gross, amount_kobo=amount_kobo)
        except InvalidAmount as exc:
            raise Refused(str(exc), code="amount") from exc

        session.execute(
            text(
                """
                INSERT INTO money.ledger_entries
                    (payment_id, direction, source, amount_kobo, note, recorded_by)
                VALUES (:p, :direction, :source, :amount, :note, :by)
                """
            ),
            {
                "p": payment.id,
                "direction": line.direction.value,
                "source": line.source.value,
                "amount": line.amount_kobo,
                "note": reason,
                "by": actor.user_id,
            },
        )
        record(
            session,
            actor=Actor(user_id=actor.user_id, label=actor.full_name, role="super_admin"),
            action="payment.reversal_recorded",
            subject_type="payment",
            subject_id=str(payment.id),
            metadata={
                "reference": reference,
                "amount_kobo": line.amount_kobo,
                "gross_kobo": gross,
                "reason": reason,
            },
            request_id=request_id,
            ip_address=ip_address,
        )
    log.warning("reversal_recorded", reference=reference, amount_kobo=amount_kobo)
    return Recorded(reference=reference, amount_kobo=amount_kobo, gross_kobo=gross)
