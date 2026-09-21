"""Fixtures for the media and verification tests: real JPEGs (with a GPS tag, because
that is what a phone puts in one), a local store, and a way through the whole
upload → pay → review path without a browser.
"""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from kafriada.api.v1 import verification as verification_api
from kafriada.contexts.access import service as access
from kafriada.contexts.media import service as media_service
from kafriada.contexts.media.store import LocalStore
from kafriada.contexts.payments.rules import Purpose
from kafriada.contexts.payments.settlement import settle_charge
from tests._access_helpers import bearer, make_user
from tests._payment_helpers import Athlete, charge_success_event, new_athlete, pending_payment

GPS_TAG = 0x8825
ORIENTATION = 0x0112
LGA = "NG-JG-BKD"
OTHER_LGA = "NG-JG-GUM"


def make_jpeg(size: tuple[int, int] = (300, 200), *, gps: bool = True, orientation: int | None = None) -> bytes:
    """A JPEG that looks like a phone's: with GPS coordinates and, optionally, rotation."""
    image = Image.new("RGB", size, (200, 30, 30))
    exif = Image.Exif()
    if gps:
        exif[GPS_TAG] = {1: "N", 2: (11.0, 45.0, 30.0), 3: "E", 4: (9.0, 30.0, 15.0)}
    if orientation:
        exif[ORIENTATION] = orientation
    out = BytesIO()
    image.save(out, format="JPEG", exif=exif)
    return out.getvalue()


def metadata_of(data: bytes) -> dict[int, object]:
    """Every EXIF tag in an image, including the GPS block."""
    with Image.open(BytesIO(data)) as image:
        exif = image.getexif()
        found = dict(exif)
        if exif.get_ifd(GPS_TAG):
            found[GPS_TAG] = dict(exif.get_ifd(GPS_TAG))
        return found


def use_local_store(monkeypatch: pytest.MonkeyPatch, root: Path) -> LocalStore:
    """Point every media code path at a temporary directory."""
    store = LocalStore(root)
    monkeypatch.setattr(media_service, "build_store", lambda _settings=None: store)
    monkeypatch.setattr(verification_api, "build_store", lambda _settings=None: store)
    return store


def upload(client: TestClient, who: Athlete, kind: str, data: bytes, *, content_type: str = "image/jpeg") -> UUID:
    """The whole no-JavaScript upload: open a slot, send the bytes, confirm."""
    slot = client.post(
        "/v1/verification/uploads",
        json={"kind": kind, "content_type": content_type, "size_bytes": len(data)},
        headers=who.headers,
    )
    assert slot.status_code == 201, slot.text
    media_id = slot.json()["media_id"]
    put = client.put(f"/v1/verification/uploads/{media_id}/content", content=data, headers=who.headers)
    assert put.status_code == 204, put.text
    confirm = client.post(f"/v1/verification/uploads/{media_id}/confirm", headers=who.headers)
    assert confirm.status_code == 204, confirm.text
    return UUID(media_id)


def athlete_with_files(client: TestClient, name: str = "Verify") -> Athlete:
    who = new_athlete(name)
    upload(client, who, "photo", make_jpeg(orientation=6))
    upload(client, who, "document", make_jpeg((600, 400), gps=False))
    return who


def pay(who: Athlete) -> str:
    """The payer's payment settles, as the webhook would make it. Returns the reference."""
    ref = pending_payment(who)
    assert settle_charge(charge_success_event(ref)).outcome.value == "settled"
    return ref


def reviewer(lga: str = LGA, *, name: str = "Reviewer") -> Athlete:
    user_id, _ = make_user(name, grants=[("lga_coordinator", "lga", lga)])
    return Athlete(user_id=user_id, kuid="", token=access.issue_session(user_id, method="test").token)


def super_admin(password: str) -> Athlete:
    user_id, _ = make_user("Admin", password=password, grants=[("super_admin", "global", None)])
    return Athlete(user_id=user_id, kuid="", token=access.issue_session(user_id, method="test").token)


def request_id_of(who: Athlete) -> UUID:
    from tests._access_helpers import sql

    rows = sql(
        "SELECT v.id FROM identity.verification_requests v JOIN identity.athletes a "
        "ON a.id = v.athlete_id WHERE a.user_id = :u ORDER BY v.created_at DESC LIMIT 1",
        u=who.user_id,
    )
    return UUID(str(rows[0]["id"]))


def review_url(request_id: UUID, lga: str = LGA) -> str:
    return f"/v1/lgas/{lga}/verification/{request_id}"


__all__ = [
    "LGA", "OTHER_LGA", "Purpose", "athlete_with_files", "bearer", "make_jpeg", "metadata_of",
    "pay", "request_id_of", "review_url", "reviewer", "super_admin", "upload", "use_local_store",
]
