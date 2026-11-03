"""Club stage three: the club administrator's side and the reviewer's.

A club at stage two adds its links and photos, pays the stage-three price through the
ordinary payment path, and waits. A reviewer (a super administrator, under
``club.approve``) looks at both and approves or rejects, with a reason the club reads
verbatim.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, Response, status
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from kafriada.api.client import client_ip
from kafriada.api.client import request_id as header_request_id
from kafriada.api.security import Requires, current_principal
from kafriada.api.throttle import Throttle
from kafriada.api.v1.payments import StartResponse
from kafriada.contexts.clubs import stage3 as service
from kafriada.contexts.media import service as media
from kafriada.contexts.media.store import build_store
from kafriada.contexts.payments import service as payments
from kafriada.settings import get_settings

router = APIRouter(tags=["club stage three"])

UNAVAILABLE = "We could not accept your photo just now. Please try again shortly."


def _detail(message: str, field: str | None = None) -> dict[str, str | None]:
    return {"message": message, "field": field}


NOT_FOUND = HTTPException(status.HTTP_404_NOT_FOUND, detail=_detail("We could not find that."))


def _club(club_id: str) -> UUID:
    try:
        return UUID(club_id)
    except ValueError:
        raise NOT_FOUND from None


def _refused(exc: service.Refused) -> HTTPException:
    if exc.code in ("reason", "invalid"):
        return HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=_detail(exc.message, exc.field))
    return HTTPException(status.HTTP_409_CONFLICT, detail=_detail(exc.message, exc.field))


def _media_refused(exc: media.MediaRefused) -> HTTPException:
    if exc.code == "unavailable":
        return HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail=_detail(UNAVAILABLE))
    if exc.code == "missing":
        return NOT_FOUND
    return HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=_detail(exc.message, "file"))


class PhotoOut(BaseModel):
    media_id: UUID
    status: str


class OverviewResponse(BaseModel):
    club_id: UUID
    club_name: str
    stage: int
    state: str
    links: list[str]
    photos: list[PhotoOut]
    price_kobo: int
    paid: bool
    reason: str | None


class LinksRequest(BaseModel):
    links: list[str] = Field(max_length=10)


class UploadRequest(BaseModel):
    content_type: str = Field(min_length=1, max_length=100)
    size_bytes: int


class UploadResponse(BaseModel):
    media_id: UUID
    upload_url: str | None


SCOPE = Requires("verification.submit_club", scope="club")


@router.get(
    "/clubs/{club_id}/stage-three",
    response_model=OverviewResponse,
    dependencies=[SCOPE],
    summary="Where the club's stage three stands",
)
def overview(club_id: str) -> OverviewResponse:
    found = service.overview(_club(club_id))
    if found is None:
        raise NOT_FOUND
    return OverviewResponse(
        **{f: getattr(found, f) for f in OverviewResponse.model_fields if f != "photos"},
        photos=[PhotoOut(media_id=p.media_id, status=p.status) for p in found.photos],
    )


@router.put(
    "/clubs/{club_id}/stage-three/links",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[SCOPE],
    summary="Set the club's website and social media links",
)
def save_links(club_id: str, body: LinksRequest) -> Response:
    try:
        service.save_links(_club(club_id), body.links)
    except service.NotFound:
        raise NOT_FOUND from None
    except service.Refused as exc:
        raise _refused(exc) from None
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/clubs/{club_id}/stage-three/photos",
    response_model=UploadResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[SCOPE, Throttle("media_upload")],
    summary="Open a slot for a club photo",
)
def open_photo(club_id: str, body: UploadRequest) -> UploadResponse:
    try:
        slot = service.begin_photo(_club(club_id), body.content_type, body.size_bytes)
    except service.NotFound:
        raise NOT_FOUND from None
    except service.Refused as exc:
        raise _refused(exc) from None
    except media.MediaRefused as exc:
        raise _media_refused(exc) from None
    return UploadResponse(media_id=slot.media_id, upload_url=slot.upload_url)


@router.put(
    "/clubs/{club_id}/stage-three/photos/{media_id}/content",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[SCOPE],
    summary="Send the photo's bytes through the API (the no-JavaScript path)",
)
async def relay_photo(club_id: str, media_id: UUID, request: Request) -> Response:
    limit = get_settings().media_max_bytes
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > limit:
        return Response(status_code=413)
    data = await request.body()
    try:
        owner = service.owned_photo(_club(club_id), media_id)
        await run_in_threadpool(media.relay_upload, owner, media_id, data)
    except service.NotFound:
        raise NOT_FOUND from None
    except media.MediaRefused as exc:
        raise _media_refused(exc) from None
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/clubs/{club_id}/stage-three/photos/{media_id}/confirm",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[SCOPE],
    summary="Say the photo has arrived; we check it really has",
)
def confirm_photo(club_id: str, media_id: UUID) -> Response:
    try:
        owner = service.owned_photo(_club(club_id), media_id)
        media.confirm_upload(owner, media_id)
    except service.NotFound:
        raise NOT_FOUND from None
    except media.MediaRefused as exc:
        raise _media_refused(exc) from None
    if not build_store().direct_upload and media.process_one(media_id) == "unreadable":
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=_detail("We could not read that file. Please send a clear JPEG, PNG or WebP photo.", "file"),
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete(
    "/clubs/{club_id}/stage-three/photos/{media_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[SCOPE],
    summary="Remove a club photo",
)
def remove_photo(club_id: str, media_id: UUID) -> Response:
    try:
        service.remove_photo(_club(club_id), media_id)
    except service.NotFound:
        raise NOT_FOUND from None
    except service.Refused as exc:
        raise _refused(exc) from None
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/clubs/{club_id}/stage-three/photos/{media_id}",
    dependencies=[SCOPE],
    summary="A club photo, for the club's own administrators",
    response_class=Response,
)
def club_photo(club_id: str, media_id: UUID) -> Response:
    try:
        data = service.photo(_club(club_id), media_id)
    except service.NotFound:
        raise NOT_FOUND from None
    return Response(content=data, media_type="image/jpeg", headers={"cache-control": "private, no-store"})


@router.post(
    "/clubs/{club_id}/stage-three/payment",
    response_model=StartResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[SCOPE, Throttle("start_payment")],
    summary="Start the checkout for the club's stage three",
)
async def start_payment(club_id: str, request: Request) -> StartResponse:
    principal = current_principal(request)
    try:
        started = await run_in_threadpool(
            payments.start_club_payment,
            principal,
            _club(club_id),
            stage=3,
            request_id=header_request_id(request),
            ip_address=client_ip(request),
        )
    except payments.Refused as exc:
        code = status.HTTP_404_NOT_FOUND if exc.code == "no_club" else status.HTTP_409_CONFLICT
        raise HTTPException(code, detail=_detail(exc.message)) from None
    except payments.Unavailable as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail=_detail(exc.message)) from None
    return StartResponse(
        reference=started.reference,
        authorization_url=started.authorization_url,
        amount_kobo=started.amount_kobo,
    )


@router.post(
    "/clubs/{club_id}/stage-three/resubmit",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[SCOPE],
    summary="Send a rejected stage-three request back for review, with no new payment",
)
def resubmit(club_id: str) -> Response:
    try:
        service.resubmit(_club(club_id))
    except service.Refused as exc:
        raise _refused(exc) from None
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# The reviewer
# ---------------------------------------------------------------------------
class QueueItemResponse(BaseModel):
    club_id: UUID
    club_name: str
    lga_name: str
    submitted_at: datetime


class RejectRequest(BaseModel):
    reason: str = Field(max_length=2000)


@router.get(
    "/admin/club-stage-three/queue",
    response_model=list[QueueItemResponse],
    dependencies=[Requires("club.approve")],
    summary="Clubs waiting for a stage-three decision, oldest first",
)
def queue() -> list[QueueItemResponse]:
    return [QueueItemResponse(**{f: getattr(i, f) for f in QueueItemResponse.model_fields}) for i in service.queue()]


@router.get(
    "/admin/club-stage-three/{club_id}",
    response_model=OverviewResponse,
    dependencies=[Requires("club.approve")],
    summary="A club's stage-three request, for the reviewer",
)
def review(club_id: str) -> OverviewResponse:
    return overview(club_id)


@router.get(
    "/admin/club-stage-three/{club_id}/photos/{media_id}",
    dependencies=[Requires("club.approve")],
    summary="A club photo, for the reviewer",
    response_class=Response,
)
def review_photo(club_id: str, media_id: UUID) -> Response:
    return club_photo(club_id, media_id)


def _decide(club_id: str, request: Request, reason: str | None) -> Response:
    principal = current_principal(request)
    try:
        if reason is None:
            service.approve(
                _club(club_id), principal.user_id, principal.full_name,
                request_id=header_request_id(request), ip_address=client_ip(request),
            )
        else:
            service.reject(
                _club(club_id), principal.user_id, principal.full_name, reason,
                request_id=header_request_id(request), ip_address=client_ip(request),
            )
    except service.NotFound:
        raise NOT_FOUND from None
    except service.Refused as exc:
        raise _refused(exc) from None
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/admin/club-stage-three/{club_id}/approve",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Requires("club.approve")],
    summary="Approve a club's stage three; the club moves to stage three",
)
def approve(club_id: str, request: Request) -> Response:
    return _decide(club_id, request, None)


@router.post(
    "/admin/club-stage-three/{club_id}/reject",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Requires("club.approve")],
    summary="Reject a club's stage three, with a reason the club reads verbatim",
)
def reject(club_id: str, body: RejectRequest, request: Request) -> Response:
    return _decide(club_id, request, body.reason)
