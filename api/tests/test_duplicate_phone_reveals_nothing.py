"""Knowing someone's phone number must not tell you who they are.

Registration used to answer a duplicate phone with the existing identity — so
anyone could type a number, with any password, and be shown the holder's name,
KUID and card. The privacy notice promises phone numbers are never public.

Until a code sent to the phone proves the caller owns it, a duplicate gets one
field error on "phone" and nothing else. This goes through the HTTP route,
because what matters is what leaves the building.

Like the burst test, it leaves its rows behind: the app role cannot delete
athletes, by design.
"""

from __future__ import annotations

import os
import time

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from kafriada.contexts.identity.service import DUPLICATE_PHONE_MESSAGE
from kafriada.main import create_app
from tests._registration import form as registration_form

pytestmark = [
    pytest.mark.db,
    pytest.mark.skipif(
        not os.environ.get("DATABASE_URL_APP"),
        reason="needs DATABASE_URL_APP",
    ),
]


def test_a_duplicate_phone_gets_a_field_error_and_no_identity() -> None:
    marker = f"{int(time.time()) % 100000:05d}"
    # Inside the range the burst test uses — no real subscriber holds it.
    phone = f"+2349{marker}7777"
    owner_name = f"Phone Owner {marker}"
    stranger_name = f"Someone Else {marker}"

    def form(full_name: str, password: str) -> dict[str, object]:
        # A different email each time, so the phone is the only thing that clashes.
        return registration_form(
            phone, full_name, password=password,
            email=f"{full_name.split()[0].lower()}{marker}@example.test",
        )

    with TestClient(create_app()) as client:
        first = client.post("/v1/register", json=form(owner_name, "owner-password-not-real"))
        assert first.status_code == 201, first.text
        owner_kuid = first.json()["kuid"]

        # A stranger with the number and a different password.
        second = client.post(
            "/v1/register", json=form(stranger_name, "stranger-password-not-real")
        )

    assert second.status_code == 422, second.text
    assert second.json()["error"]["message"] == {
        "message": DUPLICATE_PHONE_MESSAGE,
        "field": "phone",
    }
    body = second.text
    assert owner_kuid not in body
    assert "KA-NG-" not in body
    assert owner_name not in body
    assert "Phone Owner" not in body

    engine = create_engine(
        os.environ["DATABASE_URL_APP"],
        connect_args={"connect_timeout": 30},
        future=True,
    )
    with engine.connect() as conn:
        athletes = conn.execute(
            text(
                """
                SELECT count(*) FROM identity.athletes a
                  JOIN ops.users u ON u.id = a.user_id
                 WHERE u.phone_e164 = :p
                """
            ),
            {"p": phone},
        ).scalar_one()
        strangers = conn.execute(
            text("SELECT count(*) FROM ops.users WHERE full_name = :n"),
            {"n": stranger_name},
        ).scalar_one()
    engine.dispose()

    assert athletes == 1, "a duplicate phone minted a second identity"
    assert strangers == 0
