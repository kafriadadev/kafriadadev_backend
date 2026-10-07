"""Cash settlement (CRD-05): what a coordinator collected against what Paystack confirmed.

Every assisted payment is a record that cash changed hands: the coordinator ticks
"cash collected" before the checkout opens. A row that never reaches `success` is
money a coordinator holds that the ledger does not, and that difference is the point
of the report.

Rows are bounded by the athlete's LGA, the same way every coordinator query is. Within
it, `mine` narrows to the caller's own collections — the default for an LGA
coordinator settling their own cash; a state coordinator or administrator turns it off
to see everyone's.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from datetime import date, datetime
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import text

from kafriada.db.engine import transaction

_LAGOS = ZoneInfo("Africa/Lagos")
MAX_DAYS = 366
MAX_ROWS = 2000

# A payment the provider never opened was never paid with; the coordinator retries,
# and the retry is the row that counts.
_NOT_COLLECTED = ("failed",)


class RangeTooWideError(ValueError):
    """`until` before `since`, or more than a year apart."""


@dataclass(frozen=True, slots=True)
class Line:
    reference: str
    created_at: datetime
    athlete_name: str
    kuid: str
    coordinator_name: str
    amount_kobo: int
    status: str


@dataclass(frozen=True, slots=True)
class Settlement:
    lga_id: str
    lga_name: str
    since: date
    until: date
    mine: bool
    lines: tuple[Line, ...]
    truncated: bool
    collected_count: int
    collected_kobo: int
    confirmed_count: int
    confirmed_kobo: int
    pending_count: int
    review_count: int
    abandoned_count: int

    @property
    def difference_kobo(self) -> int:
        return self.collected_kobo - self.confirmed_kobo


def settlement(
    caller: UUID, lga_id: str, since: date, until: date, *, mine: bool = True
) -> Settlement | None:
    """Assisted payments for athletes in one LGA, started between two Nigerian dates."""
    if until < since or (until - since).days >= MAX_DAYS:
        raise RangeTooWideError
    with transaction() as session:
        lga = session.execute(
            text("SELECT name FROM ops.locations WHERE id = :id AND kind = 'lga'"), {"id": lga_id}
        ).scalar_one_or_none()
        if lga is None:
            return None
        rows = session.execute(
            text(
                """
                SELECT p.reference, p.created_at, p.expected_kobo, p.status,
                       au.full_name AS athlete_name, a.kuid,
                       cu.full_name AS coordinator_name
                  FROM money.payments p
                  JOIN identity.athletes a ON a.id = p.on_behalf_of
                  JOIN ops.users au ON au.id = a.user_id
                  JOIN ops.users cu ON cu.id = p.coordinator_id
                 WHERE p.coordinator_id IS NOT NULL
                   AND a.current_lga_id = :lga
                   AND (NOT :mine OR p.coordinator_id = :me)
                   AND (p.created_at AT TIME ZONE 'Africa/Lagos')::date BETWEEN :since AND :until
                 ORDER BY p.created_at DESC, p.reference
                 LIMIT :n
                """
            ),
            {"lga": lga_id, "mine": mine, "me": caller, "since": since, "until": until, "n": MAX_ROWS + 1},
        ).mappings().all()

    lines = tuple(
        Line(
            reference=r["reference"], created_at=r["created_at"],
            athlete_name=r["athlete_name"], kuid=r["kuid"],
            coordinator_name=r["coordinator_name"],
            amount_kobo=int(r["expected_kobo"]), status=r["status"],
        )
        for r in rows[:MAX_ROWS]
    )
    collected = [x for x in lines if x.status not in _NOT_COLLECTED]
    confirmed = [x for x in lines if x.status == "success"]
    return Settlement(
        lga_id=lga_id,
        lga_name=lga,
        since=since,
        until=until,
        mine=mine,
        lines=lines,
        truncated=len(rows) > MAX_ROWS,
        collected_count=len(collected),
        collected_kobo=sum(x.amount_kobo for x in collected),
        confirmed_count=len(confirmed),
        confirmed_kobo=sum(x.amount_kobo for x in confirmed),
        pending_count=sum(1 for x in lines if x.status == "pending"),
        review_count=sum(1 for x in lines if x.status == "frozen"),
        abandoned_count=sum(1 for x in lines if x.status == "abandoned"),
    )


def as_csv(report: Settlement) -> str:
    """The same lines, for a spreadsheet. Amounts in naira with kobo, times in Lagos."""
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["date", "reference", "athlete", "kafriada_net_id", "collected_by", "amount_naira", "status"])
    for x in report.lines:
        writer.writerow([
            x.created_at.astimezone(_LAGOS).strftime("%Y-%m-%d %H:%M"),
            x.reference,
            _safe(x.athlete_name),
            x.kuid,
            _safe(x.coordinator_name),
            f"{x.amount_kobo // 100}.{x.amount_kobo % 100:02d}",
            x.status,
        ])
    return out.getvalue()


def _safe(cell: str) -> str:
    """Stop a spreadsheet from reading a name as a formula."""
    return "'" + cell if cell[:1] in ("=", "+", "-", "@", "\t", "\r") else cell

