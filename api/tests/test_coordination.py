"""The coordinator's dashboard (CRD-01) and finding an athlete (CRD-03).

What must hold: everything is bounded by the LGA in the path, an athlete elsewhere is
simply not found (never "not permitted"), and the cash total is the caller's own.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from kafriada.contexts.access import service as access
from kafriada.contexts.coordination import service as coordination
from kafriada.contexts.payments import service as payments
from kafriada.contexts.payments.provider import FakeProvider
from kafriada.contexts.payments.settlement import settle_charge
from kafriada.main import create_app
from tests._access_helpers import bearer, make_user, sql
from tests._media_helpers import LGA, OTHER_LGA, athlete_with_files, pay, reviewer, use_local_store
from tests._payment_helpers import PRICE, charge_success_event, new_athlete

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


@pytest.fixture(autouse=True)
def _store(monkeypatch: pytest.MonkeyPatch, tmp_path):  # type: ignore[no-untyped-def]
    return use_local_store(monkeypatch, tmp_path)


def dash(client: TestClient, who, lga: str = LGA):  # type: ignore[no-untyped-def]
    return client.get(f"/v1/lgas/{lga}/dashboard", headers=who.headers)


def find(client: TestClient, who, q: str, *, page: int = 1, lga: str = LGA):  # type: ignore[no-untyped-def]
    return client.get(f"/v1/lgas/{lga}/athlete-search", params={"q": q, "page": page}, headers=who.headers)


def phone_of(athlete) -> str:  # type: ignore[no-untyped-def]
    return str(sql("SELECT phone_e164 FROM ops.users WHERE id = :u", u=athlete.user_id)[0]["phone_e164"])


# -- CRD-01 --------------------------------------------------------------------
def test_the_numbers_move_with_the_register(client: TestClient) -> None:
    coordinator = reviewer(LGA)
    before = dash(client, coordinator).json()
    assert before["lga_name"] == "Birnin Kudu"

    athlete = athlete_with_files(client, "Counted")
    registered = dash(client, coordinator).json()
    assert registered["registered"] == before["registered"] + 1
    assert registered["to_review"] == before["to_review"]

    pay(athlete)
    after = dash(client, coordinator).json()
    assert after["paid"] == before["paid"] + 1
    assert after["to_review"] == before["to_review"] + 1
    assert isinstance(after["oldest_waiting_hours"], int) and after["oldest_waiting_hours"] >= 0


def test_a_coordinator_never_counts_their_own_record_as_waiting(client: TestClient) -> None:
    other = reviewer(LGA)
    own = athlete_with_files(client, "Own record")
    pay(own)
    sql(
        "INSERT INTO ops.user_roles (user_id, role_code, scope_kind, scope_id, reason) "
        "VALUES (:u, 'lga_coordinator', 'lga', :l, 'test')", u=own.user_id, l=LGA,
    )
    others_waiting = sql(
        "SELECT count(*) AS n FROM identity.verification_requests v JOIN identity.athletes a ON a.id = v.athlete_id "
        "JOIN identity.media_files pm ON pm.id = v.photo_media_id AND pm.status = 'ready' "
        "JOIN identity.media_files dm ON dm.id = v.document_media_id AND dm.status = 'ready' "
        "WHERE v.status = 'under_review' AND a.current_lga_id = :l AND a.user_id <> :u", l=LGA, u=own.user_id,
    )[0]["n"]
    assert dash(client, own).json()["to_review"] == others_waiting
    assert dash(client, other).json()["to_review"] == others_waiting + 1


def test_the_cash_total_is_the_callers_own_and_the_cap_shows(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    provider = FakeProvider()
    monkeypatch.setattr(payments, "build_provider", lambda _settings=None: provider)
    coordinator, other = reviewer(LGA), reviewer(LGA)
    start = dash(client, coordinator).json()
    assert (start["collected_kobo"], start["collected_count"], start["can_assist"], start["cap_reached"]) == (
        0, 0, True, False,
    )

    athlete = athlete_with_files(client, "Cash")
    started = client.post(
        f"/v1/lgas/{LGA}/athletes/{athlete.kuid}/payments", json={"purpose": "stage2_athlete"},
        headers=coordinator.headers,
    )
    assert started.status_code == 201, started.text
    # Started but not paid: it counts against the cap, not as cash collected.
    mid = dash(client, coordinator).json()
    assert (mid["collected_kobo"], mid["collected_count"]) == (0, 0)

    assert settle_charge(charge_success_event(started.json()["reference"])).outcome.value == "settled"
    done = dash(client, coordinator).json()
    assert (done["collected_kobo"], done["collected_count"]) == (PRICE, 1)
    assert dash(client, other).json()["collected_kobo"] == 0

    capped = coordination.get_settings().model_copy(update={"assisted_payments_per_coordinator_daily": 1})
    monkeypatch.setattr(coordination, "get_settings", lambda: capped)
    assert dash(client, coordinator).json()["cap_reached"] is True
    assert dash(client, other).json()["cap_reached"] is False


# -- who may look ---------------------------------------------------------------
def test_scope_covers_own_lga_and_its_state_and_nothing_else(client: TestClient) -> None:
    mine, elsewhere = reviewer(LGA), reviewer(OTHER_LGA)
    state_id, _ = make_user("State", grants=[("state_coordinator", "state", "NG-JG")])
    state = access.issue_session(state_id, method="test").token
    root_id, _ = make_user("Root", grants=[("super_admin", "global", None)])
    root = access.issue_session(root_id, method="test").token
    plain = new_athlete("Plain")

    for path in (f"/v1/lgas/{LGA}/dashboard", f"/v1/lgas/{LGA}/athlete-search?q=ab"):
        assert client.get(path, headers=mine.headers).status_code == 200
        assert client.get(path, headers=bearer(state)).status_code == 200
        assert client.get(path, headers=bearer(root)).status_code == 200
        assert client.get(path, headers=elsewhere.headers).status_code == 403
        assert client.get(path, headers=plain.headers).status_code == 403
        assert client.get(path).status_code == 401
    assert client.get("/v1/lgas/NG-JG-NOPE/dashboard", headers=bearer(root)).status_code == 404


# -- CRD-03 ---------------------------------------------------------------------
def test_an_athlete_is_found_by_name_id_and_phone_and_nothing_private_comes_back(client: TestClient) -> None:
    coordinator = reviewer(LGA)
    tag = f"Findme{uuid4().hex[:6]}"
    athlete = new_athlete(tag)
    phone = phone_of(athlete)

    by_name = find(client, coordinator, tag.upper()).json()["people"]
    assert [p["kuid"] for p in by_name] == [athlete.kuid]
    assert find(client, coordinator, tag[2:8]).json()["people"][0]["kuid"] == athlete.kuid  # partial
    assert [p["kuid"] for p in find(client, coordinator, athlete.kuid.lower()).json()["people"]] == [athlete.kuid]
    serial = athlete.kuid.rsplit("-", 1)[1]
    assert athlete.kuid in [p["kuid"] for p in find(client, coordinator, f"2026-{serial}").json()["people"]]
    assert [p["kuid"] for p in find(client, coordinator, phone).json()["people"]] == [athlete.kuid]
    raw = find(client, coordinator, tag)
    assert phone not in raw.text and "date_of_birth" not in raw.text
    assert set(raw.json()["people"][0]) == {"kuid", "full_name", "playing_position", "verified"}


def test_short_queries_and_wildcards_match_nothing(client: TestClient) -> None:
    coordinator = reviewer(LGA)
    new_athlete("Anyone")
    for q in ("", " ", "a", "%%", "__", "%"):
        got = find(client, coordinator, q)
        assert got.status_code == 200 and got.json()["people"] == [], q


def test_an_athlete_in_another_lga_is_indistinguishable_from_no_one(client: TestClient) -> None:
    coordinator = reviewer(LGA)
    tag = f"Moved{uuid4().hex[:6]}"
    athlete = new_athlete(tag)
    assert [p["kuid"] for p in find(client, coordinator, tag).json()["people"]] == [athlete.kuid]
    sql("UPDATE identity.athletes SET current_lga_id = :l WHERE user_id = :u", l=OTHER_LGA, u=athlete.user_id)

    gone = find(client, coordinator, tag)
    nobody = find(client, coordinator, f"Nobody{uuid4().hex[:6]}")
    assert gone.status_code == nobody.status_code == 200
    assert gone.json() == nobody.json() == {"people": [], "page": 1, "has_more": False}
    assert find(client, coordinator, athlete.kuid).json()["people"] == []
    assert find(client, coordinator, phone_of(athlete)).json()["people"] == []
    # And it is found by the coordinator whose LGA it now is.
    there = reviewer(OTHER_LGA)
    assert [p["kuid"] for p in find(client, there, tag, lga=OTHER_LGA).json()["people"]] == [athlete.kuid]


def test_results_are_paged_with_a_plain_next_flag(client: TestClient) -> None:
    coordinator = reviewer(LGA)
    tag = f"Pg{uuid4().hex[:6]}"
    for i in range(coordination.PAGE_SIZE + 2):
        new_athlete(f"{tag} {i:02d}")
    first = find(client, coordinator, tag).json()
    second = find(client, coordinator, tag, page=2).json()
    assert len(first["people"]) == coordination.PAGE_SIZE and first["has_more"] is True
    assert len(second["people"]) == 2 and second["has_more"] is False
    assert not {p["kuid"] for p in first["people"]} & {p["kuid"] for p in second["people"]}
    assert find(client, coordinator, tag, page=99).json()["people"] == []
