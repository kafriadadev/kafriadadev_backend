"""Registration collects the whole athlete record, and refuses anything missing or invalid.

Each refusal names the field to fix and writes nothing. A complete registration stores
every field, and none of the private ones reaches the public profile.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from kafriada.contexts.identity.service import RegistrationError, register
from kafriada.main import create_app
from tests._access_helpers import new_phone, sql
from tests._registration import form, registration

pytestmark = [
    pytest.mark.db,
    pytest.mark.skipif(not os.environ.get("DATABASE_URL_APP"), reason="needs DATABASE_URL_APP"),
]


@pytest.fixture(scope="module")
def client() -> Iterator[TestClient]:
    with TestClient(create_app()) as c:
        yield c


@pytest.mark.parametrize(
    ("change", "field"),
    [
        ({"first_name": " "}, "first_name"),
        ({"surname": ""}, "surname"),
        ({"gender": "unknown"}, "gender"),
        ({"nationality": "Martian"}, "nationality"),
        ({"state_of_origin": "Atlantis"}, "state_of_origin"),
        ({"address_line": ""}, "address_line"),
        ({"town": " "}, "town"),
        ({"sport": "Quidditch"}, "sport"),
        ({"playing_position": "Libero"}, "playing_position"),  # a volleyball position, not football
        ({"secondary_position": "Point guard"}, "secondary_position"),
        ({"dominant_side": "middle"}, "dominant_side"),
        ({"height_cm": 90}, "height_cm"),
        ({"weight_kg": 400}, "weight_kg"),
        ({"years_experience": -1}, "years_experience"),
        ({"level_played": "galactic"}, "level_played"),
        ({"emergency_name": ""}, "emergency_name"),
        ({"emergency_relationship": ""}, "emergency_relationship"),
        ({"emergency_phone": "12"}, "emergency_phone"),
        ({"email": "not-an-email"}, "email"),
    ],
)
def test_each_missing_or_invalid_field_is_refused_by_name(change: dict[str, Any], field: str) -> None:
    phone = new_phone()
    with pytest.raises(RegistrationError) as caught:
        register(registration(phone, "Strict Check", **change))
    assert caught.value.field == field
    assert not sql("SELECT id FROM ops.users WHERE phone_e164 = :p", p=phone)


def test_the_emergency_contact_cannot_be_the_athletes_own_number() -> None:
    phone = new_phone()
    with pytest.raises(RegistrationError) as caught:
        register(registration(phone, "Self Contact", emergency_phone=phone))
    assert caught.value.field == "emergency_phone"


def test_a_complete_registration_stores_the_whole_record() -> None:
    phone = new_phone()
    result = register(registration(phone, "Whole Record", middle_name="Musa"))
    (row,) = sql(
        """
        SELECT u.first_name, u.middle_name, u.surname, u.full_name, u.email,
               u.email_verified_at, u.consent_notice_version, a.nationality,
               a.state_of_origin, a.address_line, a.town, a.height_cm, a.weight_kg,
               a.level_played, a.playing_position, a.dominant_side, a.emergency_phone
          FROM ops.users u JOIN identity.athletes a ON a.user_id = u.id
         WHERE u.id = :u
        """,
        u=result.user_id,
    )
    assert row["full_name"] == "Whole Musa Record"
    assert row["email_verified_at"] is None
    assert row["consent_notice_version"] == "1.1"
    assert (row["height_cm"], row["weight_kg"], row["level_played"]) == (178, 72, "lga")
    assert row["emergency_phone"].startswith("+234")


def test_a_non_nigerian_may_say_not_applicable_for_state_of_origin() -> None:
    phone = new_phone()
    register(registration(phone, "From Abroad", nationality="Ghanaian",
                          state_of_origin="Not applicable"))
    assert sql("SELECT id FROM ops.users WHERE phone_e164 = :p", p=phone)


def test_the_route_refuses_a_missing_field_and_the_public_profile_shows_nothing_private(
    client: TestClient,
) -> None:
    phone = new_phone()
    body = form(phone, "Route Check")
    del body["emergency_name"]
    assert client.post("/v1/register", json=body).status_code == 422

    created = client.post("/v1/register", json=form(phone, "Route Check"))
    assert created.status_code == 201, created.text
    profile = client.get(f"/v1/public/athletes/{created.json()['kuid']}").text
    for private in ("Market Road", "Amina", "example.test", "178", "Sister"):
        assert private not in profile


def test_the_athlete_keeps_their_details_current_but_cannot_change_who_they_are(
    client: TestClient,
) -> None:
    from kafriada.contexts.access import service as access

    phone = new_phone()
    result = register(registration(phone, "Keeps Current"))
    token = access.issue_session(result.user_id, method="test").token
    headers = {"authorization": f"Bearer {token}"}

    update = {
        "playing_position": "Winger", "secondary_position": "Striker", "dominant_side": "left",
        "secondary_sport": "Athletics", "years_experience": 7, "height_cm": 180,
        "weight_kg": 74, "level_played": "state", "address_line": "9 New Road",
        "town": "Dutse", "emergency_name": "Bala Keeps", "emergency_relationship": "Father",
        "emergency_phone": "08031112222",
        # Not part of the update: ignored, never applied.
        "date_of_birth": "2000-01-01", "gender": "female",
    }
    saved = client.put("/v1/athletes/me", json=update, headers=headers)
    assert saved.status_code == 200, saved.text
    body = saved.json()
    assert (body["town"], body["height_cm"], body["level_played"]) == ("Dutse", 180, "state")
    assert (body["gender"], body["date_of_birth"]) == ("male", "1996-04-20")

    missing = {**update, "address_line": ""}
    refused = client.put("/v1/athletes/me", json=missing, headers=headers)
    assert refused.status_code == 422
    assert refused.json()["error"]["message"]["field"] == "address_line"
