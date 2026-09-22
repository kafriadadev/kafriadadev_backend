"""Paying for verification (VER-03), and the Paystack webhook.

Two very different callers share this file, and the difference is the point:

* An athlete's browser (through the presentation tier) asks for a price, starts
  a checkout, and later reads back what happened. Nothing it says or does can
  make a payment succeed.
* Paystack's servers call the webhook, authenticated by an HMAC over the exact
  bytes they sent. That call — and only that call — is what records money.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Literal

import structlog
from fastapi import APIRouter, HTTPException, Request, Response, status
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field, StrictInt

from kafriada.api.client import client_ip, request_id
from kafriada.api.security import Public, Requires, current_principal
from kafriada.api.throttle import Throttle
from kafriada.contexts.ledger import reversal
from kafriada.contexts.payments import service
from kafriada.contexts.payments.rules import (
    IllegalTransition,
    MalformedEvent,
    PaymentStatus,
    Purpose,
    is_our_reference,
    parse_charge_event,
)
from kafriada.contexts.payments.settlement import settle_charge
from kafriada.security.signing import verify_paystack_signature
from kafriada.settings import get_settings

log = structlog.get_logger(__name__)

router = APIRouter(tags=["payments"])

# A charge.success is a few hundred bytes. Anything vastly larger is not Paystack,
# and the HMAC should not be spent hashing it.
MAX_WEBHOOK_BYTES = 64 * 1024

# What the person is told, not what we store: the internal statuses say more than
# they need to know (a frozen payment is our alarm, not their problem to read).
State = Literal["checking", "confirmed", "failed", "review"]
_STATE: dict[PaymentStatus, State] = {
    PaymentStatus.PENDING: "checking",
    PaymentStatus.SUCCESS: "confirmed",
    PaymentStatus.FAILED: "failed",
    PaymentStatus.ABANDONED: "failed",
    PaymentStatus.FROZEN: "review",
}


class QuoteResponse(BaseModel):
    kuid: str
    purpose: str
    amount_kobo: int
    already_paid: bool


class StartRequest(BaseModel):
    # Required, and only the athlete's own price is offered here. Required also
    # means an empty probe is refused before it can start a real checkout.
    purpose: Literal["stage2_athlete"]


class StartResponse(BaseModel):
    reference: str
    authorization_url: str
    amount_kobo: int


class PaymentResponse(BaseModel):
    reference: str
    purpose: str
    state: State
    amount_kobo: int
    created_at: datetime


@router.get(
    "/payments/quote",
    response_model=QuoteResponse,
    dependencies=[Requires("payment.initiate_self")],
    summary="What verification costs, for the caller's own record",
)
def quote(request: Request) -> QuoteResponse:
    try:
        priced = service.quote(current_principal(request).user_id, Purpose.STAGE2_ATHLETE)
    except service.Refused as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"message": exc.message, "field": None},
        ) from None
    return QuoteResponse(
        kuid=priced.kuid,
        purpose=priced.purpose.value,
        amount_kobo=priced.amount_kobo,
        already_paid=priced.already_paid,
    )


@router.post(
    "/payments",
    response_model=StartResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[
        Requires("payment.initiate_self"),
        # Each call is a request to Paystack and a row that is never deleted.
        Throttle("start_payment"),
    ],
    summary="Start a checkout for the caller's own verification",
)
def start(body: StartRequest, request: Request) -> StartResponse:
    principal = current_principal(request)
    try:
        started = service.start_payment(
            principal,
            Purpose(body.purpose),
            request_id=request_id(request),
            ip_address=client_ip(request),
        )
    except service.Refused as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT
            if exc.code != "no_athlete"
            else status.HTTP_404_NOT_FOUND,
            detail={"message": exc.message, "field": None},
        ) from None
    except service.Unavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"message": exc.message, "field": None},
        ) from None
    return StartResponse(
        reference=started.reference,
        authorization_url=started.authorization_url,
        amount_kobo=started.amount_kobo,
    )


@router.get(
    "/payments/{reference}",
    response_model=PaymentResponse,
    dependencies=[Requires("payment.read_self")],
    summary="One of the caller's own payments, as we recorded it",
)
def read(reference: str, request: Request) -> PaymentResponse:
    principal = current_principal(request)
    found = service.get_payment(principal.user_id, reference) if is_our_reference(reference) else None
    if found is None:
        # Someone else's payment and one that does not exist look identical.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"message": "We could not find that payment.", "field": None},
        )
    return PaymentResponse(
        reference=found.reference,
        purpose=found.purpose,
        state=_STATE[found.status],
        amount_kobo=found.amount_kobo,
        created_at=found.created_at,
    )


class ReversalRequest(BaseModel):
    # Strict: money is whole kobo and nothing else. Lax parsing would accept "100000" and
    # True (as 1) and quietly turn a typo into a ledger line.
    amount_kobo: StrictInt
    reason: str = Field(min_length=1, max_length=reversal.MAX_REASON_CHARS)
    current_password: str = Field(min_length=1, max_length=1024)


class ReversalResponse(BaseModel):
    reference: str
    amount_kobo: int
    gross_kobo: int


class AdminPaymentLookupResponse(BaseModel):
    reference: str
    purpose: str
    status: str
    expected_kobo: int
    payer_name: str
    athlete_kuid: str | None
    athlete_name: str | None
    gross_kobo: int | None
    already_reversed: bool
    # What the reversal screen actually cares about — settled, and not already
    # refunded once.
    reversible: bool


@router.get(
    "/admin/payments/{reference}",
    response_model=AdminPaymentLookupResponse,
    dependencies=[Requires("payment.record_reversal")],
    summary="Look up a payment by reference, to record a refund against it (ADM-04)",
)
def find_payment(reference: str) -> AdminPaymentLookupResponse:
    found = reversal.find_by_reference(reference)
    if found is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail={"message": "We could not find that payment.", "field": None}
        )
    return AdminPaymentLookupResponse(
        reference=found.reference, purpose=found.purpose, status=found.status,
        expected_kobo=found.expected_kobo, payer_name=found.payer_name,
        athlete_kuid=found.athlete_kuid, athlete_name=found.athlete_name,
        gross_kobo=found.gross_kobo, already_reversed=found.already_reversed,
        reversible=found.status == "success" and not found.already_reversed,
    )


@router.post(
    "/admin/payments/{reference}/reversal",
    response_model=ReversalResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Requires("payment.record_reversal")],
    summary="Record a refund that was already made in the Paystack dashboard",
)
def record_reversal(reference: str, body: ReversalRequest, request: Request) -> ReversalResponse:
    """RECORD, not perform. Nothing here can move money: there is no call to Paystack."""
    try:
        done = reversal.record_reversal(
            current_principal(request), reference, body.amount_kobo, body.reason,
            body.current_password, request_id=request_id(request), ip_address=client_ip(request),
        )
    except reversal.NotFound:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail={"message": "We could not find that payment.", "field": None}
        ) from None
    except reversal.Refused as exc:
        fields = {"reason": "reason", "amount": "amount_kobo", "password": "current_password"}
        if exc.code in fields:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"message": exc.message, "field": fields[exc.code]},
            ) from None
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail={"message": exc.message, "field": None}
        ) from None
    return ReversalResponse(
        reference=done.reference, amount_kobo=done.amount_kobo, gross_kobo=done.gross_kobo
    )


@router.post(
    "/payments/webhook/paystack",
    dependencies=[
        Public(
            "Paystack's servers call this with no session; the HMAC-SHA512 "
            "signature over the raw body is the authentication"
        )
    ],
    include_in_schema=False,
    summary="Paystack's event delivery",
)
async def paystack_webhook(request: Request) -> Response:
    """Verify, then parse, then settle. In that order and no other.

    The body is read as raw bytes first: re-serialising parsed JSON changes key
    order and whitespace, and the signature then never matches.

    After a valid signature the answer is 200 for everything a retry cannot
    improve — an event we do not handle, a body we cannot read, a reference that
    is not ours, a delivery already acted on — each with its own log line. The
    exception is a genuine failure to *record* (the database being down):
    that is left to become a 5xx, because Paystack redelivering is exactly what
    we want then, and the transaction rolled back so the redelivery can settle.
    """
    raw = await request.body()
    if len(raw) > MAX_WEBHOOK_BYTES:
        return Response(status_code=413)

    key = get_settings().paystack_secret_key
    if key is None:
        # We cannot tell who is calling. Refusing makes Paystack retry, which is
        # right once the key is set; the alarm is for whoever forgot to set it.
        log.error("paystack_webhook_unverifiable", reason="paystack_secret_key is not set")
        return Response(status_code=status.HTTP_400_BAD_REQUEST)

    if not verify_paystack_signature(
        raw_body=raw,
        header_signature=request.headers.get("x-paystack-signature"),
        secret_key=key.get_secret_value(),
    ):
        # Nothing is parsed, recorded or changed. Deliberately no detail.
        log.warning("paystack_webhook_bad_signature", ip=client_ip(request))
        return Response(status_code=status.HTTP_400_BAD_REQUEST)

    try:
        event = parse_charge_event(json.loads(raw))
    except (ValueError, MalformedEvent) as exc:
        # Signed by Paystack but not shaped like anything we know: their payload
        # changed. A retry will not fix it; a person must look.
        log.error("paystack_webhook_unreadable", error=str(exc)[:200])
        return _ok()
    if event is None:
        return _ok()

    try:
        result = await run_in_threadpool(settle_charge, event, request_id=request_id(request))
    except IllegalTransition as exc:
        # Redelivery cannot change what state a payment is in. Raised inside the
        # transaction, so nothing was written; needs a person.
        log.error("paystack_webhook_illegal_transition", reference=event.reference, error=str(exc))
        return _ok()

    log.info("paystack_webhook_handled", reference=event.reference, outcome=result.outcome.value)
    return _ok()


def _ok() -> Response:
    return Response(
        content='{"status":"ok"}', media_type="application/json", status_code=status.HTTP_200_OK
    )
