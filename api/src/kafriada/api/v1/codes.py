"""One-time codes: confirming a phone number (AUT-02) and resetting a password (AUT-05).

All four routes are public, and all four are deliberately uninformative. The two
reset routes answer identically whether or not the number is registered — a
screen that says "no such account" is a screen that tells anyone whether a
person is registered with KAFRIADA.

Confirming a code signs the person in: holding the phone is precisely what a
session is meant to prove.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import BaseModel, Field

from kafriada.api.client import client_ip, request_id, user_agent
from kafriada.api.security import Public
from kafriada.contexts.access import service as access
from kafriada.contexts.identity import service as identity

router = APIRouter(tags=["codes"])


class PhoneRequest(BaseModel):
    phone: str = Field(min_length=1, max_length=40)


class CodeSentResponse(BaseModel):
    """Says only when another code may be asked for. Never whether one was sent."""

    resend_in: int
    daily_limit_reached: bool = False


class ConfirmPhoneRequest(BaseModel):
    phone: str = Field(min_length=1, max_length=40)
    code: str = Field(min_length=1, max_length=12)


class ConfirmedResponse(BaseModel):
    kuid: str | None
    token: str
    idle_expires_at: datetime
    absolute_expires_at: datetime
    is_staff: bool


class ResetPasswordRequest(BaseModel):
    phone: str = Field(min_length=1, max_length=40)
    code: str = Field(min_length=1, max_length=12)
    new_password: str = Field(min_length=1, max_length=1024)


def _code_refused(exc: access.CodeRefused) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail={"message": exc.message, "field": "code"},
    )


@router.post(
    "/phone/code",
    response_model=CodeSentResponse,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Public("someone confirming their phone has no session yet")],
    summary="Send another phone confirmation code",
)
def send_phone_code(body: PhoneRequest, request: Request) -> CodeSentResponse:
    outcome = access.request_phone_code(
        body.phone,
        request_id=request_id(request),
        ip_address=client_ip(request),
    )
    return CodeSentResponse(
        resend_in=outcome.resend_in, daily_limit_reached=outcome.daily_limit_reached
    )


@router.post(
    "/phone/confirm",
    response_model=ConfirmedResponse,
    dependencies=[Public("the code itself is the credential here")],
    summary="Confirm a phone number with its code, and sign in",
)
def confirm_phone(body: ConfirmPhoneRequest, request: Request) -> ConfirmedResponse:
    try:
        confirmed = access.confirm_phone(
            body.phone,
            body.code,
            request_id=request_id(request),
            ip_address=client_ip(request),
            user_agent=user_agent(request),
        )
    except access.CodeRefused as exc:
        raise _code_refused(exc) from None

    athlete = identity.athlete_for_user(confirmed.user_id)
    return ConfirmedResponse(
        kuid=athlete.kuid if athlete else None,
        token=confirmed.session.token,
        idle_expires_at=confirmed.session.idle_expires_at,
        absolute_expires_at=confirmed.session.absolute_expires_at,
        is_staff=confirmed.session.is_staff,
    )


@router.post(
    "/password-reset/code",
    response_model=CodeSentResponse,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Public("somebody who cannot sign in cannot be signed in to ask")],
    summary="Send a password reset code",
)
def send_reset_code(body: PhoneRequest, request: Request) -> CodeSentResponse:
    outcome = access.request_password_reset(
        body.phone,
        request_id=request_id(request),
        ip_address=client_ip(request),
    )
    # Always the same answer, registered or not.
    return CodeSentResponse(resend_in=outcome.resend_in)


@router.post(
    "/password-reset/confirm",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Public("the code is the credential; that is the point of a reset")],
    summary="Set a new password with a reset code",
)
def reset_password(body: ResetPasswordRequest, request: Request) -> Response:
    try:
        access.reset_password(
            body.phone,
            body.code,
            body.new_password,
            request_id=request_id(request),
            ip_address=client_ip(request),
        )
    except access.CodeRefused as exc:
        raise _code_refused(exc) from None
    except access.AccessError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"message": exc.message, "field": exc.field},
        ) from None
    return Response(status_code=status.HTTP_204_NO_CONTENT)
