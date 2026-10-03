"""A club signs up on its own, and is reviewed only once its representative is reachable.

The representative's account is not an athlete: no athlete record, no ID. The club
waits as ``unconfirmed`` (invisible to administrators, impossible to approve) until
the representative confirms their email. Athletes can no longer register clubs.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from kafriada.main import create_app
from tests._access_helpers import audit_actions, sql
from tests._club_helpers import club_body, emailed_code, sign_up_club, signup_body
from tests._media_helpers import super_admin
from tests._payment_helpers import new_athlete

pytestmark = [
    pytest.mark.db,
    pytest.mark.skipif(not os.environ.get("DATABASE_URL_APP"), reason="needs DATABASE_URL_APP"),
]


@pytest.fixture(scope="module")
def client() -> Iterator[TestClient]:
    with TestClient(create_app()) as c:
        yield c


@pytest.fixture(scope="module")
def root() -> dict[str, str]:
    return {"authorization": f"Bearer {super_admin('a long test passphrase').token}"}


def test_a_sign_up_waits_unseen_until_the_email_is_confirmed(
    client: TestClient, root: dict[str, str]
) -> None:
    body = signup_body()
    made = client.post("/v1/clubs/register", json=body)
    assert made.status_code == 201, made.text
    club = str(made.json()["club_id"])
    assert made.json()["email"].endswith("@example.test") and "***" in made.json()["email"]

    (org,) = sql(
        "SELECT o.status, o.rep_role, o.age_groups, o.official2_phone, u.email_verified_at, "
        "(SELECT count(*) FROM identity.athletes a WHERE a.user_id = u.id) AS athlete_rows "
        "FROM identity.organizations o JOIN ops.users u ON u.id = o.rep_user_id WHERE o.id = :c",
        c=club,
    )
    assert org["status"] == "unconfirmed"
    assert (org["rep_role"], org["age_groups"]) == ("Chairman", ["senior", "u17"])
    assert org["athlete_rows"] == 0, "a club representative is not an athlete"
    assert org["email_verified_at"] is None

    listed = client.get("/v1/admin/clubs", headers=root).json()["clubs"]
    assert club not in [c["club_id"] for c in listed]
    assert client.post(f"/v1/admin/clubs/{club}/approve", headers=root).status_code == 404

    # The representative cannot sign in until the email is confirmed.
    early = client.post("/v1/sessions",
                        json={"phone": body["rep_phone"], "password": body["password"]})
    assert early.status_code == 409

    confirmed = client.post(
        "/v1/email/confirm",
        json={"phone": body["rep_phone"], "code": emailed_code(body["rep_email"])},
    )
    assert confirmed.status_code == 200
    assert sql("SELECT status FROM identity.organizations WHERE id = :c", c=club) == [
        {"status": "pending_review"}
    ]
    listed = client.get("/v1/admin/clubs", headers=root).json()["clubs"]
    assert club in [c["club_id"] for c in listed]

    headers = {"authorization": f"Bearer {confirmed.json()['token']}"}
    me = client.get("/v1/me", headers=headers).json()
    assert me["kuid"] is None
    assert [r["role"] for r in me["roles"]] == ["club_admin"]
    dash = client.get(f"/v1/clubs/{club}", headers=headers).json()
    assert dash["profile"]["ground_name"] == "Township Stadium"
    assert "club.registered" in audit_actions(club)


@pytest.mark.parametrize(
    ("change", "field"),
    [
        ({"rep_first_name": ""}, "rep_first_name"),
        ({"rep_role": "Fan"}, "rep_role"),
        ({"rep_email": "nope"}, "rep_email"),
        ({"password": "short"}, "password"),
        ({"short_name": ""}, "short_name"),
        ({"age_groups": ["u99"]}, "age_groups"),
        ({"level": "galactic"}, "level"),
        ({"ground_address": ""}, "ground_address"),
        ({"official2_name": ""}, "official2_name"),
        ({"year_founded": 1850}, "year_founded"),
        ({"accept_privacy_notice": False}, "accept_privacy_notice"),
    ],
)
def test_each_missing_or_invalid_field_is_refused_and_nothing_is_written(
    client: TestClient, change: dict[str, Any], field: str
) -> None:
    body = signup_body(**change)
    got = client.post("/v1/clubs/register", json=body)
    assert got.status_code == 422, got.text
    assert got.json()["error"]["message"]["field"] == field
    assert not sql("SELECT id FROM ops.users WHERE phone_e164 = :p", p=body["rep_phone"])
    assert not sql("SELECT id FROM identity.organizations WHERE name = :n", n=body["name"])


def test_the_second_official_needs_a_different_number(client: TestClient) -> None:
    body = signup_body()
    body["official2_phone"] = body["rep_phone"]
    got = client.post("/v1/clubs/register", json=body)
    assert got.status_code == 422
    assert got.json()["error"]["message"]["field"] == "official2_phone"


def test_a_representative_number_already_registered_is_refused(client: TestClient) -> None:
    first = signup_body()
    assert client.post("/v1/clubs/register", json=first).status_code == 201
    again = signup_body(rep_phone=first["rep_phone"])
    got = client.post("/v1/clubs/register", json=again)
    assert got.status_code == 422
    assert got.json()["error"]["message"]["field"] == "rep_phone"


def test_an_athlete_can_no_longer_register_a_club(client: TestClient) -> None:
    athlete = new_athlete("No Clubs")
    got = client.post("/v1/clubs", json=club_body(), headers=athlete.headers)
    assert got.status_code == 403


def test_a_signed_up_club_works_end_to_end_once_approved(
    client: TestClient, root: dict[str, str]
) -> None:
    rep, club = sign_up_club(client, root)
    dash = client.get(f"/v1/clubs/{club}", headers=rep.headers).json()
    assert dash["status"] == "approved"
