"""Verification: the athlete's uploads and status, the reviewer's queue, a withdrawal,
and the one public photo address.

Four different callers, four different rules, and each route declares its own:

* **The athlete** (``verification.submit_self``) adds their own photo and document and
  reads their own status. Nothing they send can move a request past ``draft``: that is
  the payment's job, and then a reviewer's.
* **A reviewer** (``verification.review``, scoped to an LGA) sees the queue for that LGA
  only, never their own record, and only files that have been re-encoded.
* **A super administrator** (``verification.revoke``) withdraws a badge, with a reason
  and their password again.
* **Anyone** may fetch an *approved* athlete's photo, and nothing else the bucket holds.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, Response, status
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from kafriada.api.client import client_ip
from kafriada.api.client import request_id as header_request_id
from kafriada.api.security import Public, Requires, current_principal
from kafriada.api.throttle import Throttle
from kafriada.contexts.media import service as media
from kafriada.contexts.media.store import build_store
from kafriada.contexts.verification import service
from kafriada.settings import get_settings

router = APIRouter(tags=["verification"])

UNAVAILABLE = "We could not accept your photo just now. Please try again shortly."


def _detail(message: str, field: str | None = None) -> dict[str, str | None]:
    return {"message": message, "field": field}


def _refused(exc: service.Refused) -> HTTPException:
    code = status.HTTP_404_NOT_FOUND if exc.code == "no_athlete" else status.HTTP_409_CONFLICT
    if exc.code in ("reason", "password"):
        return HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=_detail(exc.message, "reason" if exc.code == "reason" else "current_password"),
        )
    return HTTPException(code, detail=_detail(exc.message))


def _media_refused(exc: media.MediaRefused) -> HTTPException:
    if exc.code == "unavailable":
        return HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail=_detail(exc.message))
    if exc.code == "missing":
        return HTTPException(status.HTTP_404_NOT_FOUND, detail=_detail(exc.message))
    return HTTPException(
        status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail=_detail(exc.message, {"kind": "kind", "type": "content_type", "size": "size_bytes"}.get(exc.code)),
    )


NOT_FOUND = HTTPException(status.HTTP_404_NOT_FOUND, detail=_detail("We could not find that."))


# ---------------------------------------------------------------------------
# The athlete
# ---------------------------------------------------------------------------
class OverviewResponse(BaseModel):
    state: str
    attempt: int
    attempts_left: int
    photo: str | None
    document: str | None
    reason: str | None
    submitted_at: datetime | None
    paid_amount_kobo: int | None
    paid_at: datetime | None
    can_replace: bool
    ready_to_pay: bool
    price_kobo: int


class UploadRequest(BaseModel):
    kind: Literal["photo", "document"]
    content_type: str = Field(min_length=1, max_length=100)
    size_bytes: int


class UploadResponse(BaseModel):
    media_id: UUID
    # Present when the browser may send the bytes straight to storage; absent when
    # they must come through PUT .../content (a browser with no JavaScript, or a
    # development store).
    upload_url: str | None


@router.get(
    "/verification",
    response_model=OverviewResponse,
    dependencies=[Requires("verification.submit_self")],
    summary="Where the caller's own verification stands",
)
def my_verification(request: Request) -> OverviewResponse:
    found = service.overview(current_principal(request).user_id)
    if found is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=_detail("No athlete record."))
    return OverviewResponse(**{f: getattr(found, f) for f in OverviewResponse.model_fields})


@router.post(
    "/verification/uploads",
    response_model=UploadResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Requires("verification.submit_self"), Throttle("media_upload")],
    summary="Open a slot for the caller's photo or ID document",
)
def open_upload(body: UploadRequest, request: Request) -> UploadResponse:
    try:
        slot = service.begin_upload(
            current_principal(request).user_id, body.kind, body.content_type, body.size_bytes
        )
    except service.Refused as exc:
        raise _refused(exc) from None
    except media.MediaRefused as exc:
        raise _media_refused(exc) from None
    return UploadResponse(media_id=slot.media_id, upload_url=slot.upload_url)


@router.put(
    "/verification/uploads/{media_id}/content",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Requires("verification.submit_self")],
    summary="Send the bytes through the API (the no-JavaScript path)",
)
async def relay_content(media_id: UUID, request: Request) -> Response:
    limit = get_settings().media_max_bytes
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > limit:
        return Response(status_code=413)
    data = await request.body()
    try:
        athlete_id = service.owned_media(current_principal(request).user_id, media_id)
        await run_in_threadpool(media.relay_upload, athlete_id, media_id, data)
    except service.NotFound:
        raise NOT_FOUND from None
    except media.MediaRefused as exc:
        raise _media_refused(exc) from None
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/verification/uploads/{media_id}/confirm",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Requires("verification.submit_self")],
    summary="Say the file has arrived; we check it really has",
)
def confirm_content(media_id: UUID, request: Request) -> Response:
    try:
        athlete_id = service.owned_media(current_principal(request).user_id, media_id)
        media.confirm_upload(athlete_id, media_id)
    except service.NotFound:
        raise NOT_FOUND from None
    except media.MediaRefused as exc:
        raise _media_refused(exc) from None
    # Bytes that already passed through this process (no direct upload) are re-encoded
    # now, so a browser with no JavaScript is not left waiting for a worker. Bytes that
    # went straight to storage are left to the worker, which is where they are read.
    if not build_store().direct_upload and media.process_one(media_id) == "unreadable":
        # Say so now, while the person is still looking at the form, rather than
        # letting them pay for a review of a file nobody can open.
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=_detail(
                "We could not read that file. Please send a clear JPEG, PNG or WebP photo.",
                "file",
            ),
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/verification/resubmit",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Requires("verification.submit_self")],
    summary="Send a rejected verification back for review — no new payment",
)
def resubmit(request: Request) -> Response:
    try:
        service.resubmit(current_principal(request).user_id)
    except service.Refused as exc:
        raise _refused(exc) from None
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# The reviewer
# ---------------------------------------------------------------------------
class QueueItemResponse(BaseModel):
    request_id: UUID
    kuid: str
    full_name: str
    submitted_at: datetime
    attempt: int


class CaseResponse(BaseModel):
    request_id: UUID
    kuid: str
    full_name: str
    date_of_birth: date
    age: int
    attempt: int
    submitted_at: datetime | None
    paid_kobo: int | None
    paid_at: datetime | None
    waiting: int


class RejectRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=service.MAX_REASON_CHARS)


class DecisionResponse(BaseModel):
    outcome: str


@router.get(
    "/lgas/{lga_id}/verification/queue",
    response_model=list[QueueItemResponse],
    dependencies=[Requires("verification.review", scope="lga")],
    summary="Verifications waiting for a decision in one LGA, oldest first",
)
def review_queue(lga_id: str, request: Request) -> list[QueueItemResponse]:
    return [
        QueueItemResponse(
            request_id=i.request_id, kuid=i.kuid, full_name=i.full_name,
            submitted_at=i.submitted_at, attempt=i.attempt,
        )
        for i in service.queue(current_principal(request), lga_id)
    ]


@router.get(
    "/lgas/{lga_id}/verification/{request_id}",
    response_model=CaseResponse,
    dependencies=[Requires("verification.review", scope="lga")],
    summary="One case, with what the athlete claimed about themselves",
)
def review_case(lga_id: str, request_id: UUID, request: Request) -> CaseResponse:
    try:
        found = service.case(current_principal(request), lga_id, request_id)
    except service.NotFound:
        raise NOT_FOUND from None
    return CaseResponse(**{f: getattr(found, f) for f in CaseResponse.model_fields})


@router.get(
    "/lgas/{lga_id}/verification/{request_id}/media/{kind}",
    dependencies=[Requires("verification.review", scope="lga")],
    response_class=Response,
    summary="The safe copy of the photo or document a reviewer is deciding on",
)
def review_media(lga_id: str, request_id: UUID, kind: str, request: Request) -> Response:
    try:
        data = service.case_media(current_principal(request), lga_id, request_id, kind)
    except service.NotFound:
        raise NOT_FOUND from None
    return Response(
        content=data,
        media_type="image/jpeg",
        # An identity document must not sit in a shared cache or a proxy.
        headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"},
    )


@router.post(
    "/lgas/{lga_id}/verification/{request_id}/approve",
    response_model=DecisionResponse,
    dependencies=[Requires("verification.review", scope="lga")],
    summary="Approve: the badge and the photo go live",
)
def approve(lga_id: str, request_id: UUID, request: Request) -> DecisionResponse:
    try:
        outcome = service.approve(
            current_principal(request), lga_id, request_id,
            ip_address=client_ip(request), request_id_header=header_request_id(request),
        )
    except service.NotFound:
        raise NOT_FOUND from None
    except service.Refused as exc:
        raise _refused(exc) from None
    return DecisionResponse(outcome=outcome)


@router.post(
    "/lgas/{lga_id}/verification/{request_id}/reject",
    response_model=DecisionResponse,
    dependencies=[Requires("verification.review", scope="lga")],
    summary="Reject with a reason the athlete will read verbatim",
)
def reject(lga_id: str, request_id: UUID, body: RejectRequest, request: Request) -> DecisionResponse:
    try:
        outcome = service.reject(
            current_principal(request), lga_id, request_id, body.reason,
            ip_address=client_ip(request), request_id_header=header_request_id(request),
        )
    except service.NotFound:
        raise NOT_FOUND from None
    except service.Refused as exc:
        raise _refused(exc) from None
    return DecisionResponse(outcome=outcome)


# ---------------------------------------------------------------------------
# A super administrator
# ---------------------------------------------------------------------------
class RevokeRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=service.MAX_REASON_CHARS)
    current_password: str = Field(min_length=1, max_length=1024)


@router.post(
    "/admin/verification/{request_id}/revoke",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Requires("verification.revoke")],
    summary="Withdraw an approved verification (reason and password required)",
)
def revoke(request_id: UUID, body: RevokeRequest, request: Request) -> Response:
    try:
        service.revoke(
            current_principal(request), request_id, body.reason, body.current_password,
            ip_address=client_ip(request), request_id_header=header_request_id(request),
        )
    except service.NotFound:
        raise NOT_FOUND from None
    except service.Refused as exc:
        raise _refused(exc) from None
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# Anyone
# ---------------------------------------------------------------------------
@router.get(
    "/public/athletes/{kuid}/photo",
    dependencies=[Public("an approved athlete's photo is the product; everything else stays private")],
    response_class=Response,
    summary="An approved athlete's photo",
)
def public_photo(kuid: str) -> Response:
    data = service.public_photo(kuid)
    if data is None:
        # Not verified, withdrawn, or no such athlete: all the same answer.
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Not found.")
    return Response(
        content=data,
        media_type="image/jpeg",
        # Short, so a withdrawal takes effect within a minute rather than a day.
        headers={"Cache-Control": "public, max-age=60", "X-Content-Type-Options": "nosniff"},
    )
