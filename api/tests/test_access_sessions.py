"""Sessions and role grants, end to end through the HTTP routes.

What is proved here:
  - sign-in issues a session; sign-out ends it on the very next request
  - a wrong password and an unknown phone get the identical answer
  - ten wrong passwords lock the account, even against the right one
  - staff get a 30-minute idle window, athletes 30 days; neither outlives the
    absolute expiry, and an expired, revoked or suspended session is refused
  - granting and revoking a role asks for the password again, refuses a scoped
    role without its scope, ends the grantee's sessions, and is audited
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from kafriada.contexts.access import service as access
from kafriada.contexts.identity.service import RegistrationInput, register
from kafriada.main import create_app
from tests._access_helpers import audit_actions, bearer, make_user, new_phone, sql

pytestmark = [
    pytest.mark.db,
    pytest.mark.skipif(
        not os.environ.get("DATABASE_URL_APP"),
        reason="needs DATABASE_URL_APP",
    ),
]

PASSWORD = "a long test passphrase"


@pytest.fixture(scope="module")
def client() -> Iterator[TestClient]:
    with TestClient(create_app()) as c:
        yield c


def _sign_in(client: TestClient, phone: str, password: str = PASSWORD) -> str:
    response = client.post("/v1/sessions", json={"phone": phone, "password": password})
    assert response.status_code == 201, response.text
    return str(response.json()["token"])


def _seconds_from_now(value: str) -> float:
    return (datetime.fromisoformat(value) - datetime.now(UTC)).total_seconds()


# ---------------------------------------------------------------------------
# Sign-in and sign-out
# ---------------------------------------------------------------------------
def test_sign_in_opens_me_and_sign_out_ends_it(client: TestClient) -> None:
    user_id, phone = make_user("Athlete", password=PASSWORD, grants=[("athlete", "global", None)])

    # Any way of writing the number works, as at registration.
    local = "0" + phone.removeprefix("+234")
    token = _sign_in(client, local)

    me = client.get("/v1/me", headers=bearer(token))
    assert me.status_code == 200, me.text
    body = me.json()
    assert body["full_name"].startswith("Athlete")
    assert body["is_staff"] is False
    assert phone not in me.text, "the full phone number must not come back out"
    assert _seconds_from_now(body["idle_expires_at"]) > 29 * 86_400

    assert client.delete("/v1/sessions/current", headers=bearer(token)).status_code == 204
    assert client.get("/v1/me", headers=bearer(token)).status_code == 401

    actions = audit_actions(user_id)
    assert "session.issued" in actions
    assert "session.revoked" in actions


def test_no_token_or_a_malformed_header_is_refused(client: TestClient) -> None:
    assert client.get("/v1/me").status_code == 401
    assert client.get("/v1/me", headers={"authorization": "Bearer "}).status_code == 401
    assert client.get("/v1/me", headers={"authorization": "Basic abc"}).status_code == 401
    assert client.get("/v1/me", headers=bearer("x" * 43)).status_code == 401


def test_wrong_password_and_unknown_phone_get_the_same_answer(client: TestClient) -> None:
    user_id, phone = make_user("Known", password=PASSWORD, grants=[("athlete", "global", None)])

    wrong = client.post("/v1/sessions", json={"phone": phone, "password": "not the password"})
    unknown = client.post("/v1/sessions", json={"phone": new_phone(), "password": PASSWORD})
    junk = client.post("/v1/sessions", json={"phone": "hello", "password": PASSWORD})

    assert wrong.status_code == unknown.status_code == junk.status_code == 401
    message = wrong.json()["error"]["message"]
    assert message == unknown.json()["error"]["message"] == junk.json()["error"]["message"]
    assert message["field"] is None

    (row,) = sql("SELECT failed_login_count FROM ops.users WHERE id = :id", id=user_id)
    assert row["failed_login_count"] == 1
    assert "session.sign_in_failed" in audit_actions(user_id)


def test_ten_wrong_passwords_lock_the_account(client: TestClient) -> None:
    user_id, phone = make_user("Guessed", password=PASSWORD, grants=[("athlete", "global", None)])

    for _ in range(access.MAX_FAILED_SIGN_INS):
        r = client.post("/v1/sessions", json={"phone": phone, "password": "wrong guess"})
        assert r.status_code == 401

    # Now even the right password is refused, with the same message.
    right = client.post("/v1/sessions", json={"phone": phone, "password": PASSWORD})
    assert right.status_code == 401

    (row,) = sql(
        "SELECT locked_until > now() AS locked FROM ops.users WHERE id = :id", id=user_id
    )
    assert row["locked"] is True
    assert "account.locked" in audit_actions(user_id)


# ---------------------------------------------------------------------------
# The two clocks
# ---------------------------------------------------------------------------
def test_staff_get_a_thirty_minute_idle_window(client: TestClient) -> None:
    _, phone = make_user(
        "Coordinator", password=PASSWORD, grants=[("lga_coordinator", "lga", "NG-JG-BKD")]
    )
    response = client.post("/v1/sessions", json={"phone": phone, "password": PASSWORD})
    assert response.status_code == 201
    body = response.json()
    assert body["is_staff"] is True
    assert 28 * 60 < _seconds_from_now(body["idle_expires_at"]) <= 30 * 60 + 5
    assert _seconds_from_now(body["absolute_expires_at"]) <= 7 * 86_400 + 5


def test_expired_revoked_and_suspended_sessions_are_refused(client: TestClient) -> None:
    user_id, _ = make_user("Clock", grants=[("athlete", "global", None)])

    idle = access.issue_session(user_id, method="test")
    sql("UPDATE ops.sessions SET idle_expires_at = now() - interval '1 second' WHERE id = :id",
        id=idle.session_id)
    assert client.get("/v1/me", headers=bearer(idle.token)).status_code == 401

    absolute = access.issue_session(user_id, method="test")
    sql(
        """
        UPDATE ops.sessions
           SET issued_at = now() - interval '100 days',
               absolute_expires_at = now() - interval '1 second'
         WHERE id = :id
        """,
        id=absolute.session_id,
    )
    assert client.get("/v1/me", headers=bearer(absolute.token)).status_code == 401

    revoked = access.issue_session(user_id, method="test")
    sql("UPDATE ops.sessions SET revoked_at = now() WHERE id = :id", id=revoked.session_id)
    assert client.get("/v1/me", headers=bearer(revoked.token)).status_code == 401

    live = access.issue_session(user_id, method="test")
    assert client.get("/v1/me", headers=bearer(live.token)).status_code == 200
    sql("UPDATE ops.users SET status = 'suspended' WHERE id = :id", id=user_id)
    assert client.get("/v1/me", headers=bearer(live.token)).status_code == 401


def test_the_idle_window_slides_but_never_past_the_absolute_expiry(client: TestClient) -> None:
    user_id, _ = make_user("Slide", grants=[("athlete", "global", None)])
    issued = access.issue_session(user_id, method="test")
    sql(
        """
        UPDATE ops.sessions
           SET idle_expires_at = now() + interval '1 minute',
               absolute_expires_at = now() + interval '10 minutes'
         WHERE id = :id
        """,
        id=issued.session_id,
    )
    me = client.get("/v1/me", headers=bearer(issued.token))
    assert me.status_code == 200
    body = me.json()
    # An athlete's 30-day window would run past the absolute expiry, so it stops there.
    assert body["idle_expires_at"] == body["absolute_expires_at"]


# ---------------------------------------------------------------------------
# Roles
# ---------------------------------------------------------------------------
def test_registration_grants_the_athlete_role() -> None:
    result = register(
        RegistrationInput(
            full_name="Role Test Athlete",
            phone=new_phone(),
            password=PASSWORD,
            date_of_birth=date(1999, 1, 1),
            lga_id="NG-JG-BKD",
            sport="Football",
            consent_notice_version="1.0",
        )
    )
    rows = sql(
        "SELECT role_code, scope_kind, reason FROM ops.user_roles "
        "WHERE user_id = :id AND revoked_at IS NULL",
        id=result.user_id,
    )
    assert rows == [{"role_code": "athlete", "scope_kind": "global", "reason": "registration"}]


@pytest.fixture
def admin(client: TestClient) -> tuple[str, object]:
    admin_id, phone = make_user(
        "Admin", password=PASSWORD, grants=[("super_admin", "global", None)]
    )
    return _sign_in(client, phone), admin_id


def test_granting_a_role_is_reauthenticated_audited_and_ends_sessions(
    client: TestClient, admin: tuple[str, object]
) -> None:
    admin_token, admin_id = admin
    target_id, target_phone = make_user(
        "Grantee", password=PASSWORD, grants=[("athlete", "global", None)]
    )
    target_token = _sign_in(client, target_phone)

    granted = client.post(
        f"/v1/admin/users/{target_id}/roles",
        headers=bearer(admin_token),
        json={
            "role": "lga_coordinator",
            "scope_id": "NG-JG-BKD",
            "reason": "appointed for the first drive",
            "current_password": PASSWORD,
        },
    )
    assert granted.status_code == 201, granted.text
    grant_id = granted.json()["grant_id"]

    # Their existing session ended; the next one is a staff session.
    assert client.get("/v1/me", headers=bearer(target_token)).status_code == 401
    me = client.get("/v1/me", headers=bearer(_sign_in(client, target_phone))).json()
    assert me["is_staff"] is True
    assert {"role": "lga_coordinator", "scope_id": "NG-JG-BKD", "scope_name": "Birnin Kudu"}.items() <= next(
        g for g in me["roles"] if g["role"] == "lga_coordinator"
    ).items()

    (audit_row,) = sql(
        "SELECT actor_user_id, metadata FROM ops.audit_log "
        "WHERE action = 'role.granted' AND subject_id = :s",
        s=str(target_id),
    )
    assert audit_row["actor_user_id"] == admin_id
    assert audit_row["metadata"]["scope_id"] == "NG-JG-BKD"
    assert audit_row["metadata"]["logins_ended"] == 1

    (session_row,) = sql(
        "SELECT count(*) AS n FROM ops.sessions "
        "WHERE user_id = :id AND reauthenticated_at IS NOT NULL",
        id=admin_id,
    )
    assert session_row["n"] == 1

    # And revoking it: same password check, row kept but marked, audited.
    revoked = client.post(
        f"/v1/admin/role-grants/{grant_id}/revoke",
        headers=bearer(admin_token),
        json={"reason": "drive finished", "current_password": PASSWORD},
    )
    assert revoked.status_code == 204, revoked.text
    (grant_row,) = sql(
        "SELECT revoked_at IS NOT NULL AS revoked, revoked_by FROM ops.user_roles WHERE id = :id",
        id=grant_id,
    )
    assert grant_row == {"revoked": True, "revoked_by": admin_id}
    assert "role.revoked" in audit_actions(target_id)


@pytest.mark.parametrize(
    ("change", "field"),
    [
        ({"scope_id": None}, "scope_id"),  # a scoped role with no scope
        ({"scope_id": "NG-JG-XXX"}, "scope_id"),  # no such LGA
        ({"role": "super_admin"}, "scope_id"),  # a global role given a scope
        ({"role": "club_admin", "scope_id": "any-club"}, "scope_id"),  # no such club
        ({"role": "no_such_role"}, "role"),
        ({"current_password": "not my password"}, "current_password"),
    ],
)
def test_a_bad_grant_is_refused_and_grants_nothing(
    client: TestClient,
    admin: tuple[str, object],
    change: dict[str, object],
    field: str,
) -> None:
    admin_token, _ = admin
    target_id, _ = make_user("Refused", grants=[("athlete", "global", None)])
    body = {
        "role": "lga_coordinator",
        "scope_id": "NG-JG-BKD",
        "reason": "test",
        "current_password": PASSWORD,
        **change,
    }
    response = client.post(
        f"/v1/admin/users/{target_id}/roles", headers=bearer(admin_token), json=body
    )
    assert response.status_code == 422, response.text
    assert response.json()["error"]["message"]["field"] == field

    rows = sql(
        "SELECT role_code FROM ops.user_roles WHERE user_id = :id AND revoked_at IS NULL",
        id=target_id,
    )
    assert rows == [{"role_code": "athlete"}]


def test_an_admin_can_end_all_of_someones_sessions(
    client: TestClient, admin: tuple[str, object]
) -> None:
    admin_token, _ = admin
    target_id, _ = make_user("Lost Phone", grants=[("athlete", "global", None)])
    tokens = [access.issue_session(target_id, method="test").token for _ in range(2)]

    response = client.post(
        f"/v1/admin/users/{target_id}/sessions/end",
        headers=bearer(admin_token),
        json={"reason": "phone reported stolen"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["sessions_ended"] == 2
    for token in tokens:
        assert client.get("/v1/me", headers=bearer(token)).status_code == 401
    assert "session.revoked_all" in audit_actions(target_id)


def test_the_session_expiry_times_are_timezone_aware() -> None:
    user_id, _ = make_user("Tz", grants=[("athlete", "global", None)])
    issued = access.issue_session(user_id, method="test")
    assert issued.absolute_expires_at.tzinfo is not None
    assert issued.absolute_expires_at - datetime.now(UTC) > timedelta(days=89)
