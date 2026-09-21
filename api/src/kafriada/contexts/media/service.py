"""Photographs and identity documents: slots, confirmation, and the safe copy.

**Nothing is served until it has been re-encoded.** What a phone uploads is
untrusted bytes: it may not be an image at all, it may be a decompression bomb, and
a real photograph carries EXIF — GPS coordinates included, which is an athlete's
home. So the original is never shown to anyone. A worker decodes it, applies its
orientation, and writes a *new* JPEG from the pixels alone; the derivative has no
metadata to leak because none was ever copied. Only the derivative is ever served.

**A row means an object exists.** A slot is issued as ``pending``; the row becomes
``uploaded`` only once the store confirms the object is really there (and how big
it is). A client that says "done" without uploading anything, or uploads something
larger than it declared, never produces a usable row.

**Whether a person may see a file is not decided here.** This module moves bytes;
the caller has already established who is asking and for what.
"""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from uuid import UUID

import structlog
from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy import text

from kafriada.contexts.media.store import ObjectStore, StoreError, build_store
from kafriada.db.engine import transaction
from kafriada.settings import get_settings

log = structlog.get_logger(__name__)

KINDS = ("photo", "document")
ALLOWED_TYPES = frozenset({"image/jpeg", "image/png", "image/webp"})

# A face at a size a profile shows; a document at a size a person can still read.
_LONGEST_SIDE = {"photo": 900, "document": 1800}
# Refuse to decode anything that would expand past this many pixels: a small file
# can declare an enormous canvas, and decoding it is how a server runs out of memory.
Image.MAX_IMAGE_PIXELS = 40_000_000

UPLOAD_LINK_SECONDS = 15 * 60


class MediaRefused(Exception):
    """The upload cannot be accepted, and the person can be told why."""

    def __init__(self, message: str, *, code: str) -> None:
        super().__init__(message)
        self.message = message
        self.code = code


class Unreadable(Exception):
    """The bytes are not an image we are willing to keep."""


@dataclass(frozen=True, slots=True)
class Slot:
    media_id: UUID
    # None means "send the bytes to the API instead" (no direct upload here).
    upload_url: str | None


def original_key(athlete_id: UUID, media_id: UUID) -> str:
    return f"verification/{athlete_id}/{media_id}/original"


def derivative_key(athlete_id: UUID, media_id: UUID) -> str:
    return f"verification/{athlete_id}/{media_id}/derivative.jpg"


def open_slot(
    athlete_id: UUID, kind: str, content_type: str, size_bytes: int, *, store: ObjectStore | None = None
) -> Slot:
    """Record that a file is about to arrive, and say where to send it."""
    settings = get_settings()
    store = store or build_store(settings)
    if store.name == "none":
        raise MediaRefused(
            "We could not accept your photo just now. Please try again shortly.", code="unavailable"
        )
    if kind not in KINDS:
        raise MediaRefused("Choose whether this is your photo or your document.", code="kind")
    if content_type.lower() not in ALLOWED_TYPES:
        raise MediaRefused("Please send a JPEG, PNG or WebP image.", code="type")
    if not 0 < size_bytes <= settings.media_max_bytes:
        raise MediaRefused(
            f"That file is too large. The most we accept is {settings.media_max_bytes // (1024 * 1024)}MB.",
            code="size",
        )

    with transaction() as session:
        media_id: UUID = session.execute(
            text("SELECT gen_random_uuid()")
        ).scalar_one()
        key = original_key(athlete_id, media_id)
        session.execute(
            text(
                """
                INSERT INTO identity.media_files
                    (id, athlete_id, kind, original_key, declared_type, declared_bytes)
                VALUES (:id, :athlete, :kind, :key, :type, :bytes)
                """
            ),
            {
                "id": media_id,
                "athlete": athlete_id,
                "kind": kind,
                "key": key,
                "type": content_type.lower(),
                "bytes": size_bytes,
            },
        )
    try:
        url = store.presign_put(key, expires_seconds=UPLOAD_LINK_SECONDS)
    except StoreError as exc:
        log.error("media_slot_failed", error=exc.message)
        raise MediaRefused(
            "We could not accept your photo just now. Please try again shortly.", code="unavailable"
        ) from exc
    return Slot(media_id=media_id, upload_url=url)


def _pending_row(athlete_id: UUID, media_id: UUID):  # type: ignore[no-untyped-def]
    with transaction() as session:
        return session.execute(
            text(
                "SELECT id, status, original_key, declared_bytes FROM identity.media_files "
                "WHERE id = :id AND athlete_id = :athlete"
            ),
            {"id": media_id, "athlete": athlete_id},
        ).one_or_none()


def relay_upload(
    athlete_id: UUID, media_id: UUID, data: bytes, *, store: ObjectStore | None = None
) -> None:
    """The fallback for a browser with no JavaScript: the bytes pass through us once."""
    store = store or build_store()
    row = _pending_row(athlete_id, media_id)
    if row is None or row.status != "pending":
        raise MediaRefused("We could not find that upload.", code="missing")
    if not 0 < len(data) <= get_settings().media_max_bytes:
        raise MediaRefused("That file is too large or empty.", code="size")
    try:
        store.put(row.original_key, data)
    except StoreError as exc:
        log.error("media_relay_failed", error=exc.message)
        raise MediaRefused(
            "We could not accept your photo just now. Please try again shortly.", code="unavailable"
        ) from exc


def confirm_upload(
    athlete_id: UUID, media_id: UUID, *, store: ObjectStore | None = None
) -> None:
    """Mark a file ``uploaded`` — but only if the object is really there."""
    settings = get_settings()
    store = store or build_store(settings)
    row = _pending_row(athlete_id, media_id)
    if row is None or row.status != "pending":
        raise MediaRefused("We could not find that upload.", code="missing")
    try:
        info = store.head(row.original_key)
    except StoreError as exc:
        log.error("media_confirm_failed", error=exc.message)
        raise MediaRefused(
            "We could not check your upload just now. Please try again shortly.", code="unavailable"
        ) from exc
    if info is None:
        raise MediaRefused("Your file did not arrive. Please try again.", code="missing")
    if info.size_bytes > settings.media_max_bytes or info.size_bytes > row.declared_bytes * 2:
        # Bigger than allowed, or than it said it was: not something we keep.
        _discard(store, row.original_key)
        _set_status(media_id, "unreadable")
        raise MediaRefused(
            f"That file is too large. The most we accept is {settings.media_max_bytes // (1024 * 1024)}MB.",
            code="size",
        )
    with transaction() as session:
        session.execute(
            text(
                "UPDATE identity.media_files SET status = 'uploaded', size_bytes = :size, "
                "uploaded_at = now() WHERE id = :id AND status = 'pending'"
            ),
            {"id": media_id, "size": info.size_bytes},
        )


def reencode(data: bytes, kind: str) -> bytes:
    """A fresh JPEG built from the pixels alone. Raises :class:`Unreadable`."""
    try:
        with Image.open(BytesIO(data)) as probe:
            if probe.format not in ("JPEG", "PNG", "WEBP"):
                raise Unreadable(f"unsupported format {probe.format!r}")
            probe.verify()
        with Image.open(BytesIO(data)) as image:
            # Orientation lives in EXIF; apply it to the pixels before the EXIF is
            # left behind, or every portrait photo comes out sideways.
            upright = ImageOps.exif_transpose(image)
            flat = upright.convert("RGB")
    except Unreadable:
        raise
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError, ValueError, SyntaxError) as exc:
        raise Unreadable(type(exc).__name__) from exc

    flat.thumbnail((_LONGEST_SIDE[kind], _LONGEST_SIDE[kind]))
    out = BytesIO()
    # No exif=, no icc_profile=, no info: nothing is carried over.
    flat.save(out, format="JPEG", quality=85, optimize=True)
    return out.getvalue()


def process_one(media_id: UUID, *, store: ObjectStore | None = None) -> str:
    """Re-encode one confirmed upload. Returns its new status.

    No transaction is held while the store is talked to: a slow object store must
    not hold a database connection, and the result is written with a guard on the
    status, so two workers racing on one file both write the same bytes and only
    the first update lands.
    """
    settings = get_settings()
    store = store or build_store(settings)
    with transaction() as session:
        row = session.execute(
            text(
                "SELECT id, athlete_id, kind, status, original_key FROM identity.media_files "
                "WHERE id = :id"
            ),
            {"id": media_id},
        ).one_or_none()
    if row is None or row.status != "uploaded":
        return row.status if row else "missing"

    try:
        original = store.get(row.original_key, max_bytes=settings.media_max_bytes * 2)
    except StoreError as exc:
        if exc.transient:
            log.warning("media_process_deferred", media_id=str(media_id), error=exc.message)
            return "uploaded"
        original = None
    if original is None:
        _set_status(media_id, "unreadable")
        log.error("media_object_missing", media_id=str(media_id))
        return "unreadable"

    try:
        derivative = reencode(original, row.kind)
    except Unreadable as exc:
        # Not an image: do not keep it.
        _discard(store, row.original_key)
        _set_status(media_id, "unreadable")
        log.warning("media_unreadable", media_id=str(media_id), reason=str(exc))
        return "unreadable"

    key = derivative_key(row.athlete_id, media_id)
    try:
        store.put(key, derivative)
    except StoreError as exc:
        log.warning("media_process_deferred", media_id=str(media_id), error=exc.message)
        return "uploaded"
    with transaction() as session:
        session.execute(
            text(
                "UPDATE identity.media_files SET status = 'ready', derivative_key = :key, "
                "processed_at = now() WHERE id = :id AND status = 'uploaded'"
            ),
            {"id": media_id, "key": key},
        )
    # The original — with whatever EXIF it carried — is no longer needed by anyone.
    _discard(store, row.original_key)
    return "ready"


def process_pending(limit: int = 20, *, store: ObjectStore | None = None) -> int:
    """Process the oldest confirmed uploads. Returns how many became ready."""
    with transaction() as session:
        ids = [
            r.id
            for r in session.execute(
                text(
                    "SELECT id FROM identity.media_files WHERE status = 'uploaded' "
                    "ORDER BY uploaded_at LIMIT :n"
                ),
                {"n": limit},
            )
        ]
    return sum(1 for media_id in ids if process_one(media_id, store=store) == "ready")


def read_derivative(media_id: UUID, *, store: ObjectStore | None = None) -> bytes | None:
    """The safe copy's bytes, or None. The CALLER must already have authorised this."""
    settings = get_settings()
    store = store or build_store(settings)
    with transaction() as session:
        key = session.execute(
            text(
                "SELECT derivative_key FROM identity.media_files "
                "WHERE id = :id AND status = 'ready'"
            ),
            {"id": media_id},
        ).scalar_one_or_none()
    if key is None:
        return None
    try:
        return store.get(key, max_bytes=settings.media_max_bytes)
    except StoreError as exc:
        log.error("media_read_failed", media_id=str(media_id), error=exc.message)
        return None


def purge_expired_documents(days: int = 30, *, store: ObjectStore | None = None) -> int:
    """Remove the objects behind identity documents, ``days`` after a decision.

    "Your document is used only to check your identity and age, and is deleted 30
    days after a decision." A rejected request is not included: its document may
    still be needed for the next attempt. The row stays and records when.
    """
    store = store or build_store()
    with transaction() as session:
        rows = session.execute(
            text(
                """
                SELECT m.id, m.original_key, m.derivative_key
                  FROM identity.media_files m
                  JOIN identity.verification_requests v ON v.document_media_id = m.id
                 WHERE m.kind = 'document' AND m.deleted_at IS NULL
                   AND v.status IN ('approved', 'revoked', 'escalated')
                   AND v.decided_at < now() - make_interval(days => :days)
                """
            ),
            {"days": days},
        ).all()
    purged = 0
    for row in rows:
        try:
            for key in (row.original_key, row.derivative_key):
                if key:
                    store.delete(key)
        except StoreError as exc:
            log.warning("media_purge_deferred", media_id=str(row.id), error=exc.message)
            continue
        with transaction() as session:
            session.execute(
                text(
                    "UPDATE identity.media_files SET status = 'deleted', deleted_at = now() "
                    "WHERE id = :id"
                ),
                {"id": row.id},
            )
        purged += 1
    return purged


def _set_status(media_id: UUID, status: str) -> None:
    with transaction() as session:
        session.execute(
            text("UPDATE identity.media_files SET status = :s WHERE id = :id"),
            {"s": status, "id": media_id},
        )


def _discard(store: ObjectStore, key: str) -> None:
    try:
        store.delete(key)
    except StoreError as exc:
        log.warning("media_discard_failed", error=exc.message)
