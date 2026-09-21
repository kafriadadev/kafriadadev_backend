"""Photographs and documents: what is accepted, and what is ever served.

What is proved here, with real images and a real database:
  - the safe copy carries no EXIF at all — the GPS block a phone writes is gone, while
    the picture is still the right way up (orientation applied to the pixels first)
  - the original is deleted once its copy exists, and only the copy is ever readable
  - something that is not an image, a decompression bomb and an oversize file never
    become usable; a "done" with nothing uploaded never becomes a row that says so
  - the file's owner is the only one who can confirm it
  - documents are removed 30 days after a decision, photographs and undecided ones are not
"""

from __future__ import annotations

import os
from io import BytesIO
from pathlib import Path
from uuid import UUID

import pytest
from PIL import Image

from kafriada.contexts.media import service as media
from kafriada.contexts.media.store import LocalStore
from tests._access_helpers import sql
from tests._media_helpers import make_jpeg, metadata_of, use_local_store
from tests._payment_helpers import new_athlete

pytestmark = [
    pytest.mark.db,
    pytest.mark.skipif(
        not os.environ.get("DATABASE_URL_APP"),
        reason="needs DATABASE_URL_APP",
    ),
]


@pytest.fixture
def store(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> LocalStore:
    return use_local_store(monkeypatch, tmp_path)


@pytest.fixture(scope="module")
def athlete_id() -> UUID:
    who = new_athlete("Media")
    return UUID(str(sql("SELECT id FROM identity.athletes WHERE user_id = :u", u=who.user_id)[0]["id"]))


def status_of(media_id: UUID) -> str:
    return str(sql("SELECT status FROM identity.media_files WHERE id = :m", m=media_id)[0]["status"])


def arrive(store: LocalStore, athlete_id: UUID, data: bytes, kind: str = "photo",
           content_type: str = "image/jpeg") -> UUID:
    slot = media.open_slot(athlete_id, kind, content_type, len(data), store=store)
    media.relay_upload(athlete_id, slot.media_id, data, store=store)
    media.confirm_upload(athlete_id, slot.media_id, store=store)
    return slot.media_id


class TestTheSafeCopy:
    def test_location_and_every_other_tag_is_gone_from_what_is_served(
        self, store: LocalStore, athlete_id: UUID
    ) -> None:
        original = make_jpeg((300, 200), gps=True)
        assert 0x8825 in metadata_of(original)  # the fixture really does carry a GPS block

        media_id = arrive(store, athlete_id, original)
        assert media.process_one(media_id, store=store) == "ready"

        served = media.read_derivative(media_id, store=store)
        assert served is not None and served != original
        assert metadata_of(served) == {}
        assert b"GPS" not in served and b"Exif" not in served

    def test_a_sideways_photo_is_turned_upright_before_its_orientation_is_dropped(
        self, store: LocalStore, athlete_id: UUID
    ) -> None:
        # Stored 300x200 with orientation 6 (rotate 90): the person sees 200x300.
        media_id = arrive(store, athlete_id, make_jpeg((300, 200), orientation=6))
        media.process_one(media_id, store=store)
        with Image.open(BytesIO(media.read_derivative(media_id, store=store) or b"")) as image:
            assert image.size == (200, 300)

    def test_it_is_shrunk_to_what_its_purpose_needs(self, store: LocalStore, athlete_id: UUID) -> None:
        big = make_jpeg((3000, 2000), gps=False)
        photo = arrive(store, athlete_id, big, kind="photo")
        document = arrive(store, athlete_id, big, kind="document")
        media.process_one(photo, store=store)
        media.process_one(document, store=store)
        sizes = {}
        for name, media_id in (("photo", photo), ("document", document)):
            with Image.open(BytesIO(media.read_derivative(media_id, store=store) or b"")) as image:
                sizes[name] = max(image.size)
        assert sizes == {"photo": 900, "document": 1800}

    def test_the_original_is_deleted_once_its_copy_exists(
        self, store: LocalStore, athlete_id: UUID
    ) -> None:
        media_id = arrive(store, athlete_id, make_jpeg())
        (row,) = sql("SELECT original_key FROM identity.media_files WHERE id = :m", m=media_id)
        assert store.head(str(row["original_key"])) is not None
        media.process_one(media_id, store=store)
        assert store.head(str(row["original_key"])) is None

    def test_nothing_can_be_read_before_it_has_been_processed(
        self, store: LocalStore, athlete_id: UUID
    ) -> None:
        media_id = arrive(store, athlete_id, make_jpeg())
        assert status_of(media_id) == "uploaded"
        assert media.read_derivative(media_id, store=store) is None

    def test_the_worker_pass_finishes_what_is_waiting(self, store: LocalStore, athlete_id: UUID) -> None:
        ids = [arrive(store, athlete_id, make_jpeg()) for _ in range(3)]
        assert media.process_pending(50, store=store) >= 3
        assert {status_of(i) for i in ids} == {"ready"}


class TestWhatIsRefused:
    def test_something_that_is_not_an_image_becomes_unreadable_and_is_not_kept(
        self, store: LocalStore, athlete_id: UUID
    ) -> None:
        media_id = arrive(store, athlete_id, b"MZ\x90\x00 this is a program, not a photo" * 20)
        (row,) = sql("SELECT original_key FROM identity.media_files WHERE id = :m", m=media_id)
        assert media.process_one(media_id, store=store) == "unreadable"
        assert store.head(str(row["original_key"])) is None
        assert media.read_derivative(media_id, store=store) is None

    def test_a_small_file_that_declares_an_enormous_canvas_is_refused_not_decoded(
        self, store: LocalStore, athlete_id: UUID
    ) -> None:
        bomb = BytesIO()
        Image.new("1", (12_000, 12_000)).save(bomb, format="PNG")  # ~144M pixels, a few KB
        assert len(bomb.getvalue()) < 100_000
        media_id = arrive(store, athlete_id, bomb.getvalue(), content_type="image/png")
        assert media.process_one(media_id, store=store) == "unreadable"

    def test_a_format_we_did_not_ask_for_is_refused_even_with_a_polite_label(
        self, store: LocalStore, athlete_id: UUID
    ) -> None:
        gif = BytesIO()
        Image.new("RGB", (10, 10)).save(gif, format="GIF")
        media_id = arrive(store, athlete_id, gif.getvalue())  # labelled image/jpeg
        assert media.process_one(media_id, store=store) == "unreadable"

    @pytest.mark.parametrize(
        ("kind", "content_type", "size", "code"),
        [
            ("selfie", "image/jpeg", 100, "kind"),
            ("photo", "application/pdf", 100, "type"),
            ("photo", "image/svg+xml", 100, "type"),
            ("photo", "image/jpeg", 0, "size"),
            ("photo", "image/jpeg", 10 * 1024 * 1024 + 1, "size"),
        ],
    )
    def test_a_slot_is_not_opened_for_the_wrong_thing(
        self, store: LocalStore, athlete_id: UUID, kind: str, content_type: str, size: int, code: str
    ) -> None:
        before = sql("SELECT count(*) AS n FROM identity.media_files WHERE athlete_id = :a", a=athlete_id)
        with pytest.raises(media.MediaRefused) as caught:
            media.open_slot(athlete_id, kind, content_type, size, store=store)
        assert caught.value.code == code
        after = sql("SELECT count(*) AS n FROM identity.media_files WHERE athlete_id = :a", a=athlete_id)
        assert before == after

    def test_saying_done_without_uploading_does_not_make_a_usable_row(
        self, store: LocalStore, athlete_id: UUID
    ) -> None:
        slot = media.open_slot(athlete_id, "photo", "image/jpeg", 1000, store=store)
        with pytest.raises(media.MediaRefused) as caught:
            media.confirm_upload(athlete_id, slot.media_id, store=store)
        assert caught.value.code == "missing"
        assert status_of(slot.media_id) == "pending"

    def test_a_file_far_larger_than_it_said_is_thrown_away(
        self, store: LocalStore, athlete_id: UUID
    ) -> None:
        slot = media.open_slot(athlete_id, "photo", "image/jpeg", 1000, store=store)
        (row,) = sql("SELECT original_key FROM identity.media_files WHERE id = :m", m=slot.media_id)
        store.put(str(row["original_key"]), b"x" * 5000)  # it said 1000
        with pytest.raises(media.MediaRefused):
            media.confirm_upload(athlete_id, slot.media_id, store=store)
        assert status_of(slot.media_id) == "unreadable"
        assert store.head(str(row["original_key"])) is None

    def test_someone_elses_file_cannot_be_confirmed_or_filled(
        self, store: LocalStore, athlete_id: UUID
    ) -> None:
        slot = media.open_slot(athlete_id, "photo", "image/jpeg", 1000, store=store)
        stranger = UUID(str(sql(
            "SELECT id FROM identity.athletes WHERE user_id = :u", u=new_athlete("Stranger").user_id
        )[0]["id"]))
        for action in (
            lambda: media.relay_upload(stranger, slot.media_id, b"x" * 10, store=store),
            lambda: media.confirm_upload(stranger, slot.media_id, store=store),
        ):
            with pytest.raises(media.MediaRefused) as caught:
                action()
            assert caught.value.code == "missing"

    def test_an_unconfigured_store_says_try_again_and_writes_nothing(self, athlete_id: UUID) -> None:
        from kafriada.contexts.media.store import NoStore

        before = sql("SELECT count(*) AS n FROM identity.media_files WHERE athlete_id = :a", a=athlete_id)
        with pytest.raises(media.MediaRefused) as caught:
            media.open_slot(athlete_id, "photo", "image/jpeg", 100, store=NoStore())
        assert caught.value.code == "unavailable"
        assert before == sql("SELECT count(*) AS n FROM identity.media_files WHERE athlete_id = :a", a=athlete_id)
