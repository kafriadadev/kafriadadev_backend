"""The downloadable wallet card: name, KUID and QR code in one branded image.

Same colours and layout ideas as the web app's on-screen card (globals.css,
the ``.doc``/``.seal``/``.mrz`` styling) so a card downloaded from here and the
one printed from the browser never look like two different products.

Rendered on request from a handful of public fields — nothing here is a
secret, nothing here is expensive enough to cache. PNG for a phone's photo
gallery or a poster; PDF is the same drawing saved as a one-page document, for
printers that behave better fed a PDF than an image.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from importlib import resources
from typing import Literal

import segno
from PIL import Image, ImageChops, ImageDraw, ImageFont

_FONTS = resources.files("kafriada.assets.fonts")

# The same palette as globals.css's --plate-* tokens: a document's colours
# never change with the viewer's dark mode, and a downloaded image has no
# dark mode to answer to in the first place.
_INK = (20, 24, 21)
_MUTED = (90, 97, 88)
_GREEN = (14, 68, 41)
_PAPER = (247, 245, 239)
_CARD = (255, 253, 247)
_RULE = (220, 215, 200)
_RULE_STRONG = (194, 187, 166)
_SUNK = (239, 235, 224)
_SEAL = (166, 124, 0)
_GOLD = (245, 238, 220)

W, H = 1600, 1010
MARGIN = 20
RADIUS = 32
PAD = 64


def _font(path: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(_FONTS.joinpath(path)), size)


def _serif(size: int) -> ImageFont.FreeTypeFont:
    return _font("instrument-serif/InstrumentSerif-Regular.ttf", size)


def _sans(size: int, *, bold: bool = False) -> ImageFont.FreeTypeFont:
    name = "AtkinsonHyperlegible-Bold.ttf" if bold else "AtkinsonHyperlegible-Regular.ttf"
    return _font(f"atkinson-hyperlegible/{name}", size)


def _mono(size: int) -> ImageFont.FreeTypeFont:
    return _font("jetbrains-mono/JetBrainsMono-Variable.ttf", size)


@dataclass(frozen=True, slots=True)
class CardSubject:
    """Exactly what the card shows — the same fields the public profile does."""

    kuid: str
    full_name: str
    sport: str
    playing_position: str | None
    lga_name: str
    state_name: str
    registered_year: int


def _seal_pattern(card_box: tuple[int, int, int, int]) -> Image.Image:
    """A faint, repeating ring across the card — a watermark, not a doodle.

    Kept to one simple motif (echoing the seal badge already on the card)
    rather than a set of illustrated icons: this is a permanent ID, not a
    chat background, and the brand asked for restraint over decoration.
    """
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    x0, y0, x1, y1 = card_box
    step, outer_r, inner_r = 100, 16, 10
    colour = (*_RULE_STRONG, 90)
    row = 0
    y = float(y0 - step)
    while y < y1 + step:
        offset = 0.0 if row % 2 == 0 else step / 2
        x = x0 - step + offset
        while x < x1 + step:
            draw.ellipse((x - outer_r, y - outer_r, x + outer_r, y + outer_r), outline=colour, width=2)
            draw.ellipse((x - inner_r, y - inner_r, x + inner_r, y + inner_r), outline=colour, width=1)
            x += step
        y += step
        row += 1

    mask = Image.new("L", (W, H), 0)
    ImageDraw.Draw(mask).rounded_rectangle(card_box, radius=RADIUS, fill=255)
    alpha = ImageChops.multiply(layer.getchannel("A"), mask)
    layer.putalpha(alpha)
    return layer


def _tracked(draw: ImageDraw.ImageDraw, xy: tuple[float, float], text: str,
             font: ImageFont.FreeTypeFont, fill: tuple[int, int, int], spacing: float) -> None:
    """Draw text one character at a time, evenly spaced — Pillow has no
    letter-spacing of its own, and the mono KUID and small-caps labels on the
    web app both rely on it to read as a document rather than plain text."""
    x, y = xy
    for ch in text:
        draw.text((x, y), ch, font=font, fill=fill)
        x += draw.textlength(ch, font=font) + spacing


def render_card(subject: CardSubject, *, profile_url: str, fmt: Literal["png", "pdf"]) -> bytes:
    img = Image.new("RGB", (W, H), _PAPER)
    draw = ImageDraw.Draw(img)

    card_box = (MARGIN, MARGIN, W - MARGIN, H - MARGIN)
    draw.rounded_rectangle(card_box, radius=RADIUS, fill=_CARD, outline=_RULE_STRONG, width=2)

    pattern = _seal_pattern(card_box)
    img.paste(pattern, (0, 0), pattern)
    draw = ImageDraw.Draw(img)

    # -- wordmark -----------------------------------------------------------
    wm_font = _sans(36, bold=True)
    draw.text((PAD, PAD), "KAF", font=wm_font, fill=_INK)
    kaf_w = draw.textlength("KAF", font=wm_font)
    draw.text((PAD + kaf_w, PAD), "RIADA", font=wm_font, fill=_GREEN)
    _tracked(draw, (PAD, PAD + 50), "JIGAWA STATE · PILOT", _sans(17, bold=True), _MUTED, 1.5)

    # -- seal badge -----------------------------------------------------------
    cx, cy, r = W - MARGIN - PAD - 60, MARGIN + PAD + 4, 60
    draw.ellipse((cx - r, cy - r, cx + r, cy + r), outline=_SEAL, width=3, fill=_GOLD)
    draw.text((cx, cy - 13), "KAF", font=_sans(22, bold=True), fill=_SEAL, anchor="mm")
    draw.text((cx, cy + 15), str(subject.registered_year), font=_sans(18, bold=True), fill=_SEAL, anchor="mm")

    # -- identity block -----------------------------------------------------
    y = PAD + 160.0
    _tracked(draw, (PAD, y), "PERMANENT SPORTS ID", _sans(19, bold=True), _SEAL, 1.5)
    y += 46
    draw.text((PAD, y), subject.full_name, font=_serif(68), fill=_INK)
    y += 92
    pos = f" · {subject.playing_position}" if subject.playing_position else ""
    draw.text((PAD, y), f"{subject.sport}{pos}", font=_sans(27), fill=_MUTED)
    y += 42
    draw.text((PAD, y), f"{subject.lga_name}, {subject.state_name}", font=_sans(27), fill=_MUTED)

    # -- QR -------------------------------------------------------------------
    qr_buf = io.BytesIO()
    segno.make(profile_url, error="m").save(qr_buf, kind="png", scale=8, border=2)
    qr_buf.seek(0)
    qr_img = Image.open(qr_buf).convert("RGB")

    box_size = 300
    strip_h = 150
    qx0 = W - MARGIN - PAD - box_size
    qy0 = H - MARGIN - strip_h - PAD - box_size
    draw.rounded_rectangle(
        (qx0, qy0, qx0 + box_size, qy0 + box_size), radius=16,
        fill=(255, 255, 255), outline=_RULE, width=2,
    )
    inner = box_size - 32
    qr_img = qr_img.resize((inner, inner), Image.NEAREST)
    img.paste(qr_img, (qx0 + 16, qy0 + 16))
    draw.text(
        (qx0 + box_size / 2, qy0 + box_size + 14), "SCAN TO VERIFY",
        font=_sans(16, bold=True), fill=_MUTED, anchor="ma",
    )

    # -- MRZ strip --------------------------------------------------------------
    sy0 = H - MARGIN - strip_h
    draw.rectangle((MARGIN + 2, sy0, W - MARGIN - 2, H - MARGIN - 2), fill=_SUNK)
    draw.line((MARGIN, sy0, W - MARGIN, sy0), fill=_RULE, width=1)
    _tracked(draw, (PAD, sy0 + 26), "KAFRIADA UNIQUE IDENTIFIER", _sans(17, bold=True), _MUTED, 1.5)
    _tracked(draw, (PAD, sy0 + 60), subject.kuid, _mono(44), _INK, 4)

    buffer = io.BytesIO()
    if fmt == "png":
        img.save(buffer, format="PNG")
    else:
        img.convert("RGB").save(buffer, format="PDF", resolution=300.0)
    return buffer.getvalue()
