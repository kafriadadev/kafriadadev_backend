"""Registering a club (CLB-01) and its dashboard (CLB-02).

The one that matters is the scope: an administrator of one club must not be able to
read another's, and nothing in a club's dashboard may come from anywhere else.
"""

from __future__ import annotations

import os
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from kafriada.contexts.access import service as access
from kafriada.main import create_app
from tests._access_helpers import audit_actions, bearer, make_user, sql
from tests._media_helpers import LGA, OTHER_LGA
from tests._payment_helpers import Athlete, new_athlete

pytestmark = [
    pytest.mark.db,
    pytest.mark.skipif(not os.environ.get("DATABASE_URL_APP"), reason="needs DATABASE_URL_APP"),
]


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(create_app())


def body(**over: object) -> dict[str, object]:
    return {
        "name": f"Test United {uuid4().hex[:8]}",
        "sport": "Football",
        "lga_id": LGA,
        "contact_phone": "08031234567",
        **over,
    }


def register(client: TestClient, who: Athlete, **over: object):  # type: ignore[no-untyped-def]
    return client.post("/v1/clubs", json=body(**over), headers=who.headers)


def club_of(client: TestClient, who: Athlete) -> str:
    made = register(client, who)
    assert made.status_code == 201, made.text
    return str(made.json()["club_id"])


def put(club: str, who: Athlete, status: str, by: Athlete) -> None:
    sql(
        "INSERT INTO identity.roster_members (team_id, athlete_id, status, invited_by) "
        "SELECT t.id, a.id, :s, :by FROM identity.teams t, identity.athletes a "
        "WHERE t.org_id = :c AND a.user_id = :u",
        s=status, by=by.user_id, c=club, u=who.user_id,
    )


def test_registering_makes_the_club_a_default_team_and_its_administrator(client: TestClient) -> None:
    who = new_athlete("Founder")
    made = register(client, who, year_founded=2015)
    assert made.status_code == 201, made.text
    club = made.json()["club_id"]

    (org,) = sql(
        "SELECT status, stage, rep_user_id::text AS rep, contact_phone, year_founded "
        "FROM identity.organizations WHERE id = :c", c=club,
    )
    assert (org["status"], org["stage"], org["rep"]) == ("pending_review", 1, str(who.user_id))
    assert org["contact_phone"] == "+2348031234567" and org["year_founded"] == 2015
    assert len(sql("SELECT 1 FROM identity.teams WHERE org_id = :c", c=club)) == 1
    (grant,) = sql(
        "SELECT role_code, scope_kind FROM ops.user_roles WHERE user_id = :u AND scope_id = :c",
        u=who.user_id, c=club,
    )
    assert (grant["role_code"], grant["scope_kind"]) == ("club_admin", "club")
    assert "club.registered" in audit_actions(club)

    me = client.get("/v1/me", headers=who.headers).json()
    mine = [r for r in me["roles"] if r["scope_kind"] == "club"]
    assert [r["scope_id"] for r in mine] == [club]
    assert mine[0]["scope_name"] == made.json()["name"]


def test_the_administrator_sees_an_empty_pending_club(client: TestClient) -> None:
    who = new_athlete("Viewer")
    club = club_of(client, who)
    got = client.get(f"/v1/clubs/{club}", headers=who.headers)
    assert got.status_code == 200, got.text
    data = got.json()
    assert (data["status"], data["verified"], data["players"], data["invites_out"]) == (
        "pending_review", False, 0, 0,
    )
    assert data["roster"] == [] and data["lga_name"] == "Birnin Kudu"


@pytest.mark.parametrize(
    ("over", "field"),
    [
        ({"name": "  "}, "name"),
        ({"name": "x" * 81}, "name"),
        ({"sport": "Curling"}, "sport"),
        ({"lga_id": OTHER_LGA}, "lga_id"),
        ({"lga_id": "NG-JG-NOPE"}, "lga_id"),
        ({"contact_phone": "12"}, "contact_phone"),
        ({"year_founded": 1850}, "year_founded"),
        ({"year_founded": 2999}, "year_founded"),
    ],
)
def test_bad_input_is_refused_on_its_field_and_writes_nothing(
    client: TestClient, over: dict[str, object], field: str
) -> None:
    who = new_athlete("Bad input")
    before = sql("SELECT count(*) AS n FROM identity.organizations")[0]["n"]
    got = register(client, who, **over)
    assert got.status_code == 422, got.text
    assert got.json()["error"]["message"]["field"] == field
    assert sql("SELECT count(*) AS n FROM identity.organizations")[0]["n"] == before


def test_a_repeated_name_in_the_same_lga_is_a_question_not_a_refusal(client: TestClient) -> None:
    first, second = new_athlete("Twin A"), new_athlete("Twin B")
    name = f"Twin FC {uuid4().hex[:8]}"
    assert register(client, first, name=name).status_code == 201
    asked = register(client, second, name=name.upper())
    assert asked.status_code == 409 and asked.json()["error"]["message"]["field"] == "name"
    assert register(client, second, name=name, confirm_duplicate=True).status_code == 201


def test_an_administrator_cannot_read_another_club(client: TestClient) -> None:
    a, b = new_athlete("Admin A"), new_athlete("Admin B")
    club_a, club_b = club_of(client, a), club_of(client, b)
    assert client.get(f"/v1/clubs/{club_a}", headers=a.headers).status_code == 200
    assert client.get(f"/v1/clubs/{club_b}", headers=a.headers).status_code == 403
    assert client.get(f"/v1/clubs/{club_a}", headers=b.headers).status_code == 403


def test_a_signed_in_stranger_and_an_anonymous_caller_are_refused(client: TestClient) -> None:
    owner, stranger = new_athlete("Owner"), new_athlete("Stranger")
    club = club_of(client, owner)
    assert client.get(f"/v1/clubs/{club}", headers=stranger.headers).status_code == 403
    assert client.get(f"/v1/clubs/{club}").status_code == 401
    assert client.post("/v1/clubs", json=body()).status_code == 401


def test_a_super_administrator_reads_any_club_and_gets_404_for_none(client: TestClient) -> None:
    owner = new_athlete("Owned")
    club = club_of(client, owner)
    uid, _ = make_user("Admin", grants=[("super_admin", "global", None)])
    root = access.issue_session(uid, method="test").token
    assert client.get(f"/v1/clubs/{club}", headers=bearer(root)).status_code == 200
    assert client.get(f"/v1/clubs/{uuid4()}", headers=bearer(root)).status_code == 404
    assert client.get("/v1/clubs/not-a-uuid", headers=bearer(root)).status_code == 404


def test_the_roster_holds_only_this_clubs_people(client: TestClient) -> None:
    a, b = new_athlete("Roster A"), new_athlete("Roster B")
    club_a, club_b = club_of(client, a), club_of(client, b)
    mine, theirs, invited = new_athlete("Mine"), new_athlete("Theirs"), new_athlete("Invited")
    put(club_a, mine, "active", a)
    put(club_a, invited, "invited", a)
    put(club_b, theirs, "active", b)

    seen = client.get(f"/v1/clubs/{club_a}", headers=a.headers).json()
    assert {r["kuid"]: r["state"] for r in seen["roster"]} == {
        mine.kuid: "unverified", invited.kuid: "invited",
    }
    assert (seen["players"], seen["verified_players"], seen["invites_out"]) == (1, 0, 1)
    other = client.get(f"/v1/clubs/{club_b}", headers=b.headers).json()
    assert [r["kuid"] for r in other["roster"]] == [theirs.kuid]


def test_an_athlete_can_be_active_in_only_one_club(client: TestClient) -> None:
    a, b = new_athlete("One A"), new_athlete("One B")
    club_a, club_b = club_of(client, a), club_of(client, b)
    player = new_athlete("Player")
    put(club_a, player, "active", a)
    with pytest.raises(Exception, match="roster_members_one_active_per_athlete"):
        put(club_b, player, "active", b)
