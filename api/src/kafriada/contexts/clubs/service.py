"""Clubs: registering one, and reading its dashboard.

A club is an ``identity.organizations`` row with one default team, and its founder
holds a ``club_admin`` grant scoped to that row's id. Everything a club administrator
can see is bounded by that id — every query below takes the club id and filters on
it, and none takes a bare athlete or team id from the caller. The route's scope check
proves the caller holds a grant on the club named in the path; this module is what
makes sure nothing it returns belongs to another.

A new club starts ``pending_review``: it exists and can be viewed, but it cannot build
a roster until it is approved.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

import structlog
from sqlalchemy import text

from kafriada.clock import today_in_nigeria
from kafriada.contexts.access import phone as phone_mod
from kafriada.contexts.audit.service import Actor, record
from kafriada.db.engine import transaction

log = structlog.get_logger(__name__)

SPORTS = (
    "Football", "Athletics", "Basketball", "Volleyball", "Handball",
    "Boxing", "Wrestling", "Table Tennis", "Badminton", "Swimming",
)
ROSTER_LIMIT = 200


class Refused(Exception):
    """The action cannot be taken, and the person can be told why."""

    def __init__(self, message: str, *, code: str, field: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.field = field


@dataclass(frozen=True, slots=True)
class Registered:
    club_id: UUID
    name: str


@dataclass(frozen=True, slots=True)
class RosterRow:
    full_name: str
    kuid: str
    position: str | None
    state: str  # verified | unverified | invited


@dataclass(frozen=True, slots=True)
class Dashboard:
    club_id: UUID
    name: str
    sport: str
    type: str
    year_founded: int | None
    lga_name: str
    contact_phone: str
    status: str  # pending_review | approved | suspended
    verified: bool  # stage 2: the paid badge
    players: int
    verified_players: int
    invites_out: int
    roster: tuple[RosterRow, ...]
    created_at: datetime


def register_club(
    user_id: UUID,
    actor_name: str,
    *,
    name: str,
    sport: str,
    lga_id: str,
    contact_phone: str,
    year_founded: int | None = None,
    confirm_duplicate: bool = False,
    request_id: str | None = None,
    ip_address: str | None = None,
) -> Registered:
    name = " ".join(name.split())
    if len(name) < 3:
        raise Refused("Enter the club's name.", code="invalid", field="name")
    if len(name) > 80:
        raise Refused("The name can be at most 80 characters.", code="invalid", field="name")
    if sport not in SPORTS:
        raise Refused("Choose the club's sport.", code="invalid", field="sport")
    if year_founded is not None and not 1900 <= year_founded <= today_in_nigeria().year:
        raise Refused("Enter a valid year.", code="invalid", field="year_founded")
    try:
        phone = phone_mod.normalise(contact_phone)
    except phone_mod.InvalidPhoneNumberError as exc:
        raise Refused(str(exc), code="invalid", field="contact_phone") from exc

    with transaction() as session:
        lga = session.execute(
            text(
                "SELECT parent_id FROM ops.locations "
                "WHERE id = :id AND kind = 'lga' AND is_live"
            ),
            {"id": lga_id},
        ).mappings().one_or_none()
        if lga is None:
            raise Refused("Choose a local government area that is open.", code="invalid", field="lga_id")

        # Two clubs can honestly share a name, so this is a question, not a refusal.
        if not confirm_duplicate:
            twin = session.execute(
                text(
                    "SELECT 1 FROM identity.organizations "
                    "WHERE lga_id = :lga AND lower(name) = lower(:name) LIMIT 1"
                ),
                {"lga": lga_id, "name": name},
            ).first()
            if twin is not None:
                raise Refused(
                    "A club with this name is already registered in this local government area.",
                    code="duplicate",
                    field="name",
                )

        club_id: UUID = session.execute(
            text(
                """
                INSERT INTO identity.organizations
                    (name, sport, year_founded, state_id, lga_id, contact_phone, rep_user_id)
                VALUES (:name, :sport, :year, :state, :lga, :phone, :user)
                RETURNING id
                """
            ),
            {
                "name": name, "sport": sport, "year": year_founded,
                "state": lga["parent_id"], "lga": lga_id, "phone": phone, "user": user_id,
            },
        ).scalar_one()
        session.execute(
            text("INSERT INTO identity.teams (org_id, name, sport) VALUES (:org, :name, :sport)"),
            {"org": club_id, "name": name, "sport": sport},
        )
        session.execute(
            text(
                """
                INSERT INTO ops.user_roles (user_id, role_code, scope_kind, scope_id, granted_by, reason)
                VALUES (:user, 'club_admin', 'club', :club, :user, 'club registration')
                """
            ),
            {"user": user_id, "club": str(club_id)},
        )
        record(
            session,
            actor=Actor(user_id=user_id, label=actor_name),
            action="club.registered",
            subject_type="club",
            subject_id=str(club_id),
            metadata={"lga": lga_id, "sport": sport},
            request_id=request_id,
            ip_address=ip_address,
        )
    log.info("club_registered", club_id=str(club_id), lga=lga_id)
    return Registered(club_id=club_id, name=name)


def dashboard(club_id: UUID) -> Dashboard | None:
    """One club's numbers and roster. Every query is bounded by ``club_id``."""
    with transaction() as session:
        club = session.execute(
            text(
                """
                SELECT o.id, o.name, o.sport, o.type, o.year_founded, o.contact_phone,
                       o.status, o.stage, o.created_at, lga.name AS lga_name
                  FROM identity.organizations o
                  JOIN ops.locations lga ON lga.id = o.lga_id
                 WHERE o.id = :club
                """
            ),
            {"club": club_id},
        ).mappings().one_or_none()
        if club is None:
            return None
        rows = session.execute(
            text(
                """
                SELECT u.full_name, a.kuid, a.playing_position, rm.status,
                       EXISTS (
                           SELECT 1 FROM identity.verification_requests v
                            WHERE v.athlete_id = a.id AND v.status = 'approved'
                       ) AS is_verified
                  FROM identity.roster_members rm
                  JOIN identity.teams t ON t.id = rm.team_id
                  JOIN identity.athletes a ON a.id = rm.athlete_id
                  JOIN ops.users u ON u.id = a.user_id
                 WHERE t.org_id = :club AND rm.status IN ('active', 'invited')
                 ORDER BY rm.status, u.full_name
                 LIMIT :n
                """
            ),
            {"club": club_id, "n": ROSTER_LIMIT},
        ).mappings().all()

    roster = tuple(
        RosterRow(
            full_name=r["full_name"],
            kuid=r["kuid"],
            position=r["playing_position"],
            state="invited" if r["status"] == "invited" else ("verified" if r["is_verified"] else "unverified"),
        )
        for r in rows
    )
    return Dashboard(
        club_id=club["id"],
        name=club["name"],
        sport=club["sport"],
        type=club["type"],
        year_founded=club["year_founded"],
        lga_name=club["lga_name"],
        contact_phone=club["contact_phone"],
        status=club["status"],
        verified=club["stage"] == 2,
        players=sum(1 for r in roster if r.state != "invited"),
        verified_players=sum(1 for r in roster if r.state == "verified"),
        invites_out=sum(1 for r in roster if r.state == "invited"),
        roster=roster,
        created_at=club["created_at"],
    )
