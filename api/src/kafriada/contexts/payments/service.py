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
from sqlalchemy.orm import Session

from kafriada.clock import today_in_nigeria
from kafriada.contexts.access.service import Principal
from kafriada.contexts.audit.service import Actor, record
from kafriada.contexts.clubs import verification as club_verification
from kafriada.contexts.identity import service as identity
from kafriada.contexts.payments.provider import ProviderError, build_provider
from kafriada.contexts.payments.rules import (
    PaymentStatus,
    Purpose,
    expected_amount_kobo,
    new_reference,
    transition,
)
from kafriada.contexts.verification import service as verification
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
        if not verification.ready_for_payment(session, user_id):
            # Paying for a review nobody can perform is a refund waiting to happen.
            raise Refused(
                "Add your photo and your ID document first. We will bring you back here to pay.",
                code="no_submission",
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


def start_club_payment(
    principal: Principal,
    club_id: UUID,
    *,
    request_id: str | None = None,
    ip_address: str | None = None,
) -> Started:
    """Start the checkout for a club's verification badge (CLB-04).

    The same path as an athlete's, with a different price and a different beneficiary:
    the payment names the club (``org_id``) and the price is ours, never the caller's.
    The route has proved the caller administers ``club_id``.
    """
    settings = get_settings()
    user_id = principal.user_id
    purpose = Purpose.STAGE2_ORG

    provider = build_provider(settings)
    if provider.name == "none":
        raise Unavailable(NOT_AVAILABLE)

    with transaction() as session:
        email = session.execute(
            text("SELECT email FROM ops.users WHERE id = :id"), {"id": user_id}
        ).scalar_one()
        club = session.execute(
            text("SELECT status, stage FROM identity.organizations WHERE id = :c"), {"c": club_id}
        ).mappings().one_or_none()
    if club is None:
        raise Refused("No such club.", code="no_club")
    if club["status"] != "approved":
        raise Refused("A club must be approved before it can be verified.", code="not_approved")
    if club["stage"] == 2:
        raise Refused("This club is already verified.", code="already_paid")

    amount = expected_amount_kobo(purpose, settings)
    reference = new_reference()
    actor = Actor(user_id=user_id, label=principal.full_name, role="club_admin")

    with money_transaction(reason="start club payment") as session:
        for status, message, code in (
            (PaymentStatus.SUCCESS, "This club has already paid for verification.", "already_paid"),
            (
                PaymentStatus.FROZEN,
                "An earlier payment is being checked by our team. Please wait for us to "
                "contact you before paying again.",
                "under_review",
            ),
        ):
            if session.execute(
                text(
                    "SELECT EXISTS (SELECT 1 FROM money.payments "
                    "WHERE org_id = :c AND status = :s)"
                ),
                {"c": club_id, "s": status.value},
            ).scalar_one():
                raise Refused(message, code=code)
        if not club_verification.ready_for_payment(session, club_id):
            raise Refused(
                "Add your club's registration document or LGA letter first. "
                "We will bring you back here to pay.",
                code="no_submission",
            )
        payment_id = session.execute(
            text(
                """
                INSERT INTO money.payments (reference, purpose, expected_kobo, paid_by, org_id)
                VALUES (:reference, :purpose, :amount, :payer, :club)
                RETURNING id
                """
            ),
            {
                "reference": reference,
                "purpose": purpose.value,
                "amount": amount,
                "payer": user_id,
                "club": club_id,
            },
        ).scalar_one()
        record(
            session,
            actor=actor,
            action="payment.started",
            subject_type="payment",
            subject_id=str(payment_id),
            metadata={
                "reference": reference, "expected_kobo": amount,
                "purpose": purpose.value, "club_id": str(club_id),
            },
            request_id=request_id,
            ip_address=ip_address,
        )

    try:
        initialised = provider.initialise(
            reference=reference,
            amount_kobo=amount,
            email=email or f"{user_id.hex}@{settings.payment_placeholder_email_domain}",
            callback_url=f"{settings.public_base_url.rstrip('/')}/clubs/{club_id}/verify",
        )
    except ProviderError as exc:
        _mark_failed(payment_id, reference, exc, request_id)
        raise Unavailable(NOT_AVAILABLE) from exc

    return Started(
        reference=reference,
        authorization_url=initialised.authorization_url,
        amount_kobo=amount,
    )


@dataclass(frozen=True, slots=True)
class OnBehalfTarget:
    athlete_id: UUID
    athlete_user_id: UUID
    kuid: str


def _athlete_in_lga(session: Session, kuid: str, lga_id: str) -> OnBehalfTarget | None:
    row = session.execute(
        text(
            """
            SELECT a.id AS athlete_id, a.user_id AS athlete_user_id, a.kuid
              FROM identity.athletes a
              JOIN ops.users u ON u.id = a.user_id
             WHERE a.kuid = :kuid AND a.current_lga_id = :lga AND u.anonymised_at IS NULL
            """
        ),
        {"kuid": kuid, "lga": lga_id},
    ).mappings().one_or_none()
    return OnBehalfTarget(**row) if row is not None else None


def _has_payment_for_athlete(
    session: Session, target: OnBehalfTarget, purpose: Purpose, status: PaymentStatus
) -> bool:
    """Either kind of payment counts: this must catch an athlete who already paid
    for themselves online, not only a second assisted attempt."""
    return bool(
        session.execute(
            text(
                """
                SELECT EXISTS (
                    SELECT 1 FROM money.payments
                     WHERE purpose = :purpose AND status = :status
                       AND (on_behalf_of = :athlete_id
                            OR (paid_by = :athlete_user_id AND on_behalf_of IS NULL))
                )
                """
            ),
            {
                "athlete_id": target.athlete_id,
                "athlete_user_id": target.athlete_user_id,
                "purpose": purpose.value,
                "status": status.value,
            },
        ).scalar_one()
    )


def start_payment_on_behalf(
    coordinator: Principal,
    *,
    lga_id: str,
    athlete_kuid: str,
    purpose: Purpose,
    request_id: str | None = None,
    ip_address: str | None = None,
) -> Started:
    """A coordinator starts a checkout for an athlete in their own LGA (CRD-04).

    The ledger lands on the athlete, never the coordinator: ``on_behalf_of`` is
    set on the row, and both ``verification.mark_paid`` and the payment receipt
    read it — the receipt reaches the athlete's phone, not the coordinator's.
    ``coordinator_id`` is tagged too, which is what the two daily caps below
    are counted against.

    **The athlete must belong to the coordinator's own LGA.** The route's
    ``Requires(..., scope="lga")`` only checks that the path's ``lga_id``
    matches a grant the coordinator holds — it has no way to know that the
    *athlete named in the body* is actually in that LGA, so that check is this
    function's to make. Getting it backwards would let any LGA coordinator pay
    for any athlete in the country.

    Bounded by two daily caps per coordinator (count and total naira,
    settings.assisted_payments_per_coordinator_daily /
    assisted_kobo_per_coordinator_daily) — placeholders pending real numbers,
    but the control itself must exist from the first line of this feature:
    nothing here asks the athlete to confirm before their record is charged
    for, so a compromised coordinator session is bounded only by these caps.
    """
    settings = get_settings()

    with transaction() as session:
        target = _athlete_in_lga(session, athlete_kuid, lga_id)
    if target is None:
        raise Refused("No athlete with that ID in this LGA.", code="no_athlete")

    provider = build_provider(settings)
    if provider.name == "none":
        raise Unavailable(NOT_AVAILABLE)

    with transaction() as session:
        email = session.execute(
            text("SELECT email FROM ops.users WHERE id = :id"), {"id": target.athlete_user_id}
        ).scalar_one()

    amount = expected_amount_kobo(purpose, settings)
    reference = new_reference()
    actor = Actor(user_id=coordinator.user_id, label=coordinator.full_name, role="lga_coordinator")

    with money_transaction(reason="start assisted payment") as session:
        if _has_payment_for_athlete(session, target, purpose, PaymentStatus.SUCCESS):
            raise Refused("This athlete has already paid for this.", code="already_paid")
        if _has_payment_for_athlete(session, target, purpose, PaymentStatus.FROZEN):
            raise Refused(
                "This athlete's earlier payment is being checked by our team. "
                "Please wait for us to contact you before paying again.",
                code="under_review",
            )
        if not verification.ready_for_payment(session, target.athlete_user_id):
            raise Refused(
                "This athlete has not uploaded a photo and ID document yet.",
                code="no_submission",
            )

        today = today_in_nigeria()
        used = session.execute(
            text(
                """
                SELECT count(*) AS n, coalesce(sum(expected_kobo), 0) AS kobo
                  FROM money.payments
                 WHERE coordinator_id = :coordinator
                   AND (created_at AT TIME ZONE 'Africa/Lagos')::date = :today
                   AND status != 'failed'
                """
            ),
            {"coordinator": coordinator.user_id, "today": today},
        ).mappings().one()
        if int(used["n"]) >= settings.assisted_payments_per_coordinator_daily:
            raise Refused(
                f"You have started {settings.assisted_payments_per_coordinator_daily} "
                "assisted payments today, the most allowed in one day. Please try again "
                "tomorrow.",
                code="daily_count_cap",
            )
        if int(used["kobo"]) + amount > settings.assisted_kobo_per_coordinator_daily:
            raise Refused(
                "This would take today's assisted payments over the daily naira limit. "
                "Please try again tomorrow.",
                code="daily_amount_cap",
            )

        payment_id = session.execute(
            text(
                """
                INSERT INTO money.payments
                    (reference, purpose, expected_kobo, paid_by, on_behalf_of, coordinator_id)
                VALUES (:reference, :purpose, :amount, :payer, :athlete, :coordinator)
                RETURNING id
                """
            ),
            {
                "reference": reference,
                "purpose": purpose.value,
                "amount": amount,
                "payer": coordinator.user_id,
                "athlete": target.athlete_id,
                "coordinator": coordinator.user_id,
            },
        ).scalar_one()
        record(
            session,
            actor=actor,
            action="payment.started_on_behalf",
            subject_type="payment",
            subject_id=str(payment_id),
            metadata={
                "reference": reference,
                "expected_kobo": amount,
                "purpose": purpose.value,
                "athlete_kuid": target.kuid,
            },
            request_id=request_id,
            ip_address=ip_address,
        )

    try:
        initialised = provider.initialise(
            reference=reference,
            amount_kobo=amount,
            email=email
            or f"{target.athlete_user_id.hex}@{settings.payment_placeholder_email_domain}",
            callback_url=f"{settings.public_base_url.rstrip('/')}/pay",
        )
    except ProviderError as exc:
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


def list_payments(user_id: UUID) -> list[PaymentView]:
    """Every payment the caller has ever started, newest first (ATH-04)."""
    with transaction() as session:
        rows = session.execute(
            text(
                """
                SELECT reference, purpose, status, expected_kobo, created_at
                  FROM money.payments
                 WHERE paid_by = :user_id
                 ORDER BY created_at DESC
                """
            ),
            {"user_id": user_id},
        ).all()
    return [
        PaymentView(
            reference=row.reference,
            purpose=row.purpose,
            status=PaymentStatus(row.status),
            amount_kobo=row.expected_kobo,
            created_at=row.created_at,
        )
        for row in rows
    ]


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
