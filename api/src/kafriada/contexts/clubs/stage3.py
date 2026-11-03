"""Club stage three (GDOC 5.10): the club's links and photos, a payment, a decision.

    draft --paid--> under_review --approve--> approved (the club is stage 3)
                        |  ^
                     reject  +-- resubmit (against the same payment)
                        v
                    rejected

Only a club at stage two can start. Nothing reaches a reviewer without at least one
link, at least one re-encoded photo and a settled payment. A rejection needs a reason,
shown to the club verbatim; the club fixes what it was told and sends it back without
paying again. Photos belong to the club (``media_files.org_id``), not to whoever
uploaded them. ``mark_paid`` is called from settlement, inside the ledger transaction.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

import structlog
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from kafriada.contexts.audit.service import Actor, record
from kafriada.contexts.media import service as media
from kafriada.contexts.media.store import ObjectStore, StoreError
from kafriada.contexts.media.store import build_store as _build_store
from kafriada.contexts.payments.rules import Purpose, expected_amount_kobo
from kafriada.db.engine import transaction
from kafriada.outbox.service import queue_notification
from kafriada.settings import get_settings

log = structlog.get_logger(__name__)

MAX_LINKS = 5
MAX_PHOTOS = 6
MAX_LINK_CHARS = 200
MAX_REASON_CHARS = 1_000
_LINK_RE = re.compile(r"^https?://[^\s/$.?#][^\s]*\.[^\s]+$", re.I)
_EDITABLE = ("draft", "rejected")
_NOT_EDITABLE = {
    "under_review": "Stage three is being reviewed and cannot be changed now.",
    "approved": "This club is already at stage three.",
}


class Refused(Exception):
    def __init__(self, message: str, *, code: str, field: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.field = field


class NotFound(Exception):
    """The thing is not there, or not the caller's to see. Deliberately the same."""


@dataclass(frozen=True, slots=True)
class Photo:
    media_id: UUID
    status: str  # pending | uploaded | ready | unreadable


@dataclass(frozen=True, slots=True)
class Overview:
    club_id: UUID
    club_name: str
    stage: int
    # none | draft | under_review | approved | rejected
    state: str
    links: list[str]
    photos: list[Photo]
    price_kobo: int
    paid: bool
    reason: str | None


def _photos(session: Session, club_id: UUID) -> list[Photo]:
    rows = session.execute(
        text(
            "SELECT id, status FROM identity.media_files "
            "WHERE org_id = :c AND kind = 'club_photo' AND status <> 'deleted' "
            "ORDER BY created_at"
        ),
        {"c": club_id},
    ).mappings().all()
    return [Photo(media_id=r["id"], status=r["status"]) for r in rows]


def overview(club_id: UUID) -> Overview | None:
    with transaction() as session:
        row = session.execute(
            text(
                """
                SELECT o.id, o.name, o.stage, o.links, r.id AS request_id, r.status,
                       EXISTS (SELECT 1 FROM money.payments p WHERE p.org_id = o.id
                                  AND p.purpose = 'stage3_org' AND p.status = 'success') AS paid
                  FROM identity.organizations o
                  LEFT JOIN identity.club_stage3_requests r ON r.org_id = o.id
                 WHERE o.id = :c
                """
            ),
            {"c": club_id},
        ).mappings().one_or_none()
        if row is None:
            return None
        reason = None
        if row["status"] == "rejected":
            reason = session.execute(
                text(
                    "SELECT reason FROM identity.club_stage3_decisions "
                    "WHERE request_id = :r AND decision = 'rejected' ORDER BY id DESC LIMIT 1"
                ),
                {"r": row["request_id"]},
            ).scalar_one_or_none()
        photos = _photos(session, club_id)
    return Overview(
        club_id=row["id"],
        club_name=row["name"],
        stage=row["stage"],
        state=row["status"] or "none",
        links=list(row["links"] or []),
        photos=photos,
        price_kobo=expected_amount_kobo(Purpose.STAGE3_ORG, get_settings()),
        paid=row["paid"],
        reason=reason,
    )


def _editable(session: Session, club_id: UUID) -> None:
    """Refuse unless the club is at stage two and its request can still change.

    Takes the club row's lock, so two edits of one club run one after the other.
    """
    club = session.execute(
        text("SELECT stage FROM identity.organizations WHERE id = :c FOR UPDATE"), {"c": club_id}
    ).scalar_one_or_none()
    if club is None:
        raise NotFound()
    status = session.execute(
        text("SELECT status FROM identity.club_stage3_requests WHERE org_id = :c"), {"c": club_id}
    ).scalar_one_or_none()
    if status is not None and status not in _EDITABLE:
        raise Refused(_NOT_EDITABLE[status], code="not_editable")
    if club == 1:
        raise Refused("Complete stage-two verification first.", code="not_stage_two")
    if club == 3:
        raise Refused(_NOT_EDITABLE["approved"], code="not_editable")


def _draft(session: Session, club_id: UUID) -> None:
    session.execute(
        text(
            "INSERT INTO identity.club_stage3_requests (org_id) VALUES (:c) "
            "ON CONFLICT (org_id) DO NOTHING"
        ),
        {"c": club_id},
    )


def clean_links(links: list[str]) -> list[str]:
    kept = list(dict.fromkeys(link.strip() for link in links if link and link.strip()))
    if not kept:
        raise Refused("Add at least one link: the club's website or a social media page.",
                      code="invalid", field="links")
    if len(kept) > MAX_LINKS:
        raise Refused(f"Add at most {MAX_LINKS} links.", code="invalid", field="links")
    for link in kept:
        if len(link) > MAX_LINK_CHARS or not _LINK_RE.match(link):
            raise Refused("Enter each link as a full web address, starting with https://.",
                          code="invalid", field="links")
    return kept


def save_links(club_id: UUID, links: list[str]) -> None:
    kept = clean_links(links)
    with transaction() as session:
        _editable(session, club_id)
        session.execute(
            text("UPDATE identity.organizations SET links = :l WHERE id = :c"),
            {"l": kept, "c": club_id},
        )
        _draft(session, club_id)


def begin_photo(
    club_id: UUID, content_type: str, size_bytes: int, *, store: ObjectStore | None = None
) -> media.Slot:
    with transaction() as session:
        _editable(session, club_id)
        live = [p for p in _photos(session, club_id) if p.status != "unreadable"]
        if len(live) >= MAX_PHOTOS:
            raise Refused(f"A club can show up to {MAX_PHOTOS} photos. Remove one first.",
                          code="too_many", field="file")
    slot = media.open_slot(club_id, "club_photo", content_type, size_bytes, store=store)
    try:
        with transaction() as session:
            _draft(session, club_id)
    except IntegrityError:  # a concurrent first edit made the draft
        log.info("club_stage3_draft_race")
    return slot


def owned_photo(club_id: UUID, media_id: UUID) -> UUID:
    """The club's id, if this photo is the club's. Raises :class:`NotFound` otherwise."""
    with transaction() as session:
        found = session.execute(
            text(
                "SELECT 1 FROM identity.media_files "
                "WHERE id = :m AND org_id = :c AND kind = 'club_photo' AND status <> 'deleted'"
            ),
            {"m": media_id, "c": club_id},
        ).scalar_one_or_none()
    if found is None:
        raise NotFound()
    return club_id


def remove_photo(club_id: UUID, media_id: UUID, *, store: ObjectStore | None = None) -> None:
    with transaction() as session:
        _editable(session, club_id)
        row = session.execute(
            text(
                "UPDATE identity.media_files SET status = 'deleted', deleted_at = now() "
                "WHERE id = :m AND org_id = :c AND kind = 'club_photo' AND status <> 'deleted' "
                "RETURNING original_key, derivative_key"
            ),
            {"m": media_id, "c": club_id},
        ).one_or_none()
    if row is None:
        raise NotFound()
    store = store or _build_store()
    for key in (row.original_key, row.derivative_key):
        if key:
            try:
                store.delete(key)
            except StoreError as exc:
                log.warning("club_photo_delete_deferred", media_id=str(media_id), error=exc.message)


def photo(club_id: UUID, media_id: UUID, *, store: ObjectStore | None = None) -> bytes:
    """A photo's safe copy. The caller must have authorised access to this club."""
    owned_photo(club_id, media_id)
    data = media.read_derivative(media_id, store=store)
    if data is None:
        raise NotFound()
    return data


def ready_for_payment(session: Session, club_id: UUID) -> bool:
    """A draft with at least one link and one ready photo? (Read by payment start.)"""
    return bool(
        session.execute(
            text(
                """
                SELECT EXISTS (
                    SELECT 1 FROM identity.club_stage3_requests r
                      JOIN identity.organizations o ON o.id = r.org_id
                     WHERE r.org_id = :c AND r.status = 'draft' AND o.links IS NOT NULL
                       AND EXISTS (SELECT 1 FROM identity.media_files m
                                    WHERE m.org_id = :c AND m.kind = 'club_photo'
                                      AND m.status = 'ready')
                )
                """
            ),
            {"c": club_id},
        ).scalar_one()
    )


def mark_paid(session: Session, payment_id: UUID) -> UUID | None:
    """A stage-three payment settled: move the club's draft to review.

    Runs in the LEDGER transaction and must never fail it, so "no match" is a logged
    alarm, not an error.
    """
    request_id: UUID | None = session.execute(
        text(
            """
            UPDATE identity.club_stage3_requests r
               SET status = 'under_review', payment_id = :p, submitted_at = now()
              FROM money.payments pay
             WHERE pay.id = :p AND pay.purpose = 'stage3_org'
               AND r.org_id = pay.org_id AND r.status = 'draft'
            RETURNING r.id
            """
        ),
        {"p": payment_id},
    ).scalar_one_or_none()
    if request_id is None:
        return None
    record(
        session,
        actor=Actor.system("payment_settled"),
        action="club_stage3.submitted",
        subject_type="club_stage3",
        subject_id=str(request_id),
        metadata={"payment_id": str(payment_id)},
    )
    return request_id


def resubmit(club_id: UUID) -> None:
    """Send a rejected request back for review. Covered by the first payment."""
    with transaction() as session:
        row = session.execute(
            text("SELECT id, status FROM identity.club_stage3_requests WHERE org_id = :c FOR UPDATE"),
            {"c": club_id},
        ).one_or_none()
        if row is None or row.status != "rejected":
            raise Refused("There is nothing to send back for review.", code="not_rejected")
        if not session.execute(
            text(
                "SELECT links IS NOT NULL AND EXISTS (SELECT 1 FROM identity.media_files m "
                "WHERE m.org_id = o.id AND m.kind = 'club_photo' AND m.status = 'ready') "
                "FROM identity.organizations o WHERE o.id = :c"
            ),
            {"c": club_id},
        ).scalar_one():
            raise Refused("Add at least one link and one photo first.", code="incomplete")
        session.execute(
            text(
                "UPDATE identity.club_stage3_requests "
                "SET status = 'under_review', submitted_at = now() WHERE id = :r"
            ),
            {"r": row.id},
        )
        record(
            session,
            actor=Actor.system("club_resubmitted"),
            action="club_stage3.resubmitted",
            subject_type="club",
            subject_id=str(club_id),
        )


# ---------------------------------------------------------------------------
# The reviewer (a super administrator, under club.approve)
# ---------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class QueueItem:
    club_id: UUID
    club_name: str
    lga_name: str
    submitted_at: datetime


def queue() -> list[QueueItem]:
    with transaction() as session:
        rows = session.execute(
            text(
                """
                SELECT o.id, o.name, lga.name AS lga_name, r.submitted_at
                  FROM identity.club_stage3_requests r
                  JOIN identity.organizations o ON o.id = r.org_id
                  JOIN ops.locations lga ON lga.id = o.lga_id
                 WHERE r.status = 'under_review'
                 ORDER BY r.submitted_at
                 LIMIT 100
                """
            )
        ).mappings().all()
    return [
        QueueItem(club_id=r["id"], club_name=r["name"], lga_name=r["lga_name"], submitted_at=r["submitted_at"])
        for r in rows
    ]


def _decide(
    club_id: UUID,
    reviewer_id: UUID,
    reviewer_name: str,
    decision: str,
    reason: str | None,
    *,
    request_id: str | None,
    ip_address: str | None,
) -> None:
    with transaction() as session:
        row = session.execute(
            text(
                """
                SELECT r.id, r.status, o.name, o.rep_user_id, o.stage
                  FROM identity.club_stage3_requests r
                  JOIN identity.organizations o ON o.id = r.org_id
                 WHERE r.org_id = :c
                 FOR UPDATE OF r, o
                """
            ),
            {"c": club_id},
        ).mappings().one_or_none()
        if row is None:
            raise NotFound()
        if row["status"] != "under_review":
            raise Refused("This request is no longer waiting for a decision.", code="not_waiting")
        if decision == "approved" and row["stage"] != 2:
            raise Refused("This club is no longer verified at stage two.", code="not_stage_two")

        session.execute(
            text("UPDATE identity.club_stage3_requests SET status = :s, decided_at = now() WHERE id = :r"),
            {"s": decision, "r": row["id"]},
        )
        session.execute(
            text(
                "INSERT INTO identity.club_stage3_decisions (request_id, decision, reviewer_id, reason) "
                "VALUES (:r, :d, :by, :reason)"
            ),
            {"r": row["id"], "d": decision, "by": reviewer_id, "reason": reason},
        )
        if decision == "approved":
            session.execute(text("UPDATE identity.organizations SET stage = 3 WHERE id = :c"), {"c": club_id})
        record(
            session,
            actor=Actor(user_id=reviewer_id, label=reviewer_name, role="reviewer"),
            action=f"club_stage3.{decision}",
            subject_type="club",
            subject_id=str(club_id),
            request_id=request_id,
            ip_address=ip_address,
        )
        name = row["name"]
        if decision == "approved":
            queue_notification(
                session,
                user_id=row["rep_user_id"],
                sms=f"KAFRIADA: {name} is now a stage-three club.",
                subject=f"{name} is now a stage-three club",
                email=f"{name} has reached stage three on KAFRIADA NET. The club can now hold up to 70 players.",
                purpose="club_stage3_approved",
            )
        else:
            queue_notification(
                session,
                user_id=row["rep_user_id"],
                sms=f"KAFRIADA: {name} was not moved to stage three this time. Sign in to see why.",
                subject=f"{name} was not moved to stage three",
                email=f"Your stage-three request for {name} was not approved.\n\nReason: {reason}",
                purpose="club_stage3_rejected",
            )
    log.info("club_stage3_decided", decision=decision)


def approve(
    club_id: UUID, reviewer_id: UUID, reviewer_name: str,
    *, request_id: str | None = None, ip_address: str | None = None,
) -> None:
    _decide(club_id, reviewer_id, reviewer_name, "approved", None, request_id=request_id, ip_address=ip_address)


def reject(
    club_id: UUID, reviewer_id: UUID, reviewer_name: str, reason: str,
    *, request_id: str | None = None, ip_address: str | None = None,
) -> None:
    reason = reason.strip()
    if not reason:
        raise Refused("Say why. The club reads this exactly as you write it.", code="reason", field="reason")
    if len(reason) > MAX_REASON_CHARS:
        raise Refused(f"Keep the reason under {MAX_REASON_CHARS} characters.", code="reason", field="reason")
    _decide(club_id, reviewer_id, reviewer_name, "rejected", reason, request_id=request_id, ip_address=ip_address)
