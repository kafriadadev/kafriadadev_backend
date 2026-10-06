"""Sign-in by phone number or email address, in the one sign-in field.

The email is just another way to name the account: the same password check,
the same lock-out, and the same single answer for every kind of failure, so
the field never reveals whether an address is registered.
"""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from kafriada.main import create_app
from tests._access_helpers import bearer, make_user, sql

pytestmark = [
    pytest.mark.db,
    pytest.mark.skipif(not os.environ.get("DATABASE_URL_APP"), reason="needs DATABASE_URL_APP"),
]

PASSWORD = "a long test passphrase"


@pytest.fixture(scope="module")
def client() -> Iterator[TestClient]:
    with TestClient(create_app()) as c:
        yield c


def _email_of(user_id: object) -> str:
    (row,) = sql("SELECT email FROM ops.users WHERE id = :id", id=user_id)
    return str(row["email"])


def _post(client: TestClient, identifier: str, password: str = PASSWORD):  # type: ignore[no-untyped-def]
    return client.post("/v1/sessions", json={"phone": identifier, "password": password})


def test_the_email_signs_in_like_the_phone(client: TestClient) -> None:
    user_id, _ = make_user("By Email", password=PASSWORD, grants=[("athlete", "global", None)])
    email = _email_of(user_id)

    response = _post(client, email)
    assert response.status_code == 201, response.text
    me = client.get("/v1/me", headers=bearer(response.json()["token"]))
    assert me.status_code == 200 and me.json()["full_name"].startswith("By Email")


def test_the_email_is_matched_whatever_its_case_and_spacing(client: TestClient) -> None:
    user_id, _ = make_user("Case", password=PASSWORD, grants=[("athlete", "global", None)])
    email = _email_of(user_id)
    assert _post(client, f"  {email.upper()} ").status_code == 201


def test_every_failure_gets_the_same_answer(client: TestClient) -> None:
    user_id, _ = make_user("Known Email", password=PASSWORD, grants=[("athlete", "global", None)])
    email = _email_of(user_id)

    wrong = _post(client, email, "not the password")
    unknown = _post(client, "nobody.here@example.test")
    malformed = _post(client, "a@b")
    assert wrong.status_code == unknown.status_code == malformed.status_code == 401
    message = wrong.json()["error"]["message"]
    assert message == unknown.json()["error"]["message"] == malformed.json()["error"]["message"]
    assert message["field"] is None, "pointing at a field would say which part was wrong"

    (row,) = sql("SELECT failed_login_count FROM ops.users WHERE id = :id", id=user_id)
    assert row["failed_login_count"] == 1, "a wrong password by email counts towards the lock-out"


def test_a_long_email_is_accepted_by_the_field(client: TestClient) -> None:
    long_unknown = f"{'x' * 200}@example.test"
    assert _post(client, long_unknown).status_code == 401, "refused as unknown, not rejected as too long"
