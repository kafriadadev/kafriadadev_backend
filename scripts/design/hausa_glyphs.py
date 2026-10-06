"""Do the chosen Google fonts actually contain the Hausa hooked letters?

    pip install fonttools brotli
    PYTHONIOENCODING=utf-8 python scripts/design/hausa_glyphs.py
"""
import io, os, re, sys, urllib.request
from fontTools.ttLib import TTFont

HAUSA = {"Ɓ": 0x181, "ɓ": 0x253, "Ɗ": 0x18A, "ɗ": 0x257, "Ƙ": 0x198, "ƙ": 0x199, "Ƴ": 0x1B3, "ƴ": 0x1B4, "ʼ": 0x2BC}
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36"
FAMILIES = {
    "Noto Sans:ital,wght@1,800": "Noto+Sans:ital,wght@1,800",
    "Noto Sans:wght@400": "Noto+Sans:wght@400",
    "Andika:wght@400": "Andika:wght@400",
    "Roboto Condensed:ital,wght@1,800": "Roboto+Condensed:ital,wght@1,800",
    "Sofia Sans Condensed:ital,wght@1,800": "Sofia+Sans+Condensed:ital,wght@1,800",
    "Sofia Sans Extra Condensed:ital,wght@1,800": "Sofia+Sans+Extra+Condensed:ital,wght@1,800",
    "Archivo:ital,wght@1,800": "Archivo:ital,wght@1,800",
    "Fira Sans Condensed:ital,wght@1,800": "Fira+Sans+Condensed:ital,wght@1,800",
    "IBM Plex Sans Condensed:ital,wght@1,700": "IBM+Plex+Sans+Condensed:ital,wght@1,700",
    "Encode Sans Condensed:wght@800": "Encode+Sans+Condensed:wght@800",
    "Oswald:wght@700": "Oswald:wght@700",
    "Saira Condensed:wght@800": "Saira+Condensed:wght@800",
    "Inter:wght@400": "Inter:wght@400",
    "Roboto:wght@400": "Roboto:wght@400",
    "Lexend:wght@400": "Lexend:wght@400",
    "Figtree:wght@400": "Figtree:wght@400",
    "Public Sans:wght@400": "Public+Sans:wght@400",
    "Source Sans 3:wght@400": "Source+Sans+3:wght@400",
    "Noto Sans Mono:wght@500": "Noto+Sans+Mono:wght@500",
    "Roboto Mono:wght@500": "Roboto+Mono:wght@500",
    "JetBrains Mono:wght@500": "JetBrains+Mono:wght@500",
    "IBM Plex Mono:wght@500": "IBM+Plex+Mono:wght@500",
    "Fira Mono:wght@500": "Fira+Mono:wght@500",
    "Source Code Pro:wght@500": "Source+Code+Pro:wght@500",
    "Red Hat Mono:wght@500": "Red+Hat+Mono:wght@500",
    "Atkinson Hyperlegible Mono:wght@500": "Atkinson+Hyperlegible+Mono:wght@500",
    "Space Mono:wght@400": "Space+Mono:wght@400",
    "Barlow:ital,wght@1,800": "Barlow:ital,wght@1,800",
    "Big Shoulders Display:wght@800": "Big+Shoulders+Display:wght@800",
    "Anton:wght@400": "Anton:wght@400",
    "Mona Sans:ital,wght@1,800": "Mona+Sans:ital,wght@1,800",
    "Hubot Sans:ital,wght@1,800": "Hubot+Sans:ital,wght@1,800",
    "Instrument Sans:wght@400": "Instrument+Sans:wght@400",
    "Manrope:wght@400": "Manrope:wght@400",
    "Plus Jakarta Sans:wght@400": "Plus+Jakarta+Sans:wght@400",
}
text = "".join(HAUSA)
for name, fam in FAMILIES.items():
    url = f"https://fonts.googleapis.com/css2?family={fam}&display=swap"
    try:
        css = urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=30).read().decode()
    except Exception as e:
        print(name, "unavailable", e); continue
    srcs = re.findall(r"url\((https://[^)]+)\)", css)
    have = set()
    for s in srcs:
        data = urllib.request.urlopen(urllib.request.Request(s, headers={"User-Agent": UA}), timeout=30).read()
        have |= set(TTFont(io.BytesIO(data)).getBestCmap())
    missing = [ch for ch, cp in HAUSA.items() if cp not in have]
    print(f"{name:32s} {'all present' if not missing else 'MISSING ' + ' '.join(missing)}")
