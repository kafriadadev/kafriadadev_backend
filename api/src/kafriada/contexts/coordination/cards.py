"""Bulk QR card printing (CRD-06): turn a registration drive into a stack of cards.

Every query is bounded by one LGA. A page is at most five A4 sheets of eight cards, so a
very large batch is paged rather than built as one enormous document. The card is the
same drawing an athlete downloads themselves — a coordinator is only saving them the
trouble.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from datetime import date
from uuid import UUID

from PIL import Image
from sqlalchemy import text
from sqlalchemy.sql.elements import TextClause

from kafriada.contexts.audit.service import Actor, record
from kafriada.contexts.identity import card
from kafriada.db.engine import transaction
from kafriada.security.signing import build_qr_signer
from kafriada.settings import get_settings

PER_SHEET = 8
SHEETS_PER_PAGE = 5
PAGE_SIZE = PER_SHEET * SHEETS_PER_PAGE

# A4 at 200 dpi, two columns by four rows of credit-card-sized (85.6 x 54 mm) cards.
_A4 = (1654, 2339)
_CARD = (675, 426)
_GAP = 20


@dataclass(frozen=True, slots=True)
class CardRow:
    kuid: str
    full_name: str
    registered_on: date
    printed: bool


@dataclass(frozen=True, slots=True)
class CardPage:
    people: tuple[CardRow, ...]
    total: int
    page: int
    pages: int


_WHERE = """
    a.current_lga_id = :lga AND u.anonymised_at IS NULL
    AND (CAST(:since AS date) IS NULL OR (a.created_at AT TIME ZONE 'Africa/Lagos')::date >= :since)
    AND (CAST(:until AS date) IS NULL OR (a.created_at AT TIME ZONE 'Africa/Lagos')::date <= :until)
    AND (NOT :only_unprinted
         OR NOT EXISTS (SELECT 1 FROM identity.card_prints p WHERE p.athlete_id = a.id))
"""


def _batch(select: str, tail: str = "") -> TextClause:
    """The select list and tail are constants written above; the caller's values are bind parameters."""
    return text(
        f"{select} FROM identity.athletes a JOIN ops.users u ON u.id = a.user_id "
        f"JOIN ops.locations lga ON lga.id = a.current_lga_id "
        f"JOIN ops.locations st ON st.id = lga.parent_id WHERE {_WHERE}{tail}"
    )


def list_cards(
    lga_id: str, since: date | None, until: date | None, only_unprinted: bool, page: int
) -> CardPage:
    page = max(page, 1)
    params = {"lga": lga_id, "since": since, "until": until, "only_unprinted": only_unprinted}
    with transaction() as session:
        total = int(session.execute(_batch("SELECT count(*)"), params).scalar_one())
        rows = session.execute(
            _batch(
                "SELECT a.kuid, u.full_name, (a.created_at AT TIME ZONE 'Africa/Lagos')::date AS registered_on, "
                "EXISTS (SELECT 1 FROM identity.card_prints p WHERE p.athlete_id = a.id) AS printed",
                " ORDER BY a.created_at, a.id LIMIT :n OFFSET :off",
            ),
            {**params, "n": PAGE_SIZE, "off": (page - 1) * PAGE_SIZE},
        ).mappings().all()
    return CardPage(
        people=tuple(
            CardRow(kuid=r["kuid"], full_name=r["full_name"], registered_on=r["registered_on"], printed=r["printed"])
            for r in rows
        ),
        total=total,
        page=page,
        pages=max(1, -(-total // PAGE_SIZE)),
    )


def mark_printed(
    lga_id: str,
    kuids: list[str],
    user_id: UUID,
    user_name: str,
    *,
    request_id: str | None = None,
    ip_address: str | None = None,
) -> int:
    """Record that these cards were printed. Athletes outside the LGA are not touched."""
    kuids = list(dict.fromkeys(kuids))[:PAGE_SIZE]
    if not kuids:
        return 0
    with transaction() as session:
        marked = session.execute(
            text(
                """
                INSERT INTO identity.card_prints (athlete_id, printed_by)
                SELECT a.id, :by FROM identity.athletes a
                 WHERE a.kuid = ANY(:kuids) AND a.current_lga_id = :lga
                RETURNING athlete_id
                """
            ),
            {"by": user_id, "kuids": kuids, "lga": lga_id},
        ).all()
        if marked:
            record(
                session,
                actor=Actor(user_id=user_id, label=user_name),
                action="cards.printed",
                subject_type="lga",
                subject_id=lga_id,
                metadata={"count": len(marked)},
                request_id=request_id,
                ip_address=ip_address,
            )
    return len(marked)


def sheets_pdf(
    lga_id: str, since: date | None, until: date | None, only_unprinted: bool, page: int
) -> bytes | None:
    """One page of the batch as A4 sheets, eight cards each. None when there are none."""
    with transaction() as session:
        rows = session.execute(
            _batch(
                "SELECT a.kuid, u.full_name, a.sport, a.playing_position, lga.name AS lga_name, "
                "st.name AS state_name, a.kuid_year",
                " ORDER BY a.created_at, a.id LIMIT :n OFFSET :off",
            ),
            {
                "lga": lga_id, "since": since, "until": until, "only_unprinted": only_unprinted,
                "n": PAGE_SIZE, "off": (max(page, 1) - 1) * PAGE_SIZE,
            },
        ).mappings().all()
    if not rows:
        return None
    signer = build_qr_signer(get_settings())
    base = get_settings().public_base_url.rstrip("/")

    images: list[Image.Image] = []
    for r in rows:
        subject = card.CardSubject(
            kuid=r["kuid"], full_name=r["full_name"], sport=r["sport"],
            playing_position=r["playing_position"], lga_name=r["lga_name"],
            state_name=r["state_name"], registered_year=int(r["kuid_year"]),
        )
        url = f"{base}/a/{r['kuid']}?s={signer.sign(r['kuid'])}"
        png = card.render_card(subject, profile_url=url, fmt="png")
        images.append(Image.open(io.BytesIO(png)).convert("RGB").resize(_CARD, Image.Resampling.LANCZOS))

    width = 2 * _CARD[0] + _GAP
    height = 4 * _CARD[1] + 3 * _GAP
    left, top = (_A4[0] - width) // 2, (_A4[1] - height) // 2
    sheets: list[Image.Image] = []
    for start in range(0, len(images), PER_SHEET):
        sheet = Image.new("RGB", _A4, (255, 255, 255))
        for slot, image in enumerate(images[start : start + PER_SHEET]):
            col, row = slot % 2, slot // 2
            sheet.paste(image, (left + col * (_CARD[0] + _GAP), top + row * (_CARD[1] + _GAP)))
        sheets.append(sheet)

    buffer = io.BytesIO()
    sheets[0].save(buffer, format="PDF", save_all=True, append_images=sheets[1:], resolution=200.0)
    return buffer.getvalue()
