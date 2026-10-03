"""A complete, valid registration for tests, with any field overridden.

Registration requires every field of the athlete record, so tests build one here
rather than spelling out twenty fields at every call site. The email is derived
from the phone so two registrations never collide on it by accident.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from kafriada.contexts.identity.service import RegistrationInput


def registration(phone: str, name: str = "Test Athlete", **overrides: Any) -> RegistrationInput:
    first, _, rest = name.partition(" ")
    digits = "".join(ch for ch in phone if ch.isdigit())
    values: dict[str, Any] = {
        "first_name": first,
        "surname": rest or "Athlete",
        "email": f"t{digits}@example.test",
        "phone": phone,
        "password": "a long test passphrase",
        "date_of_birth": date(1996, 4, 20),
        "gender": "male",
        "nationality": "Nigerian",
        "state_of_origin": "Jigawa",
        "address_line": "12 Market Road",
        "town": "Birnin Kudu",
        "lga_id": "NG-JG-BKD",
        "sport": "Football",
        "playing_position": "Striker",
        "dominant_side": "right",
        "height_cm": 178,
        "weight_kg": 72,
        "years_experience": 6,
        "level_played": "lga",
        "emergency_name": "Amina Test",
        "emergency_relationship": "Sister",
        # Any valid number other than the athlete's own.
        "emergency_phone": "+2348099990000" if digits[-4:] != "0000" else "+2348099990001",
        "consent_notice_version": "1.1",
    }
    values.update(overrides)
    return RegistrationInput(**values)


def form(phone: str, name: str = "Test Athlete", **overrides: Any) -> dict[str, Any]:
    """The same registration as the JSON body of POST /v1/register."""
    data = registration(phone, name, **overrides)
    body = {f: getattr(data, f) for f in data.__dataclass_fields__}
    body.pop("consent_notice_version")
    body["date_of_birth"] = data.date_of_birth.isoformat()
    body["accept_privacy_notice"] = True
    return body
