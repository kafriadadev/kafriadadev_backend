"""Bulk QR card printing (CRD-06).

What must hold: everything is bounded by the LGA in the path, "not yet printed" follows
what was actually marked, a batch is paged rather than built whole, and a print record is
evidence that nobody can edit.
"""

from __future__ import annotations

import os
import re
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from kafriada.clock import today_in_nigeria
from kafriada.contexts.access import service as access
from kafriada.contexts.coordination import cards
from kafriada.main import create_app
from tests._access_helpers import audit_actions, bearer, make_user, sql
from tests._media_helpers import LGA, OTHER_LGA, reviewer
from tests._payment_helpers import new_athlete

pytestmark = [
    pytest.mark.db,
    pytest.mark.skipif(not os.environ.get("DATABASE_URL_APP"), reason="needs DATABASE_URL_APP"),
]


@pytest.fixture(scope="module")
def client() -> Iterator[TestClient]:
    with TestClient(create_app()) as c:
        yield c


TODAY = today_in_nigeria().isoformat()


def listing(client: TestClient, who, *, lga: str = LGA, **params):  # type: ignore[no-untyped-def]
    return client.get(f"/v1/lgas/{lga}/cards", params={"since": TODAY, "until": TODAY, **params}, headers=who.headers)


def kuids(response) -> list[str]:  # type: ignore[no-untyped-def]
    return [p["kuid"] for p in response.json()["people"]]


def mark(client: TestClient, who, ks: list[str], *, lga: str = LGA):  # type: ignore[no-untyped-def]
    return client.post(f"/v1/lgas/{lga}/cards/printed", json={"kuids": ks}, headers=who.headers)


def test_unprinted_athletes_of_the_lga_are_listed_with_the_sheet_maths(client: TestClient) -> None:
    coordinator = reviewer(LGA)
    a, b = new_athlete("Card A"), new_athlete("Card B")
    got = listing(client, coordinator)
    assert got.status_code == 200, got.text
    body = got.json()
    assert {a.kuid, b.kuid} <= set(kuids(got)) or body["pages"] > 1
    assert body["per_sheet"] == 8 and body["total"] >= 2 and body["pages"] >= 1
    assert all(p["printed"] is False for p in body["people"])


def test_the_date_window_narrows_the_batch(client: TestClient) -> None:
    coordinator = reviewer(LGA)
    new_athlete("Windowed")
    assert listing(client, coordinator, since="2001-01-01", until="2001-12-31").json()["total"] == 0
    everything = client.get(f"/v1/lgas/{LGA}/cards", params={"unprinted": False}, headers=coordinator.headers).json()
    today_only = listing(client, coordinator, unprinted=False).json()
    assert 0 < today_only["total"] <= everything["total"]
    assert client.get(f"/v1/lgas/{LGA}/cards", params={"since": "not-a-date"}, headers=coordinator.headers).status_code == 422


def test_what_was_marked_leaves_the_unprinted_list_and_stays_in_the_full_one(client: TestClient) -> None:
    coordinator = reviewer(LGA)
    a, b = new_athlete("Marked A"), new_athlete("Marked B")
    marked = mark(client, coordinator, [a.kuid])
    assert marked.status_code == 200 and marked.json() == {"marked": 1}
    assert "cards.printed" in audit_actions(LGA)

    still = kuids(listing(client, coordinator, page=1))
    assert a.kuid not in still
    every = client.get(f"/v1/lgas/{LGA}/cards", params={"unprinted": False, "since": TODAY, "until": TODAY}, headers=coordinator.headers)
    row = next((p for p in every.json()["people"] if p["kuid"] == a.kuid), None)
    assert row is None or row["printed"] is True
    # A reprint is another row, never an edit.
    assert mark(client, coordinator, [a.kuid]).json() == {"marked": 1}
    assert len(sql(
        "SELECT 1 FROM identity.card_prints p JOIN identity.athletes x ON x.id = p.athlete_id WHERE x.kuid = :k", k=a.kuid
    )) == 2
    assert b.kuid not in [r["kuid"] for r in sql(
        "SELECT x.kuid FROM identity.card_prints p JOIN identity.athletes x ON x.id = p.athlete_id"
    )]


def test_marking_ignores_anyone_outside_the_lga_and_anything_unknown(client: TestClient) -> None:
    coordinator = reviewer(LGA)
    mine, away = new_athlete("Mine"), new_athlete("Away")
    sql("UPDATE identity.athletes SET current_lga_id = :l WHERE user_id = :u", l=OTHER_LGA, u=away.user_id)
    got = mark(client, coordinator, [mine.kuid, away.kuid, "KA-NG-JG-BKD-2026-999999", "not-a-kuid"])
    assert got.json() == {"marked": 1}
    assert sql(
        "SELECT 1 FROM identity.card_prints p JOIN identity.athletes x ON x.id = p.athlete_id WHERE x.kuid = :k", k=away.kuid
    ) == []
    assert mark(client, coordinator, []).json() == {"marked": 0}
    too_many = [f"KA-NG-JG-BKD-2026-{i:06d}" for i in range(cards.PAGE_SIZE + 1)]
    assert mark(client, coordinator, too_many).status_code == 422


def test_scope_is_the_lga_its_state_and_nothing_else(client: TestClient) -> None:
    mine, elsewhere = reviewer(LGA), reviewer(OTHER_LGA)
    state_id, _ = make_user("State", grants=[("state_coordinator", "state", "NG-JG")])
    state = bearer(access.issue_session(state_id, method="test").token)
    plain = new_athlete("Plain")
    paths = [("get", f"/v1/lgas/{LGA}/cards"), ("get", f"/v1/lgas/{LGA}/cards.pdf"), ("post", f"/v1/lgas/{LGA}/cards/printed")]
    for verb, path in paths:
        def call(headers, verb=verb, path=path):  # type: ignore[no-untyped-def]
            kwargs = {"json": {"kuids": []}} if verb == "post" else {}
            return getattr(client, verb)(path, headers=headers, **kwargs)

        assert call(mine.headers).status_code in (200, 404), path
        assert call(state).status_code in (200, 404), path
        assert call(elsewhere.headers).status_code == 403, path
        assert call(plain.headers).status_code == 403, path
        assert call({}).status_code == 401, path


def test_a_batch_is_paged_not_built_whole(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    coordinator = reviewer(LGA)
    for i in range(4):
        new_athlete(f"Paged {i}")
    monkeypatch.setattr(cards, "PAGE_SIZE", 3)
    first, second = listing(client, coordinator, unprinted=False), listing(client, coordinator, unprinted=False, page=2)
    assert len(first.json()["people"]) == 3 and first.json()["pages"] == -(-first.json()["total"] // 3)
    assert not set(kuids(first)) & set(kuids(second))


def test_the_sheets_are_a_pdf_of_a4_pages_of_eight(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    coordinator = reviewer(LGA)
    for i in range(9):
        new_athlete(f"Sheet {i}")
    monkeypatch.setattr(cards, "PAGE_SIZE", 9)
    got = client.get(f"/v1/lgas/{LGA}/cards.pdf", params={"since": TODAY, "until": TODAY, "unprinted": False}, headers=coordinator.headers)
    assert got.status_code == 200 and got.headers["content-type"] == "application/pdf"
    assert got.content[:5] == b"%PDF-" and "attachment" in got.headers["content-disposition"]
    assert len(re.findall(rb"/Type\s*/Page\b", got.content)) == 2  # nine cards, eight to a sheet
    empty = client.get(f"/v1/lgas/{LGA}/cards.pdf", params={"since": "2001-01-01", "until": "2001-01-02"}, headers=coordinator.headers)
    assert empty.status_code == 404


def test_a_print_record_cannot_be_edited_or_removed(client: TestClient) -> None:
    coordinator = reviewer(LGA)
    who = new_athlete("Evidence")
    mark(client, coordinator, [who.kuid])
    with pytest.raises(Exception, match=r"permission denied|append-only"):
        sql("UPDATE identity.card_prints SET printed_at = now()")
    with pytest.raises(Exception, match=r"permission denied|append-only"):
        sql("DELETE FROM identity.card_prints")
