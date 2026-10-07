"""Data requests (ADM-07): export and erasure.

What must hold: an export carries what is held about the person and never their
password; erasure clears every identifying field, ends their sessions, withdraws their
badge and removes their files, while the ID, the payments and the audit trail stay;
the public profile, card and photo stop answering; nothing happens without a note and
the administrator's password; every answer is an insert-only row; super administrators
only.
"""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import DBAPIError

from kafriada.contexts.access import service as access
from kafriada.main import create_app
from tests._access_helpers import bearer, make_user, sql
from tests._media_helpers import (
    LGA, athlete_with_files, pay, request_id_of, review_url, reviewer, super_admin, use_local_store,
)
from tests._payment_helpers import new_athlete

pytestmark = [
    pytest.mark.db,
    pytest.mark.skipif(
        not (os.environ.get("DATABASE_URL_APP") and os.environ.get("DATABASE_URL_MONEY")),
        reason="needs DATABASE_URL_APP and DATABASE_URL_MONEY",
    ),
]

PASSWORD = "a long admin phrase 42"


@pytest.fixture(scope="module")
def client() -> Iterator[TestClient]:
    with TestClient(create_app()) as c:
        yield c


@pytest.fixture(autouse=True)
def _store(monkeypatch: pytest.MonkeyPatch, tmp_path):  # type: ignore[no-untyped-def]
    return use_local_store(monkeypatch, tmp_path)


@pytest.fixture(scope="module")
def admin():  # type: ignore[no-untyped-def]
    return super_admin(PASSWORD)


def approved_athlete(client: TestClient, name: str):  # type: ignore[no-untyped-def]
    who = athlete_with_files(client, name)
    pay(who)
    assert client.post(review_url(request_id_of(who)) + "/approve", headers=reviewer().headers).status_code == 200
    return who


def erase(client: TestClient, admin, user_id, **overrides):  # type: ignore[no-untyped-def]
    body = {"received_via": "in_person", "note": "Asked at the LGA office; ID card checked.",
            "current_password": PASSWORD, **overrides}
    return client.post(f"/v1/admin/data-requests/{user_id}/erase", json=body, headers=admin.headers)


def find(client: TestClient, admin, q: str):  # type: ignore[no-untyped-def]
    return client.get("/v1/admin/data-requests/person", params={"q": q}, headers=admin.headers)


def test_a_person_is_found_by_id_phone_or_email(client: TestClient, admin) -> None:  # type: ignore[no-untyped-def]
    who = new_athlete("Findable")
    (u,) = sql("SELECT phone_e164, email FROM ops.users WHERE id = :u", u=who.user_id)
    for q in (who.kuid, str(u["phone_e164"]), str(u["email"]).upper()):
        got = find(client, admin, q)
        assert got.status_code == 200, q
        assert got.json()["user_id"] == str(who.user_id) and got.json()["kuid"] == who.kuid
    assert find(client, admin, "nobody@example.com").status_code == 404


def test_an_export_carries_the_record_and_never_the_password(client: TestClient, admin) -> None:  # type: ignore[no-untyped-def]
    who = athlete_with_files(client, "Exported")
    reference = pay(who)
    got = client.post(f"/v1/admin/data-requests/{who.user_id}/export",
                      json={"received_via": "email"}, headers=admin.headers)
    assert got.status_code == 200, got.text
    data = got.json()
    assert data["athlete"]["kuid"] == who.kuid and data["athlete"]["date_of_birth"]
    assert [p["reference"] for p in data["payments"]] == [reference]
    assert {m["kind"] for m in data["photos_and_documents"]} == {"photo", "document"}
    assert "password" not in got.text and "token" not in got.text.lower()

    (row,) = sql("SELECT kind, received_via FROM ops.data_requests WHERE user_id = :u", u=who.user_id)
    assert row == {"kind": "export", "received_via": "email"}
    assert find(client, admin, who.kuid).json()["requests"][0]["kind"] == "export"


def test_erasure_clears_the_person_and_keeps_the_record(client: TestClient, admin) -> None:  # type: ignore[no-untyped-def]
    who = approved_athlete(client, "Erased")
    (before,) = sql("SELECT phone_e164 FROM ops.users WHERE id = :u", u=who.user_id)
    payments_before = sql("SELECT count(*) AS n FROM money.payments p JOIN identity.athletes a "
                          "ON a.id = p.on_behalf_of OR p.paid_by = a.user_id WHERE a.kuid = :k", k=who.kuid)
    assert client.get(f"/v1/public/athletes/{who.kuid}/photo").status_code == 200

    got = erase(client, admin, who.user_id)
    assert got.status_code == 204, got.text

    (u,) = sql("SELECT full_name, first_name, surname, phone_e164, email, password_hash, status, anonymised_at "
               "FROM ops.users WHERE id = :u", u=who.user_id)
    assert u["full_name"] == "Removed at the holder's request"
    assert u["first_name"] is None and u["surname"] is None and u["phone_e164"] is None
    assert u["email"] is None and u["password_hash"] is None
    assert u["status"] == "anonymised" and u["anonymised_at"] is not None
    (a,) = sql("SELECT kuid, date_of_birth, address_line, emergency_phone FROM identity.athletes WHERE user_id = :u",
               u=who.user_id)
    assert a["kuid"] == who.kuid, "the ID shell is kept"
    assert a["date_of_birth"] is None and a["address_line"] is None and a["emergency_phone"] is None

    assert client.get("/v1/me", headers=who.headers).status_code == 401, "their sessions end"
    for path in (f"/v1/public/athletes/{who.kuid}", f"/v1/public/athletes/{who.kuid}/photo",
                 f"/v1/public/athletes/{who.kuid}/card.png"):
        assert client.get(path).status_code == 404, path
    (v,) = sql("SELECT status FROM identity.verification_requests v JOIN identity.athletes a "
               "ON a.id = v.athlete_id WHERE a.kuid = :k", k=who.kuid)
    assert v["status"] == "revoked"
    assert sql("SELECT count(*) AS n FROM identity.media_files m JOIN identity.athletes a ON a.id = m.athlete_id "
               "WHERE a.kuid = :k AND m.deleted_at IS NULL", k=who.kuid) == [{"n": 0}]
    assert sql("SELECT count(*) AS n FROM money.payments p JOIN identity.athletes a "
               "ON a.id = p.on_behalf_of OR p.paid_by = a.user_id WHERE a.kuid = :k", k=who.kuid) == payments_before
    assert sql("SELECT count(*) AS n FROM ops.outbox WHERE payload ->> 'user_id' = :u OR payload ->> 'to' = :p",
               u=str(who.user_id), p=str(before["phone_e164"])) == [{"n": 0}]

    found = find(client, admin, who.kuid).json()
    assert found["anonymised"] is True and found["requests"][0]["kind"] == "erase"
    assert find(client, admin, str(before["phone_e164"])).status_code == 404, "the number is released"
    assert "data_request.erased" in [r["action"] for r in sql(
        "SELECT action FROM ops.audit_log WHERE subject_id = :u", u=str(who.user_id))]


def test_nothing_happens_without_a_note_and_the_password(client: TestClient, admin) -> None:  # type: ignore[no-untyped-def]
    who = new_athlete("Kept")
    wrong = erase(client, admin, who.user_id, current_password="not it")
    assert wrong.status_code == 422 and wrong.json()["error"]["message"]["field"] == "current_password"
    blank = erase(client, admin, who.user_id, note="   ")
    assert blank.status_code == 422
    channel = erase(client, admin, who.user_id, received_via="carrier pigeon")
    assert channel.status_code == 422 and channel.json()["error"]["message"]["field"] == "received_via"
    assert sql("SELECT anonymised_at FROM ops.users WHERE id = :u", u=who.user_id) == [{"anonymised_at": None}]
    assert sql("SELECT count(*) AS n FROM ops.data_requests WHERE user_id = :u", u=who.user_id) == [{"n": 0}]


def test_erasing_twice_or_yourself_is_refused(client: TestClient, admin) -> None:  # type: ignore[no-untyped-def]
    who = new_athlete("Twice")
    assert erase(client, admin, who.user_id).status_code == 204
    assert erase(client, admin, who.user_id).status_code == 409
    assert erase(client, admin, admin.user_id).status_code == 409


def test_the_request_log_cannot_be_edited(client: TestClient, admin) -> None:  # type: ignore[no-untyped-def]
    who = new_athlete("Logged")
    client.post(f"/v1/admin/data-requests/{who.user_id}/export", json={"received_via": "phone"}, headers=admin.headers)
    for statement in ("UPDATE ops.data_requests SET note = 'x' WHERE user_id = :u",
                      "DELETE FROM ops.data_requests WHERE user_id = :u"):
        with pytest.raises(DBAPIError):
            sql(statement, u=who.user_id)


def test_only_a_super_administrator_gets_in(client: TestClient) -> None:
    target = new_athlete("Target")
    state_id, _ = make_user("State", grants=[("state_coordinator", "state", "NG-JG")])
    others = [target.headers, reviewer(LGA).headers, bearer(access.issue_session(state_id, method="test").token)]
    for headers in others:
        assert client.get("/v1/admin/data-requests/person", params={"q": target.kuid}, headers=headers).status_code == 403
        assert client.post(f"/v1/admin/data-requests/{target.user_id}/export",
                           json={"received_via": "phone"}, headers=headers).status_code == 403
        assert client.post(f"/v1/admin/data-requests/{target.user_id}/erase",
                           json={"received_via": "phone", "note": "x", "current_password": "x"},
                           headers=headers).status_code == 403
    assert client.get("/v1/admin/data-requests/person").status_code == 401
