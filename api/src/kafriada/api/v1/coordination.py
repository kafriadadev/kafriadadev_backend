"""The coordinator's home (CRD-01) and finding an athlete (CRD-03).

Both are scoped to the LGA in the path. ``Requires(..., scope="lga")`` proves the caller
holds a grant on that LGA (or on its state, or globally); the service then bounds every
query to it, so nothing outside it can appear in a result.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel

from kafriada.api.security import Requires, current_principal
from kafriada.contexts.coordination import service

router = APIRouter(tags=["coordination"])


class DashboardResponse(BaseModel):
    lga_id: str
    lga_name: str
    registered: int
    paid: int
    to_review: int
    oldest_waiting_hours: int | None
    clubs: int
    can_assist: bool
    collected_kobo: int
    collected_count: int
    limit_kobo: int
    limit_count: int
    cap_reached: bool


class FoundOut(BaseModel):
    kuid: str
    full_name: str
    playing_position: str | None
    verified: bool


class SearchResponse(BaseModel):
    people: list[FoundOut]
    page: int
    has_more: bool


@router.get(
    "/lgas/{lga_id}/dashboard",
    response_model=DashboardResponse,
    dependencies=[Requires("athlete.search_scoped", scope="lga")],
    summary="A coordinator's day at a glance, for one LGA (CRD-01)",
)
def dashboard(lga_id: str, request: Request) -> DashboardResponse:
    found = service.dashboard(current_principal(request), lga_id)
    if found is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="No such LGA.")
    return DashboardResponse(**{f: getattr(found, f) for f in DashboardResponse.model_fields})


@router.get(
    "/lgas/{lga_id}/athlete-search",
    response_model=SearchResponse,
    dependencies=[Requires("athlete.search_scoped", scope="lga")],
    summary="Find an athlete in one LGA by name, ID or phone (CRD-03)",
)
def search(lga_id: str, q: str = "", page: int = 1) -> SearchResponse:
    found = service.find_athletes(lga_id, q[:80], min(page, 1000))
    return SearchResponse(
        people=[FoundOut(**{f: getattr(p, f) for f in FoundOut.model_fields}) for p in found.people],
        page=found.page,
        has_more=found.has_more,
    )
