"""Trace the raster logo into SVG paths, one per colour, split figure / wordmark.

    pip install potracer numpy pillow
    python scripts/design/trace_logo.py docs/design/logo-kafriada-net.png <out-dir>
    python scripts/design/build_logo.py <out-dir>/logo-trace.json web
"""
import sys, os
import numpy as np
from PIL import Image
import potrace

SRC = sys.argv[1]
OUT = sys.argv[2]
img = np.asarray(Image.open(SRC).convert("RGB")).astype(int)
H, W, _ = img.shape

# The baked-in black bars: find the white band.
row_white = (img.mean(axis=2) > 200).mean(axis=1)
band = np.where(row_white > 0.5)[0]
top, bot = band.min(), band.max()
img = img[top:bot + 1]
r, g, b = img[..., 0], img[..., 1], img[..., 2]

green = (g > 120) & (r < 120) & (b < 120)
red = (r > 150) & (g < 90) & (b < 90)
# Dark: everything dark that is not clearly green or red (includes the red's shadowed edge).
black = (img.max(axis=2) < 110) & ~green

# Columns: the figure is left of the gap before the wordmark.
cols = (green | red | black).any(axis=0)
xs = np.where(cols)[0]
gaps = [(xs[i], xs[i + 1]) for i in range(len(xs) - 1) if xs[i + 1] - xs[i] > 12]
split = gaps[0][0] + (gaps[0][1] - gaps[0][0]) // 2 if gaps else W // 3
print("crop rows", top, bot, "split at", split, "gaps", gaps[:3])


def trace(mask):
    bm = potrace.Bitmap(~mask.astype(bool))  # potracer fills the False pixels
    plist = bm.trace(turdsize=12, alphamax=1.0, opticurve=True, opttolerance=0.3)
    d = []
    for curve in plist:
        s = curve.start_point
        d.append(f"M{s.x:.1f} {s.y:.1f}")
        for seg in curve.segments:
            if seg.is_corner:
                d.append(f"L{seg.c.x:.1f} {seg.c.y:.1f}L{seg.end_point.x:.1f} {seg.end_point.y:.1f}")
            else:
                d.append(f"C{seg.c1.x:.1f} {seg.c1.y:.1f} {seg.c2.x:.1f} {seg.c2.y:.1f} {seg.end_point.x:.1f} {seg.end_point.y:.1f}")
        d.append("Z")
    return "".join(d)


def bbox(*masks):
    m = np.zeros_like(masks[0])
    for k in masks:
        m |= k
    ys, xs = np.where(m)
    return xs.min(), ys.min(), xs.max() + 1, ys.max() + 1


def region(mask, x0, x1):
    out = np.zeros_like(mask)
    out[:, x0:x1] = mask[:, x0:x1]
    return out


fig = [region(m, 0, split) for m in (green, red, black)]
word = region(black, split, W)
# Tagline is the lower text block inside the wordmark region.
wy = np.where(word.any(axis=1))[0]
wgaps = [(wy[i], wy[i + 1]) for i in range(len(wy) - 1) if wy[i + 1] - wy[i] > 8]
ysplit = wgaps[0][0] + 1 if wgaps else None
name = word.copy(); tag = word.copy()
if ysplit:
    name[ysplit:] = False; tag[:ysplit] = False
print("wordmark/tagline split at y", ysplit)

paths = {
    "fig_green": trace(fig[0]), "fig_red": trace(fig[1]), "fig_black": trace(fig[2]),
    "name": trace(name), "tag": trace(tag),
}
boxes = {
    "figure": bbox(*fig), "name": bbox(name), "tag": bbox(tag), "all": bbox(*fig, word),
}
os.makedirs(OUT, exist_ok=True)
import json
json.dump({"paths": paths, "boxes": {k: [int(v) for v in b] for k, b in boxes.items()}},
          open(os.path.join(OUT, "logo-trace.json"), "w"))
print({k: len(v) for k, v in paths.items()}, boxes)
