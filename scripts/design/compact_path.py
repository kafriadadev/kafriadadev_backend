"""Shrink a traced SVG path for inlining: whole units, relative commands, no spare separators.

The traced logo is drawn in a 1472-unit-wide box and shown about 32 px tall, so one unit
is a fifteenth of a pixel; tenths of a unit cannot be seen. Relative coordinates are
shorter still. Used by build_logo.py for the inline React component; the SVG files keep
full precision.

    python scripts/design/compact_path.py web/src/components/brand/Logo.tsx   # rewrite in place
"""
import re
import sys

TOKEN = re.compile(r"[MCLZmclz]|-?\d*\.?\d+")


def compact(d: str) -> str:
    out, cx, cy, sx, sy = [], 0, 0, 0, 0
    tokens = TOKEN.findall(d)
    i, cmd = 0, None
    while i < len(tokens):
        t = tokens[i]
        if t.isalpha():
            cmd, i = t, i + 1
            if cmd in "Zz":
                out.append("z")
                cx, cy = sx, sy
            continue
        n = {"M": 2, "L": 2, "C": 6}[cmd]
        nums = [round(float(x)) for x in tokens[i:i + n]]
        i += n
        rel = [v - (cx if k % 2 == 0 else cy) for k, v in enumerate(nums)]
        out.append(cmd.lower() + _join(rel))
        cx, cy = nums[-2], nums[-1]
        if cmd == "M":
            sx, sy = cx, cy
            cmd = "L"  # further pairs after a move are lines
    return "".join(out)


def _join(nums: list[int]) -> str:
    s = ""
    for k, v in enumerate(nums):
        s += str(v) if k == 0 or v < 0 else " " + str(v)
    return s


if __name__ == "__main__":
    path = sys.argv[1]
    src = open(path, encoding="utf8").read()
    src = re.sub(r'(const \w+ = ")([^"]*)(";)', lambda m: m.group(1) + compact(m.group(2)) + m.group(3), src)
    open(path, "w", encoding="utf8", newline="\n").write(src)
