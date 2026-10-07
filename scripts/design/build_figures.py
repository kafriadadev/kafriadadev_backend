"""Write the hairline figures (layer 2, "delight") to web/public/figures/.

The brand's running figure, taken from the logo itself, redrawn as a fine outline and set
into the scenes of the empty states, plus a large one for the landing page. They are
loaded only by web/public/delight.js, when the browser is idle, on a capable device; the
plain illustrations in components/illustrations stay for everyone else.

Every class and keyframe is prefixed hf-: an SVG inlined into a page carries its <style>
into the whole document. Reduced motion is honoured inside each file as well.

    python scripts/design/build_figures.py
"""
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LOGO = os.path.join(ROOT, "web", "src", "components", "brand", "Logo.tsx")
OUT = os.path.join(ROOT, "web", "public", "figures")

src = open(LOGO, encoding="utf8").read()
P = {k: re.search(k + r' = "(.*?)"', src).group(1) for k in ("FIG_BLACK", "FIG_RED", "FIG_GREEN")}
# The mark's box in logo units (Logo.tsx, variant "mark").
FX, FY, FW, FH = 32, 113, 431, 476

# The draw-in dash covers the longest outline of the figure (1570 units, measured with
# getTotalLength in Edge).
STYLE = """
.hf-line{fill:none;stroke:currentColor;stroke-width:1;stroke-linecap:round;stroke-linejoin:round}
.hf-soft{stroke-opacity:.35}
.hf-fig path{fill:none;stroke-linejoin:round;stroke-dasharray:1600;animation:hf-draw 1.6s cubic-bezier(.65,0,.35,1) both}
.hf-fig .hf-k{stroke:currentColor}.hf-fig .hf-r{stroke:var(--kit-red,#EB0002)}.hf-fig .hf-g{stroke:var(--pitch,#0EAD2C)}
.hf-in{animation:hf-in .9s cubic-bezier(.2,.8,.2,1) .2s both}
.hf-ball{animation:hf-roll 1.4s cubic-bezier(.2,.8,.2,1) .9s both}
.hf-sway{transform-box:fill-box;transform-origin:top center;animation:hf-sway 3.2s ease-in-out 2.3s 2 both}
.hf-rise{animation:hf-rise 3.6s ease-in-out 1.6s infinite alternate}
@keyframes hf-draw{from{stroke-dashoffset:1600}to{stroke-dashoffset:0}}
@keyframes hf-in{from{opacity:0;transform:translateX(14px)}to{opacity:1;transform:none}}
@keyframes hf-roll{from{transform:translateX(26px) rotate(240deg);opacity:0}to{transform:none;opacity:1}}
@keyframes hf-sway{0%,100%{transform:none}50%{transform:skewX(-2deg)}}
@keyframes hf-rise{from{transform:translateY(0)}to{transform:translateY(-3px)}}
@media (prefers-reduced-motion:reduce){.hf-fig path,.hf-in,.hf-ball,.hf-sway,.hf-rise{animation:none}}
"""


def figure(x: float, y: float, height: float, line: float = 1.1) -> str:
    """The runner, `height` units tall, its top-left corner at (x, y), outlined `line` units thick."""
    s = height / FH
    return (
        f'<g class="hf-fig" stroke-width="{line / s:.1f}" transform="translate({x:g} {y:g}) scale({s:.4f}) translate({-FX} {-FY})">'
        f'<path class="hf-k" d="{P["FIG_BLACK"]}"/><path class="hf-r" d="{P["FIG_RED"]}"/>'
        f'<path class="hf-g" d="{P["FIG_GREEN"]}"/></g>'
    )


def svg(view: str, body: str) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{view}" aria-hidden="true" focusable="false">'
        f"<style>{STYLE.strip()}</style>{body}</svg>\n"
    )


ground = '<path class="hf-line hf-soft" d="M8 108H152"/>'
ball = lambda cx, cy: (  # noqa: E731
    f'<g class="hf-ball"><circle class="hf-line" cx="{cx}" cy="{cy}" r="5"/>'
    f'<path class="hf-line" d="M{cx} {cy - 2}l2 1.5-.8 2.3h-2.4l-.8-2.3z" stroke-width=".8"/></g>'
)

# No results: the runner arrives at an empty goal, the ball rolls in, the net gives.
mesh = "".join(f'<path d="M{x} 30L{x + (x - 80) * 0.12:g} 104"/>' for x in range(40, 121, 10))
mesh += "".join(f'<path d="M32 {y}H128"/>' for y in range(40, 101, 10))
net = svg(
    "0 0 160 120",
    ground
    + f'<g class="hf-line hf-soft hf-sway">{mesh}</g>'
    + '<path class="hf-line" d="M30 108V26H130V108" stroke-width="1.6"/>'
    + ball(112, 103)
    + f'<g class="hf-in">{figure(128, 58, 50)}</g>',
)

# No players yet: the bench under its shelter, and the first player running up to it.
seats = "".join(f'<path d="M{x - 10} 80V64H{x + 6}V80"/>' for x in (46, 72, 98, 124))
bench = svg(
    "0 0 160 120",
    ground
    + '<g class="hf-line"><path d="M16 46Q80 10 144 46"/><path d="M24 42V108M136 42V108"/>'
    + '<path d="M30 80H130M30 80V96M130 80V96"/></g>'
    + f'<g class="hf-line hf-soft">{seats}</g>'
    + f'<g class="hf-in">{figure(6, 58, 50)}</g>',
)

# No clubs yet: the bare kit rail, and a player waiting for a shirt.
hangers = "".join(f'<path d="M{x} 24v8a5 5 0 1 1 -5 5"/>' for x in (54, 80, 106))
rail = svg(
    "0 0 160 120",
    ground
    + f'<g class="hf-line"><path d="M20 24H140M30 24V108M130 24V108"/>{hangers}</g>'
    + f'<g class="hf-in">{figure(62, 52, 56)}</g>',
)

# The landing page: the runner large, inside a chalk centre circle, rising gently.
hero = svg(
    "0 0 240 240",
    '<circle class="hf-line hf-soft" cx="120" cy="128" r="96"/>'
    + '<path class="hf-line hf-soft" d="M8 128H232"/>'
    + '<circle class="hf-line" cx="120" cy="128" r="2" fill="currentColor"/>'
    + f'<g class="hf-rise">{figure(58, 20, 196, 0.9)}</g>',
)

os.makedirs(OUT, exist_ok=True)
for name, text in (("net", net), ("bench", bench), ("rail", rail), ("hero", hero)):
    open(os.path.join(OUT, f"{name}.svg"), "w", encoding="utf8", newline="\n").write(text)
    print(name, len(text.encode()), "bytes")
