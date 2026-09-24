"""Clubs: registering one (CLB-01) and reading its dashboard (CLB-02).

Anyone signed in may register a club and becomes its administrator. Reading one is
scoped to that club: ``Requires(..., scope="club")`` reads ``club_id`` from the path
and matches it against the caller's own grants, so an administrator of one club is
refused another's, whatever they type into the address.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from kafriada.api.client import client_ip
from kafriada.api.client import request_id as header_request_id
from kafriada.api.security import Requires, current_principal
from kafriada.api.throttle import Throttle
from kafriada.contexts.clubs import service

router = APIRouter(tags=["clubs"])


def _detail(message: str, field: str | None = None) -> dict[str, str | None]:
    return {"message": message, "field": field}


class RegisterClubRequest(BaseModel):
    name: str = Field(max_length=200)
    sport: str = Field(max_length=40)
    lga_id: str = Field(max_length=40)
    contact_phone: str = Field(max_length=30)
    year_founded: int | None = None
    confirm_duplicate: bool = False


class RegisteredResponse(BaseModel):
    club_id: UUID
    name: str


class RosterRowOut(BaseModel):
    roster_id: UUID
    full_name: str
    kuid: str
    position: str | None
    state: str


class DashboardResponse(BaseModel):
    club_id: UUID
    name: str
    sport: str
    type: str
    year_founded: int | None
    lga_name: str
    contact_phone: str
    status: str
    verified: bool
    players: int
    verified_players: int
    invites_out: int
    roster: list[RosterRowOut]
    created_at: datetime


@router.post(
    "/clubs",
    response_model=RegisteredResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Requires("club.create"), Throttle("register_club")],
    summary="Register a club; the caller becomes its administrator",
)
async def register_club(body: RegisterClubRequest, request: Request) -> RegisteredResponse:
    principal = current_principal(request)
    try:
        made = await run_in_threadpool(
            service.register_club,
            principal.user_id,
            principal.full_name,
            name=body.name,
            sport=body.sport,
            lga_id=body.lga_id,
            contact_phone=body.contact_phone,
            year_founded=body.year_founded,
            confirm_duplicate=body.confirm_duplicate,
            request_id=header_request_id(request),
            ip_address=client_ip(request),
        )
    except service.Refused as exc:
        code = status.HTTP_409_CONFLICT if exc.code == "duplicate" else status.HTTP_422_UNPROCESSABLE_ENTITY
        raise HTTPException(code, detail=_detail(exc.message, exc.field)) from None
    return RegisteredResponse(club_id=made.club_id, name=made.name)


@router.get(
    "/clubs/{club_id}",
    response_model=DashboardResponse,
    dependencies=[Requires("club.read_scoped", scope="club")],
    summary="A club's dashboard: numbers and roster",
)
def club_dashboard(club_id: str) -> DashboardResponse:
    try:
        found = service.dashboard(UUID(club_id))
    except ValueError:
        found = None
    if found is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=_detail("No such club."))
    return DashboardResponse(
        **{f: getattr(found, f) for f in DashboardResponse.model_fields if f != "roster"},
        roster=[RosterRowOut(**{f: getattr(r, f) for f in RosterRowOut.model_fields}) for r in found.roster],
    )


def _uuid(value: str, message: str) -> UUID:
    try:
        return UUID(value)
    except ValueError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=_detail(message)) from None


def _refuse(exc: service.Refused) -> HTTPException:
    codes = {
        "missing": status.HTTP_404_NOT_FOUND,
        "no_athlete": status.HTTP_404_NOT_FOUND,
        "duplicate": status.HTTP_409_CONFLICT,
        "not_approved": status.HTTP_409_CONFLICT,
    }
    return HTTPException(
        codes.get(exc.code, status.HTTP_422_UNPROCESSABLE_ENTITY),
        detail=_detail(exc.message, exc.field),
    )


class PlayerMatchOut(BaseModel):
    full_name: str
    kuid: str
    position: str | None
    lga_name: str
    verified: bool
    current_club: str | None
    state: str


class InviteRequest(BaseModel):
    kuid: str = Field(max_length=60)


class MembershipOut(BaseModel):
    roster_id: UUID
    club_id: UUID
    club_name: str
    sport: str
    lga_name: str
    verified_club: bool


class MyClubsResponse(BaseModel):
    current: MembershipOut | None
    invitations: list[MembershipOut]


@router.get(
    "/clubs/{club_id}/players/find",
    response_model=PlayerMatchOut,
    dependencies=[Requires("club.manage_roster", scope="club"), Throttle("find_player")],
    summary="Find one athlete by exact KAFRIADA ID or phone number, to invite",
)
def find_player(club_id: str, q: str = "") -> PlayerMatchOut:
    found = service.find_player(_uuid(club_id, "No such club."), q[:60])
    if found is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=_detail("No athlete matches that."))
    return PlayerMatchOut(**{f: getattr(found, f) for f in PlayerMatchOut.model_fields})


@router.post(
    "/clubs/{club_id}/invitations",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Requires("club.manage_roster", scope="club")],
    summary="Invite an athlete to the club; they must accept before they are on the roster",
)
async def invite_player(club_id: str, body: InviteRequest, request: Request) -> None:
    principal = current_principal(request)
    try:
        await run_in_threadpool(
            service.invite_player,
            _uuid(club_id, "No such club."),
            principal.user_id,
            principal.full_name,
            body.kuid,
            request_id=header_request_id(request),
            ip_address=client_ip(request),
        )
    except service.Refused as exc:
        raise _refuse(exc) from None


@router.delete(
    "/clubs/{club_id}/roster/{roster_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Requires("club.manage_roster", scope="club")],
    summary="Remove a player from the roster, or withdraw an invitation",
)
async def remove_player(club_id: str, roster_id: str, request: Request) -> None:
    principal = current_principal(request)
    try:
        await run_in_threadpool(
            service.remove_player,
            _uuid(club_id, "No such club."),
            _uuid(roster_id, "That player is not on this club's roster."),
            principal.user_id,
            principal.full_name,
            request_id=header_request_id(request),
            ip_address=client_ip(request),
        )
    except service.Refused as exc:
        raise _refuse(exc) from None


def _membership(m: service.Membership) -> MembershipOut:
    return MembershipOut(**{f: getattr(m, f) for f in MembershipOut.model_fields})


@router.get(
    "/athletes/me/clubs",
    response_model=MyClubsResponse,
    dependencies=[Requires("athlete.read_self")],
    summary="The caller's current club and the invitations waiting for an answer",
)
def my_clubs(request: Request) -> MyClubsResponse:
    found = service.my_clubs(current_principal(request).user_id)
    return MyClubsResponse(
        current=_membership(found.current) if found.current else None,
        invitations=[_membership(m) for m in found.invitations],
    )


@router.post(
    "/athletes/me/invitations/{roster_id}/accept",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Requires("athlete.update_self")],
    summary="Accept an invitation; any current club membership ends",
)
async def accept_invitation(roster_id: str, request: Request) -> None:
    principal = current_principal(request)
    try:
        await run_in_threadpool(
            service.accept_invitation,
            principal.user_id,
            _uuid(roster_id, "We could not find that invitation."),
            principal.full_name,
            request_id=header_request_id(request),
            ip_address=client_ip(request),
        )
    except service.Refused as exc:
        raise _refuse(exc) from None


@router.post(
    "/athletes/me/invitations/{roster_id}/decline",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Requires("athlete.update_self")],
    summary="Decline an invitation",
)
async def decline_invitation(roster_id: str, request: Request) -> None:
    principal = current_principal(request)
    try:
        await run_in_threadpool(
            service.decline_invitation,
            principal.user_id,
            _uuid(roster_id, "We could not find that invitation."),
            principal.full_name,
            request_id=header_request_id(request),
            ip_address=client_ip(request),
        )
    except service.Refused as exc:
        raise _refuse(exc) from None


@router.post(
    "/admin/clubs/{club_id}/approve",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Requires("club.approve")],
    summary="Approve a club so it can build a roster",
)
async def approve_club(club_id: str, request: Request) -> None:
    await _set_status(club_id, "approved", request)


@router.post(
    "/admin/clubs/{club_id}/suspend",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Requires("club.approve")],
    summary="Suspend a club",
)
async def suspend_club(club_id: str, request: Request) -> None:
    await _set_status(club_id, "suspended", request)


async def _set_status(club_id: str, new_status: str, request: Request) -> None:
    principal = current_principal(request)
    try:
        await run_in_threadpool(
            service.set_status,
            _uuid(club_id, "No such club."),
            principal.user_id,
            principal.full_name,
            new_status,
            request_id=header_request_id(request),
            ip_address=client_ip(request),
        )
    except service.Refused as exc:
        raise _refuse(exc) from None
