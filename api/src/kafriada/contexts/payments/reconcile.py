"""Catching what the webhook missed, and closing what will never be paid.

Webhooks fail: Paystack retries for a while and then stops, a deploy drops a request, a
signing-key mix-up rejects a good delivery. Somebody then holds a receipt and we hold a
``pending`` row. Two jobs close that gap, and they are deliberately built on the same
code the webhook uses.

**Reconciliation asks Paystack, then hands the answer to** :func:`settle_charge`. It
does not have its own rules. The same strict reader parses the answer, the same
:func:`decide` compares it to the price recorded on the payment, the same idempotency
key stops a payment that the webhook *also* delivers from being recorded twice. A
mismatch freezes for a human exactly as it does there.

**It may only ever confirm a credit.** Paystack saying "abandoned" or "failed" changes
nothing here — a payment that is not yet paid is simply not yet paid, and we are not the
judge of that — and nothing in this module reverses, refunds or cancels money. Only a
``success`` is acted on, and only through settlement.

**Expiry is the last resort, after asking.** A payment with no charge after 72 hours is
marked ``abandoned`` — but only once Paystack has been asked and has not said it was paid.
If Paystack cannot be reached, the payment is left alone: expiring what we could not check
is how a paid customer ends up with a closed payment.
"""

from __future__ import annotations

from dataclasses import dataclass

import structlog
from sqlalchemy import text

from kafriada.contexts.audit.service import Actor, record
from kafriada.contexts.payments.provider import (
    NotConfigured,
    PaymentProvider,
    ProviderError,
    build_provider,
)
from kafriada.contexts.payments.rules import PaymentStatus, transition
from kafriada.contexts.payments.settlement import Outcome, settle_charge
from kafriada.db.engine import money_transaction, transaction

log = structlog.get_logger(__name__)

SOURCE = "reconciliation"


@dataclass(frozen=True, slots=True)
class ReconcileResult:
    checked: int = 0
    settled: int = 0  # confirmed a payment the webhook never delivered
    frozen: int = 0  # Paystack's figures did not match ours; a person looks
    not_paid: int = 0  # Paystack does not say it was paid; nothing changed
    errors: int = 0
    skipped: bool = False  # no provider configured, nothing was attempted

    def summary(self) -> dict[str, int | bool]:
        return {
            "checked": self.checked, "settled": self.settled, "frozen": self.frozen,
            "not_paid": self.not_paid, "errors": self.errors, "skipped": self.skipped,
        }


def _candidates(sql: str, params: dict[str, object]) -> list[tuple[str, str]]:
    with transaction() as session:
        return [(str(r.id), str(r.reference)) for r in session.execute(text(sql), params)]


def _confirm(provider: PaymentProvider, reference: str) -> Outcome | None:
    """Ask Paystack; if — and only if — it says paid, settle. None means "not paid"."""
    event = provider.verify(reference)
    if event is None or event.status != "success":
        return None
    if event.reference != reference:
        # An answer about some other payment is not an answer about this one.
        log.error("reconcile_reference_mismatch", asked=reference, got=event.reference)
        raise ProviderError("provider answered about a different reference", transient=False)
    return settle_charge(event, source=SOURCE).outcome


def reconcile(
    *,
    provider: PaymentProvider | None = None,
    limit: int = 100,
    min_age_minutes: int = 10,
) -> ReconcileResult:
    """Verify recent unpaid payments with Paystack and settle any it says were paid.

    Pending payments older than ``min_age_minutes`` (a customer is still typing a card
    number before that), plus attempts marked failed or abandoned in the last three
    days — a late payment on an abandoned attempt is a success, not an error.
    """
    provider = provider or build_provider()
    if provider.name == "none":
        return ReconcileResult(skipped=True)

    rows = _candidates(
        """
        SELECT id, reference FROM money.payments
         WHERE (status = 'pending' AND created_at < now() - make_interval(mins => :age))
            OR (status IN ('failed', 'abandoned') AND created_at > now() - interval '3 days')
         ORDER BY (status = 'pending') DESC, created_at
         LIMIT :n
        """,
        {"age": min_age_minutes, "n": limit},
    )

    checked = settled = frozen = not_paid = errors = 0
    for _payment_id, reference in rows:
        try:
            outcome = _confirm(provider, reference)
        except NotConfigured:
            return ReconcileResult(skipped=True)
        except ProviderError as exc:
            errors += 1
            log.warning("reconcile_check_failed", reference=reference, error=exc.message,
                        transient=exc.transient)
            continue
        checked += 1
        if outcome is Outcome.SETTLED:
            settled += 1
            # The webhook should have done this. Worth knowing when it did not.
            log.warning("reconciliation_settled_missed_webhook", reference=reference)
        elif outcome is Outcome.FROZEN:
            frozen += 1
        else:
            not_paid += 1

    result = ReconcileResult(checked, settled, frozen, not_paid, errors)
    if any((settled, frozen, errors)):
        log.info("reconcile_pass", **result.summary())
    return result


@dataclass(frozen=True, slots=True)
class ExpireResult:
    expired: int = 0
    settled: int = 0  # turned out to have been paid after all
    left_alone: int = 0  # could not be checked, so not expired
    skipped: bool = False

    def summary(self) -> dict[str, int | bool]:
        return {"expired": self.expired, "settled": self.settled,
                "left_alone": self.left_alone, "skipped": self.skipped}


def expire_stale(
    *, provider: PaymentProvider | None = None, hours: int = 72, limit: int = 200
) -> ExpireResult:
    """Mark ``pending`` payments older than ``hours`` as ``abandoned`` — after asking Paystack."""
    provider = provider or build_provider()
    if provider.name == "none":
        return ExpireResult(skipped=True)

    rows = _candidates(
        """
        SELECT id, reference FROM money.payments
         WHERE status = 'pending' AND created_at < now() - make_interval(hours => :h)
         ORDER BY created_at LIMIT :n
        """,
        {"h": hours, "n": limit},
    )

    expired = settled = left_alone = 0
    for payment_id, reference in rows:
        try:
            outcome = _confirm(provider, reference)
        except NotConfigured:
            return ExpireResult(skipped=True)
        except ProviderError as exc:
            left_alone += 1
            log.warning("expiry_check_failed", reference=reference, error=exc.message)
            continue
        if outcome is Outcome.SETTLED:
            settled += 1
            continue
        if outcome is Outcome.FROZEN:
            continue  # money moved and a person must look: certainly not "abandoned"

        with money_transaction(reason="expire an unpaid payment") as session:
            moved = session.execute(
                text(
                    "UPDATE money.payments SET status = :abandoned "
                    "WHERE id = :id AND status = :pending RETURNING id"
                ),
                {
                    "abandoned": transition(PaymentStatus.PENDING, PaymentStatus.ABANDONED).value,
                    "pending": PaymentStatus.PENDING.value,
                    "id": payment_id,
                },
            ).first()
            if moved:
                record(
                    session,
                    actor=Actor.system("payment_expiry"),
                    action="payment.abandoned",
                    subject_type="payment",
                    subject_id=payment_id,
                    metadata={"reference": reference, "after_hours": hours},
                )
                expired += 1

    result = ExpireResult(expired, settled, left_alone)
    if any((expired, settled, left_alone)):
        log.info("expiry_pass", **result.summary())
    return result
