"""Verification: an athlete's photo and document, a payment, and a reviewer's decision.

The state machine and why it has the shape it has are in migration 0007. This module
is the only thing that moves a request along it, and the rules that are policy — not
merely structure — live here, **in the service, never in a screen**:

* Nothing reaches a reviewer without both files re-encoded and the payment settled.
* **A reviewer never decides on their own record.** The case is hidden from them, and
  the action refuses server-side even if they somehow name it. (The second half of the
  rule — an athlete of a club the reviewer administers — needs clubs, which arrive with
  migration 0008; ``_conflict_with_club`` is where it goes and is tested as absent.)
* A rejection needs a reason, shown to the athlete verbatim, and the third rejection
  escalates: resubmission closes and a person takes over in person.
* A withdrawal (``revoked``) needs a reason and the actor's password again.

Every decision writes an append-only ``verification_decisions`` row, an audit row, and
queues an SMS — in the same transaction, so none of the three can exist without the
others.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from uuid import UUID

import structlog
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from kafriada.clock import age_on
from kafriada.contexts.access import service as access
from kafriada.contexts.access.service import Principal
from kafriada.contexts.audit.service import Actor, record
from kafriada.contexts.media import service as media
from kafriada.contexts.media.store import ObjectStore
from kafriada.contexts.payments.rules import Purpose, expected_amount_kobo
from kafriada.db.engine import transaction
from kafriada.outbox.service import queue_sms
from kafriada.settings import get_settings

log = structlog.get_logger(__name__)

MAX_ATTEMPTS = 3
MAX_REASON_CHARS = 1_000

SMS_APPROVED = "KAFRIADA: your verification is approved. Your photo and badge are now on your public profile."
SMS_REJECTED = (
    "KAFRIADA: your verification was not approved this time. Sign in to see why and send it "
    "again. You do not pay again."
)
SMS_ESCALATED = (
    "KAFRIADA: your verification could not be approved after three tries. Please visit your "
    "LGA coordinator, who will help you in person."
)
SMS_REVOKED = "KAFRIADA: your verification has been withdrawn. Contact your LGA coordinator for help."


class Refused(Exception):
    """The action cannot be taken, and the person can be told why."""

    def __init__(self, message: str, *, code: str) -> None:
        super().__init__(message)
        self.message = message
        self.code = code


class NotFound(Exception):
    """No such case — or one this person may not see, which looks the same."""


# ---------------------------------------------------------------------------
# The athlete's side
# ---------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class Overview:
    # none | draft | under_review | approved | rejected | escalated | revoked
    state: str
    attempt: int
    attempts_left: int
    photo: str | None  # the file's status: pending | uploaded | ready | unreadable
    document: str | None
    reason: str | None  # the reviewer's words on the latest rejection or withdrawal
    submitted_at: datetime | None
    paid_amount_kobo: int | None
    paid_at: datetime | None
    can_replace: bool
    ready_to_pay: bool
    price_kobo: int


def _athlete_id(session: Session, user_id: UUID) -> UUID | None:
    return session.execute(
        text("SELECT id FROM identity.athletes WHERE user_id = :u"), {"u": user_id}
    ).scalar_one_or_none()


def overview(user_id: UUID) -> Overview | None:
    """Where the caller's own verification stands. None when they have no athlete record."""
    price = expected_amount_kobo(Purpose.STAGE2_ATHLETE, get_settings())
    with transaction() as session:
        athlete_id = _athlete_id(session, user_id)
        if athlete_id is None:
            return None
        row = session.execute(
            text(
                """
                SELECT v.id, v.status, v.attempt, v.submitted_at,
                       pm.status AS photo, dm.status AS document,
                       p.expected_kobo AS paid_kobo, p.updated_at AS paid_at
                  FROM identity.verification_requests v
                  LEFT JOIN identity.media_files pm ON pm.id = v.photo_media_id
                  LEFT JOIN identity.media_files dm ON dm.id = v.document_media_id
                  LEFT JOIN money.payments p ON p.id = v.payment_id AND p.status = 'success'
                 WHERE v.athlete_id = :a
                 ORDER BY v.created_at DESC LIMIT 1
                """
            ),
            {"a": athlete_id},
        ).one_or_none()
        if row is None:
            return Overview("none", 0, MAX_ATTEMPTS, None, None, None, None, None, None, True, False, price)
        reason = session.execute(
            text(
                "SELECT reason FROM identity.verification_decisions "
                "WHERE request_id = :r AND reason IS NOT NULL ORDER BY id DESC LIMIT 1"
            ),
            {"r": row.id},
        ).scalar_one_or_none()

    replaceable = row.status in ("draft", "rejected")
    return Overview(
        state=row.status,
        attempt=row.attempt,
        attempts_left=max(MAX_ATTEMPTS - row.attempt, 0) if row.status != "escalated" else 0,
        photo=row.photo,
        document=row.document,
        reason=reason if row.status in ("rejected", "escalated", "revoked") else None,
        submitted_at=row.submitted_at,
        paid_amount_kobo=row.paid_kobo,
        paid_at=row.paid_at if row.paid_kobo is not None else None,
        can_replace=replaceable,
        ready_to_pay=row.status == "draft" and row.photo == "ready" and row.document == "ready",
        price_kobo=price,
    )


def begin_upload(
    user_id: UUID, kind: str, content_type: str, size_bytes: int, *, store: ObjectStore | None = None
) -> media.Slot:
    """Open a slot for the caller's photo or document, on their live request."""
    with transaction() as session:
        athlete_id = _athlete_id(session, user_id)
    if athlete_id is None:
        raise Refused("Only a registered athlete can be verified.", code="no_athlete")

    # Refuse before a slot exists, so a locked request leaves no orphan file row.
    with transaction() as session:
        current = session.execute(
            text(
                "SELECT status FROM identity.verification_requests "
                "WHERE athlete_id = :a AND status <> 'revoked'"
            ),
            {"a": athlete_id},
        ).scalar_one_or_none()
    if current is not None and current not in ("draft", "rejected"):
        raise Refused(_NOT_EDITABLE[current], code="not_editable")

    slot = media.open_slot(athlete_id, kind, content_type, size_bytes, store=store)
    column = "photo_media_id" if kind == "photo" else "document_media_id"

    for _ in range(2):  # a concurrent first upload may create the draft under us
        try:
            with transaction() as session:
                request = session.execute(
                    text(
                        "SELECT id, status FROM identity.verification_requests "
                        "WHERE athlete_id = :a AND status <> 'revoked' FOR UPDATE"
                    ),
                    {"a": athlete_id},
                ).one_or_none()
                if request is None:
                    session.execute(
                        text(
                            f"INSERT INTO identity.verification_requests (athlete_id, {column}) "  # noqa: S608
                            "VALUES (:a, :m)"
                        ),
                        {"a": athlete_id, "m": slot.media_id},
                    )
                elif request.status not in ("draft", "rejected"):
                    raise Refused(_NOT_EDITABLE[request.status], code="not_editable")
                else:
                    session.execute(
                        text(f"UPDATE identity.verification_requests SET {column} = :m WHERE id = :r"),  # noqa: S608
                        {"m": slot.media_id, "r": request.id},
                    )
            return slot
        except IntegrityError:
            log.info("verification_draft_race")
            continue
    raise Refused("Please try again.", code="busy")


_NOT_EDITABLE = {
    "under_review": "Your files are being checked and cannot be changed now.",
    "approved": "You are already verified.",
    "escalated": "Your coordinator will help you in person; files cannot be changed here.",
}


def owned_media(user_id: UUID, media_id: UUID) -> UUID:
    """The athlete id, if the file is the caller's own. Raises NotFound otherwise."""
    with transaction() as session:
        athlete_id = session.execute(
            text(
                "SELECT m.athlete_id FROM identity.media_files m "
                "JOIN identity.athletes a ON a.id = m.athlete_id "
                "WHERE m.id = :m AND a.user_id = :u"
            ),
            {"m": media_id, "u": user_id},
        ).scalar_one_or_none()
    if athlete_id is None:
        raise NotFound()
    return athlete_id  # type: ignore[no-any-return]


def resubmit(user_id: UUID) -> None:
    """Send a rejected request back for review, against the payment already made."""
    with transaction() as session:
        row = session.execute(
            text(
                """
                SELECT v.id, v.attempt, v.status, pm.status AS photo, dm.status AS document
                  FROM identity.verification_requests v
                  JOIN identity.athletes a ON a.id = v.athlete_id
                  LEFT JOIN identity.media_files pm ON pm.id = v.photo_media_id
                  LEFT JOIN identity.media_files dm ON dm.id = v.document_media_id
                 WHERE a.user_id = :u AND v.status <> 'revoked'
                 FOR UPDATE OF v
                """
            ),
            {"u": user_id},
        ).one_or_none()
        if row is None or row.status != "rejected":
            raise Refused("There is nothing to send again.", code="not_rejected")
        if row.attempt >= MAX_ATTEMPTS:  # unreachable while escalation works; belt and braces
            raise Refused("Your coordinator will help you in person.", code="escalated")
        if row.photo != "ready" or row.document != "ready":
            raise Refused("Add both files first, and wait until they are ready.", code="files_not_ready")
        session.execute(
            text(
                "UPDATE identity.verification_requests SET status = 'under_review', "
                "attempt = attempt + 1, submitted_at = now() WHERE id = :r"
            ),
            {"r": row.id},
        )
        record(
            session,
            actor=Actor(user_id=user_id, label="athlete", role="athlete"),
            action="verification.resubmitted",
            subject_type="verification",
            subject_id=str(row.id),
            metadata={"attempt": row.attempt + 1},
        )


def ready_for_payment(session: Session, user_id: UUID) -> bool:
    """Does the athlete have a draft with both files re-encoded? (Read by payment start.)"""
    return bool(
        session.execute(
            text(
                """
                SELECT EXISTS (
                    SELECT 1 FROM identity.verification_requests v
                      JOIN identity.athletes a ON a.id = v.athlete_id
                      JOIN identity.media_files pm ON pm.id = v.photo_media_id AND pm.status = 'ready'
                      JOIN identity.media_files dm ON dm.id = v.document_media_id AND dm.status = 'ready'
                     WHERE a.user_id = :u AND v.status = 'draft'
                )
                """
            ),
            {"u": user_id},
        ).scalar_one()
    )


def mark_paid(session: Session, payment_id: UUID) -> UUID | None:
    """A payment settled: move the payer's draft to review. Runs in the LEDGER transaction.

    It must never be able to fail that transaction — a webhook that cannot record a
    real payment because of a verification detail would lose money. So the UPDATE is
    guarded to match only a draft that already satisfies the table's constraints, and
    "no match" is a logged alarm, not an exception.
    """
    request_id: UUID | None = session.execute(
        text(
            """
            UPDATE identity.verification_requests v
               SET status = 'under_review', payment_id = :p, submitted_at = now()
              FROM money.payments pay, identity.athletes a
             WHERE pay.id = :p AND pay.purpose = 'stage2_athlete' AND pay.on_behalf_of IS NULL
               AND a.user_id = pay.paid_by AND v.athlete_id = a.id
               AND v.status = 'draft'
               AND v.photo_media_id IS NOT NULL AND v.document_media_id IS NOT NULL
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
        action="verification.submitted",
        subject_type="verification",
        subject_id=str(request_id),
        metadata={"payment_id": str(payment_id)},
    )
    return request_id


# ---------------------------------------------------------------------------
# The reviewer's side
# ---------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class QueueItem:
    request_id: UUID
    kuid: str
    full_name: str
    submitted_at: datetime
    attempt: int


@dataclass(frozen=True, slots=True)
class Case:
    request_id: UUID
    kuid: str
    full_name: str
    date_of_birth: date
    age: int
    attempt: int
    submitted_at: datetime | None
    paid_kobo: int | None
    paid_at: datetime | None
    waiting: int  # how many are in this queue


_CASE_SQL = """
    SELECT v.id, v.status, v.attempt, v.submitted_at, v.photo_media_id, v.document_media_id,
           a.id AS athlete_id, a.user_id AS athlete_user_id, a.kuid, a.date_of_birth,
           a.current_lga_id, u.full_name,
           pm.status AS photo, dm.status AS document,
           p.expected_kobo AS paid_kobo, p.updated_at AS paid_at
      FROM identity.verification_requests v
      JOIN identity.athletes a ON a.id = v.athlete_id
      JOIN ops.users u ON u.id = a.user_id
      LEFT JOIN identity.media_files pm ON pm.id = v.photo_media_id
      LEFT JOIN identity.media_files dm ON dm.id = v.document_media_id
      LEFT JOIN money.payments p ON p.id = v.payment_id
     WHERE v.id = :id
"""


def _conflict_with_club(session: Session, reviewer_id: UUID, athlete_id: UUID) -> bool:
    """Is the athlete on a roster of a club the reviewer administers?

    Clubs do not exist yet (migration 0008). Until they do there is nothing to be in
    conflict with, and this says so plainly rather than pretending the rule is met.
    """
    return False


def _visible_case(session: Session, reviewer: Principal, lga_id: str, request_id: UUID, *, lock: bool):  # type: ignore[no-untyped-def]
    """The case row, or NotFound — for a wrong LGA and for the reviewer's own record alike."""
    row = session.execute(
        text(_CASE_SQL + (" FOR UPDATE OF v" if lock else "")), {"id": request_id}
    ).one_or_none()
    if (
        row is None
        or row.current_lga_id != lga_id
        or row.athlete_user_id == reviewer.user_id
        or _conflict_with_club(session, reviewer.user_id, row.athlete_id)
    ):
        raise NotFound()
    return row


def queue(reviewer: Principal, lga_id: str) -> list[QueueItem]:
    """Cases waiting in one LGA, oldest first. The reviewer's own record is never in it."""
    with transaction() as session:
        rows = session.execute(
            text(
                """
                SELECT v.id, v.attempt, v.submitted_at, a.id AS athlete_id, a.kuid, u.full_name
                  FROM identity.verification_requests v
                  JOIN identity.athletes a ON a.id = v.athlete_id
                  JOIN ops.users u ON u.id = a.user_id
                  JOIN identity.media_files pm ON pm.id = v.photo_media_id AND pm.status = 'ready'
                  JOIN identity.media_files dm ON dm.id = v.document_media_id AND dm.status = 'ready'
                 WHERE v.status = 'under_review' AND a.current_lga_id = :lga
                   AND a.user_id <> :me
                 ORDER BY v.submitted_at
                """
            ),
            {"lga": lga_id, "me": reviewer.user_id},
        ).all()
        return [
            QueueItem(r.id, r.kuid, r.full_name, r.submitted_at, r.attempt)
            for r in rows
            if not _conflict_with_club(session, reviewer.user_id, r.athlete_id)
        ]


def case(reviewer: Principal, lga_id: str, request_id: UUID) -> Case:
    with transaction() as session:
        row = _visible_case(session, reviewer, lga_id, request_id, lock=False)
        waiting = session.execute(
            text(
                "SELECT count(*) FROM identity.verification_requests v "
                "JOIN identity.athletes a ON a.id = v.athlete_id "
                "WHERE v.status = 'under_review' AND a.current_lga_id = :lga AND a.user_id <> :me"
            ),
            {"lga": lga_id, "me": reviewer.user_id},
        ).scalar_one()
    if row.status != "under_review":
        raise NotFound()
    return Case(
        request_id=row.id,
        kuid=row.kuid,
        full_name=row.full_name,
        date_of_birth=row.date_of_birth,
        age=age_on(row.date_of_birth),
        attempt=row.attempt,
        submitted_at=row.submitted_at,
        paid_kobo=row.paid_kobo,
        paid_at=row.paid_at,
        waiting=waiting,
    )


def case_media(
    reviewer: Principal, lga_id: str, request_id: UUID, kind: str, *, store: ObjectStore | None = None
) -> bytes:
    """The photo or document a reviewer is deciding on — only while deciding."""
    with transaction() as session:
        row = _visible_case(session, reviewer, lga_id, request_id, lock=False)
    if row.status != "under_review" or kind not in ("photo", "document"):
        raise NotFound()
    media_id = row.photo_media_id if kind == "photo" else row.document_media_id
    data = media.read_derivative(media_id, store=store) if media_id else None
    if data is None:
        raise NotFound()
    return data


def _decide(
    reviewer: Principal,
    lga_id: str,
    request_id: UUID,
    *,
    decision: str,
    reason: str | None,
    request_ip: str | None,
    request_id_header: str | None,
) -> str:
    with transaction() as session:
        row = _visible_case(session, reviewer, lga_id, request_id, lock=True)
        if row.status != "under_review":
            raise Refused("This case is no longer waiting for a decision.", code="not_waiting")
        if row.photo != "ready" or row.document != "ready":
            # Never decide on a file the reviewer cannot see.
            raise Refused("The files for this case are not ready to be seen.", code="files_not_ready")

        actor = Actor(user_id=reviewer.user_id, label=reviewer.full_name, role="reviewer")
        if decision == "approved":
            new_status, sms = "approved", SMS_APPROVED
        else:
            new_status = "escalated" if row.attempt >= MAX_ATTEMPTS else "rejected"
            sms = SMS_ESCALATED if new_status == "escalated" else SMS_REJECTED

        session.execute(
            text(
                "UPDATE identity.verification_requests SET status = :s, decided_at = now() "
                "WHERE id = :id"
            ),
            {"s": new_status, "id": row.id},
        )
        _write_decision(session, row.id, row.attempt, decision, reviewer.user_id, reason)
        if new_status == "escalated":
            _write_decision(session, row.id, row.attempt, "escalated", None, None)
        record(
            session,
            actor=actor,
            action=f"verification.{decision}",
            subject_type="verification",
            subject_id=str(row.id),
            metadata={"attempt": row.attempt, "outcome": new_status, "kuid": row.kuid},
            request_id=request_id_header,
            ip_address=request_ip,
        )
        _tell_athlete(session, row.athlete_user_id, sms, purpose=f"verification_{new_status}")
    log.info("verification_decided", outcome=new_status, attempt=row.attempt)
    return new_status


def approve(
    reviewer: Principal,
    lga_id: str,
    request_id: UUID,
    *,
    ip_address: str | None = None,
    request_id_header: str | None = None,
) -> str:
    return _decide(
        reviewer, lga_id, request_id, decision="approved", reason=None,
        request_ip=ip_address, request_id_header=request_id_header,
    )


def reject(
    reviewer: Principal,
    lga_id: str,
    request_id: UUID,
    reason: str,
    *,
    ip_address: str | None = None,
    request_id_header: str | None = None,
) -> str:
    reason = reason.strip()
    if not reason:
        raise Refused("Say what is wrong, so the athlete can fix it.", code="reason")
    if len(reason) > MAX_REASON_CHARS:
        raise Refused(f"Keep the reason under {MAX_REASON_CHARS} characters.", code="reason")
    return _decide(
        reviewer, lga_id, request_id, decision="rejected", reason=reason,
        request_ip=ip_address, request_id_header=request_id_header,
    )


@dataclass(frozen=True, slots=True)
class AdminLookup:
    """What a super_admin needs to decide whether — and what — to revoke."""

    request_id: UUID
    kuid: str
    full_name: str
    status: str
    attempt: int
    decided_at: datetime | None


def find_by_kuid(kuid: str) -> AdminLookup | None:
    """The current verification request for an athlete, by KUID (ADM-03).

    The only way today a super_admin gets from "which athlete" to the request
    id ``revoke`` needs. Returns whatever exists, at whatever status — the
    caller decides what, if anything, can be done with it; ``revoke`` itself
    still refuses anything that is not ``approved``.
    """
    with transaction() as session:
        row = session.execute(
            text(
                "SELECT v.id, v.status, v.attempt, v.decided_at, a.kuid, u.full_name "
                "FROM identity.verification_requests v "
                "JOIN identity.athletes a ON a.id = v.athlete_id "
                "JOIN ops.users u ON u.id = a.user_id "
                "WHERE a.kuid = :k"
            ),
            {"k": kuid.strip()},
        ).mappings().one_or_none()
    if row is None:
        return None
    return AdminLookup(
        request_id=row["id"], kuid=row["kuid"], full_name=row["full_name"],
        status=row["status"], attempt=row["attempt"], decided_at=row["decided_at"],
    )


def revoke(
    actor: Principal,
    request_id: UUID,
    reason: str,
    current_password: str,
    *,
    ip_address: str | None = None,
    request_id_header: str | None = None,
) -> None:
    """Withdraw an approved verification (ADM-03). Reason and password are both required."""
    reason = reason.strip()
    if not reason:
        raise Refused("Say why this is being withdrawn. It is kept permanently.", code="reason")
    if len(reason) > MAX_REASON_CHARS:
        raise Refused(f"Keep the reason under {MAX_REASON_CHARS} characters.", code="reason")
    try:
        access.reauthenticate(
            actor, current_password, request_id=request_id_header, ip_address=ip_address
        )
    except access.AccessError as exc:
        raise Refused(exc.message, code="password") from exc

    with transaction() as session:
        row = session.execute(
            text(
                "SELECT v.id, v.status, v.attempt, a.user_id AS athlete_user_id, a.kuid "
                "FROM identity.verification_requests v "
                "JOIN identity.athletes a ON a.id = v.athlete_id WHERE v.id = :id FOR UPDATE OF v"
            ),
            {"id": request_id},
        ).one_or_none()
        if row is None:
            raise NotFound()
        if row.status != "approved":
            raise Refused("This verification is not currently approved.", code="not_approved")
        session.execute(
            text(
                "UPDATE identity.verification_requests SET status = 'revoked', decided_at = now() "
                "WHERE id = :id"
            ),
            {"id": row.id},
        )
        _write_decision(session, row.id, row.attempt, "revoked", actor.user_id, reason)
        record(
            session,
            actor=Actor(user_id=actor.user_id, label=actor.full_name, role="super_admin"),
            action="verification.revoked",
            subject_type="verification",
            subject_id=str(row.id),
            metadata={"kuid": row.kuid},
            request_id=request_id_header,
            ip_address=ip_address,
        )
        _tell_athlete(session, row.athlete_user_id, SMS_REVOKED, purpose="verification_revoked")


def _write_decision(
    session: Session,
    request_id: UUID,
    attempt: int,
    decision: str,
    reviewer_id: UUID | None,
    reason: str | None,
) -> None:
    session.execute(
        text(
            "INSERT INTO identity.verification_decisions "
            "(request_id, attempt, decision, reviewer_id, reason) "
            "VALUES (:r, :a, :d, :rev, :reason)"
        ),
        {"r": request_id, "a": attempt, "d": decision, "rev": reviewer_id, "reason": reason},
    )


def _tell_athlete(session: Session, athlete_user_id: UUID, body: str, *, purpose: str) -> None:
    phone = session.execute(
        text("SELECT phone_e164 FROM ops.users WHERE id = :u"), {"u": athlete_user_id}
    ).scalar_one_or_none()
    if phone:
        queue_sms(session, to_phone=phone, body=body, purpose=purpose)


# ---------------------------------------------------------------------------
# The public side
# ---------------------------------------------------------------------------
def public_photo(kuid: str, *, store: ObjectStore | None = None) -> bytes | None:
    """An approved athlete's photo, and nothing else, ever. None otherwise."""
    with transaction() as session:
        media_id = session.execute(
            text(
                """
                SELECT v.photo_media_id
                  FROM identity.verification_requests v
                  JOIN identity.athletes a ON a.id = v.athlete_id
                 WHERE a.kuid = :k AND v.status = 'approved'
                """
            ),
            {"k": kuid},
        ).scalar_one_or_none()
    return media.read_derivative(media_id, store=store) if media_id else None
