"""Signing a club up for a test, the way a club does it: the public form, then the code
emailed to its representative."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any
from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from tests._access_helpers import new_phone, sql

LGA = "NG-JG-BKD"


def profile_body(**overrides: Any) -> dict[str, Any]:
    """Every club field beyond name, sport, area and phone, all valid."""
    body: dict[str, Any] = {
        "short_name": "TFC",
        "type": "club",
        "category": "men",
        "age_groups": ["senior", "u17"],
        "level": "amateur",
        "year_founded": 2015,
        "ground_name": "Township Stadium",
        "ground_address": "Stadium Road",
        "town": "Birnin Kudu",
        "club_email": f"club{uuid4().hex[:10]}@example.test",
        "official2_name": "Second Official",
        "official2_role": "Secretary",
        "official2_phone": "08077770000",
    }
    body.update(overrides)
    return body


def club_body(name: str | None = None, **overrides: Any) -> dict[str, Any]:
    """POST /v1/clubs (a coordinator or administrator registering a club)."""
    body = {
        "name": name or f"Test FC {uuid4().hex[:8]}",
        "sport": "Football",
        "lga_id": LGA,
        "contact_phone": "08031234567",
        **profile_body(),
    }
    body.update(overrides)
    return body


def signup_body(name: str | None = None, **overrides: Any) -> dict[str, Any]:
    """POST /v1/clubs/register (a club signing itself up)."""
    phone = new_phone()
    body = {
        **club_body(name),
        "rep_first_name": "Club",
        "rep_surname": "Representative",
        "rep_role": "Chairman",
        "rep_phone": phone,
        "rep_email": f"rep{phone.lstrip('+')}@example.test",
        "password": "a long test passphrase",
        "accept_privacy_notice": True,
    }
    body.update(overrides)
    return body


@dataclass(frozen=True)
class Rep:
    user_id: UUID
    phone: str
    token: str

    @property
    def headers(self) -> dict[str, str]:
        return {"authorization": f"Bearer {self.token}"}


def emailed_code(address: str) -> str:
    rows = sql(
        "SELECT payload ->> 'body' AS body FROM ops.outbox "
        "WHERE payload ->> 'to' = :e AND payload ? 'body' ORDER BY id DESC LIMIT 1",
        e=address,
    )
    assert rows, f"no code emailed to {address}"
    found = re.search(r"\b(\d{6})\b", str(rows[0]["body"]))
    assert found
    return found.group(1)


def sign_up_club(
    client: TestClient, root: dict[str, str] | None = None, *, name: str | None = None,
    approve: bool = True,
) -> tuple[Rep, str]:
    """A club signed up, its representative's email confirmed, and (with ``root``, an
    administrator's headers) approved. Returns (representative, club id)."""
    body = signup_body(name)
    made = client.post("/v1/clubs/register", json=body)
    assert made.status_code == 201, made.text
    club = str(made.json()["club_id"])
    confirmed = client.post(
        "/v1/email/confirm",
        json={"phone": body["rep_phone"], "code": emailed_code(body["rep_email"])},
    )
    assert confirmed.status_code == 200, confirmed.text
    (user,) = sql("SELECT rep_user_id FROM identity.organizations WHERE id = :c", c=club)
    rep = Rep(user_id=user["rep_user_id"], phone=body["rep_phone"],
              token=confirmed.json()["token"])
    if approve and root is not None:
        assert client.post(f"/v1/admin/clubs/{club}/approve", headers=root).status_code == 204
    return rep, club


def registers_clubs(user_id: object, lga: str = LGA) -> None:
    """Let an account register clubs the staff way (POST /v1/clubs), as an LGA coordinator.

    Athlete accounts no longer hold club.create (migration 0015); tests that need a
    club with a particular founder give that founder this role.
    """
    sql(
        "INSERT INTO ops.user_roles (user_id, role_code, scope_kind, scope_id, reason) "
        "SELECT :u, 'lga_coordinator', 'lga', :lga, 'test fixture' WHERE NOT EXISTS ("
        "SELECT 1 FROM ops.user_roles WHERE user_id = :u AND role_code = 'lga_coordinator' "
        "AND scope_id = :lga AND revoked_at IS NULL)",
        u=user_id, lga=lga,
    )
