"""Signing in, signing out, and the caller's own account (AUT-04, ATH-01).

The presentation tier posts the phone and password here, receives an opaque
token once, and keeps it in an httpOnly cookie. Every later call forwards it as
a bearer token. The token never reaches browser JavaScript.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import BaseModel, Field

from kafriada.api.client import client_ip, request_id, user_agent
from kafriada.api.security import Public, SignedIn, current_principal
from kafriada.api.throttle import Throttle
from kafriada.contexts.access import service as access
from kafriada.contexts.identity import service as identity

router = APIRouter(tags=["sessions"])


class SignInRequest(BaseModel):
    phone: str = Field(min_length=1, max_length=40)
    password: str = Field(min_length=1, max_length=1024)
    # Only read when the account has no email on file: it is added, and a
    # confirmation code is sent to it.
    email: str | None = Field(default=None, max_length=254)


class SessionResponse(BaseModel):
    token: str
    idle_expires_at: datetime
    absolute_expires_at: datetime
    is_staff: bool
    # False sends the caller to the confirm screen (AUT-04's own note). Signing
    # in still works: the ID exists, only the confirmation is outstanding.
    phone_verified: bool


class RoleGrantOut(BaseModel):
    grant_id: UUID
    role: str
    scope_kind: str
    scope_id: str | None
    scope_name: str | None


class MeResponse(BaseModel):
    """What a signed-in person sees about themselves."""

    full_name: str
    phone: str  # masked — the full number is never sent back out
    kuid: str | None
    lga_name: str | None
    is_staff: bool
    phone_verified: bool
    email_verified: bool
    roles: list[RoleGrantOut]
    idle_expires_at: datetime
    absolute_expires_at: datetime


@router.post(
    "/sessions",
    response_model=SessionResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[
        Public("signing in is how a session begins"),
        # Per account, a lock already stops repeated wrong passwords. This stops
        # one password being tried against thousands of different accounts,
        # which trips no account's lock at all.
        Throttle("sign_in"),
    ],
    summary="Sign in with phone and password",
)
def sign_in(body: SignInRequest, request: Request) -> SessionResponse:
    try:
        issued = access.sign_in(
            body.phone,
            body.password,
            email=body.email,
            ip_address=client_ip(request),
            user_agent=user_agent(request),
            request_id=request_id(request),
        )
    except access.EmailUnconfirmed as exc:
        # The password was right, so the reason can be given.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": "Confirm your email to sign in. We have sent a code to "
                f"{exc.email_masked}.",
                "field": None,
                "reason": "email_unconfirmed",
                "email_masked": exc.email_masked,
            },
        ) from None
    except access.EmailMissing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": "Add your email address. We will send a code to confirm it.",
                "field": "email",
                "reason": "email_missing",
            },
        ) from None
    except access.AccessError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"message": exc.message, "field": exc.field},
        ) from None
    except access.SignInRefused as exc:
        # No field: pointing at the phone or the password would say which was wrong.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"message": exc.message, "field": None},
        ) from None
    return SessionResponse(
        token=issued.token,
        phone_verified=issued.phone_verified,
        idle_expires_at=issued.idle_expires_at,
        absolute_expires_at=issued.absolute_expires_at,
        is_staff=issued.is_staff,
    )


@router.delete(
    "/sessions/current",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[SignedIn("anyone may end their own session")],
    summary="Sign out",
)
def sign_out(request: Request) -> Response:
    access.sign_out(
        current_principal(request),
        request_id=request_id(request),
        ip_address=client_ip(request),
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/me",
    response_model=MeResponse,
    dependencies=[SignedIn("a signed-in person may see their own account")],
    summary="The caller's own account",
)
def me(request: Request) -> MeResponse:
    principal = current_principal(request)
    account = access.describe_account(principal.user_id)
    athlete = identity.athlete_for_user(principal.user_id)
    return MeResponse(
        full_name=account.full_name,
        phone=account.phone_masked,
        kuid=athlete.kuid if athlete else None,
        lga_name=athlete.lga_name if athlete else None,
        is_staff=account.is_staff,
        phone_verified=account.phone_verified,
        email_verified=account.email_verified,
        roles=[
            RoleGrantOut(
                grant_id=g.grant_id,
                role=g.role,
                scope_kind=g.scope_kind,
                scope_id=g.scope_id,
                scope_name=g.scope_name,
            )
            for g in account.roles
        ],
        idle_expires_at=principal.idle_expires_at,
        absolute_expires_at=principal.absolute_expires_at,
    )
