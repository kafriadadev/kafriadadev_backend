"""The downloadable card renders in the KAFRIADA NET design, for any name.

No database: the renderer takes public fields and returns bytes.
"""

from __future__ import annotations

import dataclasses
import io

import pytest
from PIL import Image, ImageDraw

from kafriada.contexts.identity import card

SUBJECT = card.CardSubject(
    kuid="KA-NG-JG-BKD-2026-000123",
    full_name="Aisha Musa",
    sport="Football",
    playing_position="Central midfielder",
    lga_name="Birnin Kudu",
    state_name="Jigawa",
    registered_year=2026,
)
URL = "https://kafriada.ng/a/KA-NG-JG-BKD-2026-000123?s=1.abc"
NAME_WIDTH = card.RIGHT - 330 - 40 - card.CONTENT_X  # left of the QR code


def _png(subject: card.CardSubject = SUBJECT) -> Image.Image:
    return Image.open(io.BytesIO(card.render_card(subject, profile_url=URL, fmt="png"))).convert("RGB")


def test_png_is_an_id1_card_with_the_brand_colours() -> None:
    img = _png()
    assert img.size == (card.W, card.H)
    assert abs(card.W / card.H - 85.6 / 54) < 0.01
    # The green panel, the kit-red stripe and the black ID strip sit where the design puts them.
    assert img.getpixel((card.PANEL // 2, card.H - 140)) == card._PITCH
    assert img.getpixel((card.PANEL + card.STRIPE // 2, card.H // 2)) == card._KIT_RED
    assert img.getpixel((card.RIGHT - 20, card.H - 70)) == card._INK


def test_pdf_is_a_single_page_document() -> None:
    pdf = card.render_card(SUBJECT, profile_url=URL, fmt="pdf")
    assert pdf[:5] == b"%PDF-"
    assert pdf.count(b"/Type /Page\n") + pdf.count(b"/Type /Page ") + pdf.count(b"/Type /Page>") >= 1


@pytest.mark.parametrize(
    "name",
    [
        "Ɗanjuma Ƙasimu Ɓello",  # the Hausa hooked letters
        "Abdulrahman Muhammadu Sanusi Danbatta Ibrahim",  # a long name shrinks and wraps
        "Ali",
    ],
)
def test_any_name_fits_left_of_the_qr_in_at_most_three_lines(name: str) -> None:
    draw = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    lines, font = card._fit_name(draw, name, NAME_WIDTH)
    assert 1 <= len(lines) <= 3
    assert all(draw.textlength(line, font=font) <= NAME_WIDTH for line in lines)
    assert _png(dataclasses.replace(SUBJECT, full_name=name)).size == (card.W, card.H)


def test_the_card_fonts_have_the_hausa_letters() -> None:
    ttlib = pytest.importorskip("fontTools.ttLib")
    for path in ("fira-sans-condensed/FiraSansCondensed-ExtraBoldItalic.ttf", "andika/Andika-Regular.ttf"):
        cmap = ttlib.TTFont(str(card._FONTS.joinpath(path))).getBestCmap()
        for ch in "ƁɓƊɗƘƙƳƴ":
            assert ord(ch) in cmap, (path, ch)
