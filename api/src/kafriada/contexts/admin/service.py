"""What the administrator console reads: the dashboard, users and roles, clubs, the audit log.

Read models only. Everything that *changes* something (a grant, a revocation, an approval)
stays in the context that owns it and keeps its own checks; this module never writes.
Who may call these is decided by the routes, not here.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from uuid import UUID

from sqlalchemy import text

from kafriada.contexts.access import phone as phone_mod
from kafriada.contexts.identity import kuid as kuid_mod
from kafriada.db.engine import transaction

PAGE = 25
AUDIT_PAGE = 50


def _like(fragment: str) -> str:
    escaped = fragment.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


# ---------------------------------------------------------------------------
# ADM-01
# ---------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class Overview:
    collected_kobo: int
    payments: int
    unresolved: int
    # None until the nightly check has ever run.
    ledger_ok: bool | None
    ledger_checked_at: datetime | None
    registered: int
    paid: int
    conversion_percent: float
    clubs: int
    verified_clubs: int
    clubs_waiting: int
    review_median_hours: float | None
    live_lgas: int


def overview() -> Overview:
    with transaction() as session:
        money = session.execute(
            text(
                """
                SELECT count(*) FILTER (WHERE status = 'success' AND updated_at > now() - interval '24 hours') AS paid_n,
                       coalesce(sum(expected_kobo) FILTER (WHERE status = 'success'
                                AND updated_at > now() - interval '24 hours'), 0) AS paid_kobo,
                       count(*) FILTER (WHERE status = 'frozen') AS frozen_n
                  FROM money.payments
                """
            )
        ).mappings().one()
        check = session.execute(
            text("SELECT ok, finished_at FROM ops.job_runs WHERE job = 'integrity' ORDER BY finished_at DESC LIMIT 1")
        ).mappings().one_or_none()
        funnel = session.execute(
            text(
                """
                SELECT (SELECT count(*) FROM identity.athletes a JOIN ops.users u ON u.id = a.user_id
                         WHERE u.anonymised_at IS NULL) AS registered,
                       (SELECT count(*) FROM identity.verification_requests WHERE payment_id IS NOT NULL) AS paid,
                       (SELECT count(*) FROM identity.organizations WHERE status <> 'unconfirmed') AS clubs,
                       (SELECT count(*) FROM identity.organizations WHERE stage = 2) AS verified_clubs,
                       (SELECT count(*) FROM identity.club_verification_requests
                         WHERE status = 'under_review') AS clubs_waiting,
                       (SELECT count(*) FROM ops.locations WHERE kind = 'lga' AND is_live) AS live
                """
            )
        ).mappings().one()
        median = session.execute(
            text(
                """
                SELECT percentile_cont(0.5) WITHIN GROUP (
                         ORDER BY extract(epoch FROM (decided_at - submitted_at)) / 3600.0) AS hours
                  FROM identity.verification_requests
                 WHERE decided_at IS NOT NULL AND submitted_at IS NOT NULL
                   AND decided_at > now() - interval '30 days'
                """
            )
        ).scalar_one_or_none()
    registered = int(funnel["registered"])
    paid = int(funnel["paid"])
    return Overview(
        collected_kobo=int(money["paid_kobo"]),
        payments=int(money["paid_n"]),
        unresolved=int(money["frozen_n"]),
        ledger_ok=None if check is None else bool(check["ok"]),
        ledger_checked_at=None if check is None else check["finished_at"],
        registered=registered,
        paid=paid,
        conversion_percent=round(100.0 * paid / registered, 1) if registered else 0.0,
        clubs=int(funnel["clubs"]),
        verified_clubs=int(funnel["verified_clubs"]),
        clubs_waiting=int(funnel["clubs_waiting"]),
        review_median_hours=None if median is None else round(float(median), 1),
        live_lgas=int(funnel["live"]),
    )


# ---------------------------------------------------------------------------
# ADM-02
# ---------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class Grant:
    grant_id: UUID
    role: str
    scope_kind: str
    scope_id: str | None
    scope_name: str | None


@dataclass(frozen=True, slots=True)
class UserRow:
    user_id: UUID
    full_name: str
    phone_masked: str
    kuid: str | None
    last_seen: datetime | None
    roles: tuple[Grant, ...]


@dataclass(frozen=True, slots=True)
class UserPage:
    users: tuple[UserRow, ...]
    page: int
    has_more: bool


_USER_SQL = """
    SELECT u.id, u.full_name, u.phone_e164, a.kuid,
           (SELECT max(s.last_seen_at) FROM ops.sessions s WHERE s.user_id = u.id) AS last_seen,
           coalesce((
               SELECT json_agg(json_build_object(
                          'grant_id', ur.id, 'role', ur.role_code, 'scope_kind', ur.scope_kind,
                          'scope_id', ur.scope_id, 'scope_name', coalesce(loc.name, org.name))
                      ORDER BY ur.granted_at)
                 FROM ops.user_roles ur
                 LEFT JOIN ops.locations loc ON loc.id = ur.scope_id
                 LEFT JOIN identity.organizations org
                        ON ur.scope_kind = 'club' AND org.id::text = ur.scope_id
                WHERE ur.user_id = u.id AND ur.revoked_at IS NULL), '[]'::json) AS roles
      FROM ops.users u
      LEFT JOIN identity.athletes a ON a.user_id = u.id
"""


def _user(row) -> UserRow:  # type: ignore[no-untyped-def]
    return UserRow(
        user_id=row["id"],
        full_name=row["full_name"],
        phone_masked=phone_mod.mask(row["phone_e164"]),
        kuid=row["kuid"],
        last_seen=row["last_seen"],
        roles=tuple(
            Grant(
                grant_id=UUID(g["grant_id"]), role=g["role"], scope_kind=g["scope_kind"],
                scope_id=g["scope_id"], scope_name=g["scope_name"],
            )
            for g in row["roles"]
        ),
    )


def find_users(q: str = "", role: str = "", page: int = 1) -> UserPage:
    """People by name (partial), whole phone number or KAFRIADA ID (partial), optionally by role."""
    q = " ".join(q.split())
    page = max(page, 1)
    phone: str | None = None
    if q:
        try:
            phone = phone_mod.normalise(q)
        except phone_mod.InvalidPhoneNumberError:
            phone = None
    kuid_fragment = kuid_mod.normalise(q) if q and any(c.isdigit() for c in q) else None

    with transaction() as session:
        rows = session.execute(
            text(
                _USER_SQL  # noqa: S608 - constant fragments only, no caller input
                + """
                 WHERE u.anonymised_at IS NULL
                   AND (CAST(:q AS text) IS NULL
                        OR u.full_name ILIKE :name ESCAPE '\\'
                        OR (CAST(:phone AS text) IS NOT NULL AND u.phone_e164 = :phone)
                        OR (CAST(:kuid AS text) IS NOT NULL AND a.kuid LIKE :kuid_like ESCAPE '\\'))
                   AND (CAST(:role AS text) IS NULL OR EXISTS (
                            SELECT 1 FROM ops.user_roles r
                             WHERE r.user_id = u.id AND r.role_code = :role AND r.revoked_at IS NULL))
                 ORDER BY u.full_name, u.id
                 LIMIT :n OFFSET :off
                """
            ),
            {
                "q": q or None, "name": _like(q), "phone": phone,
                "kuid": kuid_fragment, "kuid_like": _like(kuid_fragment) if kuid_fragment else None,
                "role": role or None, "n": PAGE + 1, "off": (page - 1) * PAGE,
            },
        ).mappings().all()
    return UserPage(users=tuple(_user(r) for r in rows[:PAGE]), page=page, has_more=len(rows) > PAGE)


def get_user(user_id: UUID) -> UserRow | None:
    with transaction() as session:
        row = session.execute(
            text(_USER_SQL + " WHERE u.id = :id AND u.anonymised_at IS NULL"),
            {"id": user_id},
        ).mappings().one_or_none()
    return None if row is None else _user(row)


@dataclass(frozen=True, slots=True)
class RoleKind:
    code: str
    description: str
    scope_kind: str


def role_kinds() -> list[RoleKind]:
    with transaction() as session:
        rows = session.execute(
            text("SELECT code, description, scope_kind FROM ops.roles ORDER BY scope_kind, code")
        ).mappings().all()
    return [RoleKind(r["code"], r["description"], r["scope_kind"]) for r in rows]


# ---------------------------------------------------------------------------
# Clubs, for approval
# ---------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class ClubRow:
    club_id: UUID
    name: str
    sport: str
    lga_name: str
    status: str
    verified: bool
    representative: str
    verification: str | None
    created_at: datetime


@dataclass(frozen=True, slots=True)
class ClubPage:
    clubs: tuple[ClubRow, ...]
    page: int
    has_more: bool


def list_clubs(status: str = "", page: int = 1) -> ClubPage:
    page = max(page, 1)
    with transaction() as session:
        rows = session.execute(
            text(
                """
                SELECT o.id, o.name, o.sport, o.status, o.stage, o.created_at,
                       lga.name AS lga_name, u.full_name AS rep,
                       (SELECT v.status FROM identity.club_verification_requests v
                         WHERE v.org_id = o.id AND v.status <> 'revoked') AS verification
                  FROM identity.organizations o
                  JOIN ops.locations lga ON lga.id = o.lga_id
                  JOIN ops.users u ON u.id = o.rep_user_id
                 WHERE o.status <> 'unconfirmed'
                   AND (CAST(:status AS text) IS NULL OR o.status = :status)
                 ORDER BY (o.status = 'pending_review') DESC, o.created_at DESC
                 LIMIT :n OFFSET :off
                """
            ),
            {"status": status or None, "n": PAGE + 1, "off": (page - 1) * PAGE},
        ).mappings().all()
    return ClubPage(
        clubs=tuple(
            ClubRow(
                club_id=r["id"], name=r["name"], sport=r["sport"], lga_name=r["lga_name"],
                status=r["status"], verified=r["stage"] == 2, representative=r["rep"],
                verification=r["verification"], created_at=r["created_at"],
            )
            for r in rows[:PAGE]
        ),
        page=page,
        has_more=len(rows) > PAGE,
    )


# ---------------------------------------------------------------------------
# ADM-06
# ---------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class AuditRow:
    entry_id: int
    occurred_at: datetime
    actor: str
    actor_role: str | None
    action: str
    subject_type: str
    subject_id: str
    reference: str | None


@dataclass(frozen=True, slots=True)
class AuditPage:
    entries: tuple[AuditRow, ...]
    page: int
    has_more: bool


def audit_entries(
    actor: str = "", action: str = "", since: date | None = None, until: date | None = None, page: int = 1
) -> AuditPage:
    """Newest first. There is no way to change or remove an entry — this only ever reads."""
    page = max(page, 1)
    actor, action = actor.strip(), action.strip()
    with transaction() as session:
        rows = session.execute(
            text(
                """
                SELECT id, occurred_at, actor_label, actor_role, action, subject_type, subject_id, request_id
                  FROM ops.audit_log
                 WHERE (CAST(:actor AS text) IS NULL OR actor_label ILIKE :actor_like ESCAPE '\\')
                   AND (CAST(:action AS text) IS NULL OR action ILIKE :action_like ESCAPE '\\')
                   AND (CAST(:since AS date) IS NULL
                        OR (occurred_at AT TIME ZONE 'Africa/Lagos')::date >= :since)
                   AND (CAST(:until AS date) IS NULL
                        OR (occurred_at AT TIME ZONE 'Africa/Lagos')::date <= :until)
                 ORDER BY id DESC
                 LIMIT :n OFFSET :off
                """
            ),
            {
                "actor": actor or None, "actor_like": _like(actor),
                "action": action or None, "action_like": _like(action),
                "since": since, "until": until,
                "n": AUDIT_PAGE + 1, "off": (page - 1) * AUDIT_PAGE,
            },
        ).mappings().all()
    return AuditPage(
        entries=tuple(
            AuditRow(
                entry_id=r["id"], occurred_at=r["occurred_at"], actor=r["actor_label"],
                actor_role=r["actor_role"], action=r["action"], subject_type=r["subject_type"],
                subject_id=r["subject_id"], reference=r["request_id"],
            )
            for r in rows[:AUDIT_PAGE]
        ),
        page=page,
        has_more=len(rows) > AUDIT_PAGE,
    )
