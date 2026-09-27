"""Club verification (CLB-04): the club administrator's side and the reviewer's.

A club administrator uploads the club's registration document or LGA letter, pays the
club price through the ordinary payment path, and waits. A reviewer (a super
administrator, under ``club.approve``) reads the document and approves or rejects it,
with a reason the club reads verbatim.
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
from kafriada.contexts.clubs import verification as service
from kafriada.contexts.media import service as media
from kafriada.contexts.media.store import build_store
from kafriada.contexts.payments import service as payments
from kafriada.settings import get_settings

router = APIRouter(tags=["club verification"])

UNAVAILABLE = "We could not accept your document just now. Please try again shortly."


def _detail(message: str, field: str | None = None) -> dict[str, str | None]:
    return {"message": message, "field": field}


NOT_FOUND = HTTPException(status.HTTP_404_NOT_FOUND, detail=_detail("We could not find that."))


def _club(club_id: str) -> UUID:
    try:
        return UUID(club_id)
    except ValueError:
        raise NOT_FOUND from None


def _refused(exc: service.Refused) -> HTTPException:
    if exc.code in ("reason", "password"):
        return HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=_detail(exc.message, exc.field))
    return HTTPException(status.HTTP_409_CONFLICT, detail=_detail(exc.message, exc.field))


def _media_refused(exc: media.MediaRefused) -> HTTPException:
    if exc.code == "unavailable":
        return HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail=_detail(UNAVAILABLE))
    if exc.code == "missing":
        return NOT_FOUND
    return HTTPException(
        status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail=_detail(exc.message, {"type": "content_type", "size": "size_bytes"}.get(exc.code)),
    )


class OverviewResponse(BaseModel):
    club_id: UUID
    club_name: str
    club_status: str
    verified: bool
    state: str
    document: str | None
    price_kobo: int
    paid: bool
    reason: str | None


class UploadRequest(BaseModel):
    content_type: str = Field(min_length=1, max_length=100)
    size_bytes: int


class UploadResponse(BaseModel):
    media_id: UUID
    upload_url: str | None


@router.get(
    "/clubs/{club_id}/verification",
    response_model=OverviewResponse,
    dependencies=[Requires("verification.submit_club", scope="club")],
    summary="Where the club's verification stands",
)
def my_club_verification(club_id: str) -> OverviewResponse:
    found = service.overview(_club(club_id))
    if found is None:
        raise NOT_FOUND
    return OverviewResponse(**{f: getattr(found, f) for f in OverviewResponse.model_fields})


@router.post(
    "/clubs/{club_id}/verification/uploads",
    response_model=UploadResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Requires("verification.submit_club", scope="club"), Throttle("media_upload")],
    summary="Open a slot for the club's registration document or LGA letter",
)
def open_upload(club_id: str, body: UploadRequest, request: Request) -> UploadResponse:
    try:
        slot = service.begin_upload(
            current_principal(request).user_id, _club(club_id), body.content_type, body.size_bytes
        )
    except service.NotFound:
        raise NOT_FOUND from None
    except service.Refused as exc:
        raise _refused(exc) from None
    except media.MediaRefused as exc:
        raise _media_refused(exc) from None
    return UploadResponse(media_id=slot.media_id, upload_url=slot.upload_url)


@router.put(
    "/clubs/{club_id}/verification/uploads/{media_id}/content",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Requires("verification.submit_club", scope="club")],
    summary="Send the bytes through the API (the no-JavaScript path)",
)
async def relay_content(club_id: str, media_id: UUID, request: Request) -> Response:
    limit = get_settings().media_max_bytes
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > limit:
        return Response(status_code=413)
    data = await request.body()
    try:
        athlete_id = service.owned_media(current_principal(request).user_id, _club(club_id), media_id)
        await run_in_threadpool(media.relay_upload, athlete_id, media_id, data)
    except service.NotFound:
        raise NOT_FOUND from None
    except media.MediaRefused as exc:
        raise _media_refused(exc) from None
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/clubs/{club_id}/verification/uploads/{media_id}/confirm",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Requires("verification.submit_club", scope="club")],
    summary="Say the file has arrived; we check it really has",
)
def confirm_content(club_id: str, media_id: UUID, request: Request) -> Response:
    try:
        athlete_id = service.owned_media(current_principal(request).user_id, _club(club_id), media_id)
        media.confirm_upload(athlete_id, media_id)
    except service.NotFound:
        raise NOT_FOUND from None
    except media.MediaRefused as exc:
        raise _media_refused(exc) from None
    if not build_store().direct_upload and media.process_one(media_id) == "unreadable":
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=_detail(
                "We could not read that file. Please send a clear JPEG, PNG or WebP photo of the document.",
                "file",
            ),
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/clubs/{club_id}/verification/resubmit",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Requires("verification.submit_club", scope="club")],
    summary="Send a rejected request back for review — no new payment",
)
def resubmit(club_id: str, request: Request) -> Response:
    try:
        service.resubmit(_club(club_id), current_principal(request).user_id)
    except service.Refused as exc:
        raise _refused(exc) from None
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/clubs/{club_id}/verification/payment",
    response_model=StartResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[
        Requires("verification.submit_club", scope="club"),
        Throttle("start_payment"),
    ],
    summary="Start the checkout for the club's verification",
)
async def start_payment(club_id: str, request: Request) -> StartResponse:
    principal = current_principal(request)
    try:
        started = await run_in_threadpool(
            payments.start_club_payment,
            principal,
            _club(club_id),
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
    "/admin/club-verification/queue",
    response_model=list[QueueItemResponse],
    dependencies=[Requires("club.approve")],
    summary="Clubs waiting for a verification decision, oldest first",
)
def queue() -> list[QueueItemResponse]:
    return [QueueItemResponse(**{f: getattr(i, f) for f in QueueItemResponse.model_fields}) for i in service.queue()]


@router.get(
    "/admin/club-verification/{club_id}/document",
    dependencies=[Requires("club.approve")],
    summary="The document a reviewer is deciding on",
    response_class=Response,
)
def document(club_id: str) -> Response:
    try:
        data = service.document(_club(club_id))
    except service.NotFound:
        raise NOT_FOUND from None
    return Response(content=data, media_type="image/jpeg", headers={"cache-control": "private, no-store"})


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
    "/admin/club-verification/{club_id}/approve",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Requires("club.approve")],
    summary="Approve a club's verification; the club becomes verified",
)
def approve(club_id: str, request: Request) -> Response:
    return _decide(club_id, request, None)


@router.post(
    "/admin/club-verification/{club_id}/reject",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Requires("club.approve")],
    summary="Reject a club's verification, with a reason the club reads verbatim",
)
def reject(club_id: str, body: RejectRequest, request: Request) -> Response:
    return _decide(club_id, request, body.reason)


class RevokeRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=2000)
    current_password: str = Field(min_length=1, max_length=1024)


@router.post(
    "/admin/club-verification/{club_id}/revoke",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Requires("club.approve")],
    summary="Withdraw a club's verified badge (reason and password required)",
)
def revoke(club_id: str, body: RevokeRequest, request: Request) -> Response:
    try:
        service.revoke(
            current_principal(request), _club(club_id), body.reason, body.current_password,
            request_id=header_request_id(request), ip_address=client_ip(request),
        )
    except service.NotFound:
        raise NOT_FOUND from None
    except service.Refused as exc:
        raise _refused(exc) from None
    return Response(status_code=status.HTTP_204_NO_CONTENT)
