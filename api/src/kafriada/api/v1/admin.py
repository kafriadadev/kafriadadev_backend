"""Users and roles (ADM-02): grant, revoke, and end someone's sessions.

super_admin only, through ``admin.manage_users``. Granting or revoking asks for
the actor's password again, and role and scope are one action — the service
refuses a scoped role without its scope, whatever the form sends.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field

from kafriada.api.client import client_ip, request_id
from kafriada.api.security import Requires, current_principal
from kafriada.contexts.access import service as access

router = APIRouter(prefix="/admin", tags=["admin"])


class GrantRoleRequest(BaseModel):
    role: str = Field(min_length=1, max_length=40)
    scope_id: str | None = Field(default=None, max_length=64)
    reason: str = Field(min_length=1, max_length=300)
    current_password: str = Field(min_length=1, max_length=1024)


class GrantRoleResponse(BaseModel):
    grant_id: UUID


class RevokeRoleRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=300)
    current_password: str = Field(min_length=1, max_length=1024)


class EndSessionsRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=300)


class EndSessionsResponse(BaseModel):
    sessions_ended: int


def _refused(exc: access.AccessError) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail={"message": exc.message, "field": exc.field},
    )


@router.post(
    "/users/{user_id}/roles",
    response_model=GrantRoleResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Requires("admin.manage_users")],
    summary="Grant a role, with its scope",
)
def grant_role(user_id: UUID, body: GrantRoleRequest, request: Request) -> GrantRoleResponse:
    try:
        grant_id = access.grant_role(
            actor=current_principal(request),
            current_password=body.current_password,
            user_id=user_id,
            role=body.role,
            scope_id=body.scope_id,
            reason=body.reason,
            request_id=request_id(request),
            ip_address=client_ip(request),
        )
    except access.AccessError as exc:
        raise _refused(exc) from None
    return GrantRoleResponse(grant_id=grant_id)


@router.post(
    "/role-grants/{grant_id}/revoke",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Requires("admin.manage_users")],
    summary="Revoke a role grant",
)
def revoke_role(grant_id: UUID, body: RevokeRoleRequest, request: Request) -> None:
    try:
        access.revoke_role(
            actor=current_principal(request),
            current_password=body.current_password,
            grant_id=grant_id,
            reason=body.reason,
            request_id=request_id(request),
            ip_address=client_ip(request),
        )
    except access.AccessError as exc:
        raise _refused(exc) from None


@router.post(
    "/users/{user_id}/sessions/end",
    response_model=EndSessionsResponse,
    dependencies=[Requires("admin.manage_users")],
    summary="End every session a user holds",
)
def end_sessions(user_id: UUID, body: EndSessionsRequest, request: Request) -> EndSessionsResponse:
    try:
        count = access.end_all_sessions(
            actor=current_principal(request),
            user_id=user_id,
            reason=body.reason,
            request_id=request_id(request),
            ip_address=client_ip(request),
        )
    except access.AccessError as exc:
        raise _refused(exc) from None
    return EndSessionsResponse(sessions_ended=count)
