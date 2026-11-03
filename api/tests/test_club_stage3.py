"""Club stage three (GDOC 5.10): links, photos, the ordinary payment path, a reviewer.

What must hold: only a stage-two club can start; nothing is paid for or reviewed without
a link and a re-encoded photo; the price is ours; only a reviewer decides; approval makes
the club stage three and raises its player limit to 70; a club only ever touches its own
photos. Also here, because stage three shares its cause: a representative who signed the
club up without an athlete account can upload the stage-two document.
"""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from kafriada.contexts.access import service as access
from kafriada.contexts.payments import service as payments
from kafriada.contexts.payments.provider import FakeProvider
from kafriada.contexts.payments.settlement import settle_charge
from kafriada.main import create_app
from kafriada.settings import get_settings
from tests._access_helpers import audit_actions, bearer, make_user, sql
from tests._club_helpers import Rep, sign_up_club
from tests._media_helpers import make_jpeg, use_local_store
from tests._payment_helpers import charge_success_event

pytestmark = [
    pytest.mark.db,
    pytest.mark.skipif(
        not (os.environ.get("DATABASE_URL_APP") and os.environ.get("DATABASE_URL_MONEY")),
        reason="needs DATABASE_URL_APP and DATABASE_URL_MONEY",
    ),
]

STAGE3_PRICE = get_settings().price_club_stage3_kobo


@pytest.fixture(scope="module")
def client() -> Iterator[TestClient]:
    with TestClient(create_app()) as c:
        yield c


@pytest.fixture(scope="module")
def root() -> dict[str, str]:
    uid, _ = make_user("Stage three reviewer", grants=[("super_admin", "global", None)])
    return bearer(access.issue_session(uid, method="test").token)


@pytest.fixture(autouse=True)
def _store(monkeypatch: pytest.MonkeyPatch, tmp_path):  # type: ignore[no-untyped-def]
    from kafriada.api.v1 import club_stage3, club_verification
    from kafriada.contexts.clubs import stage3

    store = use_local_store(monkeypatch, tmp_path)
    for module in (club_stage3, club_verification):
        monkeypatch.setattr(module, "build_store", lambda _settings=None: store)
    monkeypatch.setattr(stage3, "_build_store", lambda _settings=None: store)
    return store


@pytest.fixture
def fake(monkeypatch: pytest.MonkeyPatch) -> FakeProvider:
    provider = FakeProvider()
    monkeypatch.setattr(payments, "build_provider", lambda _settings=None: provider)
    return provider


def stage_two_club(client: TestClient, root: dict[str, str]) -> tuple[Rep, str]:
    rep, club = sign_up_club(client, root)
    sql("UPDATE identity.organizations SET stage = 2 WHERE id = :c", c=club)
    return rep, club


def add_photo(client: TestClient, rep: Rep, club: str, data: bytes | None = None):  # type: ignore[no-untyped-def]
    data = data if data is not None else make_jpeg((800, 600), gps=True)
    slot = client.post(
        f"/v1/clubs/{club}/stage-three/photos", headers=rep.headers,
        json={"content_type": "image/jpeg", "size_bytes": len(data)},
    )
    if slot.status_code != 201:
        return slot
    media_id = slot.json()["media_id"]
    put = client.put(f"/v1/clubs/{club}/stage-three/photos/{media_id}/content", content=data, headers=rep.headers)
    assert put.status_code == 204, put.text
    return client.post(f"/v1/clubs/{club}/stage-three/photos/{media_id}/confirm", headers=rep.headers)


def links(client: TestClient, rep: Rep, club: str, *values: str):  # type: ignore[no-untyped-def]
    return client.put(f"/v1/clubs/{club}/stage-three/links", headers=rep.headers, json={"links": list(values)})


def ready(client: TestClient, root: dict[str, str]) -> tuple[Rep, str]:
    rep, club = stage_two_club(client, root)
    assert links(client, rep, club, "https://example.com/club").status_code == 204
    assert add_photo(client, rep, club).status_code == 204
    return rep, club


def pay(client: TestClient, rep: Rep, club: str) -> None:
    started = client.post(f"/v1/clubs/{club}/stage-three/payment", headers=rep.headers)
    assert started.status_code == 201, started.text
    assert started.json()["amount_kobo"] == STAGE3_PRICE
    reference = started.json()["reference"]
    assert settle_charge(charge_success_event(reference, amount_kobo=STAGE3_PRICE)).outcome.value == "settled"


def overview(client: TestClient, rep: Rep, club: str) -> dict[str, object]:
    got = client.get(f"/v1/clubs/{club}/stage-three", headers=rep.headers)
    assert got.status_code == 200, got.text
    return got.json()  # type: ignore[no-any-return]


def test_a_representative_without_an_athlete_account_can_send_the_stage_two_document(
    client: TestClient, root: dict[str, str]
) -> None:
    rep, club = sign_up_club(client, root)
    assert sql("SELECT 1 FROM identity.athletes WHERE user_id = :u", u=rep.user_id) == []
    data = make_jpeg((600, 400), gps=False)
    slot = client.post(f"/v1/clubs/{club}/verification/uploads", headers=rep.headers,
                       json={"content_type": "image/jpeg", "size_bytes": len(data)})
    assert slot.status_code == 201, slot.text
    media_id = slot.json()["media_id"]
    assert client.put(f"/v1/clubs/{club}/verification/uploads/{media_id}/content",
                      content=data, headers=rep.headers).status_code == 204
    assert client.post(f"/v1/clubs/{club}/verification/uploads/{media_id}/confirm",
                       headers=rep.headers).status_code == 204
    assert sql("SELECT org_id::text AS org, athlete_id FROM identity.media_files WHERE id = :m",
               m=media_id) == [{"org": club, "athlete_id": None}]


def test_only_a_stage_two_club_can_start(client: TestClient, root: dict[str, str]) -> None:
    rep, club = sign_up_club(client, root)
    refused = links(client, rep, club, "https://example.com/club")
    assert refused.status_code == 409
    assert overview(client, rep, club)["state"] == "none"


def test_links_must_be_web_addresses_and_at_most_five(client: TestClient, root: dict[str, str]) -> None:
    rep, club = stage_two_club(client, root)
    assert links(client, rep, club).status_code == 422
    assert links(client, rep, club, "facebook dot com").status_code == 422
    assert links(client, rep, club, *[f"https://example.com/{i}" for i in range(6)]).status_code == 422
    assert links(client, rep, club, "https://facebook.com/club", "https://example.com").status_code == 204
    assert overview(client, rep, club)["links"] == ["https://facebook.com/club", "https://example.com"]


def test_paying_needs_a_link_and_a_photo_and_writes_no_payment_until_then(
    client: TestClient, root: dict[str, str], fake: FakeProvider
) -> None:
    rep, club = stage_two_club(client, root)
    assert links(client, rep, club, "https://example.com/club").status_code == 204
    assert client.post(f"/v1/clubs/{club}/stage-three/payment", headers=rep.headers).status_code == 409
    assert sql("SELECT 1 FROM money.payments WHERE org_id = :c", c=club) == []


def test_a_photo_is_re_encoded_without_its_location(client: TestClient, root: dict[str, str]) -> None:
    rep, club = ready(client, root)
    (photo,) = overview(client, rep, club)["photos"]  # type: ignore[misc]
    assert photo["status"] == "ready"
    got = client.get(f"/v1/clubs/{club}/stage-three/photos/{photo['media_id']}", headers=rep.headers)
    assert got.status_code == 200 and got.content[:2] == b"\xff\xd8"
    assert b"GPS" not in got.content


def test_a_club_cannot_see_or_remove_another_clubs_photo(client: TestClient, root: dict[str, str]) -> None:
    rep, club = ready(client, root)
    (photo,) = overview(client, rep, club)["photos"]  # type: ignore[misc]
    other, other_club = stage_two_club(client, root)
    path = f"/v1/clubs/{other_club}/stage-three/photos/{photo['media_id']}"
    assert client.get(path, headers=other.headers).status_code == 404
    assert client.delete(path, headers=other.headers).status_code == 404
    assert client.get(f"/v1/clubs/{club}/stage-three/photos/{photo['media_id']}",
                      headers=other.headers).status_code == 403


def test_a_photo_can_be_removed_while_the_request_is_a_draft(client: TestClient, root: dict[str, str]) -> None:
    rep, club = ready(client, root)
    (photo,) = overview(client, rep, club)["photos"]  # type: ignore[misc]
    assert client.delete(f"/v1/clubs/{club}/stage-three/photos/{photo['media_id']}",
                         headers=rep.headers).status_code == 204
    assert overview(client, rep, club)["photos"] == []


def test_approval_makes_the_club_stage_three_with_room_for_seventy(
    client: TestClient, root: dict[str, str], fake: FakeProvider
) -> None:
    rep, club = ready(client, root)
    pay(client, rep, club)
    assert overview(client, rep, club)["state"] == "under_review"
    # Nothing can change while it is being reviewed.
    assert links(client, rep, club, "https://example.com/other").status_code == 409
    assert add_photo(client, rep, club).status_code == 409

    assert club in [i["club_id"] for i in client.get("/v1/admin/club-stage-three/queue", headers=root).json()]
    seen = client.get(f"/v1/admin/club-stage-three/{club}", headers=root).json()
    photo = seen["photos"][0]["media_id"]
    assert client.get(f"/v1/admin/club-stage-three/{club}/photos/{photo}", headers=root).status_code == 200
    assert client.post(f"/v1/admin/club-stage-three/{club}/approve", headers=rep.headers).status_code == 403

    assert client.post(f"/v1/admin/club-stage-three/{club}/approve", headers=root).status_code == 204
    dash = client.get(f"/v1/clubs/{club}", headers=rep.headers).json()
    assert (dash["stage"], dash["player_limit"], dash["verified"]) == (3, 70, True)
    assert "club_stage3.approved" in audit_actions(club)
    assert client.post(f"/v1/admin/club-stage-three/{club}/approve", headers=root).status_code == 409
    assert client.post(f"/v1/clubs/{club}/stage-three/payment", headers=rep.headers).status_code == 409


def test_a_rejection_needs_a_reason_and_goes_back_without_paying_again(
    client: TestClient, root: dict[str, str], fake: FakeProvider
) -> None:
    rep, club = ready(client, root)
    pay(client, rep, club)
    reject = f"/v1/admin/club-stage-three/{club}/reject"
    assert client.post(reject, headers=root, json={"reason": "  "}).status_code == 422
    assert client.post(reject, headers=root, json={"reason": "The photos are not of the club."}).status_code == 204
    seen = overview(client, rep, club)
    assert (seen["state"], seen["reason"]) == ("rejected", "The photos are not of the club.")

    assert add_photo(client, rep, club).status_code == 204
    assert client.post(f"/v1/clubs/{club}/stage-three/resubmit", headers=rep.headers).status_code == 204
    assert overview(client, rep, club)["state"] == "under_review"
    assert len(sql("SELECT 1 FROM money.payments WHERE org_id = :c AND purpose = 'stage3_org'", c=club)) == 1


def test_a_club_at_its_limit_cannot_invite_more_players(client: TestClient, root: dict[str, str]) -> None:
    from kafriada.contexts.clubs import service as clubs

    rep, club = sign_up_club(client, root)
    dash = client.get(f"/v1/clubs/{club}", headers=rep.headers).json()
    assert (dash["stage"], dash["player_limit"]) == (1, 50)
    original = clubs.PLAYER_LIMITS[1]
    clubs.PLAYER_LIMITS[1] = 0
    try:
        got = client.post(f"/v1/clubs/{club}/invitations", headers=rep.headers,
                          json={"kuid": "KA-NG-JG-BKD-2026-000001"})
    finally:
        clubs.PLAYER_LIMITS[1] = original
    assert got.status_code == 409, got.text
    assert "limit" in got.json()["error"]["message"]["message"]
