"""Starting a payment, and reading one back (VER-03).

**The row comes first, the provider second.** A ``pending`` payment is committed
before Paystack is called, so a webhook can never arrive for a reference we have
not recorded, and a crash between the two leaves a pending row that the 72-hour
sweep will expire — not a customer who paid for something we have no trace of.

**Nothing here decides that money moved.** Starting a checkout hands back an
address. Whether anything was paid is the signed webhook's to say
(``settlement.py``); reading a payment back only reports what that path wrote.
The browser is never asked, and the customer's return to the site proves nothing.

**The price is ours.** The amount is read from configuration at this moment and
recorded on the row; the webhook is later compared against the recorded figure,
never against what the request or the provider claims.

**Own account only.** The payer is the signed-in athlete and the payment is for
their own record. Paying for someone else is the coordinator flow (2.4) and has
its own rules, its own permission and its own daily caps.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

import structlog
from sqlalchemy import text

from kafriada.contexts.access.service import Principal
from kafriada.contexts.audit.service import Actor, record
from kafriada.contexts.identity import service as identity
from kafriada.contexts.payments.provider import ProviderError, build_provider
from kafriada.contexts.payments.rules import (
    PaymentStatus,
    Purpose,
    expected_amount_kobo,
    new_reference,
    transition,
)
from kafriada.db.engine import money_transaction, transaction
from kafriada.settings import get_settings

log = structlog.get_logger(__name__)


class Refused(Exception):
    """A payment cannot be started, and the person can be told why."""

    def __init__(self, message: str, *, code: str) -> None:
        super().__init__(message)
        self.message = message
        self.code = code


class Unavailable(Exception):
    """Paystack could not be reached or refused. Nothing was charged."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


NOT_AVAILABLE = "Payments are temporarily unavailable. Nothing has been charged. Please try again soon."


@dataclass(frozen=True, slots=True)
class Quote:
    kuid: str
    purpose: Purpose
    amount_kobo: int
    # A settled payment for this record already exists.
    already_paid: bool


@dataclass(frozen=True, slots=True)
class Started:
    reference: str
    authorization_url: str
    amount_kobo: int


@dataclass(frozen=True, slots=True)
class PaymentView:
    reference: str
    purpose: str
    status: PaymentStatus
    amount_kobo: int
    created_at: datetime


def quote(user_id: UUID, purpose: Purpose) -> Quote:
    athlete = identity.athlete_for_user(user_id)
    if athlete is None:
        raise Refused("Only a registered athlete can pay for verification.", code="no_athlete")
    with transaction() as session:
        settled = _has_payment(session, user_id, purpose, PaymentStatus.SUCCESS)
    return Quote(
        kuid=athlete.kuid,
        purpose=purpose,
        amount_kobo=expected_amount_kobo(purpose, get_settings()),
        already_paid=settled,
    )


def start_payment(
    principal: Principal,
    purpose: Purpose,
    *,
    request_id: str | None = None,
    ip_address: str | None = None,
) -> Started:
    settings = get_settings()
    user_id = principal.user_id

    athlete = identity.athlete_for_user(user_id)
    if athlete is None:
        raise Refused("Only a registered athlete can pay for verification.", code="no_athlete")

    provider = build_provider(settings)
    if provider.name == "none":
        # Before any row exists: an unconfigured environment must not fill the
        # payments table with attempts that could never have worked.
        raise Unavailable(NOT_AVAILABLE)

    with transaction() as session:
        email = session.execute(
            text("SELECT email FROM ops.users WHERE id = :id"), {"id": user_id}
        ).scalar_one()

    amount = expected_amount_kobo(purpose, settings)
    reference = new_reference()
    actor = Actor(user_id=user_id, label=principal.full_name, role="athlete")

    with money_transaction(reason="start payment") as session:
        if _has_payment(session, user_id, purpose, PaymentStatus.SUCCESS):
            raise Refused("You have already paid for this.", code="already_paid")
        if _has_payment(session, user_id, purpose, PaymentStatus.FROZEN):
            raise Refused(
                "Your earlier payment is being checked by our team. "
                "Please wait for us to contact you before paying again.",
                code="under_review",
            )
        payment_id = session.execute(
            text(
                """
                INSERT INTO money.payments (reference, purpose, expected_kobo, paid_by)
                VALUES (:reference, :purpose, :amount, :payer)
                RETURNING id
                """
            ),
            {
                "reference": reference,
                "purpose": purpose.value,
                "amount": amount,
                "payer": user_id,
            },
        ).scalar_one()
        record(
            session,
            actor=actor,
            action="payment.started",
            subject_type="payment",
            subject_id=str(payment_id),
            metadata={"reference": reference, "expected_kobo": amount, "purpose": purpose.value},
            request_id=request_id,
            ip_address=ip_address,
        )

    # No transaction is open across the network call.
    try:
        initialised = provider.initialise(
            reference=reference,
            amount_kobo=amount,
            email=email or f"{user_id.hex}@{settings.payment_placeholder_email_domain}",
            callback_url=f"{settings.public_base_url.rstrip('/')}/pay",
        )
    except ProviderError as exc:
        # The customer never received an address, so nothing they do can pay
        # this reference. (A late charge on it would still settle: failed → success.)
        _mark_failed(payment_id, reference, exc, request_id)
        raise Unavailable(NOT_AVAILABLE) from exc

    return Started(
        reference=reference,
        authorization_url=initialised.authorization_url,
        amount_kobo=amount,
    )


def get_payment(user_id: UUID, reference: str) -> PaymentView | None:
    """One of the caller's own payments. Anyone else's is simply not found."""
    with transaction() as session:
        row = session.execute(
            text(
                """
                SELECT reference, purpose, status, expected_kobo, created_at
                  FROM money.payments
                 WHERE reference = :reference AND paid_by = :user_id
                """
            ),
            {"reference": reference, "user_id": user_id},
        ).one_or_none()
    if row is None:
        return None
    return PaymentView(
        reference=row.reference,
        purpose=row.purpose,
        status=PaymentStatus(row.status),
        amount_kobo=row.expected_kobo,
        created_at=row.created_at,
    )


def _has_payment(session, user_id: UUID, purpose: Purpose, status: PaymentStatus) -> bool:  # type: ignore[no-untyped-def]
    return bool(
        session.execute(
            text(
                """
                SELECT EXISTS (
                    SELECT 1 FROM money.payments
                     WHERE paid_by = :user_id AND on_behalf_of IS NULL
                       AND purpose = :purpose AND status = :status
                )
                """
            ),
            {"user_id": user_id, "purpose": purpose.value, "status": status.value},
        ).scalar_one()
    )


def _mark_failed(
    payment_id: UUID, reference: str, error: ProviderError, request_id: str | None
) -> None:
    with money_transaction(reason="payment could not be started") as session:
        # Guarded on status: a webhook cannot have settled this yet, but if it
        # somehow has, the row is left alone rather than overwritten.
        moved = session.execute(
            text(
                "UPDATE money.payments SET status = :failed "
                "WHERE id = :id AND status = :pending RETURNING id"
            ),
            {
                "failed": transition(PaymentStatus.PENDING, PaymentStatus.FAILED).value,
                "pending": PaymentStatus.PENDING.value,
                "id": payment_id,
            },
        ).first()
        if moved:
            record(
                session,
                actor=Actor.system("payment_start"),
                action="payment.failed",
                subject_type="payment",
                subject_id=str(payment_id),
                metadata={
                    "reference": reference,
                    "reason": "the provider did not start a checkout",
                    "transient": error.transient,
                },
                request_id=request_id,
            )
    log.error(
        "payment_start_failed",
        reference=reference,
        transient=error.transient,
        error=error.message,
    )
