"""LGA rollout (ADM-05).

What must hold: opening an LGA lets people register there and closing it stops them,
for real, in the service; either needs a reason and the administrator's password and
leaves an audit row; only a super administrator gets in. Uses an LGA no other test
touches, and puts it back the way it found it.
"""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from kafriada.contexts.access import service as access
from kafriada.contexts.identity import service as identity
from kafriada.main import create_app
from tests._access_helpers import bearer, make_user, new_phone, sql
from tests._media_helpers import LGA, reviewer
from tests._payment_helpers import new_athlete
from tests._registration import registration

pytestmark = [
    pytest.mark.db,
    pytest.mark.skipif(not os.environ.get("DATABASE_URL_APP"), reason="needs DATABASE_URL_APP"),
]

SPARE = "NG-JG-YAN"
PASSWORD = "a long admin phrase 42"


@pytest.fixture(scope="module")
def client() -> Iterator[TestClient]:
    with TestClient(create_app()) as c:
        yield c


@pytest.fixture(scope="module")
def root() -> dict[str, str]:
    uid, _ = make_user("Rollout admin", password=PASSWORD, grants=[("super_admin", "global", None)])
    return bearer(access.issue_session(uid, method="test").token)


@pytest.fixture(autouse=True)
def _spare_closed() -> Iterator[None]:
    sql("UPDATE ops.locations SET is_live = false WHERE id = :id", id=SPARE)
    yield
    sql("UPDATE ops.locations SET is_live = false WHERE id = :id", id=SPARE)


def toggle(client: TestClient, who: dict[str, str], open_: bool, **overrides: object):  # type: ignore[no-untyped-def]
    body = {"open": open_, "reason": "Wave 4 launch", "current_password": PASSWORD, **overrides}
    return client.post(f"/v1/admin/lgas/{SPARE}/rollout", json=body, headers=who)


def registers_in_spare() -> bool:
    try:
        identity.register(registration(new_phone(), "Rollout Test", lga_id=SPARE, town="Yankwashi"))
    except identity.RegistrationError as exc:
        assert exc.field == "lga_id"
        return False
    return True


def test_every_lga_is_listed_with_its_wave_and_state(client: TestClient, root: dict[str, str]) -> None:
    got = client.get("/v1/admin/lgas", headers=root).json()
    assert len(got) == 27
    by_id = {x["id"]: x for x in got}
    assert by_id["NG-JG-BKD"]["is_open"] is True and by_id["NG-JG-BKD"]["wave"] == 1
    assert by_id[SPARE]["is_open"] is False
    assert [x["wave"] for x in got] == sorted(x["wave"] for x in got)


def test_opening_lets_people_register_and_closing_stops_them(client: TestClient, root: dict[str, str]) -> None:
    assert not registers_in_spare()

    opened = toggle(client, root, True)
    assert opened.status_code == 200, opened.text
    assert opened.json()["is_open"] is True and opened.json()["went_live_at"]
    assert registers_in_spare()
    first_opened = opened.json()["went_live_at"]

    closed = toggle(client, root, False, reason="Coordinator unavailable")
    assert closed.status_code == 200 and closed.json()["is_open"] is False
    assert closed.json()["registered"] >= 1, "closing never removes anyone already registered"
    assert not registers_in_spare()

    again = toggle(client, root, True, reason="Back on")
    assert again.json()["went_live_at"] == first_opened, "went_live_at keeps the first opening"

    actions = [r["action"] for r in sql(
        "SELECT action FROM ops.audit_log WHERE subject_type = 'location' AND subject_id = :id "
        "ORDER BY id DESC LIMIT 3", id=SPARE,
    )]
    assert actions == ["rollout.lga_opened", "rollout.lga_closed", "rollout.lga_opened"]


def test_a_wrong_password_or_no_reason_changes_nothing(client: TestClient, root: dict[str, str]) -> None:
    wrong = toggle(client, root, True, current_password="not it")
    assert wrong.status_code == 422 and wrong.json()["error"]["message"]["field"] == "current_password"
    blank = toggle(client, root, True, reason="   ")
    assert blank.status_code == 422 and blank.json()["error"]["message"]["field"] == "reason"
    assert sql("SELECT is_live FROM ops.locations WHERE id = :id", id=SPARE)[0]["is_live"] is False


def test_asking_for_the_state_it_is_already_in_is_refused(client: TestClient, root: dict[str, str]) -> None:
    got = toggle(client, root, False)
    assert got.status_code == 409


def test_only_a_super_administrator_gets_in(client: TestClient) -> None:
    state_id, _ = make_user("State", grants=[("state_coordinator", "state", "NG-JG")])
    others = [
        new_athlete("Plain").headers,
        reviewer(LGA).headers,
        bearer(access.issue_session(state_id, method="test").token),
    ]
    for headers in others:
        assert client.get("/v1/admin/lgas", headers=headers).status_code == 403
        assert toggle(client, headers, True).status_code == 403
    assert client.get("/v1/admin/lgas").status_code == 401
