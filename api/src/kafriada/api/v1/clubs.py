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
