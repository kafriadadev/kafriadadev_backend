"""The coordinator's day (CRD-01) and finding an athlete (CRD-03).

Both are bounded by one LGA, and the LGA is a query condition here, not something a
caller may widen: an athlete outside it is not "not permitted", they are simply not in
the result. The distinction matters — a refusal would tell a coordinator who exists
elsewhere.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import text

from kafriada.clock import today_in_nigeria
from kafriada.contexts.access import phone as phone_mod
from kafriada.contexts.access import service as access
from kafriada.contexts.access.service import Principal
from kafriada.contexts.identity import kuid as kuid_mod
from kafriada.contexts.verification import service as verification
from kafriada.db.engine import transaction
from kafriada.settings import get_settings

PAGE_SIZE = 20
MIN_QUERY = 2


@dataclass(frozen=True, slots=True)
class Dashboard:
    lga_id: str
    lga_name: str
    registered: int
    paid: int
    to_review: int
    oldest_waiting_hours: int | None
    clubs: int
    # Assisted (cash) payments this person started today. Only meaningful for someone
    # who can start them; `can_assist` says whether that is this caller.
    can_assist: bool
    collected_kobo: int
    collected_count: int
    limit_kobo: int
    limit_count: int
    cap_reached: bool


def dashboard(principal: Principal, lga_id: str) -> Dashboard | None:
    """The LGA's numbers, and this coordinator's own running cash total."""
    with transaction() as session:
        lga = session.execute(
            text("SELECT name FROM ops.locations WHERE id = :id AND kind = 'lga'"), {"id": lga_id}
        ).scalar_one_or_none()
        if lga is None:
            return None
        counts = session.execute(
            text(
                """
                SELECT
                  (SELECT count(*) FROM identity.athletes a
                     JOIN ops.users u ON u.id = a.user_id
                    WHERE a.current_lga_id = :lga AND u.anonymised_at IS NULL) AS registered,
                  (SELECT count(*) FROM identity.verification_requests v
                     JOIN identity.athletes a ON a.id = v.athlete_id
                    WHERE a.current_lga_id = :lga AND v.payment_id IS NOT NULL) AS paid,
                  (SELECT count(*) FROM identity.organizations o WHERE o.lga_id = :lga) AS clubs
                """
            ),
            {"lga": lga_id},
        ).mappings().one()
        today = today_in_nigeria()
        cash = session.execute(
            text(
                """
                SELECT
                  count(*) FILTER (WHERE status = 'success') AS collected_count,
                  coalesce(sum(expected_kobo) FILTER (WHERE status = 'success'), 0) AS collected_kobo,
                  count(*) FILTER (WHERE status <> 'failed') AS started_count,
                  coalesce(sum(expected_kobo) FILTER (WHERE status <> 'failed'), 0) AS started_kobo
                  FROM money.payments
                 WHERE coordinator_id = :me
                   AND (created_at AT TIME ZONE 'Africa/Lagos')::date = :today
                """
            ),
            {"me": principal.user_id, "today": today},
        ).mappings().one()

    waiting = verification.queue(principal, lga_id)
    oldest = None
    if waiting:
        oldest = max(0, int((datetime.now(UTC) - waiting[0].submitted_at).total_seconds() // 3600))

    settings = get_settings()
    limit_count = settings.assisted_payments_per_coordinator_daily
    limit_kobo = settings.assisted_kobo_per_coordinator_daily
    return Dashboard(
        lga_id=lga_id,
        lga_name=lga,
        registered=int(counts["registered"]),
        paid=int(counts["paid"]),
        to_review=len(waiting),
        oldest_waiting_hours=oldest,
        clubs=int(counts["clubs"]),
        can_assist=access.can(
            principal.user_id, "payment.initiate_behalf", access.Scope(kind="lga", id=lga_id)
        ),
        collected_kobo=int(cash["collected_kobo"]),
        collected_count=int(cash["collected_count"]),
        limit_kobo=limit_kobo,
        limit_count=limit_count,
        cap_reached=int(cash["started_count"]) >= limit_count or int(cash["started_kobo"]) >= limit_kobo,
    )


@dataclass(frozen=True, slots=True)
class Found:
    kuid: str
    full_name: str
    playing_position: str | None
    verified: bool


@dataclass(frozen=True, slots=True)
class Results:
    people: tuple[Found, ...]
    page: int
    has_more: bool


def _like(fragment: str) -> str:
    """A LIKE pattern that matches the text literally, whatever the person typed."""
    escaped = fragment.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def find_athletes(lga_id: str, query: str, page: int = 1) -> Results:
    """People in one LGA by name (partial), KAFRIADA ID (partial) or phone (whole number).

    Anyone in another LGA is not found — the same answer as someone who does not exist.
    """
    query = " ".join(query.split())
    page = max(page, 1)
    if len(query) < MIN_QUERY:
        return Results(people=(), page=page, has_more=False)

    by_phone: str | None
    try:
        by_phone = phone_mod.normalise(query)
    except phone_mod.InvalidPhoneNumberError:
        by_phone = None
    kuid_fragment = kuid_mod.normalise(query) if any(c.isdigit() for c in query) else None

    with transaction() as session:
        rows = session.execute(
            text(
                """
                SELECT a.kuid, u.full_name, a.playing_position,
                       EXISTS (SELECT 1 FROM identity.verification_requests v
                                WHERE v.athlete_id = a.id AND v.status = 'approved') AS is_verified
                  FROM identity.athletes a
                  JOIN ops.users u ON u.id = a.user_id
                 WHERE a.current_lga_id = :lga AND u.anonymised_at IS NULL
                   AND (   u.full_name ILIKE :name ESCAPE '\\'
                        OR (CAST(:kuid AS text) IS NOT NULL AND a.kuid LIKE :kuid_like ESCAPE '\\')
                        OR (CAST(:phone AS text) IS NOT NULL AND u.phone_e164 = :phone))
                 ORDER BY u.full_name, a.kuid
                 LIMIT :n OFFSET :off
                """
            ),
            {
                "lga": lga_id,
                "name": _like(query),
                "kuid": kuid_fragment,
                "kuid_like": _like(kuid_fragment) if kuid_fragment else None,
                "phone": by_phone,
                "n": PAGE_SIZE + 1,
                "off": (page - 1) * PAGE_SIZE,
            },
        ).mappings().all()
    return Results(
        people=tuple(
            Found(
                kuid=r["kuid"], full_name=r["full_name"],
                playing_position=r["playing_position"], verified=r["is_verified"],
            )
            for r in rows[:PAGE_SIZE]
        ),
        page=page,
        has_more=len(rows) > PAGE_SIZE,
    )
