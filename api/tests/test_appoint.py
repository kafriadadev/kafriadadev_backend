"""The first super administrator, and granting a role that is scoped to a club.

The command exists because nobody holds the authority to ask for a password yet; what it
must not do is become a way around the console afterwards. It grants one role, to one
registered and confirmed person, once, and leaves an audit row.
"""

from __future__ import annotations

import os
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from kafriada.appoint import AppointRefused, appoint_super_admin
from kafriada.contexts.access import service as access
from kafriada.main import create_app
from tests._access_helpers import bearer, make_user, sql
from tests._media_helpers import super_admin
from tests._payment_helpers import new_athlete

pytestmark = [
    pytest.mark.db,
    pytest.mark.skipif(not os.environ.get("DATABASE_URL_APP"), reason="needs DATABASE_URL_APP"),
]

PASSWORD = "a long test passphrase"


def confirmed(name: str) -> tuple[object, str]:
    user_id, phone = make_user(name)
    sql("UPDATE ops.users SET phone_verified_at = now() WHERE id = :u", u=user_id)
    return user_id, phone


def roles_of(user_id: object) -> list[tuple[str, str]]:
    return [
        (str(r["role_code"]), str(r["scope_kind"]))
        for r in sql(
            "SELECT role_code, scope_kind FROM ops.user_roles WHERE user_id = :u AND revoked_at IS NULL",
            u=user_id,
        )
    ]


def test_a_confirmed_person_is_appointed_once_and_it_is_on_the_record() -> None:
    user_id, phone = confirmed("Founder")
    name = appoint_super_admin(phone, "founding administrator")
    assert name.startswith("Founder")
    assert roles_of(user_id) == [("super_admin", "global")]
    assert access.can(user_id, "admin.manage_users")  # type: ignore[arg-type]
    (row,) = sql(
        "SELECT actor_label, metadata->>'reason' AS reason FROM ops.audit_log "
        "WHERE subject_id = :s AND action = 'role.granted'", s=str(user_id),
    )
    assert row["actor_label"] == "system:operator" and row["reason"] == "founding administrator"
    with pytest.raises(AppointRefused, match="already"):
        appoint_super_admin(phone, "again")
    assert roles_of(user_id) == [("super_admin", "global")]


def test_a_local_number_works_the_same_as_the_full_one() -> None:
    user_id, phone = confirmed("Local format")
    local = "0" + phone[4:]  # +234XXXXXXXXXX -> 0XXXXXXXXXX
    appoint_super_admin(local, "founding administrator")
    assert roles_of(user_id) == [("super_admin", "global")]


@pytest.mark.parametrize(
    ("kind", "match"),
    [("unknown", "registered"), ("unconfirmed", "confirmed"), ("no reason", "why"), ("bad number", "phone|digit|number")],
)
def test_it_refuses_what_it_should_and_grants_nothing(kind: str, match: str) -> None:
    user_id, phone = make_user("Refused")  # registered
    if kind == "unknown":
        with pytest.raises(AppointRefused, match=match):
            appoint_super_admin("+2348090000000", "x")
    elif kind == "unconfirmed":
        sql("UPDATE ops.users SET email_verified_at = NULL WHERE id = :u", u=user_id)
        with pytest.raises(AppointRefused, match=match):
            appoint_super_admin(phone, "founding administrator")
    elif kind == "no reason":
        sql("UPDATE ops.users SET phone_verified_at = now() WHERE id = :u", u=user_id)
        with pytest.raises(AppointRefused, match=match):
            appoint_super_admin(phone, "   ")
    else:
        with pytest.raises(AppointRefused):
            appoint_super_admin("12", "x")
    assert roles_of(user_id) == []


def test_an_anonymised_account_cannot_be_appointed() -> None:
    user_id, phone = confirmed("Erased")
    sql("UPDATE ops.users SET anonymised_at = now() WHERE id = :u", u=user_id)
    with pytest.raises(AppointRefused, match="registered"):
        appoint_super_admin(phone, "founding administrator")


# -- granting a club role from the console ----------------------------------------
@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(create_app())


def test_a_club_role_needs_a_real_club(client: TestClient) -> None:
    admin = super_admin(PASSWORD)
    founder = new_athlete("Club owner")
    made = client.post(
        "/v1/clubs", headers=founder.headers,
        json={"name": f"Scope FC {uuid4().hex[:6]}", "sport": "Football", "lga_id": "NG-JG-BKD",
              "contact_phone": "08031234567"},
    )
    club = str(made.json()["club_id"])
    assistant, _ = make_user("Assistant")

    def grant(scope: str | None, role: str = "coach"):  # type: ignore[no-untyped-def]
        return client.post(
            f"/v1/admin/users/{assistant}/roles", headers=bearer(admin.token),
            json={"role": role, "scope_id": scope, "reason": "test", "current_password": PASSWORD},
        )

    for bad in ("not-a-uuid", str(uuid4()), "NG-JG-BKD", None):
        got = grant(bad)
        assert got.status_code == 422 and got.json()["error"]["message"]["field"] in ("scope_id", "role"), bad
    assert roles_of(assistant) == []

    assert grant(club).status_code == 201
    assert roles_of(assistant) == [("coach", "club")]
    # The role now works where it is scoped, and only there.
    token = access.issue_session(assistant, method="test").token  # type: ignore[arg-type]
    assert client.get(f"/v1/clubs/{club}", headers=bearer(token)).status_code == 200
    other = client.post(
        "/v1/clubs", headers=new_athlete("Other owner").headers,
        json={"name": f"Other FC {uuid4().hex[:6]}", "sport": "Football", "lga_id": "NG-JG-BKD",
              "contact_phone": "08031234567"},
    )
    assert client.get(f"/v1/clubs/{other.json()['club_id']}", headers=bearer(token)).status_code == 403
