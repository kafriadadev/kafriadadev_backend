"""The coordinator's home (CRD-01) and finding an athlete (CRD-03).

Both are scoped to the LGA in the path. ``Requires(..., scope="lga")`` proves the caller
holds a grant on that LGA (or on its state, or globally); the service then bounds every
query to it, so nothing outside it can appear in a result.
"""

from __future__ import annotations

from datetime import date, datetime

from fastapi import APIRouter, HTTPException, Request, Response, status
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from kafriada.api.client import client_ip
from kafriada.api.client import request_id as header_request_id
from kafriada.api.security import Requires, current_principal
from kafriada.clock import today_in_nigeria
from kafriada.contexts.coordination import cards, service
from kafriada.contexts.coordination import settlement as settlement_mod

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


# ---------------------------------------------------------------------------
# CRD-06: bulk QR card printing
# ---------------------------------------------------------------------------
class CardRowOut(BaseModel):
    kuid: str
    full_name: str
    registered_on: date
    printed: bool


class CardsResponse(BaseModel):
    people: list[CardRowOut]
    total: int
    page: int
    pages: int
    per_sheet: int


class MarkPrintedRequest(BaseModel):
    kuids: list[str] = Field(max_length=cards.PAGE_SIZE)


class MarkPrintedResponse(BaseModel):
    marked: int


@router.get(
    "/lgas/{lga_id}/cards",
    response_model=CardsResponse,
    dependencies=[Requires("athlete.search_scoped", scope="lga")],
    summary="Athletes whose cards can be printed, filtered by registration date and print status",
)
def card_list(
    lga_id: str,
    since: date | None = None,
    until: date | None = None,
    unprinted: bool = True,
    page: int = 1,
) -> CardsResponse:
    found = cards.list_cards(lga_id, since, until, unprinted, min(page, 10_000))
    return CardsResponse(
        people=[CardRowOut(**{f: getattr(p, f) for f in CardRowOut.model_fields}) for p in found.people],
        total=found.total,
        page=found.page,
        pages=found.pages,
        per_sheet=cards.PER_SHEET,
    )


@router.get(
    "/lgas/{lga_id}/cards.pdf",
    dependencies=[Requires("athlete.search_scoped", scope="lga")],
    summary="One page of the batch as A4 sheets of eight cards",
    response_class=Response,
)
async def card_sheets(
    lga_id: str,
    since: date | None = None,
    until: date | None = None,
    unprinted: bool = True,
    page: int = 1,
) -> Response:
    pdf = await run_in_threadpool(cards.sheets_pdf, lga_id, since, until, unprinted, min(page, 10_000))
    if pdf is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="No cards match.")
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="cards-{lga_id}-{page}.pdf"', "Cache-Control": "private, no-store"},
    )


@router.post(
    "/lgas/{lga_id}/cards/printed",
    response_model=MarkPrintedResponse,
    dependencies=[Requires("athlete.search_scoped", scope="lga")],
    summary="Record that these cards were printed; athletes outside the LGA are ignored",
)
def mark_printed(lga_id: str, body: MarkPrintedRequest, request: Request) -> MarkPrintedResponse:
    principal = current_principal(request)
    marked = cards.mark_printed(
        lga_id, body.kuids, principal.user_id, principal.full_name,
        request_id=header_request_id(request), ip_address=client_ip(request),
    )
    return MarkPrintedResponse(marked=marked)


# ---------------------------------------------------------------------------
# CRD-05: cash settlement
# ---------------------------------------------------------------------------
class SettlementLineOut(BaseModel):
    reference: str
    created_at: datetime
    athlete_name: str
    kuid: str
    coordinator_name: str
    amount_kobo: int
    status: str


class SettlementResponse(BaseModel):
    lga_id: str
    lga_name: str
    since: date
    until: date
    mine: bool
    lines: list[SettlementLineOut]
    truncated: bool
    collected_count: int
    collected_kobo: int
    confirmed_count: int
    confirmed_kobo: int
    difference_kobo: int
    pending_count: int
    review_count: int
    abandoned_count: int


def _settlement(request: Request, lga_id: str, since: date | None, until: date | None, mine: bool):
    end = until or today_in_nigeria()
    start = since or end.replace(day=1)
    try:
        found = settlement_mod.settlement(current_principal(request).user_id, lga_id, start, end, mine=mine)
    except settlement_mod.RangeTooWideError:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Choose an end date on or after the start date, no more than a year apart.",
        ) from None
    if found is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="No such LGA.")
    return found


@router.get(
    "/lgas/{lga_id}/settlement",
    response_model=SettlementResponse,
    dependencies=[Requires("payment.read_scoped", scope="lga")],
    summary="Cash collected on behalf of athletes against what Paystack confirmed (CRD-05)",
)
def settlement(
    lga_id: str, request: Request, since: date | None = None, until: date | None = None, mine: bool = True
) -> SettlementResponse:
    found = _settlement(request, lga_id, since, until, mine)
    return SettlementResponse(
        **{f: getattr(found, f) for f in SettlementResponse.model_fields if f != "lines"},
        lines=[SettlementLineOut(**{f: getattr(x, f) for f in SettlementLineOut.model_fields}) for x in found.lines],
    )


@router.get(
    "/lgas/{lga_id}/settlement.csv",
    dependencies=[Requires("payment.read_scoped", scope="lga")],
    summary="The settlement lines as CSV",
    response_class=Response,
)
def settlement_csv(
    lga_id: str, request: Request, since: date | None = None, until: date | None = None, mine: bool = True
) -> Response:
    found = _settlement(request, lga_id, since, until, mine)
    return Response(
        content=settlement_mod.as_csv(found),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="settlement-{lga_id}-{found.since}-{found.until}.csv"',
            "Cache-Control": "private, no-store",
        },
    )
