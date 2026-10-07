"""Data requests (ADM-07): a copy of what is held about a person, or its erasure.

A super administrator answers both. Each answer is a row in `ops.data_requests` and an
audit row.

Erasure is anonymisation, as the privacy notice says before anyone registers. Cleared:
the name, phone, email, password, date of birth, address, body measurements and
emergency contact, every photo and document (the objects themselves, then the rows
marked deleted), and every queued or delivered message addressed to them. Kept: the
KAFRIADA NET ID shell, payments and the ledger, verification decisions, and the audit
trail. Their sessions end, their roles are revoked, club memberships are released, an
approved verification is withdrawn and one under review is closed. The public profile,
card and photo for the ID stop answering.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any
from uuid import UUID

import structlog
from sqlalchemy import text

from kafriada.contexts.access import phone as phone_mod
from kafriada.contexts.access import service as access
from kafriada.contexts.access.service import Principal
from kafriada.contexts.audit.service import Actor, record
from kafriada.contexts.identity import kuid as kuid_mod
from kafriada.contexts.media.store import ObjectStore, StoreError, build_store
from kafriada.db.engine import transaction

log = structlog.get_logger(__name__)

ERASED_NAME = "Removed at the holder's request"
CHANNELS = ("in_person", "phone", "email", "letter")
MAX_NOTE_CHARS = 1_000


class Refused(Exception):
    def __init__(self, message: str, *, code: str) -> None:
        super().__init__(message)
        self.message = message
        self.code = code


class NotFound(Exception):
    pass


@dataclass(frozen=True, slots=True)
class HandledRequest:
    kind: str
    received_via: str
    note: str | None
    handled_by: str
    handled_at: datetime


@dataclass(frozen=True, slots=True)
class Person:
    user_id: UUID
    full_name: str
    kuid: str | None
    roles: tuple[str, ...]
    registered_on: date
    anonymised: bool
    requests: tuple[HandledRequest, ...]


def find(query: str) -> Person | None:
    """One person by KAFRIADA NET ID, phone number or email address. Erased people are found
    by ID only, so their request history can still be read."""
    query = query.strip()
    if not query:
        return None
    try:
        kuid = str(kuid_mod.Kuid.parse(query))
    except kuid_mod.InvalidKuidError:
        kuid = None
    try:
        phone = phone_mod.normalise(query)
    except phone_mod.InvalidPhoneNumberError:
        phone = None
    email = query.lower() if "@" in query else None
    if not (kuid or phone or email):
        return None

    with transaction() as session:
        row = session.execute(
            text(
                """
                SELECT u.id, u.full_name, u.created_at, u.anonymised_at, a.kuid
                  FROM ops.users u
                  LEFT JOIN identity.athletes a ON a.user_id = u.id
                 WHERE (CAST(:kuid AS text) IS NOT NULL AND a.kuid = :kuid)
                    OR (u.anonymised_at IS NULL AND CAST(:phone AS text) IS NOT NULL AND u.phone_e164 = :phone)
                    OR (u.anonymised_at IS NULL AND CAST(:email AS text) IS NOT NULL AND lower(u.email) = :email)
                 LIMIT 1
                """
            ),
            {"kuid": kuid, "phone": phone, "email": email},
        ).mappings().one_or_none()
        if row is None:
            return None
        roles = session.execute(
            text(
                "SELECT DISTINCT role_code FROM ops.user_roles WHERE user_id = :u AND revoked_at IS NULL "
                "ORDER BY role_code"
            ),
            {"u": row["id"]},
        ).scalars().all()
        handled = session.execute(
            text(
                """
                SELECT r.kind, r.received_via, r.note, h.full_name AS handled_by, r.handled_at
                  FROM ops.data_requests r JOIN ops.users h ON h.id = r.handled_by
                 WHERE r.user_id = :u ORDER BY r.handled_at DESC
                """
            ),
            {"u": row["id"]},
        ).mappings().all()
    return Person(
        user_id=row["id"],
        full_name=row["full_name"],
        kuid=row["kuid"],
        roles=tuple(roles),
        registered_on=row["created_at"].date(),
        anonymised=row["anonymised_at"] is not None,
        requests=tuple(HandledRequest(**dict(h)) for h in handled),
    )


def _check(received_via: str, note: str | None, *, required: bool) -> str | None:
    if received_via not in CHANNELS:
        raise Refused("Say how the request arrived.", code="received_via")
    note = (note or "").strip() or None
    if required and not note:
        raise Refused("Say who asked and how their identity was checked. It is kept permanently.", code="note")
    if note and len(note) > MAX_NOTE_CHARS:
        raise Refused(f"Keep the note under {MAX_NOTE_CHARS} characters.", code="note")
    return note


def export(
    actor: Principal,
    user_id: UUID,
    *,
    received_via: str,
    note: str | None = None,
    request_id: str | None = None,
    ip_address: str | None = None,
) -> dict[str, Any]:
    """Everything held about one person, as plain data, and a record that it was handed over."""
    note = _check(received_via, note, required=False)
    with transaction() as session:
        user = session.execute(
            text(
                """
                SELECT id, full_name, first_name, middle_name, surname, phone_e164, phone_verified_at,
                       email, email_verified_at, status, consent_notice_version, consent_given_at,
                       last_login_at, anonymised_at, created_at
                  FROM ops.users WHERE id = :u
                """
            ),
            {"u": user_id},
        ).mappings().one_or_none()
        if user is None:
            raise NotFound
        athlete = session.execute(
            text(
                """
                SELECT a.id, a.kuid, a.date_of_birth, a.gender, a.nationality, a.state_of_origin,
                       a.address_line, a.town, a.sport, a.playing_position, a.secondary_position,
                       a.secondary_sport, a.dominant_side, a.height_cm, a.weight_kg,
                       a.years_experience, a.level_played, a.emergency_name,
                       a.emergency_relationship, a.emergency_phone,
                       reg.name AS registration_lga, cur.name AS current_lga, a.created_at
                  FROM identity.athletes a
                  JOIN ops.locations reg ON reg.id = a.registration_lga_id
                  JOIN ops.locations cur ON cur.id = a.current_lga_id
                 WHERE a.user_id = :u
                """
            ),
            {"u": user_id},
        ).mappings().one_or_none()
        athlete_id = athlete["id"] if athlete else None
        payments = session.execute(
            text(
                """
                SELECT reference, purpose, expected_kobo AS amount_kobo, status,
                       (on_behalf_of IS NOT NULL AND paid_by <> :u) AS paid_by_someone_else,
                       created_at
                  FROM money.payments
                 WHERE paid_by = :u OR on_behalf_of = :a
                 ORDER BY created_at
                """
            ),
            {"u": user_id, "a": athlete_id},
        ).mappings().all()
        verification = session.execute(
            text(
                """
                SELECT v.attempt, v.status, v.submitted_at, v.decided_at,
                       (SELECT json_agg(json_build_object('decision', d.decision, 'reason', d.reason,
                                                          'decided_at', d.decided_at) ORDER BY d.decided_at)
                          FROM identity.verification_decisions d WHERE d.request_id = v.id) AS decisions
                  FROM identity.verification_requests v
                 WHERE v.athlete_id = :a ORDER BY v.created_at
                """
            ),
            {"a": athlete_id},
        ).mappings().all()
        media = session.execute(
            text(
                "SELECT kind, status, created_at, deleted_at FROM identity.media_files "
                "WHERE athlete_id = :a ORDER BY created_at"
            ),
            {"a": athlete_id},
        ).mappings().all()
        clubs = session.execute(
            text(
                """
                SELECT o.name AS club, r.status, r.jersey_no, r.invited_at, r.decided_at
                  FROM identity.roster_members r
                  JOIN identity.teams t ON t.id = r.team_id
                  JOIN identity.organizations o ON o.id = t.org_id
                 WHERE r.athlete_id = :a ORDER BY r.invited_at
                """
            ),
            {"a": athlete_id},
        ).mappings().all()
        roles = session.execute(
            text(
                "SELECT role_code AS role, scope_kind, scope_id, granted_at, revoked_at "
                "FROM ops.user_roles WHERE user_id = :u ORDER BY granted_at"
            ),
            {"u": user_id},
        ).mappings().all()
        activity = session.execute(
            text(
                """
                SELECT occurred_at, action, subject_type
                  FROM ops.audit_log
                 WHERE actor_user_id = :u OR subject_id = :us
                 ORDER BY occurred_at
                """
            ),
            {"u": user_id, "us": str(user_id)},
        ).mappings().all()

        _record(session, actor, user_id, "export", received_via, note, request_id, ip_address)

    profile = {k: v for k, v in dict(athlete).items() if k != "id"} if athlete else None
    return _plain({
        "prepared_at": datetime.now().astimezone(),
        "account": dict(user),
        "athlete": profile,
        "payments": [dict(p) for p in payments],
        "verification": [dict(v) for v in verification],
        "photos_and_documents": [dict(m) for m in media],
        "clubs": [dict(c) for c in clubs],
        "roles": [dict(r) for r in roles],
        "activity": [dict(a) for a in activity],
    })


def erase(
    actor: Principal,
    user_id: UUID,
    *,
    received_via: str,
    note: str,
    current_password: str,
    request_id: str | None = None,
    ip_address: str | None = None,
    store: ObjectStore | None = None,
) -> None:
    """Anonymise one person. Cannot be undone."""
    note = _check(received_via, note, required=True)
    if user_id == actor.user_id:
        raise Refused("Another administrator must handle a request about your own account.", code="self")
    try:
        access.reauthenticate(actor, current_password, request_id=request_id, ip_address=ip_address)
    except access.AccessError as exc:
        raise Refused(exc.message, code="current_password") from exc

    with transaction() as session:
        user = session.execute(
            text("SELECT id, anonymised_at FROM ops.users WHERE id = :u FOR UPDATE"), {"u": user_id}
        ).one_or_none()
        if user is None:
            raise NotFound
        if user.anonymised_at is not None:
            raise Refused("This person has already been erased.", code="already")
        athlete_id = session.execute(
            text("SELECT id FROM identity.athletes WHERE user_id = :u FOR UPDATE"), {"u": user_id}
        ).scalar_one_or_none()

        # Messages first: they hold the phone number and email this is about to clear.
        session.execute(
            text(
                """
                DELETE FROM ops.outbox o USING ops.users u
                 WHERE u.id = :u
                   AND (o.payload ->> 'user_id' = :us
                        OR o.payload ->> 'to' IN (u.phone_e164, u.email))
                """
            ),
            {"u": user_id, "us": str(user_id)},
        )
        session.execute(
            text(
                """
                UPDATE ops.users
                   SET full_name = :erased, first_name = NULL, middle_name = NULL, surname = NULL,
                       phone_e164 = NULL, phone_verified_at = NULL,
                       email = NULL, email_verified_at = NULL,
                       password_hash = NULL, locked_until = NULL,
                       status = 'anonymised', anonymised_at = now()
                 WHERE id = :u
                """
            ),
            {"u": user_id, "erased": ERASED_NAME},
        )
        session.execute(
            text(
                "UPDATE ops.sessions SET revoked_at = now(), revoked_reason = 'anonymised' "
                "WHERE user_id = :u AND revoked_at IS NULL"
            ),
            {"u": user_id},
        )
        session.execute(
            text(
                "UPDATE ops.user_roles SET revoked_at = now(), revoked_by = :by "
                "WHERE user_id = :u AND revoked_at IS NULL"
            ),
            {"u": user_id, "by": actor.user_id},
        )
        media_rows: list[Any] = []
        if athlete_id is not None:
            session.execute(
                text(
                    """
                    UPDATE identity.athletes
                       SET date_of_birth = NULL, gender = NULL, nationality = NULL,
                           state_of_origin = NULL, address_line = NULL, town = NULL,
                           height_cm = NULL, weight_kg = NULL, emergency_name = NULL,
                           emergency_relationship = NULL, emergency_phone = NULL
                     WHERE id = :a
                    """
                ),
                {"a": athlete_id},
            )
            session.execute(
                text(
                    "UPDATE identity.roster_members SET status = 'released', decided_at = now() "
                    "WHERE athlete_id = :a AND status IN ('invited', 'active')"
                ),
                {"a": athlete_id},
            )
            _close_verification(session, athlete_id, actor.user_id)
            media_rows = list(session.execute(
                text(
                    "SELECT id, original_key, derivative_key FROM identity.media_files "
                    "WHERE athlete_id = :a AND deleted_at IS NULL"
                ),
                {"a": athlete_id},
            ).all())

        _record(session, actor, user_id, "erase", received_via, note, request_id, ip_address)

    _delete_objects(media_rows, store or build_store())


def _close_verification(session: Any, athlete_id: UUID, actor_id: UUID) -> None:
    """An approved badge is withdrawn; one waiting for a decision is closed. A draft has no
    payment and simply stays a draft with its files gone."""
    for status_from, decision in (("approved", "revoked"), ("under_review", "rejected"), ("escalated", "rejected")):
        ids = session.execute(
            text(
                "UPDATE identity.verification_requests SET status = :to, decided_at = now() "
                "WHERE athlete_id = :a AND status = :from RETURNING id, attempt"
            ),
            {"a": athlete_id, "from": status_from, "to": decision},
        ).all()
        for row in ids:
            session.execute(
                text(
                    "INSERT INTO identity.verification_decisions (request_id, attempt, decision, reviewer_id, reason) "
                    "VALUES (:r, :n, :d, :by, 'Erased at the holder''s request.')"
                ),
                {"r": row.id, "n": row.attempt, "d": decision, "by": actor_id},
            )


def _delete_objects(rows: list[Any], store: ObjectStore) -> None:
    """Remove the stored files. One that cannot be removed now is left for the hourly purge,
    which picks up rows not yet marked deleted."""
    for row in rows:
        try:
            for key in (row.original_key, row.derivative_key):
                if key:
                    store.delete(key)
        except StoreError as exc:
            log.warning("erase_media_deferred", media_id=str(row.id), error=exc.message)
            continue
        with transaction() as session:
            session.execute(
                text("UPDATE identity.media_files SET status = 'deleted', deleted_at = now() WHERE id = :id"),
                {"id": row.id},
            )


def _record(
    session: Any, actor: Principal, user_id: UUID, kind: str, received_via: str,
    note: str | None, request_id: str | None, ip_address: str | None,
) -> None:
    session.execute(
        text(
            "INSERT INTO ops.data_requests (user_id, kind, received_via, note, handled_by) "
            "VALUES (:u, :k, :via, :note, :by)"
        ),
        {"u": user_id, "k": kind, "via": received_via, "note": note, "by": actor.user_id},
    )
    record(
        session,
        actor=Actor(user_id=actor.user_id, label=actor.full_name, role="super_admin"),
        action=f"data_request.{'exported' if kind == 'export' else 'erased'}",
        subject_type="user",
        subject_id=str(user_id),
        metadata={"received_via": received_via},
        request_id=request_id,
        ip_address=ip_address,
    )


def _plain(value: Any) -> Any:
    """Dates and ids as strings, so the result is JSON as it stands."""
    if isinstance(value, dict):
        return {k: _plain(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [_plain(v) for v in value]
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    return value
