"""What the administrator console reads: overview, users and roles, clubs, the audit log.

Super administrator only (clubs: whoever holds club.approve, which is the same person
today). The audit log is read-only through this door and every other.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from datetime import timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from kafriada.clock import today_in_nigeria
from kafriada.contexts.access import service as access
from kafriada.contexts.payments import service as payments
from kafriada.contexts.payments.provider import FakeProvider
from kafriada.contexts.payments.settlement import settle_charge
from kafriada.main import create_app
from tests._access_helpers import bearer, make_user, sql
from tests._media_helpers import LGA, athlete_with_files, pay, reviewer, use_local_store
from tests._payment_helpers import PRICE, charge_success_event, new_athlete, pending_payment

pytestmark = [
    pytest.mark.db,
    pytest.mark.skipif(
        not (os.environ.get("DATABASE_URL_APP") and os.environ.get("DATABASE_URL_MONEY")),
        reason="needs DATABASE_URL_APP and DATABASE_URL_MONEY",
    ),
]


@pytest.fixture(scope="module")
def client() -> Iterator[TestClient]:
    with TestClient(create_app()) as c:
        yield c


@pytest.fixture(scope="module")
def root() -> dict[str, str]:
    uid, _ = make_user("Console admin", grants=[("super_admin", "global", None)])
    return bearer(access.issue_session(uid, method="test").token)


@pytest.fixture(autouse=True)
def _store(monkeypatch: pytest.MonkeyPatch, tmp_path):  # type: ignore[no-untyped-def]
    return use_local_store(monkeypatch, tmp_path)


# -- who may look ---------------------------------------------------------------
READS = ("/v1/admin/overview", "/v1/admin/users", "/v1/admin/roles", "/v1/admin/clubs", "/v1/admin/audit")


def test_only_a_super_administrator_can_read_any_of_it(client: TestClient, root: dict[str, str]) -> None:
    state_id, _ = make_user("State", grants=[("state_coordinator", "state", "NG-JG")])
    others = [
        new_athlete("Plain").headers,
        reviewer(LGA).headers,
        bearer(access.issue_session(state_id, method="test").token),  # holds admin.read_audit, scoped
    ]
    for path in READS:
        assert client.get(path, headers=root).status_code == 200, path
        assert client.get(path).status_code == 401, path
        for headers in others:
            assert client.get(path, headers=headers).status_code == 403, path


def test_the_audit_log_has_no_way_to_change_it(client: TestClient, root: dict[str, str]) -> None:
    for method in ("post", "put", "patch", "delete"):
        got = getattr(client, method)("/v1/admin/audit", headers=root)
        assert got.status_code == 405, method


# -- ADM-01 ---------------------------------------------------------------------
def test_the_overview_moves_with_the_money_and_the_ledger_check(
    client: TestClient, root: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    before = client.get("/v1/admin/overview", headers=root).json()
    athlete = athlete_with_files(client, "Counted money")
    pay(athlete)
    after = client.get("/v1/admin/overview", headers=root).json()
    assert after["registered"] == before["registered"] + 1
    assert after["paid"] == before["paid"] + 1
    assert after["payments"] == before["payments"] + 1
    assert after["collected_kobo"] == before["collected_kobo"] + PRICE

    provider = FakeProvider()
    monkeypatch.setattr(payments, "build_provider", lambda _settings=None: provider)
    ref = pending_payment(new_athlete("Frozen"))
    assert settle_charge(charge_success_event(ref, amount_kobo=1_000)).outcome.value == "frozen"
    frozen = client.get("/v1/admin/overview", headers=root).json()
    assert frozen["unresolved"] == after["unresolved"] + 1

    sql("INSERT INTO ops.job_runs (job, started_at, ok, summary) VALUES ('integrity', now(), false, '{}')")
    assert client.get("/v1/admin/overview", headers=root).json()["ledger_ok"] is False
    sql("INSERT INTO ops.job_runs (job, started_at, ok, summary) VALUES ('integrity', now(), true, '{}')")
    seen = client.get("/v1/admin/overview", headers=root).json()
    assert seen["ledger_ok"] is True and seen["ledger_checked_at"] is not None
    assert isinstance(seen["conversion_percent"], float) and seen["live_lgas"] >= 1


# -- ADM-02 ---------------------------------------------------------------------
def make_named(tag: str, name: str, *grants):  # type: ignore[no-untyped-def]
    return make_user(f"{tag} {name}", grants=list(grants))


def test_people_are_found_by_name_phone_and_id_with_their_roles_and_no_full_number(
    client: TestClient, root: dict[str, str]
) -> None:
    tag = f"Dir{uuid4().hex[:6]}"
    coordinator, phone = make_named(tag, "Coordinator", ("lga_coordinator", "lga", LGA))
    athlete = new_athlete(tag)

    by_name = client.get("/v1/admin/users", params={"q": tag.lower()}, headers=root)
    names = {u["user_id"]: u for u in by_name.json()["users"]}
    assert str(coordinator) in names and str(athlete.user_id) in names
    row = names[str(coordinator)]
    assert [(r["role"], r["scope_kind"], r["scope_name"]) for r in row["roles"]] == [
        ("lga_coordinator", "lga", "Birnin Kudu")
    ]
    assert phone not in by_name.text and row["phone_masked"] != phone

    assert [u["user_id"] for u in client.get("/v1/admin/users", params={"q": phone}, headers=root).json()["users"]] == [str(coordinator)]
    by_id = client.get("/v1/admin/users", params={"q": athlete.kuid}, headers=root).json()["users"]
    assert [u["user_id"] for u in by_id] == [str(athlete.user_id)] and by_id[0]["kuid"] == athlete.kuid
    only = client.get("/v1/admin/users", params={"q": tag, "role": "lga_coordinator"}, headers=root).json()["users"]
    assert [u["user_id"] for u in only] == [str(coordinator)]
    assert client.get("/v1/admin/users", params={"q": "%%"}, headers=root).json()["users"] == []


def test_a_person_shows_when_they_were_last_seen_and_erased_people_do_not_show(
    client: TestClient, root: dict[str, str]
) -> None:
    tag = f"Seen{uuid4().hex[:6]}"
    seen, _ = make_named(tag, "Seen")
    gone, _ = make_named(tag, "Gone")
    access.issue_session(seen, method="test")  # type: ignore[arg-type]
    sql("UPDATE ops.users SET anonymised_at = now() WHERE id = :u", u=gone)
    rows = {u["user_id"]: u for u in client.get("/v1/admin/users", params={"q": tag}, headers=root).json()["users"]}
    assert str(gone) not in rows and rows[str(seen)]["last_seen"] is not None
    assert client.get(f"/v1/admin/users/{gone}", headers=root).status_code == 404
    assert client.get(f"/v1/admin/users/{seen}", headers=root).json()["user_id"] == str(seen)
    assert client.get(f"/v1/admin/users/{uuid4()}", headers=root).status_code == 404


def test_people_are_paged(client: TestClient, root: dict[str, str]) -> None:
    tag = f"Page{uuid4().hex[:6]}"
    for i in range(27):
        make_named(tag, f"{i:02d}")
    first = client.get("/v1/admin/users", params={"q": tag}, headers=root).json()
    second = client.get("/v1/admin/users", params={"q": tag, "page": 2}, headers=root).json()
    assert len(first["users"]) == 25 and first["has_more"] is True
    assert len(second["users"]) == 2 and second["has_more"] is False


def test_the_grantable_roles_say_what_each_is_scoped_to(client: TestClient, root: dict[str, str]) -> None:
    kinds = {r["code"]: r["scope_kind"] for r in client.get("/v1/admin/roles", headers=root).json()}
    assert kinds["super_admin"] == "global" and kinds["lga_coordinator"] == "lga" and kinds["club_admin"] == "club"


# -- clubs ----------------------------------------------------------------------
def test_clubs_awaiting_approval_come_first_and_can_be_filtered(client: TestClient, root: dict[str, str]) -> None:
    founder = new_athlete("Waiting founder")
    made = client.post(
        "/v1/clubs", headers=founder.headers,
        json={"name": f"Queue FC {uuid4().hex[:6]}", "sport": "Football", "lga_id": LGA, "contact_phone": "08031234567"},
    )
    club = str(made.json()["club_id"])
    listing = client.get("/v1/admin/clubs", headers=root).json()["clubs"]
    assert listing[0]["status"] == "pending_review"
    mine = next(c for c in listing if c["club_id"] == club)
    assert mine["representative"].startswith("Waiting founder") and mine["lga_name"] == "Birnin Kudu"
    assert client.post(f"/v1/admin/clubs/{club}/approve", headers=root).status_code == 204
    pending = client.get("/v1/admin/clubs", params={"status": "pending_review"}, headers=root).json()["clubs"]
    assert club not in [c["club_id"] for c in pending]
    approved = client.get("/v1/admin/clubs", params={"status": "approved"}, headers=root).json()["clubs"]
    assert club in [c["club_id"] for c in approved]


# -- ADM-06 ---------------------------------------------------------------------
def test_the_audit_log_shows_who_did_what_and_filters(client: TestClient, root: dict[str, str]) -> None:
    founder = new_athlete("Audited founder")
    club = str(client.post(
        "/v1/clubs", headers=founder.headers,
        json={"name": f"Audit FC {uuid4().hex[:6]}", "sport": "Football", "lga_id": LGA, "contact_phone": "08031234567"},
    ).json()["club_id"])
    client.post(f"/v1/admin/clubs/{club}/approve", headers=root)

    everything = client.get("/v1/admin/audit", headers=root).json()
    assert everything["entries"][0]["entry_id"] > everything["entries"][-1]["entry_id"]  # newest first
    approved = client.get("/v1/admin/audit", params={"action": "club.approved"}, headers=root).json()["entries"]
    hit = next(e for e in approved if e["subject_id"] == club)
    assert hit["actor"].startswith("Console admin")
    by_actor = client.get("/v1/admin/audit", params={"actor": "Audited founder"}, headers=root).json()["entries"]
    assert by_actor and all("Audited founder" in e["actor"] for e in by_actor)
    assert any(e["action"] == "club.registered" and e["subject_id"] == club for e in by_actor)

    today = today_in_nigeria()
    assert client.get("/v1/admin/audit", params={"since": str(today - timedelta(days=1))}, headers=root).json()["entries"]
    assert client.get("/v1/admin/audit", params={"until": "2001-01-01"}, headers=root).json()["entries"] == []
    assert client.get("/v1/admin/audit", params={"action": "%%"}, headers=root).json()["entries"] == []
    assert client.get("/v1/admin/audit", params={"since": "not-a-date"}, headers=root).status_code == 422


def test_the_audit_log_is_paged(client: TestClient, root: dict[str, str]) -> None:
    first = client.get("/v1/admin/audit", headers=root).json()
    second = client.get("/v1/admin/audit", params={"page": 2}, headers=root).json()
    assert len(first["entries"]) == 50 and first["has_more"] is True
    assert not {e["entry_id"] for e in first["entries"]} & {e["entry_id"] for e in second["entries"]}
