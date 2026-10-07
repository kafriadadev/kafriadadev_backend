"""Cash settlement (CRD-05).

What must hold: a coordinator's collected total counts every assisted payment they
started, the confirmed total counts only what Paystack settled, and the difference
between them is exactly what is still unaccounted for. Rows stay inside the LGA; the
default view is the caller's own cash; the CSV cannot smuggle a formula into a
spreadsheet.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from datetime import UTC, date, datetime

import pytest
from fastapi.testclient import TestClient

from kafriada.clock import today_in_nigeria
from kafriada.contexts.access import service as access
from kafriada.contexts.coordination import settlement as settlement_mod
from kafriada.contexts.payments import service
from kafriada.contexts.payments.provider import FakeProvider
from kafriada.contexts.payments.settlement import settle_charge
from kafriada.main import create_app
from tests._access_helpers import bearer, make_user
from tests._media_helpers import LGA, OTHER_LGA, athlete_with_files, reviewer, use_local_store
from tests._payment_helpers import PRICE, charge_success_event, new_athlete

db = pytest.mark.skipif(
    not (os.environ.get("DATABASE_URL_APP") and os.environ.get("DATABASE_URL_MONEY")),
    reason="needs DATABASE_URL_APP and DATABASE_URL_MONEY",
)
TODAY = today_in_nigeria().isoformat()


@pytest.fixture(scope="module")
def client() -> Iterator[TestClient]:
    with TestClient(create_app()) as c:
        yield c


@pytest.fixture
def fake(monkeypatch: pytest.MonkeyPatch, tmp_path) -> FakeProvider:  # type: ignore[no-untyped-def]
    use_local_store(monkeypatch, tmp_path)
    provider = FakeProvider()
    monkeypatch.setattr(service, "build_provider", lambda _settings=None: provider)
    return provider


def collect(client: TestClient, coordinator, name: str) -> str:  # type: ignore[no-untyped-def]
    athlete = athlete_with_files(client, name)
    got = client.post(
        f"/v1/lgas/{LGA}/athletes/{athlete.kuid}/payments",
        json={"purpose": "stage2_athlete"}, headers=coordinator.headers,
    )
    assert got.status_code == 201, got.text
    return str(got.json()["reference"])


def report(client: TestClient, who, **params):  # type: ignore[no-untyped-def]
    return client.get(
        f"/v1/lgas/{LGA}/settlement", params={"since": TODAY, "until": TODAY, **params}, headers=who.headers
    )


@pytest.mark.db
@db
def test_the_difference_is_what_paystack_has_not_confirmed(client: TestClient, fake: FakeProvider) -> None:
    coordinator = reviewer(LGA)
    paid = collect(client, coordinator, "Settled cash")
    waiting = collect(client, coordinator, "Waiting cash")
    assert settle_charge(charge_success_event(paid)).outcome.value == "settled"

    body = report(client, coordinator).json()
    assert {x["reference"]: x["status"] for x in body["lines"]} == {paid: "success", waiting: "pending"}
    assert body["collected_count"] == 2 and body["collected_kobo"] == 2 * PRICE
    assert body["confirmed_count"] == 1 and body["confirmed_kobo"] == PRICE
    assert body["difference_kobo"] == PRICE
    assert body["pending_count"] == 1
    assert sorted(x["athlete_name"].split()[0] for x in body["lines"]) == ["Settled", "Waiting"]


@pytest.mark.db
@db
def test_the_default_is_the_callers_own_cash(client: TestClient, fake: FakeProvider) -> None:
    mine, colleague = reviewer(LGA), reviewer(LGA, name="Colleague")
    own = collect(client, mine, "Mine")
    theirs = collect(client, colleague, "Theirs")

    refs = {x["reference"] for x in report(client, mine).json()["lines"]}
    assert own in refs and theirs not in refs

    everyone = report(client, mine, mine=False).json()
    names = {x["reference"]: x["coordinator_name"] for x in everyone["lines"]}
    assert names[own].startswith("Reviewer") and names[theirs].startswith("Colleague")


@pytest.mark.db
@db
def test_scope_is_the_lga_its_state_and_nothing_else(client: TestClient) -> None:
    mine, elsewhere = reviewer(LGA), reviewer(OTHER_LGA)
    state_id, _ = make_user("State", grants=[("state_coordinator", "state", "NG-JG")])
    state = bearer(access.issue_session(state_id, method="test").token)
    plain = new_athlete("Plain")
    for path in (f"/v1/lgas/{LGA}/settlement", f"/v1/lgas/{LGA}/settlement.csv"):
        assert client.get(path, headers=mine.headers).status_code == 200, path
        assert client.get(path, headers=state).status_code == 200, path
        assert client.get(path, headers=elsewhere.headers).status_code == 403, path
        assert client.get(path, headers=plain.headers).status_code == 403, path
        assert client.get(path).status_code == 401, path


@pytest.mark.db
@db
def test_a_backwards_or_overlong_range_is_refused(client: TestClient) -> None:
    coordinator = reviewer(LGA)
    assert report(client, coordinator, since="2026-05-02", until="2026-05-01").status_code == 422
    assert report(client, coordinator, since="2025-01-01", until="2026-01-02").status_code == 422
    assert report(client, coordinator, since="2025-01-01", until="2026-01-01").status_code == 200


@pytest.mark.db
@db
def test_the_csv_carries_the_same_lines(client: TestClient, fake: FakeProvider) -> None:
    coordinator = reviewer(LGA)
    reference = collect(client, coordinator, "In the sheet")
    got = client.get(
        f"/v1/lgas/{LGA}/settlement.csv", params={"since": TODAY, "until": TODAY}, headers=coordinator.headers
    )
    assert got.status_code == 200
    assert got.headers["content-type"].startswith("text/csv")
    assert "attachment" in got.headers["content-disposition"]
    lines = got.text.strip().splitlines()
    assert lines[0].startswith("date,reference,athlete")
    assert any(reference in line and "In the sheet" in line and "2500.00" in line for line in lines[1:])


def test_a_name_cannot_become_a_spreadsheet_formula() -> None:
    line = settlement_mod.Line(
        reference="KAF-x", created_at=datetime(2026, 10, 1, 9, 30, tzinfo=UTC),
        athlete_name="=HYPERLINK(\"http://x\")", kuid="KA-NG-JG-BKD-2026-000001",
        coordinator_name="+Coordinator", amount_kobo=250005, status="pending",
    )
    report = settlement_mod.Settlement(
        lga_id=LGA, lga_name="Birnin Kudu", since=date(2026, 10, 1), until=date(2026, 10, 1), mine=True,
        lines=(line,), truncated=False, collected_count=1, collected_kobo=250005,
        confirmed_count=0, confirmed_kobo=0, pending_count=1, review_count=0, abandoned_count=0,
    )
    row = settlement_mod.as_csv(report).splitlines()[1]
    assert "'=HYPERLINK" in row and "'+Coordinator" in row
    assert "2026-10-01 10:30" in row, "times are read in Lagos"
    assert "2500.05" in row
