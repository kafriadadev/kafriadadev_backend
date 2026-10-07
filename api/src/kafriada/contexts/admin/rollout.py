"""LGA rollout (ADM-05): which LGAs accept registrations.

Opening or closing an LGA is one UPDATE of `ops.locations.is_live`; registration checks
it in the service (`identity.register`), so closing really stops sign-ups. Either way
needs a reason and the administrator's password, and leaves an audit row. Closing never
touches anyone already registered: their IDs, cards and profiles stay exactly as they are.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import text

from kafriada.contexts.access import service as access
from kafriada.contexts.access.service import Principal
from kafriada.contexts.audit.service import Actor, record
from kafriada.db.engine import transaction

MAX_REASON_CHARS = 1_000


class Refused(Exception):
    def __init__(self, message: str, *, code: str) -> None:
        super().__init__(message)
        self.message = message
        self.code = code


class NotFound(Exception):
    pass


@dataclass(frozen=True, slots=True)
class Lga:
    id: str
    code: str
    name: str
    wave: int | None
    is_open: bool
    went_live_at: datetime | None
    registered: int


def list_lgas(state_id: str = "NG-JG") -> tuple[Lga, ...]:
    """Every LGA in the state, by wave then name, with how many athletes it holds."""
    with transaction() as session:
        rows = session.execute(
            text(
                """
                SELECT l.id, l.code, l.name, l.rollout_wave, l.is_live, l.went_live_at,
                       (SELECT count(*) FROM identity.athletes a WHERE a.current_lga_id = l.id) AS registered
                  FROM ops.locations l
                 WHERE l.kind = 'lga' AND l.parent_id = :state
                 ORDER BY l.rollout_wave NULLS LAST, l.name
                """
            ),
            {"state": state_id},
        ).mappings().all()
    return tuple(
        Lga(
            id=r["id"], code=r["code"], name=r["name"], wave=r["rollout_wave"],
            is_open=r["is_live"], went_live_at=r["went_live_at"], registered=int(r["registered"]),
        )
        for r in rows
    )


def set_open(
    actor: Principal,
    lga_id: str,
    *,
    open_: bool,
    reason: str,
    current_password: str,
    request_id: str | None = None,
    ip_address: str | None = None,
) -> Lga:
    """Open or close one LGA for registration. Asking for the state it is already in is refused."""
    reason = reason.strip()
    if not reason:
        raise Refused("Say why. The reason is kept permanently.", code="reason")
    if len(reason) > MAX_REASON_CHARS:
        raise Refused(f"Keep the reason under {MAX_REASON_CHARS} characters.", code="reason")
    try:
        access.reauthenticate(actor, current_password, request_id=request_id, ip_address=ip_address)
    except access.AccessError as exc:
        raise Refused(exc.message, code="password") from exc

    with transaction() as session:
        row = session.execute(
            text("SELECT id, name, is_live, parent_id FROM ops.locations WHERE id = :id AND kind = 'lga' FOR UPDATE"),
            {"id": lga_id},
        ).one_or_none()
        if row is None:
            raise NotFound
        if row.is_live == open_:
            raise Refused(
                f"{row.name} is already {'open' if open_ else 'closed'}.", code="unchanged"
            )
        # went_live_at keeps the first opening: when the LGA joined, not the latest toggle.
        session.execute(
            text(
                "UPDATE ops.locations SET is_live = :open, "
                "went_live_at = CASE WHEN :open THEN coalesce(went_live_at, now()) ELSE went_live_at END "
                "WHERE id = :id"
            ),
            {"open": open_, "id": lga_id},
        )
        record(
            session,
            actor=Actor(user_id=actor.user_id, label=actor.full_name, role="super_admin"),
            action="rollout.lga_opened" if open_ else "rollout.lga_closed",
            subject_type="location",
            subject_id=lga_id,
            metadata={"reason": reason},
            request_id=request_id,
            ip_address=ip_address,
        )
    return next(x for x in list_lgas(row.parent_id) if x.id == lga_id)
