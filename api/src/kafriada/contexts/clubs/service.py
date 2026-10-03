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
from sqlalchemy.orm import Session

from kafriada.clock import today_in_nigeria
from kafriada.contexts.access import phone as phone_mod
from kafriada.contexts.audit.service import Actor, record
from kafriada.contexts.clubs import profile as club_profile
from kafriada.contexts.clubs.profile import ClubProfile
from kafriada.contexts.identity import kuid as kuid_mod
from kafriada.contexts.identity.profile import SPORTS
from kafriada.db.engine import transaction
from kafriada.outbox.service import queue_notification

log = structlog.get_logger(__name__)

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
    roster_id: UUID
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
    profile: dict[str, object] | None = None  # the club's full record; None before 0015


def register_club(
    user_id: UUID,
    actor_name: str,
    *,
    name: str,
    sport: str,
    lga_id: str,
    contact_phone: str,
    profile: ClubProfile,
    confirm_duplicate: bool = False,
    request_id: str | None = None,
    ip_address: str | None = None,
) -> Registered:
    """A coordinator or administrator registers a club; they become its administrator."""
    checked = check_club(name=name, sport=sport, contact_phone=contact_phone, profile=profile)
    with transaction() as session:
        club_id = create_club(
            session, user_id, actor_name, checked, lga_id=lga_id,
            confirm_duplicate=confirm_duplicate, status="pending_review",
            request_id=request_id, ip_address=ip_address,
        )
    log.info("club_registered", club_id=str(club_id), lga=lga_id)
    return Registered(club_id=club_id, name=str(checked["name"]))


def check_club(
    *, name: str, sport: str, contact_phone: str, profile: ClubProfile,
) -> dict[str, object]:
    """Every rule a club's record must meet, before any database work."""
    name = " ".join(name.split())
    if len(name) < 3:
        raise Refused("Enter the club's registered name.", code="invalid", field="name")
    if len(name) > 80:
        raise Refused("The name can be at most 80 characters.", code="invalid", field="name")
    if sport not in SPORTS:
        raise Refused("Choose the club's sport.", code="invalid", field="sport")
    try:
        phone = phone_mod.normalise(contact_phone)
    except phone_mod.InvalidPhoneNumberError as exc:
        raise Refused(str(exc), code="invalid", field="contact_phone") from exc
    try:
        values = club_profile.clean(profile)
    except club_profile.ProfileError as exc:
        raise Refused(exc.message, code="invalid", field=exc.field) from None
    return {"name": name, "sport": sport, "contact_phone": phone, **values}


def create_club(
    session: Session,
    user_id: UUID,
    actor_name: str,
    checked: dict[str, object],
    *,
    lga_id: str,
    confirm_duplicate: bool,
    status: str,
    request_id: str | None,
    ip_address: str | None,
) -> UUID:
    """Insert the club, its default team and its administrator's grant, in the caller's
    transaction. ``checked`` comes from :func:`check_club`."""
    lga = session.execute(
        text("SELECT parent_id FROM ops.locations WHERE id = :id AND kind = 'lga' AND is_live"),
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
            {"lga": lga_id, "name": checked["name"]},
        ).first()
        if twin is not None:
            raise Refused(
                "A club with this name is already registered in this local government area.",
                code="duplicate",
                field="name",
            )

    columns = ("name", "sport", "contact_phone", *club_profile.COLUMNS)
    club_id: UUID = session.execute(
        text(
            f"""
            INSERT INTO identity.organizations
                ({", ".join(columns)}, state_id, lga_id, rep_user_id, rep_role, status)
            VALUES ({", ".join(":" + c for c in columns)}, :state, :lga, :user, :rep_role, :status)
            RETURNING id
            """  # noqa: S608 - column names are this module's own constants
        ),
        {
            **{c: checked[c] for c in columns},
            "state": lga["parent_id"], "lga": lga_id, "user": user_id,
            "rep_role": checked.get("rep_role"), "status": status,
        },
    ).scalar_one()
    session.execute(
        text("INSERT INTO identity.teams (org_id, name, sport) VALUES (:org, :name, :sport)"),
        {"org": club_id, "name": checked["name"], "sport": checked["sport"]},
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
        metadata={"lga": lga_id, "sport": checked["sport"], "status": status},
        request_id=request_id,
        ip_address=ip_address,
    )
    return club_id


def dashboard(club_id: UUID) -> Dashboard | None:
    """One club's numbers and roster. Every query is bounded by ``club_id``."""
    with transaction() as session:
        club = session.execute(
            text(
                """
                SELECT o.id, o.name, o.sport, o.type, o.year_founded, o.contact_phone,
                       o.status, o.stage, o.created_at, lga.name AS lga_name,
                       o.short_name, o.category, o.age_groups, o.level, o.ground_name,
                       o.ground_address, o.town, o.club_email, o.cac_number, o.affiliation,
                       o.colours, o.website, o.rep_role, o.official2_name, o.official2_role,
                       o.official2_phone
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
                SELECT rm.id AS roster_id, u.full_name, a.kuid, a.playing_position, rm.status,
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
            roster_id=r["roster_id"],
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
        profile={c: club[c] for c in (*club_profile.COLUMNS, "rep_role")},
    )


# ---------------------------------------------------------------------------
# Approval
# ---------------------------------------------------------------------------
def set_status(
    club_id: UUID,
    actor_id: UUID,
    actor_name: str,
    status: str,
    *,
    request_id: str | None = None,
    ip_address: str | None = None,
) -> None:
    """Approve or suspend a club. The caller has already been checked for the permission."""
    if status not in ("approved", "suspended"):
        raise Refused("Unknown status.", code="invalid")
    with transaction() as session:
        changed = session.execute(
            text(
                "UPDATE identity.organizations SET status = :s "
                "WHERE id = :c AND status <> :s AND status <> 'unconfirmed' "
                "RETURNING rep_user_id"
            ),
            {"s": status, "c": club_id},
        ).mappings().one_or_none()
        if changed is None:
            current = session.execute(
                text("SELECT status FROM identity.organizations WHERE id = :c"), {"c": club_id}
            ).scalar_one_or_none()
            if current is None or current == "unconfirmed":
                # Not yet in the review queue: as far as an administrator is concerned,
                # the club does not exist until its representative confirms their email.
                raise Refused("No such club.", code="missing")
            return
        record(
            session,
            actor=Actor(user_id=actor_id, label=actor_name),
            action=f"club.{status}",
            subject_type="club",
            subject_id=str(club_id),
            request_id=request_id,
            ip_address=ip_address,
        )
        if status == "approved":
            queue_notification(
                session,
                user_id=changed["rep_user_id"],
                sms="KAFRIADA: your club is approved. You can now invite players.",
                subject="Your club is approved",
                email="Your club is approved on KAFRIADA. You can now invite players.",
                purpose="club_approved",
            )


# ---------------------------------------------------------------------------
# CLB-03: inviting a player
# ---------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class PlayerMatch:
    full_name: str
    kuid: str
    position: str | None
    lga_name: str
    verified: bool
    current_club: str | None
    state: str  # found | on_roster | invited


def find_player(club_id: UUID, query: str) -> PlayerMatch | None:
    """An exact match on a KAFRIADA ID or a phone number, never a search.

    Browsing would turn the register into a directory anyone could harvest by
    registering a club, so a match needs the full identifier. The result carries no
    phone number, date of birth or document.
    """
    query = query.strip()
    if not query:
        return None
    try:
        kuid = kuid_mod.normalise(query)
        kuid_mod.Kuid.parse(kuid)
        by_kuid, by_phone = kuid, None
    except Exception:
        try:
            by_kuid, by_phone = None, phone_mod.normalise(query)
        except phone_mod.InvalidPhoneNumberError:
            return None

    with transaction() as session:
        row = session.execute(
            text(
                """
                SELECT a.id, a.kuid, a.playing_position, u.full_name, lga.name AS lga_name,
                       EXISTS (SELECT 1 FROM identity.verification_requests v
                                WHERE v.athlete_id = a.id AND v.status = 'approved') AS is_verified,
                       (SELECT o.name FROM identity.roster_members rm
                          JOIN identity.teams t ON t.id = rm.team_id
                          JOIN identity.organizations o ON o.id = t.org_id
                         WHERE rm.athlete_id = a.id AND rm.status = 'active') AS current_club
                  FROM identity.athletes a
                  JOIN ops.users u ON u.id = a.user_id
                  JOIN ops.locations lga ON lga.id = a.current_lga_id
                 WHERE (a.kuid = :k OR u.phone_e164 = :p) AND u.anonymised_at IS NULL
                """
            ),
            {"k": by_kuid, "p": by_phone},
        ).mappings().one_or_none()
        if row is None:
            return None
        here = session.execute(
            text(
                """
                SELECT rm.status FROM identity.roster_members rm
                  JOIN identity.teams t ON t.id = rm.team_id
                 WHERE t.org_id = :club AND rm.athlete_id = :a AND rm.status IN ('active', 'invited')
                """
            ),
            {"club": club_id, "a": row["id"]},
        ).mappings().one_or_none()
    state = "found" if here is None else ("on_roster" if here["status"] == "active" else "invited")
    return PlayerMatch(
        full_name=row["full_name"], kuid=row["kuid"], position=row["playing_position"],
        lga_name=row["lga_name"], verified=row["is_verified"],
        current_club=row["current_club"], state=state,
    )


def invite_player(
    club_id: UUID,
    actor_id: UUID,
    actor_name: str,
    kuid: str,
    *,
    request_id: str | None = None,
    ip_address: str | None = None,
) -> None:
    kuid = kuid_mod.normalise(kuid)
    with transaction() as session:
        club = session.execute(
            text("SELECT name, status FROM identity.organizations WHERE id = :c FOR SHARE"),
            {"c": club_id},
        ).mappings().one_or_none()
        if club is None:
            raise Refused("No such club.", code="missing")
        if club["status"] != "approved":
            raise Refused("A club can invite players once it is approved.", code="not_approved")
        athlete = session.execute(
            text(
                "SELECT a.id, a.user_id FROM identity.athletes a JOIN ops.users u ON u.id = a.user_id "
                "WHERE a.kuid = :k AND u.anonymised_at IS NULL"
            ),
            {"k": kuid},
        ).mappings().one_or_none()
        if athlete is None:
            raise Refused("No athlete has that KAFRIADA ID.", code="no_athlete", field="kuid")
        team = session.execute(
            text("SELECT id FROM identity.teams WHERE org_id = :c ORDER BY created_at LIMIT 1"),
            {"c": club_id},
        ).scalar_one()
        already = session.execute(
            text(
                "SELECT 1 FROM identity.roster_members "
                "WHERE team_id = :t AND athlete_id = :a AND status IN ('invited', 'active')"
            ),
            {"t": team, "a": athlete["id"]},
        ).first()
        if already is not None:
            raise Refused(
                "This player is already on your roster or invited.", code="duplicate", field="kuid"
            )
        session.execute(
            text(
                "INSERT INTO identity.roster_members (team_id, athlete_id, invited_by) "
                "VALUES (:t, :a, :by)"
            ),
            {"t": team, "a": athlete["id"], "by": actor_id},
        )
        record(
            session,
            actor=Actor(user_id=actor_id, label=actor_name),
            action="club.player_invited",
            subject_type="club",
            subject_id=str(club_id),
            metadata={"kuid": kuid},
            request_id=request_id,
            ip_address=ip_address,
        )
        queue_notification(
            session,
            user_id=athlete["user_id"],
            sms=f"KAFRIADA: {club['name']} has invited you to join. Sign in to accept or decline.",
            subject=f"{club['name']} has invited you to join",
            email=f"{club['name']} has invited you to join their roster on KAFRIADA. Sign in to accept or decline.",
            purpose="club_invitation",
        )


def remove_player(
    club_id: UUID,
    roster_id: UUID,
    actor_id: UUID,
    actor_name: str,
    *,
    request_id: str | None = None,
    ip_address: str | None = None,
) -> None:
    """End a membership, or withdraw an invitation. Bounded to this club's own teams."""
    with transaction() as session:
        row = session.execute(
            text(
                """
                SELECT rm.athlete_id, rm.status, o.name AS club_name
                  FROM identity.roster_members rm
                  JOIN identity.teams t ON t.id = rm.team_id
                  JOIN identity.organizations o ON o.id = t.org_id
                 WHERE rm.id = :r AND o.id = :c AND rm.status IN ('active', 'invited')
                 FOR UPDATE OF rm
                """
            ),
            {"r": roster_id, "c": club_id},
        ).mappings().one_or_none()
        if row is None:
            raise Refused("That player is not on this club's roster.", code="missing")
        session.execute(
            text("UPDATE identity.roster_members SET status = 'released', decided_at = now() WHERE id = :r"),
            {"r": roster_id},
        )
        if row["status"] == "active":
            _career(session, row["athlete_id"], "left_club", club_id, row["club_name"])
        record(
            session,
            actor=Actor(user_id=actor_id, label=actor_name),
            action="club.player_removed",
            subject_type="club",
            subject_id=str(club_id),
            metadata={"roster_id": str(roster_id), "was": row["status"]},
            request_id=request_id,
            ip_address=ip_address,
        )


# ---------------------------------------------------------------------------
# ATH-05: an athlete's clubs and invitations
# ---------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class Membership:
    roster_id: UUID
    club_id: UUID
    club_name: str
    sport: str
    lga_name: str
    verified_club: bool


@dataclass(frozen=True, slots=True)
class MyClubs:
    current: Membership | None
    invitations: tuple[Membership, ...]


_MEMBERSHIP_SQL = """
    SELECT rm.id AS roster_id, o.id AS club_id, o.name AS club_name, o.sport,
           lga.name AS lga_name, o.stage = 2 AS verified_club
      FROM identity.roster_members rm
      JOIN identity.athletes a ON a.id = rm.athlete_id
      JOIN identity.teams t ON t.id = rm.team_id
      JOIN identity.organizations o ON o.id = t.org_id
      JOIN ops.locations lga ON lga.id = o.lga_id
     WHERE a.user_id = :u AND rm.status = :status AND o.status = 'approved'
     ORDER BY rm.invited_at DESC
"""


def my_clubs(user_id: UUID) -> MyClubs:
    with transaction() as session:
        def rows(status: str) -> list[Membership]:
            return [
                Membership(**{k: r[k] for k in Membership.__dataclass_fields__})
                for r in session.execute(text(_MEMBERSHIP_SQL), {"u": user_id, "status": status}).mappings()
            ]

        active, invited = rows("active"), rows("invited")
    return MyClubs(current=active[0] if active else None, invitations=tuple(invited))


def _own_invitation(session: Session, user_id: UUID, roster_id: UUID):  # type: ignore[no-untyped-def]
    """The invitation, only if it is this person's own and still waiting."""
    return session.execute(
        text(
            """
            SELECT rm.id, rm.athlete_id, o.id AS club_id, o.name AS club_name, o.rep_user_id,
                   o.status AS club_status, u.full_name
              FROM identity.roster_members rm
              JOIN identity.athletes a ON a.id = rm.athlete_id
              JOIN ops.users u ON u.id = a.user_id
              JOIN identity.teams t ON t.id = rm.team_id
              JOIN identity.organizations o ON o.id = t.org_id
             WHERE rm.id = :r AND a.user_id = :u AND rm.status = 'invited'
             FOR UPDATE OF rm
            """
        ),
        {"r": roster_id, "u": user_id},
    ).mappings().one_or_none()


def _career(session: Session, athlete_id: UUID, event: str, club_id: UUID, club_name: str) -> None:
    session.execute(
        text(
            "INSERT INTO identity.career_events (athlete_id, event_type, club_id, club_name, occurred_on) "
            "VALUES (:a, :e, :c, :n, :d)"
        ),
        {"a": athlete_id, "e": event, "c": club_id, "n": club_name, "d": today_in_nigeria()},
    )


def accept_invitation(
    user_id: UUID,
    roster_id: UUID,
    actor_name: str,
    *,
    request_id: str | None = None,
    ip_address: str | None = None,
) -> None:
    """Join the club. Any current membership ends in the same transaction."""
    with transaction() as session:
        inv = _own_invitation(session, user_id, roster_id)
        if inv is None:
            raise Refused("We could not find that invitation.", code="missing")
        if inv["club_status"] != "approved":
            raise Refused("This club is not accepting players right now.", code="not_approved")
        left = session.execute(
            text(
                """
                UPDATE identity.roster_members rm SET status = 'released', decided_at = now()
                  FROM identity.teams t, identity.organizations o
                 WHERE rm.athlete_id = :a AND rm.status = 'active'
                   AND t.id = rm.team_id AND o.id = t.org_id
                RETURNING o.id AS club_id, o.name AS club_name
                """
            ),
            {"a": inv["athlete_id"]},
        ).mappings().all()
        for old in left:
            _career(session, inv["athlete_id"], "left_club", old["club_id"], old["club_name"])
        session.execute(
            text("UPDATE identity.roster_members SET status = 'active', decided_at = now() WHERE id = :r"),
            {"r": roster_id},
        )
        _career(
            session, inv["athlete_id"], "transferred" if left else "joined_club",
            inv["club_id"], inv["club_name"],
        )
        record(
            session,
            actor=Actor(user_id=user_id, label=actor_name),
            action="club.invitation_accepted",
            subject_type="club",
            subject_id=str(inv["club_id"]),
            metadata={"roster_id": str(roster_id)},
            request_id=request_id,
            ip_address=ip_address,
        )
        queue_notification(
            session,
            user_id=inv["rep_user_id"],
            sms=f"KAFRIADA: {inv['full_name']} has joined {inv['club_name']}.",
            subject=f"{inv['full_name']} has joined {inv['club_name']}",
            email=f"{inv['full_name']} accepted your invitation and is now on the {inv['club_name']} roster.",
            purpose="club_invitation_accepted",
        )


def decline_invitation(
    user_id: UUID,
    roster_id: UUID,
    actor_name: str,
    *,
    request_id: str | None = None,
    ip_address: str | None = None,
) -> None:
    with transaction() as session:
        inv = _own_invitation(session, user_id, roster_id)
        if inv is None:
            raise Refused("We could not find that invitation.", code="missing")
        session.execute(
            text("UPDATE identity.roster_members SET status = 'released', decided_at = now() WHERE id = :r"),
            {"r": roster_id},
        )
        record(
            session,
            actor=Actor(user_id=user_id, label=actor_name),
            action="club.invitation_declined",
            subject_type="club",
            subject_id=str(inv["club_id"]),
            metadata={"roster_id": str(roster_id)},
            request_id=request_id,
            ip_address=ip_address,
        )


# ---------------------------------------------------------------------------
# Editing a club's details
# ---------------------------------------------------------------------------
def update_details(
    club_id: UUID,
    actor_id: UUID,
    actor_name: str,
    *,
    name: str,
    contact_phone: str,
    profile: ClubProfile,
    request_id: str | None = None,
    ip_address: str | None = None,
) -> None:
    """Change the club's record. Sport and area are not editable: a club that moved
    sport or area is a different club, and rosters and reviews are attached to what it
    was registered as."""
    with transaction() as session:
        sport = session.execute(
            text("SELECT sport FROM identity.organizations WHERE id = :c"), {"c": club_id}
        ).scalar_one_or_none()
    if sport is None:
        raise Refused("No such club.", code="missing")
    checked = check_club(name=name, sport=sport, contact_phone=contact_phone, profile=profile)
    name = str(checked["name"])
    phone = checked["contact_phone"]
    year_founded = checked["year_founded"]

    with transaction() as session:
        before = session.execute(
            text(
                "SELECT name, contact_phone, year_founded FROM identity.organizations "
                "WHERE id = :c FOR UPDATE"
            ),
            {"c": club_id},
        ).mappings().one_or_none()
        if before is None:
            raise Refused("No such club.", code="missing")
        editable = ("name", "contact_phone", *club_profile.COLUMNS)
        # Column names come from this module's own constants, never from the caller.
        assignments = ", ".join(f"{c} = :{c}" for c in editable)
        statement = f"UPDATE identity.organizations SET {assignments} WHERE id = :club_id"  # noqa: S608
        session.execute(
            text(statement),
            {**{c: checked[c] for c in editable}, "club_id": club_id},
        )
        if name != before["name"]:
            # The default team was named for the club when it was registered.
            session.execute(
                text("UPDATE identity.teams SET name = :n WHERE org_id = :c AND name = :old"),
                {"n": name, "c": club_id, "old": before["name"]},
            )
        changed = [
            field
            for field, old, new in (
                ("name", before["name"], name),
                ("contact_phone", before["contact_phone"], phone),
                ("year_founded", before["year_founded"], year_founded),
            )
            if old != new
        ]
        record(
            session,
            actor=Actor(user_id=actor_id, label=actor_name),
            action="club.details_updated",
            subject_type="club",
            subject_id=str(club_id),
            metadata={"changed": changed},
            request_id=request_id,
            ip_address=ip_address,
        )
