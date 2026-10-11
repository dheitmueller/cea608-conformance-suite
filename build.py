#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2026 Devin Heitmueller <devin.heitmueller@gmail.com>
"""Build the CEA-608 Conformance Suite test stream (MPEG-TS).

  python build.py [--format 720p59|480i59] [--codec h264|mpeg2] [--out out/X.ts]
                  [--no-caption-descriptor] [--size WxH] [--version-label TEXT]

Two formats: 720p59 (1280x720 progressive 59.94, 16:9) and 480i59 (720x480 interlaced 59.94 fields,
4:3 anamorphic).  Captions keep their native line-21 timeline of 29.97 pairs/s per field.
  720p59: picture n carries field 1 pair n//2 (even n) or field 2 pair n//2 (odd n) - one NTSC pair per
          picture, as CEA-CEB-10-A 25.2.2 describes for 60 Hz frame rates (cc_count 10).
  480i59: each frame carries both field pairs, field-2 pair first for top-field-first video
          (CEA-CEB-10-A Annex B), cc_count 20.

Pipeline (no intermediate caption file yet - see DEVELOPING.md "How the stream is made"):
  testplan.py scripts -> per-field byte-pair arrays (one pair per 29.97 Hz frame)   [in memory]
  -> render graticule + labels (Pillow) -> encode (ffmpeg)
  -> inject A/53 cc_data in display order -> mux with AC-3
  -> patch PMT with the ATSC caption_service_descriptor.
Needs ffmpeg, Pillow, numpy.

"""
import argparse
import json
import os
import re
import struct
import subprocess
import sys
import tempfile

import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from cea608 import Chan, Field, FPS_D, FPS_N, R, burst_pairs, parity, sec2f  # noqa: E402

# Output formats.  canvas = square-pixel drawing size; coded = what is encoded (480i59 is anamorphic:
# the 640x480 canvas is scaled to 720x480 with pixel aspect ratio 8:9, display aspect ratio 4:3).
FORMATS = {
    "720p59": dict(canvas=(1280, 720), vfps=(60000, 1001), ppf=2, interlaced=False, dar="16:9",
                   gop=30, kind="16x9", cc_count=10, level="3.2"),
    "480i59": dict(canvas=(640, 480), vfps=(30000, 1001), ppf=1, interlaced=True, dar="4:3",
                   gop=15, kind="4x3", cc_count=20, level="3.0"),
}
# (ppf = video pictures per 29.97 Hz caption frame)
from testplan import SEGMENTS  # noqa: E402

META = dict(name="CEA-608 Conformance Suite", author="Devin Heitmueller",
            year=2026, license="CC BY-SA 4.0",
            license_url="https://creativecommons.org/licenses/by-sa/4.0/",
            repo_url="https://github.com/dheitmueller/cea608-conformance-suite")
VERSION = ["unversioned"]          # set in main(): git tag if HEAD is tagged, else git rev
TS_BITRATE = 4_000_000             # constant transport-stream rate (null-packet padded)
VIDEO_BITRATE = 3_500_000          # video CBR inside it; AC-3 128 kbps + TS overhead fill the rest


def git_version():
    """Git tag if HEAD has one (exact match), else short rev; '+dirty' if the tree has changes."""
    def git(*a):
        r = subprocess.run(["git", "-C", HERE, *a], capture_output=True, text=True)
        return r.stdout.strip() if r.returncode == 0 else None
    if git("rev-parse", "--is-inside-work-tree") != "true":
        return "unversioned"
    label = git("describe", "--tags", "--exact-match", "HEAD") or git("rev-parse", "--short=10", "HEAD")
    if label and git("status", "--porcelain", "--untracked-files=no"):
        label += "+dirty"
    return label or "unversioned"


def footer():
    return (f"{META['name']} {VERSION[0]}  |  (c) {META['year']} {META['author']}  |  "
            f"{META['license']}  |  creativecommons.org/licenses/by-sa/4.0")


def footer_short():
    return f"{META['name']} {VERSION[0]}  |  (c) {META['year']} {META['author']}  |  {META['license']}"


LEVEL_ABBR = [("CTA-608-E ", "608-E "), ("CEA-CEB-10-A ", "10-A "), ("10A-RECOMMENDATION", "10A-REC"),
              ("UNSPECIFIED", "UNSPEC"), ("REGULATORY", "REG"), ("NORMATIVE", "NORM"), ("PREFERRED", "PREF"),
              ("OPTIONAL", "OPT"), ("RECOMMENDED", "REC"), ("INFORMATIVE", "INFO")]


def abbreviate(text):
    for a, b in LEVEL_ABBR:
        text = text.replace(a, b)
    return text


def find_font(env, candidates):
    """First existing font among $env and the candidate paths (macOS, Linux)."""
    for p in [os.environ.get(env, "")] + candidates:
        if p and os.path.exists(p):
            return p
    raise SystemExit(f"no usable font found; set {env} to a .ttf with the Latin-1 and symbol glyphs "
                     f"(e.g. DejaVu Sans)")


FONT_B = find_font("CEA608_FONT_BOLD", [
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"])
FONT_U = find_font("CEA608_FONT", [
    "/Library/Fonts/Arial Unicode.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"])
NULLP = (parity(0), parity(0))
# Cards where the periodic CC2/CC4 label must not be interleaved (they test pure null/hold,
# loss of data, redundant-pair adjacency, or use CC2/CC4 themselves).
# Card H01 uses CC2/CC4 itself: its test lines ride on the label bursts (see add_labels).
# Card S02 tests "hold on valid nulls", so its label refresh is sparse (every 8 s, below the ~10 s
# idle timeout some decoders apply) to keep the stream mostly nulls.
SPARSE_LABEL = {"S02": 240}
H01_LINES = {"CC2": R(6, "CC2: field 1, data channel 2"), "CC4": R(11, "CC4: field 2, data channel 2")}


# ------------------------------------------------------------ scheduling
def schedule():
    f1, f2 = Field(0), Field(1)
    # 608-E D.2 p.78: double control codes (field 1); B.14 p.70: not on field 2.
    chans = {"CC1": Chan("CC1", f1, 1, double=True), "CC2": Chan("CC2", f1, 2, double=True),
             "CC3": Chan("CC3", f2, 1, double=False), "CC4": Chan("CC4", f2, 2, double=False)}
    t = 0.0
    starts = []
    for s in SEGMENTS:
        starts.append(t)
        if s.chans == "1234":
            s.fn(chans, t)
        else:
            for n in s.chans:
                s.fn(chans[f"CC{n}"], t)
        t += s.dur
    total = sec2f(t)
    for f in (f1, f2):
        f.pad_to(max(total, f.cursor))
    n_labels = add_labels(f1, f2, chans, starts, total)
    return f1, f2, starts, total, n_labels


def add_labels(f1, f2, chans, starts, total):
    """Persistent 'Rendering on CC2/CC4' label, refreshed every ~2 s in idle gaps so it is present
    from any seek point.  Bursts only go into runs of valid nulls that are followed by a control code,
    so a channel switch can never swallow following bare text and adjacent-code tests stay intact."""
    wins = {s.id: (sec2f(t), sec2f(t + s.dur)) for s, t in zip(SEGMENTS, starts)}
    count = 0
    for fld, name in ((f1, "CC2"), (f2, "CC4")):
        ch = chans[name]
        label = burst_pairs(ch, [R(3, f"Rendering on {name}", col=(32 - 16) // 2 + 1)])
        h01 = burst_pairs(ch, [R(3, f"Rendering on {name}", col=(32 - 16) // 2 + 1), H01_LINES[name]])
        p = fld.pairs
        i = 0
        while i < len(p):
            if p[i] != NULLP:
                i += 1
                continue
            j = i
            while j < len(p) and p[j] == NULLP:
                j += 1
            nxt_ok = j >= len(p) or (p[j] is not None and 0x10 <= (p[j][0] & 0x7F) <= 0x1F)
            pos = i + 6
            while nxt_ok and pos + len(label) + 8 <= j:
                in_h01 = wins["H01"][0] <= pos < wins["H01"][1]
                burst = h01 if in_h01 else label
                if pos + len(burst) + 8 > j:
                    break
                step = 60
                for cid, st in SPARSE_LABEL.items():
                    if wins[cid][0] <= pos < wins[cid][1]:
                        step = st
                p[pos:pos + len(burst)] = burst
                count += 1
                pos += step
            i = j
    return count


# ------------------------------------------------------------ video
def fit(draw, text, path, size, maxw):
    while True:
        font = ImageFont.truetype(path, size)
        if draw.textlength(text, font=font) <= maxw or size < 10:
            return font
        size -= 1


def graticule_16x9(w, h):
    """Dark graticule with the FCC safe caption area (608-E C.22 p.77, Table 46), the 4:3
    picture, a 15-row x 32-column grid, and the 80% box of the 16:9 frame."""
    k = w / 1920
    img = Image.new("RGB", (w, h), (38, 44, 52))
    d = ImageDraw.Draw(img)
    s = lambda v: v * k  # noqa: E731
    lab = ImageFont.truetype(FONT_U, int(s(20)))
    small = ImageFont.truetype(FONT_U, int(s(16)))
    # 4:3 picture box (1440x1080 centered in 1920x1080)
    px0, px1 = s(240), s(1680)
    d.rectangle([px0, 0, px1, h - 1], outline=(110, 120, 130), width=max(1, int(s(2))))
    # FCC safe caption area: 80% x 80% of the 4:3 picture
    sx0, sx1, sy0, sy1 = s(384), s(1536), s(108), s(972)
    rows, cols = 15, 32
    rh, cw = (sy1 - sy0) / rows, (sx1 - sx0) / cols
    for r in range(rows + 1):
        y = sy0 + r * rh
        d.line([sx0, y, sx1, y], fill=(70, 82, 94), width=1)
    for c in range(cols + 1):
        x = sx0 + c * cw
        major = c % 4 == 0
        d.line([x, sy0, x, sy1], fill=(70, 82, 94) if not major else (90, 104, 118), width=1)
    for r in range(rows):
        t = str(r + 1)
        d.text((sx0 - s(10) - d.textlength(t, font=lab), sy0 + r * rh + rh / 2 - s(11)), t, font=lab,
               fill=(150, 200, 150))
    for c in range(0, cols, 4):
        t = str(c + 1)
        d.text((sx0 + c * cw + s(2), sy1 + s(4)), t, font=small, fill=(150, 200, 150))
    d.text((sx1 - s(60), sy1 + s(4)), "32", font=small, fill=(150, 200, 150))
    d.rectangle([sx0, sy0, sx1, sy1], outline=(60, 220, 90), width=max(2, int(s(3))))
    # 80% box of the full 16:9 frame (implementation-defined mapping)
    wx0, wx1 = s(192), s(1728)
    for x in range(int(wx0), int(wx1), int(s(16))):
        d.line([x, sy0, x + s(8), sy0], fill=(80, 190, 230), width=max(1, int(s(2))))
        d.line([x, sy1, x + s(8), sy1], fill=(80, 190, 230), width=max(1, int(s(2))))
    for y in range(int(sy0), int(sy1), int(s(16))):
        d.line([wx0, y, wx0, y + s(8)], fill=(80, 190, 230), width=max(1, int(s(2))))
        d.line([wx1, y, wx1, y + s(8)], fill=(80, 190, 230), width=max(1, int(s(2))))
    d.text((s(1556), s(120)), "green: FCC safe area", font=small, fill=(60, 220, 90))
    d.text((s(1556), s(142)), "(80% x 80% of 4:3)", font=small, fill=(60, 220, 90))
    d.text((s(1556), s(170)), "cyan: 80% of 16:9", font=small, fill=(80, 190, 230))
    d.text((s(1556), s(198)), "grey: 4:3 picture,", font=small, fill=(150, 160, 170))
    d.text((s(1556), s(220)), "15 rows x 32 cols", font=small, fill=(150, 160, 170))
    cx, cy = w / 2, h / 2
    d.line([cx - s(30), cy, cx + s(30), cy], fill=(120, 130, 140), width=1)
    d.line([cx, cy - s(30), cx, cy + s(30)], fill=(120, 130, 140), width=1)
    return img


def make_base_16x9(grat, seg, idx, n, w, h):
    k = w / 1920
    img = grat.copy().convert("RGBA")
    ov = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    top, bot = int(108 * k), int(88 * k)
    d.rectangle([0, 0, w, top], fill=(0, 0, 0, 225))
    d.rectangle([0, h - bot, w, h], fill=(0, 0, 0, 225))
    chans = seg.shown or {"1234": "CC1 CC2 CC3 CC4", "13": "CC1 + CC3"}.get(seg.chans, "")
    l1 = f"{seg.id}  {seg.title}" + (f"   [{chans}]" if chans else "")
    l2 = f"{seg.detail}   |   Expect: {seg.expect}"
    if seg.refs:
        l3 = "Ref: " + "   ·   ".join(f"{c} [{lv}]" for c, lv in seg.refs)
    else:
        l3 = f"{META['name']} {VERSION[0]}  ·  by {META['author']}  ·  {META['license']}"
    mw = w - 40 * k
    d.text((20 * k, 4 * k), l1, font=fit(d, l1, FONT_B, int(34 * k), mw), fill=(255, 255, 255, 255))
    d.text((20 * k, 44 * k), l2, font=fit(d, l2, FONT_U, int(25 * k), mw), fill=(255, 224, 102, 255))
    d.text((20 * k, 76 * k), l3, font=fit(d, l3, FONT_U, int(21 * k), mw), fill=(140, 215, 255, 255))
    ft = footer()
    ff = fit(d, ft, FONT_U, int(23 * k), mw)
    d.text(((w - d.textlength(ft, font=ff)) / 2, h - 34 * k), ft, font=ff, fill=(230, 230, 230, 255))
    right = f"{VERSION[0]}   test {idx + 1}/{n}"      # git version is always visible
    fnt = fit(d, right, FONT_B, int(30 * k), w - 1130 * k)
    d.text((w - 20 * k - d.textlength(right, font=fnt), h - bot + 8 * k), right, font=fnt, fill=(255, 224, 102, 255))
    if seg.id in ("G00", "Z99"):
        big = ImageFont.truetype(FONT_B, int(54 * k))
        mid = ImageFont.truetype(FONT_U, int(34 * k))
        lines = [(META["name"], big, (255, 255, 255)), (f"Version {VERSION[0]}", mid, (255, 224, 102)),
                 (f"Author: {META['author']}", mid, (255, 255, 255)),
                 (f"License: {META['license']} - attribution required; share alike", mid, (140, 215, 255)),
                 (META["repo_url"], mid, (255, 255, 255))]
        y = 330 * k
        for text, font, col in lines:
            d.text(((w - d.textlength(text, font=font)) / 2, y), text, font=font, fill=col + (255,))
            y += font.size * 1.5
    bot_ = int(88 * k)
    tl = dict(box=(0, h - bot_, int(1100 * k), h - bot_ + int(44 * k)), origin=(20 * k, 8 * k), size=int(30 * k))
    return np.asarray(Image.alpha_composite(img, ov).convert("RGB")).copy(), tl


def fit_text(draw, text, path, size, maxw, min_size):
    """Largest font <= size that fits; below min_size the text is truncated with an ellipsis."""
    while True:
        font = ImageFont.truetype(path, size)
        if draw.textlength(text, font=font) <= maxw:
            return font, text
        if size > min_size:
            size -= 1
            continue
        while text and draw.textlength(text + "...", font=font) > maxw:
            text = text[:-1]
        return font, text + "..."


def graticule_4x3(w, h):
    """4:3 picture (the whole frame) with the FCC safe caption area (608-E C.22 p.77, Table 46): 80% of
    the picture, i.e. 106.67% of the picture height wide, 13.33% (of the height) in from the left and 10%
    down, 80% tall - plus the 15-row x 32-column caption grid."""
    k = h / 480
    img = Image.new("RGB", (w, h), (38, 44, 52))
    d = ImageDraw.Draw(img)
    lab = ImageFont.truetype(FONT_U, max(8, int(12 * k)))
    small = ImageFont.truetype(FONT_U, max(8, int(10 * k)))
    d.rectangle([0, 0, w - 1, h - 1], outline=(110, 120, 130), width=1)
    sx0 = 0.1333 * h
    sx1 = sx0 + 1.0667 * h
    sy0, sy1 = 0.10 * h, 0.90 * h
    rows, cols = 15, 32
    rh, cw = (sy1 - sy0) / rows, (sx1 - sx0) / cols
    for r in range(rows + 1):
        d.line([sx0, sy0 + r * rh, sx1, sy0 + r * rh], fill=(70, 82, 94), width=1)
    for c in range(cols + 1):
        d.line([sx0 + c * cw, sy0, sx0 + c * cw, sy1], fill=(90, 104, 118) if c % 4 == 0 else (70, 82, 94), width=1)
    for r in range(rows):
        t = str(r + 1)
        d.text((sx0 - 4 * k - d.textlength(t, font=lab), sy0 + r * rh + rh / 2 - 7 * k), t, font=lab, fill=(150, 200, 150))
    for c in range(0, cols, 4):
        d.text((sx0 + c * cw + 1, sy1 + 1), str(c + 1), font=small, fill=(150, 200, 150))
    d.text((sx1 - 12 * k, sy1 + 1), "32", font=small, fill=(150, 200, 150))
    d.rectangle([sx0, sy0, sx1, sy1], outline=(60, 220, 90), width=max(2, int(2 * k)))
    d.line([w / 2 - 15 * k, h / 2, w / 2 + 15 * k, h / 2], fill=(120, 130, 140), width=1)
    d.line([w / 2, h / 2 - 15 * k, w / 2, h / 2 + 15 * k], fill=(120, 130, 140), width=1)
    return img


def make_base_4x3(grat, seg, idx, n, w, h):
    """Compact banner confined to the 10% bands above and below the safe area so that it never covers
    caption rows.  Reference lines are abbreviated (CTA-608-E -> 608-E, REGULATORY -> REG ...)."""
    k = h / 480
    img = grat.copy().convert("RGBA")
    ov = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    top = int(48 * k)
    sy1 = 0.90 * h
    y0 = int(sy1 + 11 * k)
    d.rectangle([0, 0, w, top], fill=(0, 0, 0, 225))
    d.rectangle([0, y0, w, h], fill=(0, 0, 0, 225))
    chans = seg.shown or {"1234": "CC1 CC2 CC3 CC4", "13": "CC1+CC3"}.get(seg.chans, "")
    l1 = f"{seg.id}  {seg.title}" + (f"  [{chans}]" if chans else "")
    l2 = f"Expect: {seg.expect}"
    l3 = abbreviate("Ref: " + "  ".join(f"{c} [{lv}]" for c, lv in seg.refs)) if seg.refs else \
        f"{META['name']} {VERSION[0]}  by {META['author']}  {META['license']}"
    mw = w - 8 * k
    f1_, t1 = fit_text(d, l1, FONT_B, int(15 * k), mw, int(11 * k))
    f2_, t2 = fit_text(d, l2, FONT_U, int(13 * k), mw, int(10 * k))
    f3_, t3 = fit_text(d, l3, FONT_U, int(12 * k), mw, int(9 * k))
    d.text((4 * k, 1 * k), t1, font=f1_, fill=(255, 255, 255, 255))
    d.text((4 * k, 18 * k), t2, font=f2_, fill=(255, 224, 102, 255))
    d.text((4 * k, 33 * k), t3, font=f3_, fill=(140, 215, 255, 255))
    ft = footer_short()
    ff, ft = fit_text(d, ft, FONT_U, int(11 * k), mw, int(8 * k))
    d.text(((w - d.textlength(ft, font=ff)) / 2, y0 + 20 * k), ft, font=ff, fill=(230, 230, 230, 255))
    right = f"{VERSION[0]}  test {idx + 1}/{n}"
    fr, right = fit_text(d, right, FONT_B, int(13 * k), w - 340 * k, int(9 * k))
    d.text((w - 4 * k - d.textlength(right, font=fr), y0 + 2 * k), right, font=fr, fill=(255, 224, 102, 255))
    if seg.id in ("G00", "Z99"):
        big = ImageFont.truetype(FONT_B, int(26 * k))
        mid = ImageFont.truetype(FONT_U, int(16 * k))
        lines = [(META["name"], big, (255, 255, 255)), (f"Version {VERSION[0]}", mid, (255, 224, 102)),
                 (f"Author: {META['author']}", mid, (255, 255, 255)),
                 (f"License: {META['license']} - attribution required; share alike", mid, (140, 215, 255)),
                 (META["repo_url"], mid, (255, 255, 255))]
        y = 150 * k
        for text, font, col in lines:
            d.text(((w - d.textlength(text, font=font)) / 2, y), text, font=font, fill=col + (255,))
            y += font.size * 1.5
    tl = dict(box=(0, y0, int(330 * k), y0 + int(19 * k)), origin=(4 * k, 1 * k), size=max(9, int(13 * k)))
    return np.asarray(Image.alpha_composite(img, ov).convert("RGB")).copy(), tl


def render_video(starts, total, m2v, codec, fmt):
    """`total` is in 29.97 Hz caption frames; each caption frame is `ppf` pictures of this format."""
    cw, ch = fmt["canvas"]
    coded_w = cw if fmt["kind"] == "16x9" else int(round(cw * 9 / 8 / 2)) * 2
    vn, vd = fmt["vfps"]
    ppf = fmt["ppf"]
    vf = f"scale={coded_w}:{ch}:out_color_matrix=bt709:out_range=tv"
    if fmt["kind"] == "4x3":
        vf += ",setsar=8/9"                      # 720x480 anamorphic, display aspect ratio 4:3
    vf += ",format=yuv420p"
    common = ["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{cw}x{ch}",
              "-framerate", f"{vn}/{vd}", "-i", "-", "-vf", vf]
    color = ["-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709", "-color_range", "tv"]
    br = str(VIDEO_BITRATE)
    il = ["-flags", "+ilme+ildct+cgop", "-top", "1"] if fmt["interlaced"] else ["-flags", "+cgop"]
    gop = str(fmt["gop"])
    if codec == "mpeg2":
        enc = ["-c:v", "mpeg2video", "-profile:v", "main", *il, "-g", gop, "-bf", "2",
               "-sc_threshold", "1000000000", "-b:v", br, "-minrate", br, "-maxrate", br,
               "-bufsize", "1835008", "-aspect", fmt["dar"], "-f", "mpeg2video"]
    else:   # carrier for the H.264 build: near-lossless MPEG-2 that only transports the cc_data
        enc = ["-c:v", "mpeg2video", *il, "-g", gop, "-bf", "2", "-sc_threshold", "1000000000",
               "-q:v", "2", "-aspect", fmt["dar"], "-f", "mpeg2video"]
    cmd = common + enc + color + [m2v]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    mk_grat, mk_base = ((graticule_16x9, make_base_16x9) if fmt["kind"] == "16x9"
                        else (graticule_4x3, make_base_4x3))
    grat = mk_grat(cw, ch)
    for si, seg in enumerate(SEGMENTS):
        base, tl = mk_base(grat, seg, si, len(SEGMENTS), cw, ch)
        tfont = ImageFont.truetype(FONT_B, tl["size"])
        x0, y0, x1, y1 = tl["box"]
        f0 = ppf * sec2f(starts[si])
        f1 = ppf * (sec2f(starts[si + 1]) if si + 1 < len(SEGMENTS) else total)
        # a flash marks the picture carrying the first EOC of the field-1 (CC1) pair
        flash = {ppf * sec2f(starts[si] + x) for x in seg.flashes}
        region = Image.fromarray(base[y0:y1, x0:x1])
        k = ch / 720 if fmt["kind"] == "16x9" else ch / 480
        for f in range(f0, f1):
            t = f * vd / vn
            ct = (f - f0) * vd / vn
            frame = base.copy()
            im = region.copy()
            ImageDraw.Draw(im).text(tl["origin"],
                                    f"{int(t // 60):02d}:{int(t % 60):02d}.{int(t * 1000) % 1000:03d}  frame {f:05d}"
                                    f"  card +{ct:05.1f}s", font=tfont, fill=(255, 255, 255))
            frame[y0:y1, x0:x1] = np.asarray(im)
            if f in flash:
                if fmt["kind"] == "16x9":
                    frame[int(100 * k):int(290 * k), int(27 * k):int(267 * k)] = 255
                else:
                    frame[int(75 * k):int(170 * k), int(4 * k):int(60 * k)] = 255
            p.stdin.write(frame.tobytes())
    p.stdin.close()
    if p.wait():
        raise SystemExit("ffmpeg video encode failed")


# ------------------------------------------------------------ cc_data
def _trip(typ, pair):
    if pair is None:                                    # cc_valid = 0: no waveform
        return bytes([0xF8 | typ, 0, 0])
    return bytes([0xFC | typ, pair[0], pair[1]])


def cc_payload(items, cc_count):
    """A/53 part 4 cc_data for one picture.  `items` = [(cc_type, pair)] in transmission order: the NTSC
    pairs come first, then one cc_valid=0/cc_type=11 end-of-packet marker and cc_valid=0/cc_type=00 padding
    up to cc_count (CEA-CEB-10-A 26.3/26.4 p.42, Annex B Table 9 p.53)."""
    trip = b"".join(_trip(t, p) for t, p in items) + bytes([0xFB, 0, 0]) \
        + bytes([0xF8, 0, 0]) * (cc_count - len(items) - 1)
    return bytes([0x40 | cc_count, 0xFF]) + trip + b"\xff"      # follows 'GA94' + user_data_type_code 0x03


def mpeg2_user_data(items, cc_count):
    return b"\x00\x00\x01\xb2GA94\x03" + cc_payload(items, cc_count)


def picture_items(v, f1, f2, ppf):
    """The NTSC pairs carried by display-order picture v.
    ppf 2 (59.94 fps progressive): one pair, field 1 on even pictures, field 2 on odd ones, alternating
    (CEA-CEB-10-A 18.1 p.34 / 25.2.2 p.40).  ppf 1 (interlaced frame): both pairs, the cc_type 01 (field 2)
    pair first for top-field-first video (708-B 4.4.2 as quoted in 10-A Annex B p.53)."""
    def pair(fld, c):
        return fld.pairs[c] if c < len(fld.pairs) else NULLP
    if ppf == 2:
        return [(0, pair(f1, v // 2))] if v % 2 == 0 else [(1, pair(f2, v // 2))]
    return [(1, pair(f2, v)), (0, pair(f1, v))]


def inject(src, dst, f1, f2, fmt):
    d = open(src, "rb").read()
    toks = [(m.start(), m.group()[3]) for m in re.finditer(rb"\x00\x00\x01[\x00\xb8\x01]", d)]
    ins = []
    gop_base = count = 0
    cur = None
    for pos, code in toks:
        if code == 0xB8:
            gop_base += count
            count = 0
        elif code == 0x00:
            tr = (d[pos + 4] << 2) | (d[pos + 5] >> 6)
            cur = gop_base + tr
            count += 1
        elif cur is not None:       # first slice after a picture header
            ins.append((pos, mpeg2_user_data(picture_items(cur, f1, f2, fmt["ppf"]), fmt["cc_count"])))
            cur = None
    out, last = [], 0
    for pos, pl in ins:
        out += [d[last:pos], pl]
        last = pos
    out.append(d[last:])
    open(dst, "wb").write(b"".join(out))
    return len(ins)


# ------------------------------------------------------------ TS patching
def crc32_mpeg(b):
    crc = 0xFFFFFFFF
    for x in b:
        crc ^= x << 24
        for _ in range(8):
            crc = ((crc << 1) ^ 0x04C11DB7) & 0xFFFFFFFF if crc & 0x80000000 else (crc << 1) & 0xFFFFFFFF
    return crc


def caption_descriptor():
    """ATSC A/65:2013 caption_service_descriptor (0x86) with ONE entry for the CEA-608 data stream
    (digital_cc = 0): 'each iteration defines one 708 service or one 608 data stream', and CTA-708-E 4.5
    allows at most one 608 data stream to be signalled.  For a 608 entry language, easy_reader and
    wide_aspect_ratio have no meaning and line21_field is not expected to be used by receivers
    (A/65:2013 p.69-70); they are set to neutral values.  The 608 data itself identifies CC1-CC4."""
    body = bytes([0xE0 | 1]) + b"eng" + bytes([0x7E | 1, 0x3F, 0xFF])
    return bytes([0x86, len(body)]) + body


def patch_pmt(path):
    data = bytearray(open(path, "rb").read())
    pmt_pid = None
    for i in range(0, len(data), 188):
        pid = ((data[i + 1] & 0x1F) << 8) | data[i + 2]
        if pid == 0 and data[i + 1] & 0x40:
            pmt_pid = ((data[i + 15] & 0x1F) << 8) | data[i + 16]
            break
    n = 0
    desc = caption_descriptor()
    for i in range(0, len(data), 188):
        pid = ((data[i + 1] & 0x1F) << 8) | data[i + 2]
        if pid != pmt_pid or not data[i + 1] & 0x40:
            continue
        sec = bytes(data[i + 5:i + 5 + 3 + (((data[i + 6] & 0xF) << 8) | data[i + 7])])
        pil = ((sec[10] & 0xF) << 8) | sec[11]
        pos = 12 + pil
        body = bytearray(sec[:pos])
        end = len(sec) - 4
        while pos < end:
            st = sec[pos]
            il = ((sec[pos + 3] & 0xF) << 8) | sec[pos + 4]
            es = sec[pos + 5:pos + 5 + il]
            if st in (0x02, 0x1B):
                es += desc
            body += bytes([st, sec[pos + 1], sec[pos + 2], 0xF0 | (len(es) >> 8), len(es) & 0xFF]) + es
            pos += 5 + il
        slen = len(body) - 3 + 4
        body[1], body[2] = 0xB0 | (slen >> 8), slen & 0xFF
        body += struct.pack(">I", crc32_mpeg(bytes(body)))
        pkt = data[i:i + 5] + body
        assert len(pkt) <= 188
        data[i:i + 188] = pkt + b"\xff" * (188 - len(pkt))
        n += 1
    open(path, "wb").write(data)
    return n


# ------------------------------------------------------------ documentation
def ts(t):
    return f"{int(t // 60):02d}:{t % 60:05.2f}"


def write_cards_json(path, starts, total):
    import testplan
    testplan.apply_format(None)
    cards = []
    for s, t in zip(SEGMENTS, starts):
        c = dict(id=s.id, title=s.title, group=s.group, start=round(t, 3), duration=s.dur,
                 channels=s.shown or s.chans, refs=[dict(cite=x, level=lv) for x, lv in s.refs],
                 expect=s.expect)
        if s.variants:
            c["variants"] = {f: {k: ([dict(cite=x, level=lv) for x, lv in v] if k == "refs" else v)
                                 for k, v in o.items()} for f, o in s.variants.items()}
        cards.append(c)
    json.dump(dict(stream=META["name"], author=META["author"], license=META["license"],
                   caption_frames=total, caption_fps="30000/1001",
                   formats={n: dict(size=("x".join(map(str, f["canvas"])) if f["kind"] == "16x9" else "720x480"),
                                    video_fps=f"{f['vfps'][0]}/{f['vfps'][1]}",
                                    pictures=f["ppf"] * total,
                                    scan="interlaced" if f["interlaced"] else "progressive",
                                    display_aspect_ratio=f["dar"]) for n, f in FORMATS.items()},
                   cards=cards), open(path, "w"), indent=1, ensure_ascii=False)


LEVELS_MD = """\
## How to read the "level" tags

Every card names the specification section it exercises and says **how binding** the expected
behavior is, using the source document's own wording:

| Tag | Source | Meaning |
|---|---|---|
| `REGULATORY` | CTA-608-E | Required by the FCC rules (47 CFR 15.119) as reproduced/clarified in 608-E. A conforming caption decoder shall do this. |
| `NORMATIVE` | CTA-608-E | Normative text of 608-E (including section 6.4 character sets and Annex C/D "shall" statements). |
| `PREFERRED` | CTA-608-E | 608-E states a preferred option; other reasonable choices are permitted "with no significant degradation of service" (C.1). |
| `OPTIONAL` | CTA-608-E | Optional decoder feature (extended characters, background/foreground attributes). If implemented it shall behave as described. A renderer that omits it is not non-conforming. |
| `RECOMMENDED` | CTA-608-E | Recommended practice addressed mainly to caption providers/encoders (Annex B); shown because the card checks the decoder against that practice. |
| `INFORMATIVE` | either | Context, not a requirement. |
| `10A-RECOMMENDATION` | CEA-CEB-10-A | CEA-CEB-10-A is a **bulletin**: its recommendations are best practice and are **not mandatory**. (It is written for EIA-708-B; only the sections on 608 carried in `cc_data` are used here.) |
| `UNSPECIFIED` | none | Neither document defines the result; the card records what a renderer does. |

Citations use **printed** page numbers (not PDF page numbers). A card with two levels
(e.g. `REGULATORY/PREFERRED`) reproduces the section's own heading.
"""


def write_tests_md(path, starts, total):
    import testplan
    testplan.apply_format(None)
    with open(path, "w") as m:
        m.write(f"# {META['name']} - test cards\n\n")
        m.write(f"By {META['author']}. Licensed {META['license']} ({META['license_url']}).\n\n")
        m.write(f"{len(SEGMENTS)} cards, {ts(total * FPS_D / FPS_N)} long. Two formats are built from the same cards: "
                "**720p59** (1280x720 progressive, 59.94 fps, 16:9) and **480i59** (720x480 anamorphic interlaced, "
                "59.94 fields/s, 4:3), each as H.264 (default) or MPEG-2 at 3.5 Mbps CBR with AC-3 (128 kbps) in a 4 Mbps "
                "CBR MPEG-TS. Caption data: CEA-608 in ATSC A/53 `cc_data`; field 1 = CC1 (+CC2), field 2 = CC3 (+CC4). "
                "CC1 and CC3 carry identical tests; CC2 and CC4 show a continuous `Rendering on CCn` label (refreshed "
                "every 2 s) and are used by card H01. Two cards word their expectation differently per format and say so below.\n\n")
        m.write("Each card's name, expected result and spec reference with its level are burned into the "
                "video, over a graticule showing the FCC safe caption area and the 15 x 32 grid.\n\n")
        m.write(LEVELS_MD + "\n")
        m.write("## Specifications\n\n"
                "* **CTA-608-E** (ANSI/CTA-608-E S-2019), *Line 21 Data Services*.\n"
                "* **CEA-CEB-10-A** (Dec 2002), *EIA-708-B Implementation Guidance*.\n"
                "* **ATSC A/65:2013** (descriptor syntax) and **CTA-708-E** are consulted for the program-table signalling and "
                "the 16:9 behavior of DTVCC.\n\n")
        grp = None
        for s, t in zip(SEGMENTS, starts):
            if s.group != grp:
                grp = s.group
                m.write(f"## {grp}\n\n")
            ch = "CC1-CC4" if s.shown else {"1234": "CC1-CC4", "13": "CC1, CC3"}.get(s.chans, "-")
            m.write(f"### {s.id} - {s.title}\n\n")
            m.write(f"*Starts {ts(t)}, lasts {s.dur:g} s, channels: {ch}*\n\n")
            m.write(f"**Purpose.** {s.purpose}\n\n")
            m.write(f"**Test.** {s.detail}.\n\n**Expected.** {s.expect}\n\n")
            if s.refs:
                m.write("**References.**\n\n")
                for c, lv in s.refs:
                    m.write(f"* {c} - `{lv}`\n")
                m.write("\n")
            for fname, o in s.variants.items():
                bits = []
                if "expect" in o:
                    bits.append(f"**Expected.** {o['expect']}")
                if "purpose" in o:
                    bits.append(f"**Purpose.** {o['purpose']}")
                if "refs" in o:
                    bits.append("**References.** " + "; ".join(f"{c} - `{lv}`" for c, lv in o["refs"]))
                if bits:
                    m.write(f"*{fname} ({'16:9' if fname == '720p59' else '4:3'}) differs:* " + " ".join(bits) + "\n\n")


# ------------------------------------------------------------ main
def x264_opts(fmt):
    p = ("aud=1:keyint=%d:min-keyint=%d:scenecut=0:bframes=2:b-pyramid=none:open-gop=0:"
         "nal-hrd=cbr:force-cfr=1" % (fmt["gop"], fmt["gop"]))
    if fmt["interlaced"]:
        p = "tff=1:" + p
    br = str(VIDEO_BITRATE)
    return ["-c:v", "libx264", "-profile:v", "high", "-level", fmt["level"], "-preset", "medium",
            "-x264-params", p, "-b:v", br, "-minrate", br, "-maxrate", br, "-bufsize", br,
            "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709", "-color_range", "tv"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--format", choices=sorted(FORMATS), default="720p59",
                    help="720p59 = 1280x720 progressive 16:9; 480i59 = 720x480 interlaced 4:3 anamorphic")
    ap.add_argument("--size", default=None,
                    help="square-pixel drawing size override for quick builds, e.g. 640x360 (720p59) or 320x240 (480i59)")
    ap.add_argument("--out", default=None)
    ap.add_argument("--codec", choices=("h264", "mpeg2"), default="h264",
                    help="video essence: H.264 (default, plays on more hardware decoders) or MPEG-2")
    ap.add_argument("--version-label", default=None,
                    help="override the burned-in version (default: git tag at HEAD, else git rev)")
    ap.add_argument("--no-caption-descriptor", action="store_true",
                    help="omit the PMT caption_service_descriptor (CEA-CEB-10-A 23.2.2 variant)")
    a = ap.parse_args()
    fmt = dict(FORMATS[a.format])
    if a.size:
        fmt["canvas"] = tuple(map(int, a.size.split("x")))
    import testplan
    testplan.apply_format(a.format)
    VERSION[0] = a.version_label or git_version()
    suffix = "-nodesc" if a.no_caption_descriptor else ""
    safe = re.sub(r"[^A-Za-z0-9._+-]", "_", VERSION[0])
    out = a.out or os.path.join(HERE, "out", f"CEA608-conformance-{safe}-{a.format}-{a.codec}{suffix}.ts")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    f1, f2, starts, total, n_labels = schedule()
    dur = total * FPS_D / FPS_N
    vn, vd = fmt["vfps"]
    print(f"version label: {VERSION[0]}   format {a.format}   codec {a.codec}")
    print(f"scheduled {len(SEGMENTS)} cards, {fmt['ppf'] * total} pictures at {vn / vd:.2f} fps ({dur:.1f}s), "
          f"{n_labels} CC2/CC4 label refreshes")
    with tempfile.TemporaryDirectory(dir=os.environ.get("KEEP_TMP")) as tmp:
        m2v, cc = os.path.join(tmp, "v.m2v"), os.path.join(tmp, "cc.m2v")
        render_video(starts, total, m2v, a.codec, fmt)
        print(f"injected cc_data into {inject(m2v, cc, f1, f2, fmt)} pictures ({a.codec})")
        # H.264: libavcodec's MPEG-2 decoder exports the A53 cc_data as frame side data and libx264
        # re-emits it verbatim as the ITU-T T.35 'GA94' SEI of each access unit (display-order association
        # handled by ffmpeg).  MPEG-2: the injected stream is copied.
        vopts = x264_opts(fmt) if a.codec == "h264" else ["-c:v", "copy"]
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-fflags", "+genpts", "-framerate", f"{vn}/{vd}",
                        "-f", "mpegvideo", "-i", cc, "-f", "lavfi", "-i",
                        f"aevalsrc=0.1*sin(2*PI*1000*t)*lt(mod(t\\,1)\\,0.1)|0.1*sin(2*PI*1000*t)*lt(mod(t\\,1)\\,0.1):s=48000:d={dur + 1}",
                        "-map", "0:v", "-map", "1:a", *vopts, "-c:a", "ac3", "-b:a", "128k",
                        "-metadata:s:a:0", "language=eng", "-shortest",
                        "-f", "mpegts", "-muxrate", str(TS_BITRATE), "-pcr_period", "40",
                        "-mpegts_pmt_start_pid", "0x20", "-mpegts_start_pid", "0x21",
                        "-metadata", f"service_provider={META['author']} {META['license']}",
                        "-metadata", f"service_name={META['name']} {VERSION[0]}",
                        out], check=True)
    if not a.no_caption_descriptor:
        print("patched", patch_pmt(out), "PMT packets")
    write_tests_md(os.path.join(HERE, "TESTS.md"), starts, total)
    write_cards_json(os.path.join(HERE, "cards.json"), starts, total)
    print("wrote", out)


if __name__ == "__main__":
    main()
