"""A coordinator starting a checkout for an athlete in their own LGA (CRD-04).

What is proved here, each one a real way this feature could quietly do the
wrong thing with real money:

  - the payment lands on the *athlete* named in the URL, not the coordinator:
    on_behalf_of is set, and when it settles, that athlete's draft moves to
    review (not the coordinator's, who has none) and the receipt goes to that
    athlete's phone
  - **a coordinator cannot pay for an athlete outside their own LGA** — the
    route's scope check only confirms the coordinator holds a grant on the
    lga_id in the path; it says nothing about whether the athlete in the body
    is actually in that LGA, so that check has to live in the service
  - an athlete who has not uploaded a photo and a document yet cannot be paid
    for, same as they could not pay for themselves
  - an athlete who already paid (by either channel) cannot be paid for again
  - the two daily caps per coordinator — count and total naira — both refuse
    once reached, and naira is checked before the amount would push it over,
    not after
  - only someone holding payment.initiate_behalf, scoped to that LGA, gets in
"""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from kafriada.contexts.payments import service
from kafriada.contexts.payments.provider import FakeProvider
from kafriada.contexts.payments.settlement import settle_charge
from kafriada.main import create_app
from tests._access_helpers import bearer, make_user, sql
from tests._media_helpers import LGA, OTHER_LGA, athlete_with_files, reviewer, use_local_store
from tests._payment_helpers import PRICE, charge_success_event

pytestmark = [
    pytest.mark.db,
    pytest.mark.skipif(
        not (os.environ.get("DATABASE_URL_APP") and os.environ.get("DATABASE_URL_MONEY")),
        reason="needs DATABASE_URL_APP and DATABASE_URL_MONEY",
    ),
]

BODY = {"purpose": "stage2_athlete"}


@pytest.fixture(scope="module")
def client() -> Iterator[TestClient]:
    with TestClient(create_app()) as c:
        yield c


@pytest.fixture(autouse=True)
def _store(monkeypatch: pytest.MonkeyPatch, tmp_path):  # type: ignore[no-untyped-def]
    return use_local_store(monkeypatch, tmp_path)


@pytest.fixture
def fake(monkeypatch: pytest.MonkeyPatch) -> FakeProvider:
    provider = FakeProvider()
    monkeypatch.setattr(service, "build_provider", lambda _settings=None: provider)
    return provider


def start(client: TestClient, coordinator, kuid: str, *, lga: str = LGA):  # type: ignore[no-untyped-def]
    return client.post(f"/v1/lgas/{lga}/athletes/{kuid}/payments", json=BODY,
                        headers=coordinator.headers)


def outbox_for(user_id) -> list[dict[str, object]]:  # type: ignore[no-untyped-def]
    return sql(
        "SELECT payload FROM ops.outbox WHERE payload ->> 'user_id' = :u "
        "AND payload ->> 'purpose' = 'payment_received'",
        u=str(user_id),
    )


class TestTheMoneyLandsOnTheAthlete:
    def test_a_coordinator_can_pay_for_an_athlete_in_their_own_lga(
        self, client: TestClient, fake: FakeProvider
    ) -> None:
        coordinator = reviewer(LGA)
        athlete = athlete_with_files(client, "Assisted")

        response = start(client, coordinator, athlete.kuid)

        assert response.status_code == 201
        body = response.json()
        assert body["amount_kobo"] == PRICE
        (row,) = sql(
            "SELECT paid_by, on_behalf_of, coordinator_id FROM money.payments WHERE reference = :r",
            r=body["reference"],
        )
        (athlete_row,) = sql(
            "SELECT id FROM identity.athletes WHERE kuid = :k", k=athlete.kuid
        )
        assert row["paid_by"] == coordinator.user_id
        assert row["on_behalf_of"] == athlete_row["id"], "the ledger must name the athlete"
        assert row["coordinator_id"] == coordinator.user_id

    def test_the_athletes_verification_moves_to_review_not_the_coordinators(
        self, client: TestClient, fake: FakeProvider
    ) -> None:
        coordinator = reviewer(LGA)
        athlete = athlete_with_files(client, "Assisted settle")
        reference = start(client, coordinator, athlete.kuid).json()["reference"]

        outcome = settle_charge(charge_success_event(reference))
        assert outcome.outcome.value == "settled"
        assert outcome.verification_moved is True, (
            "mark_paid must resolve on_behalf_of, or money settles for a "
            "review that never starts"
        )
        (v,) = sql(
            "SELECT v.status FROM identity.verification_requests v "
            "JOIN identity.athletes a ON a.id = v.athlete_id WHERE a.kuid = :k",
            k=athlete.kuid,
        )
        assert v["status"] == "under_review"

    def test_the_receipt_reaches_the_athletes_phone_not_the_coordinators(
        self, client: TestClient, fake: FakeProvider
    ) -> None:
        coordinator = reviewer(LGA)
        athlete = athlete_with_files(client, "Assisted receipt")
        reference = start(client, coordinator, athlete.kuid).json()["reference"]
        (athlete_row,) = sql(
            "SELECT user_id FROM identity.athletes WHERE kuid = :k", k=athlete.kuid
        )

        settle_charge(charge_success_event(reference))

        assert outbox_for(athlete_row["user_id"]), "the athlete was not told"
        assert not outbox_for(coordinator.user_id), "the coordinator is not who paid for this"


class TestTheScopeCheckIsNotOptional:
    def test_a_coordinator_cannot_pay_for_an_athlete_outside_their_lga(
        self, client: TestClient, fake: FakeProvider
    ) -> None:
        """The route's own scope rule cannot catch this: it only confirms the
        coordinator holds a grant on the lga_id named in the *path*. Whether the
        athlete named in the path is really in that LGA is a fact only the
        service can check, against the database, not against the caller's claim.
        """
        coordinator = reviewer(OTHER_LGA)
        athlete = athlete_with_files(client, "Wrong LGA")

        response = start(client, coordinator, athlete.kuid, lga=OTHER_LGA)

        assert response.status_code == 404
        assert fake.calls == [], "Paystack must never be called for a refused attempt"

    def test_an_athlete_cannot_reach_this_route_at_all(self, client: TestClient) -> None:
        athlete = athlete_with_files(client, "Not a coordinator")
        assert start(client, athlete, athlete.kuid).status_code in (401, 403)


class TestReadiness:
    def test_an_athlete_with_no_files_yet_cannot_be_paid_for(
        self, client: TestClient, fake: FakeProvider
    ) -> None:
        from tests._payment_helpers import new_athlete

        coordinator = reviewer(LGA)
        athlete = new_athlete("No files")

        response = start(client, coordinator, athlete.kuid)

        assert response.status_code == 409
        assert fake.calls == []

    def test_an_athlete_already_paid_cannot_be_paid_for_again(
        self, client: TestClient, fake: FakeProvider
    ) -> None:
        coordinator = reviewer(LGA)
        athlete = athlete_with_files(client, "Already paid")
        first = start(client, coordinator, athlete.kuid).json()["reference"]
        settle_charge(charge_success_event(first))

        response = start(client, coordinator, athlete.kuid)

        assert response.status_code == 409


class TestDailyCaps:
    def test_the_daily_count_cap_refuses_once_reached(
        self, client: TestClient, fake: FakeProvider, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from kafriada.settings import get_settings

        # Settings is frozen (by design — see settings.py); a copy is patched in
        # rather than mutating the live singleton other tests share.
        capped = get_settings().model_copy(update={"assisted_payments_per_coordinator_daily": 2})
        monkeypatch.setattr(service, "get_settings", lambda: capped)
        coordinator = reviewer(LGA)

        first = athlete_with_files(client, "Cap one")
        second = athlete_with_files(client, "Cap two")
        third = athlete_with_files(client, "Cap three")
        assert start(client, coordinator, first.kuid).status_code == 201
        assert start(client, coordinator, second.kuid).status_code == 201

        response = start(client, coordinator, third.kuid)
        assert response.status_code == 429
        assert response.json()["error"]["message"]["field"] is None

    def test_the_daily_naira_cap_refuses_a_payment_that_would_cross_it(
        self, client: TestClient, fake: FakeProvider, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from kafriada.settings import get_settings

        # One payment (PRICE) fits; a second would not.
        capped = get_settings().model_copy(update={"assisted_kobo_per_coordinator_daily": PRICE + 1})
        monkeypatch.setattr(service, "get_settings", lambda: capped)
        coordinator = reviewer(LGA)

        first = athlete_with_files(client, "Naira one")
        second = athlete_with_files(client, "Naira two")
        assert start(client, coordinator, first.kuid).status_code == 201

        response = start(client, coordinator, second.kuid)
        assert response.status_code == 429

    def test_a_failed_attempt_does_not_count_against_either_cap(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from kafriada.contexts.payments.provider import ProviderError
        from kafriada.settings import get_settings

        class Dead:
            name = "dead"

            def initialise(self, **_kw: object):  # type: ignore[no-untyped-def]
                raise ProviderError("down", transient=True)

        capped = get_settings().model_copy(update={"assisted_payments_per_coordinator_daily": 1})
        monkeypatch.setattr(service, "get_settings", lambda: capped)
        coordinator = reviewer(LGA)
        athlete = athlete_with_files(client, "Provider down")

        monkeypatch.setattr(service, "build_provider", lambda _settings=None: Dead())
        assert start(client, coordinator, athlete.kuid).status_code == 503

        working = FakeProvider()
        monkeypatch.setattr(service, "build_provider", lambda _settings=None: working)
        second = athlete_with_files(client, "Provider back")
        assert start(client, coordinator, second.kuid).status_code == 201
