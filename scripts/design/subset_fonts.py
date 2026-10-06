"""Cut the web fonts down to what KAFRIADA NET prints.

    pip install fonttools brotli
    python scripts/design/subset_fonts.py

Reads the static TTFs in web/assets/fonts and writes woff2 files to
web/assets/fonts/web: one "latin" file per face (preloaded) and one
"extended" file (Latin Extended, including the Hausa hooked letters
Ɓ ɓ Ɗ ɗ Ƙ ƙ Ƴ ƴ and ʼ) that browsers fetch only when a page uses one of those
characters. The ID font keeps only what an ID, code or phone number uses.
Hinting is dropped: it is most of the weight and phones render
these sizes well without it. The ranges must match LATIN and EXTENDED in
web/src/app/fonts.ts.
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "web" / "assets" / "fonts"
OUT = ROOT / "web"

LATIN = "U+0020-007E,U+00A0-00FF,U+2013-2014,U+2018-201A,U+201C-201E,U+2022,U+2026,U+20A6"
EXTENDED = "U+0100-024F,U+02BC,U+1E00-1EFF"
# The ID font sets only KUIDs, codes, references and phone digits.
ID_CHARS = "U+0020,U+002B,U+002D,U+002E,U+0030-0039,U+0041-005A,U+00B7"

FACES = {
    "FiraSansCondensed-ExtraBoldItalic": "display-800i",
    "Andika-Regular": "body-400",
    "Andika-Bold": "body-700",
    "GeistMono-Medium": "mono-500",
}


def subset(src: Path, unicodes: str, out: Path) -> None:
    subprocess.run(
        [
            sys.executable, "-m", "fontTools.subset", str(src),
            f"--unicodes={unicodes}", "--flavor=woff2", "--no-hinting", "--desubroutinize",
            "--layout-features=kern,liga,tnum,zero", "--name-IDs=1,2,4,6", f"--output-file={out}",
        ],
        check=True,
    )


OUT.mkdir(exist_ok=True)
for ttf, stem in FACES.items():
    parts = (("latin", ID_CHARS),) if stem.startswith("mono") else (("latin", LATIN), ("extended", EXTENDED))
    for part, unicodes in parts:
        out = OUT / f"{stem}-{part}.woff2"
        subset(ROOT / f"{ttf}.ttf", unicodes, out)
        print(f"{out.name:28s} {out.stat().st_size:7d} bytes")
