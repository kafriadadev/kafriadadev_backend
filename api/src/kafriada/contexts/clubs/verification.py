"""Club verification (CLB-04): a document, a payment, and an administrator's decision.

The same machine as an athlete's, with a club as the subject:

    draft --paid--> under_review --approve--> approved (the club is stage 2)
                        |  ^
                     reject  +-- resubmit (against the same payment)
                        v
                    rejected

The rules that are policy live here, not in a screen: nothing reaches a reviewer without
its document re-encoded and the payment settled; only an approved, not-yet-verified club
can start; a rejection needs a reason, shown to the club verbatim. Every decision writes
an append-only ``club_verification_decisions`` row, an audit row and a notification, in
one transaction. Money is the ordinary payment path: ``payments.service`` starts the
checkout and ``mark_paid`` below is called from settlement, inside the ledger
transaction, so it can never be the reason a real payment goes unrecorded.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

import structlog
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from kafriada.contexts.audit.service import Actor, record
from kafriada.contexts.media import service as media
from kafriada.contexts.media.store import ObjectStore
from kafriada.contexts.payments.rules import Purpose, expected_amount_kobo
from kafriada.db.engine import transaction
from kafriada.outbox.service import queue_notification
from kafriada.settings import get_settings

log = structlog.get_logger(__name__)

MAX_REASON_CHARS = 1_000

_NOT_EDITABLE = {
    "under_review": "Your document is being checked and cannot be changed now.",
    "approved": "This club is already verified.",
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
class Overview:
    club_id: UUID
    club_name: str
    club_status: str  # pending_review | approved | suspended
    verified: bool
    # none | draft | under_review | approved | rejected
    state: str
    document: str | None  # media status: pending | uploaded | ready | unreadable
    price_kobo: int
    paid: bool
    reason: str | None  # the reviewer's words on the latest rejection


def overview(club_id: UUID) -> Overview | None:
    with transaction() as session:
        row = session.execute(
            text(
                """
                SELECT o.id, o.name, o.status, o.stage,
                       v.id AS request_id, v.status AS request_status, v.payment_id,
                       dm.status AS document,
                       EXISTS (SELECT 1 FROM money.payments p
                                WHERE p.org_id = o.id AND p.status = 'success') AS paid
                  FROM identity.organizations o
                  LEFT JOIN identity.club_verification_requests v
                         ON v.org_id = o.id AND v.status <> 'revoked'
                  LEFT JOIN identity.media_files dm ON dm.id = v.document_media_id
                 WHERE o.id = :c
                """
            ),
            {"c": club_id},
        ).mappings().one_or_none()
        if row is None:
            return None
        reason = None
        if row["request_status"] == "rejected":
            reason = session.execute(
                text(
                    "SELECT reason FROM identity.club_verification_decisions "
                    "WHERE request_id = :r AND decision = 'rejected' ORDER BY id DESC LIMIT 1"
                ),
                {"r": row["request_id"]},
            ).scalar_one_or_none()
    return Overview(
        club_id=row["id"],
        club_name=row["name"],
        club_status=row["status"],
        verified=row["stage"] == 2,
        state=row["request_status"] or "none",
        document=row["document"],
        price_kobo=expected_amount_kobo(Purpose.STAGE2_ORG, get_settings()),
        paid=row["paid"],
        reason=reason,
    )


def _admin_athlete_id(session: Session, user_id: UUID) -> UUID | None:
    return session.execute(
        text("SELECT id FROM identity.athletes WHERE user_id = :u"), {"u": user_id}
    ).scalar_one_or_none()


def begin_upload(
    user_id: UUID,
    club_id: UUID,
    content_type: str,
    size_bytes: int,
    *,
    store: ObjectStore | None = None,
) -> media.Slot:
    """Open a slot for the club's registration document or LGA letter."""
    with transaction() as session:
        club = session.execute(
            text("SELECT status, stage FROM identity.organizations WHERE id = :c"), {"c": club_id}
        ).mappings().one_or_none()
        athlete_id = _admin_athlete_id(session, user_id)
        current = session.execute(
            text(
                "SELECT status FROM identity.club_verification_requests "
                "WHERE org_id = :c AND status <> 'revoked'"
            ),
            {"c": club_id},
        ).scalar_one_or_none()
    if club is None:
        raise NotFound()
    if athlete_id is None:
        raise Refused("Only a registered athlete can administer a club.", code="no_athlete")
    if club["status"] != "approved":
        raise Refused("A club must be approved before it can be verified.", code="not_approved")
    if current is not None and current not in ("draft", "rejected"):
        raise Refused(_NOT_EDITABLE[current], code="not_editable")

    slot = media.open_slot(athlete_id, "club_document", content_type, size_bytes, store=store)

    for _ in range(2):  # a concurrent first upload may create the draft under us
        try:
            with transaction() as session:
                request = session.execute(
                    text(
                        "SELECT id, status FROM identity.club_verification_requests "
                        "WHERE org_id = :c AND status <> 'revoked' FOR UPDATE"
                    ),
                    {"c": club_id},
                ).one_or_none()
                if request is None:
                    session.execute(
                        text(
                            "INSERT INTO identity.club_verification_requests (org_id, document_media_id) "
                            "VALUES (:c, :m)"
                        ),
                        {"c": club_id, "m": slot.media_id},
                    )
                elif request.status not in ("draft", "rejected"):
                    raise Refused(_NOT_EDITABLE[request.status], code="not_editable")
                else:
                    session.execute(
                        text(
                            "UPDATE identity.club_verification_requests "
                            "SET document_media_id = :m WHERE id = :r"
                        ),
                        {"m": slot.media_id, "r": request.id},
                    )
            return slot
        except IntegrityError:
            log.info("club_verification_draft_race")
            continue
    raise Refused("Please try again.", code="busy")


def owned_media(user_id: UUID, club_id: UUID, media_id: UUID) -> UUID:
    """The uploader's athlete id, if this file is the caller's and belongs to this club's request."""
    with transaction() as session:
        athlete_id = session.execute(
            text(
                """
                SELECT m.athlete_id
                  FROM identity.media_files m
                  JOIN identity.athletes a ON a.id = m.athlete_id
                  JOIN identity.club_verification_requests v ON v.document_media_id = m.id
                 WHERE m.id = :m AND a.user_id = :u AND v.org_id = :c AND m.kind = 'club_document'
                """
            ),
            {"m": media_id, "u": user_id, "c": club_id},
        ).scalar_one_or_none()
    if athlete_id is None:
        raise NotFound()
    return athlete_id  # type: ignore[no-any-return]


def resubmit(club_id: UUID, user_id: UUID) -> None:
    """Send a rejected request back for review, against the payment already made."""
    with transaction() as session:
        row = session.execute(
            text(
                """
                SELECT v.id, v.status, dm.status AS document
                  FROM identity.club_verification_requests v
                  LEFT JOIN identity.media_files dm ON dm.id = v.document_media_id
                 WHERE v.org_id = :c AND v.status <> 'revoked'
                 FOR UPDATE OF v
                """
            ),
            {"c": club_id},
        ).one_or_none()
        if row is None or row.status != "rejected":
            raise Refused("There is nothing to send again.", code="not_rejected")
        if row.document != "ready":
            raise Refused("Add the document first, and wait until it is ready.", code="files_not_ready")
        session.execute(
            text(
                "UPDATE identity.club_verification_requests "
                "SET status = 'under_review', submitted_at = now() WHERE id = :r"
            ),
            {"r": row.id},
        )
        record(
            session,
            actor=Actor(user_id=user_id, label="club administrator", role="club_admin"),
            action="club_verification.resubmitted",
            subject_type="club",
            subject_id=str(club_id),
        )


def ready_for_payment(session: Session, club_id: UUID) -> bool:
    """Does the club have a draft whose document has been re-encoded? (Read by payment start.)"""
    return bool(
        session.execute(
            text(
                """
                SELECT EXISTS (
                    SELECT 1 FROM identity.club_verification_requests v
                      JOIN identity.media_files dm ON dm.id = v.document_media_id AND dm.status = 'ready'
                     WHERE v.org_id = :c AND v.status = 'draft'
                )
                """
            ),
            {"c": club_id},
        ).scalar_one()
    )


def mark_paid(session: Session, payment_id: UUID) -> UUID | None:
    """A payment settled: move that club's draft to review. Runs in the LEDGER transaction.

    It must never be able to fail that transaction, so the UPDATE only matches a draft
    that already satisfies the table's constraints and "no match" is a logged alarm.
    """
    request_id: UUID | None = session.execute(
        text(
            """
            UPDATE identity.club_verification_requests v
               SET status = 'under_review', payment_id = :p, submitted_at = now()
              FROM money.payments pay
             WHERE pay.id = :p AND pay.purpose = 'stage2_org'
               AND v.org_id = pay.org_id AND v.status = 'draft'
               AND v.document_media_id IS NOT NULL
            RETURNING v.id
            """
        ),
        {"p": payment_id},
    ).scalar_one_or_none()
    if request_id is None:
        return None
    record(
        session,
        actor=Actor.system("payment_settled"),
        action="club_verification.submitted",
        subject_type="club_verification",
        subject_id=str(request_id),
        metadata={"payment_id": str(payment_id)},
    )
    return request_id


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
                SELECT o.id, o.name, lga.name AS lga_name, v.submitted_at
                  FROM identity.club_verification_requests v
                  JOIN identity.organizations o ON o.id = v.org_id
                  JOIN ops.locations lga ON lga.id = o.lga_id
                 WHERE v.status = 'under_review'
                 ORDER BY v.submitted_at
                 LIMIT 100
                """
            )
        ).mappings().all()
    return [
        QueueItem(club_id=r["id"], club_name=r["name"], lga_name=r["lga_name"], submitted_at=r["submitted_at"])
        for r in rows
    ]


def document(club_id: UUID, *, store: ObjectStore | None = None) -> bytes:
    """The document a reviewer is deciding on — only while it is waiting for a decision."""
    with transaction() as session:
        media_id = session.execute(
            text(
                "SELECT document_media_id FROM identity.club_verification_requests "
                "WHERE org_id = :c AND status = 'under_review'"
            ),
            {"c": club_id},
        ).scalar_one_or_none()
    data = media.read_derivative(media_id, store=store) if media_id else None
    if data is None:
        raise NotFound()
    return data


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
                SELECT v.id, v.status, dm.status AS document, o.name, o.rep_user_id
                  FROM identity.club_verification_requests v
                  JOIN identity.organizations o ON o.id = v.org_id
                  LEFT JOIN identity.media_files dm ON dm.id = v.document_media_id
                 WHERE v.org_id = :c AND v.status <> 'revoked'
                 FOR UPDATE OF v
                """
            ),
            {"c": club_id},
        ).mappings().one_or_none()
        if row is None:
            raise NotFound()
        if row["status"] != "under_review":
            raise Refused("This request is no longer waiting for a decision.", code="not_waiting")
        if row["document"] != "ready":
            raise Refused("The document is not ready to be seen.", code="files_not_ready")

        new_status = "approved" if decision == "approved" else "rejected"
        session.execute(
            text(
                "UPDATE identity.club_verification_requests SET status = :s, decided_at = now() WHERE id = :r"
            ),
            {"s": new_status, "r": row["id"]},
        )
        session.execute(
            text(
                "INSERT INTO identity.club_verification_decisions (request_id, decision, reviewer_id, reason) "
                "VALUES (:r, :d, :by, :reason)"
            ),
            {"r": row["id"], "d": decision, "by": reviewer_id, "reason": reason},
        )
        if decision == "approved":
            session.execute(
                text("UPDATE identity.organizations SET stage = 2 WHERE id = :c"), {"c": club_id}
            )
        record(
            session,
            actor=Actor(user_id=reviewer_id, label=reviewer_name, role="reviewer"),
            action=f"club_verification.{decision}",
            subject_type="club",
            subject_id=str(club_id),
            request_id=request_id,
            ip_address=ip_address,
        )
        if decision == "approved":
            queue_notification(
                session,
                user_id=row["rep_user_id"],
                sms=f"KAFRIADA: {row['name']} is now a verified club.",
                subject=f"{row['name']} is now a verified club",
                email=f"{row['name']} is now a verified club on KAFRIADA. The badge shows on your club page.",
                purpose="club_verification_approved",
            )
        else:
            queue_notification(
                session,
                user_id=row["rep_user_id"],
                sms=f"KAFRIADA: {row['name']} was not verified this time. Sign in to see why.",
                subject=f"{row['name']} was not verified",
                email=f"Your verification request for {row['name']} was not approved.\n\nReason: {reason}",
                purpose="club_verification_rejected",
            )
    log.info("club_verification_decided", decision=decision)


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
