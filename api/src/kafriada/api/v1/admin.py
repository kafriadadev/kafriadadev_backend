"""Users and roles (ADM-02): grant, revoke, and end someone's sessions.

super_admin only, through ``admin.manage_users``. Granting or revoking asks for
the actor's password again, and role and scope are one action — the service
refuses a scoped role without its scope, whatever the form sends.
"""

from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request, status
from pydantic import BaseModel, Field

from kafriada.api.client import client_ip, request_id
from kafriada.api.security import Requires, current_principal
from kafriada.contexts.access import service as access
from kafriada.contexts.admin import data_requests, rollout
from kafriada.contexts.admin import service as directory

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


# ---------------------------------------------------------------------------
# What the console reads (ADM-01, ADM-02, ADM-06, and clubs awaiting approval)
# ---------------------------------------------------------------------------
class OverviewResponse(BaseModel):
    collected_kobo: int
    payments: int
    unresolved: int
    ledger_ok: bool | None
    ledger_checked_at: datetime | None
    registered: int
    paid: int
    conversion_percent: float
    clubs: int
    verified_clubs: int
    clubs_waiting: int
    review_median_hours: float | None
    live_lgas: int


class GrantOut(BaseModel):
    grant_id: UUID
    role: str
    scope_kind: str
    scope_id: str | None
    scope_name: str | None


class UserOut(BaseModel):
    user_id: UUID
    full_name: str
    phone_masked: str
    kuid: str | None
    last_seen: datetime | None
    roles: list[GrantOut]


class UsersResponse(BaseModel):
    users: list[UserOut]
    page: int
    has_more: bool


class RoleKindOut(BaseModel):
    code: str
    description: str
    scope_kind: str


class ClubOut(BaseModel):
    club_id: UUID
    name: str
    sport: str
    lga_name: str
    status: str
    verified: bool
    representative: str
    verification: str | None
    created_at: datetime


class ClubsResponse(BaseModel):
    clubs: list[ClubOut]
    page: int
    has_more: bool


class AuditOut(BaseModel):
    entry_id: int
    occurred_at: datetime
    actor: str
    actor_role: str | None
    action: str
    subject_type: str
    subject_id: str
    reference: str | None


class AuditResponse(BaseModel):
    entries: list[AuditOut]
    page: int
    has_more: bool


def _fields(model: type[BaseModel], source: object) -> dict[str, object]:
    return {f: getattr(source, f) for f in model.model_fields}


def _user_out(u: directory.UserRow) -> UserOut:
    return UserOut(
        **{f: getattr(u, f) for f in UserOut.model_fields if f != "roles"},
        roles=[GrantOut(**_fields(GrantOut, g)) for g in u.roles],
    )


@router.get(
    "/overview",
    response_model=OverviewResponse,
    dependencies=[Requires("admin.manage_users")],
    summary="Money, funnel and review speed at a glance (ADM-01)",
)
def overview() -> OverviewResponse:
    return OverviewResponse(**_fields(OverviewResponse, directory.overview()))


@router.get(
    "/users",
    response_model=UsersResponse,
    dependencies=[Requires("admin.manage_users")],
    summary="People with their roles, by name, phone or ID (ADM-02)",
)
def users(q: str = "", role: str = "", page: int = 1) -> UsersResponse:
    found = directory.find_users(q[:80], role[:40], min(page, 1000))
    return UsersResponse(users=[_user_out(u) for u in found.users], page=found.page, has_more=found.has_more)


@router.get(
    "/users/{user_id}",
    response_model=UserOut,
    dependencies=[Requires("admin.manage_users")],
    summary="One person with their roles",
)
def user(user_id: UUID) -> UserOut:
    found = directory.get_user(user_id)
    if found is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No such user.")
    return _user_out(found)


@router.get(
    "/roles",
    response_model=list[RoleKindOut],
    dependencies=[Requires("admin.manage_users")],
    summary="The roles that can be granted, and what each is scoped to",
)
def roles() -> list[RoleKindOut]:
    return [RoleKindOut(**_fields(RoleKindOut, r)) for r in directory.role_kinds()]


@router.get(
    "/clubs",
    response_model=ClubsResponse,
    dependencies=[Requires("club.approve")],
    summary="Clubs, those waiting for approval first",
)
def clubs(status_filter: str = Query("", alias="status"), page: int = 1) -> ClubsResponse:
    found = directory.list_clubs(status_filter[:20], min(page, 1000))
    return ClubsResponse(
        clubs=[ClubOut(**_fields(ClubOut, c)) for c in found.clubs], page=found.page, has_more=found.has_more
    )


@router.get(
    "/audit",
    response_model=AuditResponse,
    dependencies=[Requires("admin.read_audit")],
    summary="Who did what, and when (ADM-06). Read only: nothing here changes an entry",
)
def audit(
    actor: str = "",
    action: str = "",
    since: date | None = None,
    until: date | None = None,
    page: int = 1,
) -> AuditResponse:
    found = directory.audit_entries(actor[:80], action[:80], since, until, min(page, 5000))
    return AuditResponse(
        entries=[AuditOut(**_fields(AuditOut, e)) for e in found.entries], page=found.page, has_more=found.has_more
    )


# ---------------------------------------------------------------------------
# ADM-05: LGA rollout
# ---------------------------------------------------------------------------
class LgaOut(BaseModel):
    id: str
    code: str
    name: str
    wave: int | None
    is_open: bool
    went_live_at: datetime | None
    registered: int


class SetOpenRequest(BaseModel):
    open: bool
    reason: str = Field(min_length=1, max_length=rollout.MAX_REASON_CHARS)
    current_password: str = Field(min_length=1, max_length=1024)


@router.get(
    "/lgas",
    response_model=list[LgaOut],
    dependencies=[Requires("admin.manage_rollout")],
    summary="Every LGA in the state, its wave and whether it accepts registrations",
)
def lgas() -> list[LgaOut]:
    return [LgaOut(**_fields(LgaOut, x)) for x in rollout.list_lgas()]


@router.post(
    "/lgas/{lga_id}/rollout",
    response_model=LgaOut,
    dependencies=[Requires("admin.manage_rollout")],
    summary="Open or close one LGA for registration (reason and password required)",
)
def set_rollout(lga_id: str, body: SetOpenRequest, request: Request) -> LgaOut:
    try:
        found = rollout.set_open(
            current_principal(request), lga_id, open_=body.open, reason=body.reason,
            current_password=body.current_password,
            request_id=request_id(request), ip_address=client_ip(request),
        )
    except rollout.NotFound:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="No such LGA.") from None
    except rollout.Refused as exc:
        code = status.HTTP_409_CONFLICT if exc.code == "unchanged" else status.HTTP_422_UNPROCESSABLE_CONTENT
        field = "current_password" if exc.code == "password" else exc.code
        raise HTTPException(code, detail={"message": exc.message, "field": field}) from None
    return LgaOut(**_fields(LgaOut, found))


# ---------------------------------------------------------------------------
# ADM-07: data requests
# ---------------------------------------------------------------------------
class HandledOut(BaseModel):
    kind: str
    received_via: str
    note: str | None
    handled_by: str
    handled_at: datetime


class PersonOut(BaseModel):
    user_id: UUID
    full_name: str
    kuid: str | None
    roles: list[str]
    registered_on: date
    anonymised: bool
    requests: list[HandledOut]


class ExportRequest(BaseModel):
    received_via: str = Field(max_length=20)
    note: str | None = Field(default=None, max_length=data_requests.MAX_NOTE_CHARS)


class EraseRequest(BaseModel):
    received_via: str = Field(max_length=20)
    note: str = Field(min_length=1, max_length=data_requests.MAX_NOTE_CHARS)
    current_password: str = Field(min_length=1, max_length=1024)


def _data_refused(exc: data_requests.Refused) -> HTTPException:
    code = status.HTTP_409_CONFLICT if exc.code in ("already", "self") else status.HTTP_422_UNPROCESSABLE_CONTENT
    return HTTPException(code, detail={"message": exc.message, "field": exc.code})


@router.get(
    "/data-requests/person",
    response_model=PersonOut,
    dependencies=[Requires("admin.data_requests")],
    summary="Find the person a data request is about, with the requests already handled",
)
def data_request_person(q: str = "") -> PersonOut:
    found = data_requests.find(q[:254])
    if found is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Nobody matches that ID, phone number or email.")
    return PersonOut(
        **{f: getattr(found, f) for f in PersonOut.model_fields if f not in ("roles", "requests")},
        roles=list(found.roles),
        requests=[HandledOut(**_fields(HandledOut, r)) for r in found.requests],
    )


@router.post(
    "/data-requests/{user_id}/export",
    dependencies=[Requires("admin.data_requests")],
    summary="Everything held about one person, as JSON; the hand-over is recorded",
)
def data_request_export(user_id: UUID, body: ExportRequest, request: Request) -> dict[str, object]:
    try:
        return data_requests.export(
            current_principal(request), user_id, received_via=body.received_via, note=body.note,
            request_id=request_id(request), ip_address=client_ip(request),
        )
    except data_requests.NotFound:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="No such person.") from None
    except data_requests.Refused as exc:
        raise _data_refused(exc) from None


@router.post(
    "/data-requests/{user_id}/erase",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Requires("admin.data_requests")],
    summary="Anonymise one person (note and password required; cannot be undone)",
)
def data_request_erase(user_id: UUID, body: EraseRequest, request: Request) -> None:
    try:
        data_requests.erase(
            current_principal(request), user_id, received_via=body.received_via, note=body.note,
            current_password=body.current_password,
            request_id=request_id(request), ip_address=client_ip(request),
        )
    except data_requests.NotFound:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="No such person.") from None
    except data_requests.Refused as exc:
        raise _data_refused(exc) from None
