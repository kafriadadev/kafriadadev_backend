"""The downloadable card: the KAFRIADA NET player card as one image.

The same design as the web tier's printed card (web/src/components/ui/PlayerCard.tsx,
``PrintCard``): a pitch-green panel with chalk lines and the photo space, the
kit-red stripe, the name set like the back of a shirt, the QR code, and the ID in
a black scoreboard strip. A card downloaded here and one printed from the browser
must look like the same product.

Colours are the web tier's ``--plate-*`` and brand tokens (web/src/styles/tokens.css).
The card never follows a dark mode, and an image has none to follow.

Rendered on request from public fields only. PNG for a phone's gallery or a
poster; PDF is the same drawing as a one-page document, for printers.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from importlib import resources
from typing import Literal

import segno
from PIL import Image, ImageDraw, ImageFont

_FONTS = resources.files("kafriada.assets.fonts")
_BRAND = resources.files("kafriada.assets.brand")

# tokens.css
_PLATE = (255, 255, 255)       # --plate-bg / --chalk
_INK = (10, 15, 11)            # --boot / --plate-ink
_MUTED = (75, 90, 79)          # --plate-muted
_PITCH = (14, 173, 44)         # --pitch
_KIT_RED = (235, 0, 2)         # --kit-red
_PHOTO_BG = (230, 234, 228)
_SILHOUETTE = (163, 174, 166)
_CHALK_LINE = (255, 255, 255, 90)
_EDGE = (214, 220, 211)

# ID-1 proportions (85.6 x 54 mm) at about 475 dpi.
W, H = 1600, 1010
RADIUS = 56
PANEL = 560          # the green panel: 30 mm of 85.6
STRIPE = 22          # the kit-red stripe
CONTENT_X = PANEL + STRIPE + 60
RIGHT = W - 60


def _font(path: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(_FONTS.joinpath(path)), size)


def _display(size: int) -> ImageFont.FreeTypeFont:
    return _font("fira-sans-condensed/FiraSansCondensed-ExtraBoldItalic.ttf", size)


def _body(size: int, *, bold: bool = False) -> ImageFont.FreeTypeFont:
    return _font(f"andika/Andika-{'Bold' if bold else 'Regular'}.ttf", size)


def _mono(size: int) -> ImageFont.FreeTypeFont:
    return _font("geist-mono/GeistMono-Medium.ttf", size)


@dataclass(frozen=True, slots=True)
class CardSubject:
    """Exactly what the card shows: the same fields the public profile does."""

    kuid: str
    full_name: str
    sport: str
    playing_position: str | None
    lga_name: str
    state_name: str
    registered_year: int


def _tracked(draw: ImageDraw.ImageDraw, xy: tuple[float, float], text: str,
             font: ImageFont.FreeTypeFont, fill: tuple[int, int, int], spacing: float) -> float:
    """Letter-spaced text, which Pillow has no setting for. Returns the end x."""
    x, y = xy
    for ch in text:
        draw.text((x, y), ch, font=font, fill=fill)
        x += draw.textlength(ch, font=font) + spacing
    return x


def _wrap(draw: ImageDraw.ImageDraw, words: list[str], font: ImageFont.FreeTypeFont, width: int) -> list[str]:
    lines: list[str] = []
    for word in words:
        trial = f"{lines[-1]} {word}" if lines else word
        if lines and draw.textlength(trial, font=font) <= width:
            lines[-1] = trial
        else:
            lines.append(word)
    return lines


def _fit_name(draw: ImageDraw.ImageDraw, name: str, width: int) -> tuple[list[str], ImageFont.FreeTypeFont]:
    """The name as large as it fits: one line at the biggest sizes, up to three
    at the smallest, shrinking until every line fits beside the QR code."""
    words = name.upper().split()
    for size in range(108, 35, -4):
        font = _display(size)
        lines = _wrap(draw, words, font, width)
        allowed = 1 if size > 96 else 2 if size > 60 else 3
        if len(lines) <= allowed and all(draw.textlength(line, font=font) <= width for line in lines):
            return lines, font
    font = _display(36)
    return _wrap(draw, words, font, width), font


def _panel(img: Image.Image, year: int) -> None:
    """The green panel: chalk halfway line and centre circle, the photo space, the year."""
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    d.rectangle((0, 0, PANEL, H), fill=(*_PITCH, 255))
    mid = H // 2
    d.line((0, mid, PANEL, mid), fill=_CHALK_LINE, width=5)
    d.ellipse((PANEL / 2 - 170, mid - 170, PANEL / 2 + 170, mid + 170), outline=_CHALK_LINE, width=5)
    mask = Image.new("L", (W, H), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, W - 1, H - 1), radius=RADIUS, fill=255)
    img.paste(layer, (0, 0), Image.composite(layer.getchannel("A"), Image.new("L", (W, H), 0), mask))

    draw = ImageDraw.Draw(img)
    # The photo space, in a white frame: the silhouette until a photo is approved.
    px0, py0, px1, py1 = 70, 110, PANEL - 70, 110 + int((PANEL - 140) * 1.22)
    draw.rounded_rectangle((px0 - 12, py0 - 12, px1 + 12, py1 + 12), radius=26, fill=_PLATE)
    draw.rounded_rectangle((px0, py0, px1, py1), radius=16, fill=_PHOTO_BG)
    cx, w = (px0 + px1) / 2, px1 - px0
    head = w * 0.2
    draw.ellipse((cx - head, py0 + w * 0.22, cx + head, py0 + w * 0.22 + 2 * head), fill=_SILHOUETTE)
    shoulders_top = py0 + w * 0.22 + 2 * head + w * 0.06
    draw.pieslice((px0 + w * 0.08, shoulders_top, px1 - w * 0.08, shoulders_top + w * 0.9), 180, 360, fill=_SILHOUETTE)
    draw.rectangle((px0 + w * 0.08, shoulders_top + w * 0.45, px1 - w * 0.08, py1 - 1), fill=_SILHOUETTE)

    draw.text((70, H - 70), str(year), font=_mono(44), fill=_INK, anchor="ls")


def render_card(subject: CardSubject, *, profile_url: str, fmt: Literal["png", "pdf"]) -> bytes:
    img = Image.new("RGB", (W, H), _PLATE)
    draw = ImageDraw.Draw(img)
    _panel(img, subject.registered_year)
    draw = ImageDraw.Draw(img)
    draw.rectangle((PANEL, 0, PANEL + STRIPE, H), fill=_KIT_RED)

    # -- the logo -------------------------------------------------------------
    with _BRAND.joinpath("kafriada-net-horizontal.png").open("rb") as f:
        logo = Image.open(f).convert("RGBA")
    logo_h = 84
    logo = logo.resize((round(logo.width * logo_h / logo.height), logo_h), Image.Resampling.LANCZOS)
    img.paste(logo, (CONTENT_X, 70), logo)

    # -- QR, top right --------------------------------------------------------
    qr_size = 330
    qx0, qy0 = RIGHT - qr_size, 70
    qr_buf = io.BytesIO()
    segno.make(profile_url, error="m").save(qr_buf, kind="png", scale=10, border=2)
    qr_buf.seek(0)
    qr = Image.open(qr_buf).convert("RGB").resize((qr_size, qr_size), Image.Resampling.NEAREST)
    img.paste(qr, (qx0, qy0))
    draw.rounded_rectangle((qx0 - 4, qy0 - 4, qx0 + qr_size + 4, qy0 + qr_size + 4), radius=14, outline=_EDGE, width=3)
    draw.text((qx0 + qr_size / 2, qy0 + qr_size + 22), "SCAN TO CHECK", font=_display(36), fill=_INK, anchor="ma")

    # -- the name, set like the back of a shirt -------------------------------
    lines, name_font = _fit_name(draw, subject.full_name, qx0 - 40 - CONTENT_X)
    y = 230.0
    for line in lines:
        draw.text((CONTENT_X, y), line, font=name_font, fill=_INK)
        y += name_font.size * 0.98
    y += 24
    # Position on one line, place on the next: the same as the on-screen card.
    if subject.playing_position:
        draw.text((CONTENT_X, y), subject.playing_position, font=_body(38, bold=True), fill=_INK)
        y += 52
    draw.text((CONTENT_X, y), f"{subject.lga_name}, {subject.state_name}", font=_body(38), fill=_MUTED)

    # -- the issuing line and the scoreboard strip ----------------------------
    strip_y0, strip_y1 = H - 230, H - 60
    draw.text((CONTENT_X, strip_y0 - 26), "Issued by KAFRIADA NET · Federation of Nigerian Sports",
              font=_body(30, bold=True), fill=_INK, anchor="ls")
    draw.rounded_rectangle((CONTENT_X, strip_y0, RIGHT, strip_y1), radius=18, fill=_INK)
    _tracked(draw, (CONTENT_X + 34, strip_y0 + 28), "KAFRIADA NET ID", _body(26, bold=True), _PLATE, 5)
    kuid_font = _mono(64)
    while draw.textlength(subject.kuid, font=kuid_font) + 3 * len(subject.kuid) > RIGHT - CONTENT_X - 68 and kuid_font.size > 36:
        kuid_font = _mono(kuid_font.size - 2)
    _tracked(draw, (CONTENT_X + 34, strip_y0 + 74), subject.kuid, kuid_font, _PLATE, 3)

    # -- the card edge --------------------------------------------------------
    mask = Image.new("L", (W, H), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, W - 1, H - 1), radius=RADIUS, fill=255)
    framed = Image.new("RGB", (W, H), _PLATE)
    framed.paste(img, (0, 0), mask)
    ImageDraw.Draw(framed).rounded_rectangle((1, 1, W - 2, H - 2), radius=RADIUS, outline=_EDGE, width=4)

    buffer = io.BytesIO()
    if fmt == "png":
        framed.save(buffer, format="PNG", optimize=True)
    else:
        framed.save(buffer, format="PDF", resolution=300.0)
    return buffer.getvalue()
