#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2026 Devin Heitmueller <devin.heitmueller@gmail.com>
"""The annotated screenshot of the README (images/test-pattern-720p59.png): a frame of one card of the 720p59 stream
with the numbered callouts that the README explains.

The frame is drawn by the same code as the video (build.py): the card number, the test counter, the timer and the
text of the banner all come from the schedule, so they follow the cards when they change. The card is chosen by its id
(G02), not by its number. The callouts are placed from the layout of the frame (the end of each line of the banner,
the safe area, the grid, the outlines).

  python screenshot.py                 write images/test-pattern-720p59.png
  python screenshot.py --check         exit 1 if the committed image does not show the current cards (see below)
  options: --card G02  --at 2.0 (seconds into the card)  --out FILE  --version-label LABEL

The image has the data it was made from in a PNG text chunk (card id, test number and count, time into the card, the text
of the banner). --check compares it with the current cards, not the pixels, so it does not depend on the fonts of the
machine, and it does not look at the version label. Change LAYOUT when the drawing of the frame or of the callouts changes.
For the look of the released streams build on Linux or point CEA608_FONT and CEA608_FONT_BOLD at DejaVu Sans.
"""
import argparse
import json
import os
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont, PngImagePlugin

import build
import testplan
from cea608 import sec2f

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_OUT = os.path.join(HERE, "images", "test-pattern-720p59.png")
FORMAT = "720p59"
LAYOUT = 1                  # bump when the drawing of the frame or of the callouts changes
TEXT_KEY = "CEA608-screenshot"
ORANGE, BLACK = (255, 150, 0), (0, 0, 0)


def data_of(card, at, label=None):
    """What the image shows, without drawing it: {card, test, count, at, banner}; also the schedule (for the picture)."""
    testplan.apply_format(FORMAT)
    build.VERSION[0] = label or build.git_version()
    f1, f2, starts, total, _ = build.schedule()
    ids = [s.id for s in build.SEGMENTS]
    if card not in ids:
        sys.exit(f"no card {card} in the plan; the cards are {', '.join(ids)}")
    si = ids.index(card)
    seg = build.SEGMENTS[si]
    # the third line of a card that has no reference shows the version label: it is not what the image is checked on
    banner = list(build.banner_lines(seg)) if seg.refs else list(build.banner_lines(seg))[:2]
    data = {"layout": LAYOUT, "format": FORMAT, "card": card, "test": f"{si + 1}/{len(ids)}", "at": at, "banner": banner}
    return data, si, seg, starts


def textlen(draw, text, font):
    return draw.textlength(text, font=font)


def callouts(w, h, seg, si, n, tl, timer):
    """[(number, x, y)] of the nine callouts of the README, placed from the layout of the 16:9 frame (build.py)."""
    k = w / 1920
    d = ImageDraw.Draw(Image.new("RGB", (w, h)))
    mw = w - 40 * k
    l1, l2, l3 = build.banner_lines(seg)
    f1 = build.fit(d, l1, build.FONT_B, int(34 * k), mw)
    f2 = build.fit(d, l2, build.FONT_U, int(25 * k), mw)
    f3 = build.fit(d, l3, build.FONT_U, int(21 * k), mw)
    gap = 19 * k * 1.5
    bot = int(88 * k)
    out = [
        (1, 20 * k + textlen(d, l1, f1) + gap, 4 * k + f1.size * 0.62),
        (2, 20 * k + textlen(d, l2, f2) + gap, 44 * k + f2.size * 0.62),
        (3, 20 * k + textlen(d, l3, f3) + gap, 76 * k + f3.size * 0.62),
        (4, 1536 * k, h / 2),                                         # right edge of the safe area (green)
        (5, 384 * k - 44 * k * 1.5, h / 2),                           # the row numbers, left of the grid
        (6, 1728 * k - 16 * k * 1.5, h / 2 + 60 * k * 1.5),           # right edge of the 80% outline (cyan)
    ]
    tfont = ImageFont.truetype(build.FONT_B, tl["size"])
    out.append((7, tl["origin"][0] + textlen(d, timer, tfont) + gap, h - bot + 8 * k + tfont.size * 0.55))
    right = f"{build.VERSION[0]}   test {si + 1}/{n}"
    rfont = build.fit(d, right, build.FONT_B, int(30 * k), w - 1130 * k)
    out.append((8, w - 20 * k - textlen(d, right, rfont) - gap, h - bot + 8 * k + rfont.size * 0.55))
    ft = build.footer()
    ffont = build.fit(d, ft, build.FONT_U, int(23 * k), mw)
    out.append((9, (w + textlen(d, ft, ffont)) / 2 + gap, h - 34 * k + ffont.size * 0.55))
    return out


def draw_callouts(img, points, w):
    k = w / 1920
    r = 15 * k
    d = ImageDraw.Draw(img)
    font = ImageFont.truetype(build.FONT_B, int(22 * k))
    for num, x, y in points:
        d.ellipse([x - r, y - r, x + r, y + r], fill=ORANGE, outline=BLACK, width=max(1, int(2 * k)))
        s = str(num)
        d.text((x - textlen(d, s, font) / 2, y - font.size * 0.55), s, font=font, fill=BLACK)


def render(card, at, label):
    data, si, seg, starts = data_of(card, at, label)
    fmt = build.FORMATS[FORMAT]
    cw, ch = fmt["canvas"]
    n = len(build.SEGMENTS)
    base, tl = build.make_base_16x9(build.graticule_16x9(cw, ch), seg, si, n, cw, ch)
    ppf = fmt["ppf"]
    vn, vd = fmt["vfps"]
    f0 = ppf * sec2f(starts[si])
    f = ppf * sec2f(starts[si] + at)
    timer = build.timer_text(f, f0, vn, vd)
    x0, y0, x1, y1 = tl["box"]
    frame = build.draw_timer(base, Image.fromarray(base[y0:y1, x0:x1]), tl, ImageFont.truetype(build.FONT_B, tl["size"]), timer)
    img = Image.fromarray(np.asarray(frame))
    draw_callouts(img, callouts(cw, ch, seg, si, n, tl, timer), cw)
    return img, data


def png_info(data):
    info = PngImagePlugin.PngInfo()
    info.add_text(TEXT_KEY, json.dumps(data, sort_keys=True, ensure_ascii=False))
    return info


def check(path, card, at):
    """0 if the image at path was made from the current cards, else 1 (with the differences printed)."""
    if not os.path.exists(path):
        print(f"{path} does not exist; run python screenshot.py")
        return 1
    data, *_ = data_of(card, at)
    with Image.open(path) as im:
        raw = im.text.get(TEXT_KEY) if hasattr(im, "text") else None
    if raw is None:
        print(f"{path} has no {TEXT_KEY} data; run python screenshot.py")
        return 1
    have = json.loads(raw)
    diffs = [f"  {k}: image {have.get(k)!r}, cards {data.get(k)!r}" for k in sorted(set(have) | set(data))
             if have.get(k) != data.get(k)]
    if diffs:
        print(f"{path} is out of date (run python screenshot.py and commit it):")
        print("\n".join(diffs))
        return 1
    print(f"{path} shows the current card {card} ({data['test']})")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--card", default="G02", help="id of the card to show (default G02)")
    ap.add_argument("--at", type=float, default=2.0, help="seconds into the card (default 2.0)")
    ap.add_argument("--out", default=DEFAULT_OUT)
    ap.add_argument("--version-label", default=None,
                    help="the version burned in the frame (default: git tag at HEAD, else git rev); not checked")
    ap.add_argument("--check", action="store_true", help="only check that the committed image is current")
    a = ap.parse_args()
    if a.check:
        return check(a.out, a.card, a.at)
    img, data = render(a.card, a.at, a.version_label)
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    img.save(a.out, pnginfo=png_info(data), optimize=True)
    print(f"wrote {a.out}: card {a.card}, test {data['test']}, {a.at:g} s into the card")
    return 0


if __name__ == "__main__":
    sys.exit(main())
