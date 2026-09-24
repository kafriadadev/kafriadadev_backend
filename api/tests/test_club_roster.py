"""Inviting players (CLB-03), answering invitations (ATH-05) and club approval.

What must hold: a club only ever touches its own roster, an athlete only ever answers
their own invitations, a player is active in one club at a time, and an unapproved or
suspended club cannot recruit.
"""

from __future__ import annotations

import os
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from kafriada.contexts.access import service as access
from kafriada.main import create_app
from tests._access_helpers import audit_actions, bearer, make_user, sql
from tests._media_helpers import LGA
from tests._payment_helpers import Athlete, new_athlete

pytestmark = [
    pytest.mark.db,
    pytest.mark.skipif(not os.environ.get("DATABASE_URL_APP"), reason="needs DATABASE_URL_APP"),
]


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(create_app())


@pytest.fixture(scope="module")
def root() -> dict[str, str]:
    uid, _ = make_user("Club approver", grants=[("super_admin", "global", None)])
    return bearer(access.issue_session(uid, method="test").token)


def new_club(client: TestClient, root: dict[str, str], *, approve: bool = True) -> tuple[Athlete, str]:
    admin = new_athlete("Club admin")
    made = client.post(
        "/v1/clubs",
        headers=admin.headers,
        json={
            "name": f"Roster FC {uuid4().hex[:8]}", "sport": "Football", "lga_id": LGA,
            "contact_phone": "08031234567",
        },
    )
    assert made.status_code == 201, made.text
    club = str(made.json()["club_id"])
    if approve:
        assert client.post(f"/v1/admin/clubs/{club}/approve", headers=root).status_code == 204
    return admin, club


def invite(client: TestClient, admin: Athlete, club: str, player: Athlete):  # type: ignore[no-untyped-def]
    return client.post(f"/v1/clubs/{club}/invitations", headers=admin.headers, json={"kuid": player.kuid})


def roster_id(club: str, player: Athlete) -> str:
    (row,) = sql(
        "SELECT rm.id::text AS id FROM identity.roster_members rm "
        "JOIN identity.teams t ON t.id = rm.team_id JOIN identity.athletes a ON a.id = rm.athlete_id "
        "WHERE t.org_id = :c AND a.user_id = :u AND rm.status IN ('invited', 'active')",
        c=club, u=player.user_id,
    )
    return str(row["id"])


def join(client: TestClient, admin: Athlete, club: str, player: Athlete) -> None:
    assert invite(client, admin, club, player).status_code == 204
    accepted = client.post(
        f"/v1/athletes/me/invitations/{roster_id(club, player)}/accept", headers=player.headers
    )
    assert accepted.status_code == 204, accepted.text


def status_of(club: str, player: Athlete) -> list[str]:
    return [
        str(r["status"])
        for r in sql(
            "SELECT rm.status FROM identity.roster_members rm JOIN identity.teams t ON t.id = rm.team_id "
            "JOIN identity.athletes a ON a.id = rm.athlete_id WHERE t.org_id = :c AND a.user_id = :u "
            "ORDER BY rm.created_at",
            c=club, u=player.user_id,
        )
    ]


def events(player: Athlete) -> list[str]:
    return [
        str(r["event_type"])
        for r in sql(
            "SELECT e.event_type FROM identity.career_events e JOIN identity.athletes a ON a.id = e.athlete_id "
            "WHERE a.user_id = :u AND e.event_type IN ('joined_club', 'left_club', 'transferred') ORDER BY e.id",
            u=player.user_id,
        )
    ]


# -- approval ---------------------------------------------------------------
def test_an_unapproved_club_cannot_invite_and_approval_needs_the_permission(
    client: TestClient, root: dict[str, str]
) -> None:
    admin, club = new_club(client, root, approve=False)
    player = new_athlete("Waiting")
    refused = invite(client, admin, club, player)
    assert refused.status_code == 409
    assert client.post(f"/v1/admin/clubs/{club}/approve", headers=admin.headers).status_code == 403
    assert client.post(f"/v1/admin/clubs/{club}/approve").status_code == 401
    assert client.post(f"/v1/admin/clubs/{uuid4()}/approve", headers=root).status_code == 404
    assert client.post(f"/v1/admin/clubs/{club}/approve", headers=root).status_code == 204
    assert invite(client, admin, club, player).status_code == 204
    assert "club.approved" in audit_actions(club)


def test_a_suspended_club_stops_recruiting_and_its_invitations_disappear(
    client: TestClient, root: dict[str, str]
) -> None:
    admin, club = new_club(client, root)
    player = new_athlete("Suspended")
    assert invite(client, admin, club, player).status_code == 204
    assert client.post(f"/v1/admin/clubs/{club}/suspend", headers=root).status_code == 204
    assert invite(client, admin, club, new_athlete("Later")).status_code == 409
    mine = client.get("/v1/athletes/me/clubs", headers=player.headers).json()
    assert mine["invitations"] == []
    accepted = client.post(
        f"/v1/athletes/me/invitations/{roster_id(club, player)}/accept", headers=player.headers
    )
    assert accepted.status_code == 409


# -- finding and inviting ---------------------------------------------------
def test_a_player_is_found_only_by_the_full_id_or_phone_and_no_private_field_comes_back(
    client: TestClient, root: dict[str, str]
) -> None:
    admin, club = new_club(client, root)
    player = new_athlete("Findable")
    (phone,) = [r["phone_e164"] for r in sql("SELECT phone_e164 FROM ops.users WHERE id = :u", u=player.user_id)]

    by_id = client.get(f"/v1/clubs/{club}/players/find", params={"q": player.kuid.lower()}, headers=admin.headers)
    by_phone = client.get(f"/v1/clubs/{club}/players/find", params={"q": str(phone)}, headers=admin.headers)
    assert by_id.status_code == by_phone.status_code == 200
    assert by_id.json() == by_phone.json()
    body = by_id.json()
    assert body["kuid"] == player.kuid and body["state"] == "found" and body["current_club"] is None
    assert str(phone) not in by_id.text and "date_of_birth" not in by_id.text

    for miss in (player.kuid[:-3], "Findable", "0803", "", "KA-NG-JG-BKD-2026-999999"):
        got = client.get(f"/v1/clubs/{club}/players/find", params={"q": miss}, headers=admin.headers)
        assert got.status_code == 404, miss


def test_the_lookup_says_where_a_player_already_is(client: TestClient, root: dict[str, str]) -> None:
    a, club_a = new_club(client, root)
    b, club_b = new_club(client, root)
    player = new_athlete("Placed")
    join(client, a, club_a, player)

    seen_by_b = client.get(f"/v1/clubs/{club_b}/players/find", params={"q": player.kuid}, headers=b.headers).json()
    assert seen_by_b["state"] == "found" and seen_by_b["current_club"]
    seen_by_a = client.get(f"/v1/clubs/{club_a}/players/find", params={"q": player.kuid}, headers=a.headers).json()
    assert seen_by_a["state"] == "on_roster"

    other = new_athlete("Asked")
    assert invite(client, a, club_a, other).status_code == 204
    asked = client.get(f"/v1/clubs/{club_a}/players/find", params={"q": other.kuid}, headers=a.headers).json()
    assert asked["state"] == "invited"


def test_inviting_queues_a_message_and_writes_an_audit_row(client: TestClient, root: dict[str, str]) -> None:
    admin, club = new_club(client, root)
    player = new_athlete("Told")
    assert invite(client, admin, club, player).status_code == 204
    queued = sql(
        "SELECT payload->>'purpose' AS purpose FROM ops.outbox "
        "WHERE event_type = 'notification.requested' AND payload->>'user_id' = :u",
        u=str(player.user_id),
    )
    assert "club_invitation" in [r["purpose"] for r in queued]
    assert "club.player_invited" in audit_actions(club)


def test_a_repeated_invitation_and_an_unknown_id_are_refused_on_the_field(
    client: TestClient, root: dict[str, str]
) -> None:
    admin, club = new_club(client, root)
    player = new_athlete("Twice")
    assert invite(client, admin, club, player).status_code == 204
    again = invite(client, admin, club, player)
    assert again.status_code == 409 and again.json()["error"]["message"]["field"] == "kuid"
    ghost = client.post(f"/v1/clubs/{club}/invitations", headers=admin.headers, json={"kuid": "KA-NG-JG-BKD-2026-999999"})
    assert ghost.status_code == 404 and ghost.json()["error"]["message"]["field"] == "kuid"


def test_a_club_cannot_act_on_another_clubs_roster(client: TestClient, root: dict[str, str]) -> None:
    a, club_a = new_club(client, root)
    b, club_b = new_club(client, root)
    theirs = new_athlete("Theirs")
    join(client, b, club_b, theirs)

    assert invite(client, a, club_b, new_athlete("Poach")).status_code == 403
    assert client.get(f"/v1/clubs/{club_b}/players/find", params={"q": theirs.kuid}, headers=a.headers).status_code == 403
    # Naming the other club's roster row through one's own club must find nothing.
    stolen = client.delete(f"/v1/clubs/{club_a}/roster/{roster_id(club_b, theirs)}", headers=a.headers)
    assert stolen.status_code == 404
    assert status_of(club_b, theirs) == ["active"]
    direct = client.delete(f"/v1/clubs/{club_b}/roster/{roster_id(club_b, theirs)}", headers=a.headers)
    assert direct.status_code == 403
    assert status_of(club_b, theirs) == ["active"]


# -- answering ---------------------------------------------------------------
def test_accepting_puts_the_player_on_the_roster_and_in_their_history(
    client: TestClient, root: dict[str, str]
) -> None:
    admin, club = new_club(client, root)
    player = new_athlete("Joins")
    assert invite(client, admin, club, player).status_code == 204
    waiting = client.get("/v1/athletes/me/clubs", headers=player.headers).json()
    assert waiting["current"] is None and [i["club_id"] for i in waiting["invitations"]] == [club]

    join_id = waiting["invitations"][0]["roster_id"]
    assert client.post(f"/v1/athletes/me/invitations/{join_id}/accept", headers=player.headers).status_code == 204
    now = client.get("/v1/athletes/me/clubs", headers=player.headers).json()
    assert now["current"]["club_id"] == club and now["invitations"] == []
    assert events(player) == ["joined_club"]
    seen = client.get(f"/v1/clubs/{club}", headers=admin.headers).json()
    assert [r["kuid"] for r in seen["roster"]] == [player.kuid] and seen["players"] == 1 and seen["invites_out"] == 0
    # A second answer to the same invitation finds nothing to answer.
    assert client.post(f"/v1/athletes/me/invitations/{join_id}/accept", headers=player.headers).status_code == 404


def test_accepting_a_second_club_moves_the_player(client: TestClient, root: dict[str, str]) -> None:
    a, club_a = new_club(client, root)
    b, club_b = new_club(client, root)
    player = new_athlete("Mover")
    join(client, a, club_a, player)
    join(client, b, club_b, player)
    assert status_of(club_a, player) == ["released"] and status_of(club_b, player) == ["active"]
    assert events(player) == ["joined_club", "left_club", "transferred"]
    assert client.get(f"/v1/clubs/{club_a}", headers=a.headers).json()["roster"] == []


def test_declining_ends_the_invitation(client: TestClient, root: dict[str, str]) -> None:
    admin, club = new_club(client, root)
    player = new_athlete("Declines")
    assert invite(client, admin, club, player).status_code == 204
    rid = roster_id(club, player)
    assert client.post(f"/v1/athletes/me/invitations/{rid}/decline", headers=player.headers).status_code == 204
    assert status_of(club, player) == ["released"] and events(player) == []
    assert client.post(f"/v1/athletes/me/invitations/{rid}/accept", headers=player.headers).status_code == 404
    assert invite(client, admin, club, player).status_code == 204  # may be asked again


def test_an_athlete_cannot_answer_someone_elses_invitation(client: TestClient, root: dict[str, str]) -> None:
    admin, club = new_club(client, root)
    owner, other = new_athlete("Owner"), new_athlete("Other")
    assert invite(client, admin, club, owner).status_code == 204
    rid = roster_id(club, owner)
    for verb in ("accept", "decline"):
        assert client.post(f"/v1/athletes/me/invitations/{rid}/{verb}", headers=other.headers).status_code == 404
    assert client.post(f"/v1/athletes/me/invitations/{rid}/accept").status_code == 401
    assert status_of(club, owner) == ["invited"] and status_of(club, other) == []


def test_a_malformed_id_is_a_404_not_a_500(client: TestClient, root: dict[str, str]) -> None:
    who = new_athlete("Malformed")
    assert client.post("/v1/athletes/me/invitations/not-a-uuid/accept", headers=who.headers).status_code == 404
    admin, club = new_club(client, root)
    assert client.delete(f"/v1/clubs/{club}/roster/not-a-uuid", headers=admin.headers).status_code == 404


# -- removing ----------------------------------------------------------------
def test_removing_ends_a_membership_and_withdraws_an_invitation(client: TestClient, root: dict[str, str]) -> None:
    admin, club = new_club(client, root)
    member, asked = new_athlete("Member"), new_athlete("Asked")
    join(client, admin, club, member)
    assert invite(client, admin, club, asked).status_code == 204

    assert client.delete(f"/v1/clubs/{club}/roster/{roster_id(club, member)}", headers=admin.headers).status_code == 204
    assert client.delete(f"/v1/clubs/{club}/roster/{roster_id(club, asked)}", headers=admin.headers).status_code == 204
    assert status_of(club, member) == ["released"] and status_of(club, asked) == ["released"]
    assert events(member) == ["joined_club", "left_club"] and events(asked) == []
    assert client.get(f"/v1/clubs/{club}", headers=admin.headers).json()["roster"] == []
    assert "club.player_removed" in audit_actions(club)
