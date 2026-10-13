#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2026 Devin Heitmueller <devin.heitmueller@gmail.com>
"""Reference slides: what each test card should look like when captions are rendered correctly.

  python reference.py [--format 720p59|480i59|both] [--out DIR] [--zip DIR] [--version-label TEXT]

Writes <out>/<format>/slide-NNN-*.png and <out>/<format>/index.html (a self-contained viewer with a
slide dropdown, Previous/Next buttons and the arrow keys), plus <out>/index.html linking the formats.
--zip DIR also packs the result as DIR/CEA608-conformance-<version>-reference.zip (one top-level folder),
the form attached to a release.  Nothing here is committed; the build regenerates it.

How it works: the byte pairs the generator puts on each field (testplan.py -> build.schedule()) are replayed
through a small CEA-608 decoder model written from CTA-608-E (class Decoder below), and the caption
memory it displays is drawn on the same graticule and banner as the test stream.  This is the *author's reading
of the spec*, not an independent decoder: see README "Reference slides" for what is and is not shown.

Needs Pillow and numpy (same as build.py).
"""
import argparse
import html
import json
import os
import re
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import build  # noqa: E402
from cea608 import (BASIC_SUBST, COLORS, EXT12, EXT13, PAC_ROW_BASE, PAC_ROW_FIRST, SPECIAL, BG_COLORS,  # noqa: E402
                    FPS_D, FPS_N, sec2f)

ROWS, COLS = 15, 32
MIN_STATE_FRAMES = 12            # a caption state shown for under ~0.4 s gets no slide of its own
LOSS_FRAMES = 45                 # C.21: frames without valid data before the display is disabled
RGB = {"w": (255, 255, 255), "g": (0, 255, 0), "b": (0, 0, 255), "c": (0, 255, 255),
       "r": (255, 0, 0), "y": (255, 255, 0), "m": (255, 0, 255), "k": (0, 0, 0)}
PAC_ROW = {(PAC_ROW_FIRST[r], PAC_ROW_BASE[r] >= 0x60): r for r in PAC_ROW_FIRST}

# A cell is (char, fg, ul, italic, bg, bg_alpha, flash); bg_alpha is 'o'paque, 's'emi or 't'ransparent.
DEFAULT_STYLE = ("w", False, False, "k", "o", False)       # fg, underline, italic, bg, alpha, flash


class Memory:
    """A 15 x 32 caption memory plus the order in which rows were started (for the four-row limit)."""

    def __init__(self):
        self.grid = [[None] * COLS for _ in range(ROWS)]
        self.seq = {}
        self.counter = 0

    def erase(self):
        self.__init__()

    def row_used(self, row):
        return any(self.grid[row - 1])

    def touch(self, row):
        """608-E C.5/C.6: at most four rows; a fifth replaces the oldest (newer rows preferred)."""
        if not self.row_used(row):
            used = [r for r in range(1, ROWS + 1) if self.row_used(r) and r != row]
            if len(used) >= 4:
                oldest = min(used, key=lambda r: self.seq.get(r, 0))
                self.grid[oldest - 1] = [None] * COLS
            self.counter += 1
            self.seq[row] = self.counter

    def snapshot(self):
        return tuple(tuple(r) for r in self.grid)


class Decoder:
    """One caption channel (CC1..CC4) of a field, following CTA-608-E."""

    def __init__(self):
        self.shown, self.hidden = Memory(), Memory()
        self.mode = None                 # 'pop', 'paint', 'roll'
        self.depth, self.base = 2, ROWS
        self.row, self.col = ROWS, 1
        self.style = list(DEFAULT_STYLE)
        self.inherit = False             # a PAC was just received: C.7 attribute inheritance applies
        self.dirty = False

    # -- helpers
    @property
    def target(self):
        return self.hidden if self.mode == "pop" else self.shown

    def mark(self):
        self.dirty = True

    def erase_all(self):
        self.shown.erase()
        self.hidden.erase()
        self.mark()

    def put(self, ch):
        mem = self.target
        row = self.base if self.mode == "roll" else self.row
        if self.mode != "roll":
            mem.touch(row)
        if self.inherit and self.col > 1 and mem.grid[row - 1][self.col - 2]:      # C.7
            c = mem.grid[row - 1][self.col - 2]
            self.style = [c[1], c[2], c[3], c[4], c[5], c[6]]
        self.inherit = False
        fg, ul, it, bg, al, fl = self.style
        mem.grid[row - 1][self.col - 1] = (ch, fg, ul, it, bg, al, fl)
        if self.col < COLS:
            self.col += 1
        if mem is self.shown:
            self.mark()

    def spacing(self, **change):
        """Mid-row codes, FON and the background/foreground attribute codes occupy one cell, shown as a space."""
        names = ("fg", "ul", "it", "bg", "al", "fl")
        for k, v in change.items():
            self.style[names.index(k)] = v
        self.put(" ")

    # -- commands
    def pac(self, row, code):
        self.inherit = True
        self.style = list(DEFAULT_STYLE)
        if code >= 0x10:
            self.col = 1 + 4 * ((code - 0x10) // 2)
        else:
            self.col = 1
            if code >= 0x0E:
                self.style[2] = True
            else:
                self.style[0] = COLORS[code // 2]
        self.style[1] = bool(code & 1)
        if self.mode == "roll":
            self.set_base(max(row, self.depth))
        else:
            self.row = row

    def set_base(self, base):
        """PAC in roll-up: the whole displayed block moves with the base row (R07); depth wins (R08)."""
        if base != self.base:
            top, bot = self.base - self.depth + 1, self.base
            rows = [self.shown.grid[r - 1] for r in range(top, bot + 1)]
            for r in range(top, bot + 1):
                self.shown.grid[r - 1] = [None] * COLS
            for i, cells in enumerate(rows):
                self.shown.grid[base - self.depth + i] = cells
            self.base = base
            self.mark()

    def misc(self, code):
        if code == 0x20:                                   # RCL
            self.mode = "pop"
        elif code == 0x21:                                 # BS
            if self.col > 1:
                self.col -= 1
            mem = self.target
            row = self.base if self.mode == "roll" else self.row
            if mem.grid[row - 1][self.col - 1]:
                mem.grid[row - 1][self.col - 1] = None
                if mem is self.shown:
                    self.mark()
        elif code == 0x24:                                 # DER
            mem = self.target
            row = self.base if self.mode == "roll" else self.row
            for c in range(self.col - 1, COLS):
                mem.grid[row - 1][c] = None
            if mem is self.shown:
                self.mark()
        elif code in (0x25, 0x26, 0x27):                   # RU2-4
            if self.mode != "roll":
                self.erase_all()                           # C.10: roll-up erases both memories
                self.base, self.col = ROWS, 1
                self.style = list(DEFAULT_STYLE)
            else:
                self.hidden.erase()
                if not any(any(r) for r in self.shown.grid):
                    # C.15: the row-15 default applies when no roll-up caption is currently displayed
                    # (only an RU command with a caption on screen keeps the last base row)
                    self.base, self.col = ROWS, 1
                    self.style = list(DEFAULT_STYLE)
            depth = code - 0x23
            if self.mode == "roll" and depth < self.depth:
                for r in range(1, self.base - depth + 1):
                    self.shown.grid[r - 1] = [None] * COLS
                self.mark()
            self.depth = depth
            self.base = max(self.base, depth)
            self.mode = "roll"
        elif code == 0x29:                                 # RDC
            self.mode = "paint"
        elif code == 0x28:                                 # FON
            self.spacing(fl=True)
        elif code == 0x2C:                                 # EDM
            self.shown.erase()
            self.mark()
        elif code == 0x2D:                                 # CR
            if self.mode == "roll":
                top = self.base - self.depth + 1
                for r in range(top, self.base):
                    self.shown.grid[r - 1] = self.shown.grid[r]
                self.shown.grid[self.base - 1] = [None] * COLS
                self.col = 1
                self.style = list(DEFAULT_STYLE)
                self.inherit = False
                self.mark()
        elif code == 0x2E:                                 # ENM
            self.hidden.erase()
        elif code == 0x2F:                                 # EOC
            self.shown, self.hidden = self.hidden, self.shown
            self.mode = "pop"
            self.mark()

    def midrow(self, code):
        if code >= 0x2E:
            self.spacing(fg="w", it=True, ul=bool(code & 1), fl=False)
        else:
            self.spacing(fg=COLORS[(code - 0x20) // 2], it=False, ul=bool(code & 1), fl=False)

    def background(self, code):
        i = (code - 0x20) // 2
        if self.col > 1:
            self.col -= 1                                  # 6.2: the code carries an automatic backspace
        self.spacing(bg=BG_COLORS[i], al="s" if code & 1 else "o")

    def attribute(self, code):                             # 0x17 0x2D BT, 0x2E FA, 0x2F FAU
        if self.col > 1:
            self.col -= 1
        if code == 0x2D:
            self.spacing(al="t")
        else:
            self.spacing(fg="k", ul=code == 0x2F)

    def extended(self, first, code):
        if self.col > 1:
            self.col -= 1                                  # the extended character replaces the fallback
        self.put((EXT12 if first == 0x12 else EXT13)[code - 0x20])


class FieldDecoder:
    """Runs the byte pairs of one field through the decoders of its two data channels."""

    def __init__(self, pairs):
        self.pairs = pairs
        self.dec = {1: Decoder(), 2: Decoder()}
        self.cur = None
        self.last = None
        self.bad = 0
        # per channel: [(frame, snapshot of the displayed memory)] at every change
        self.states = {1: [(0, self.dec[1].shown.snapshot())], 2: [(0, self.dec[2].shown.snapshot())]}

    def run(self):
        for f, p in enumerate(self.pairs):
            self.step(p)
            for ch, d in self.dec.items():
                if d.dirty:
                    d.dirty = False
                    snap = d.shown.snapshot()
                    if snap != self.states[ch][-1][1]:
                        self.states[ch].append((f, snap))

    def step(self, p):
        valid = p is not None and all(bin(b).count("1") % 2 == 1 for b in p)
        if not valid:
            self.bad += 1
            self.last = None
            if self.bad == LOSS_FRAMES:                     # C.21: disable display, erase memory
                for d in self.dec.values():
                    d.erase_all()
            return
        self.bad = 0
        a, b = p[0] & 0x7F, p[1] & 0x7F
        if a == 0 and b == 0:
            self.last = None
            return
        if 0x10 <= a <= 0x1F:
            if (a, b) == self.last:                          # D.2: the second of a redundant pair is ignored
                self.last = None
                return
            self.last = (a, b)
            self.control(a, b)
            return
        self.last = None
        d = self.dec.get(self.cur)
        if d is None:
            return
        for x in (a, b):
            if x >= 0x20:
                d.put(BASIC_SUBST.get(x, chr(x)))

    def control(self, a, b):
        ch = 2 if a & 0x08 else 1
        lo = a & 0x07
        if b >= 0x40:                                        # PAC
            row = PAC_ROW.get((a & 0x17, b >= 0x60))
            if row:
                self.cur = ch
                self.dec[ch].pac(row, b & 0x1F)
            return
        d = self.dec[ch]
        if lo in (4, 5) and 0x20 <= b <= 0x2F:              # miscellaneous control
            self.cur = ch
            d.misc(b)
        elif lo == 1 and 0x20 <= b <= 0x2F:
            self.cur = ch
            d.midrow(b)
        elif lo == 1 and 0x30 <= b <= 0x3F:
            self.cur = ch
            d.put(SPECIAL[b - 0x30])
        elif lo == 0 and 0x20 <= b <= 0x2F:
            self.cur = ch
            d.background(b)
        elif lo in (2, 3) and 0x20 <= b <= 0x3F:
            self.cur = ch
            d.extended(0x12 if lo == 2 else 0x13, b)
        elif lo == 7 and 0x21 <= b <= 0x23:
            self.cur = ch
            d.col = min(COLS, d.col + (b - 0x20))
        elif lo == 7 and 0x2D <= b <= 0x2F:
            self.cur = ch
            d.attribute(b)


# ---------------------------------------------------------------------------------------------- drawing
class Geometry:
    def __init__(self, kind, w, h):
        self.kind, self.w, self.h = kind, w, h
        if kind == "16x9":
            k = w / 1920
            self.sx0, self.sx1, self.sy0, self.sy1 = 384 * k, 1536 * k, 108 * k, 972 * k
        else:
            self.sx0 = 0.1333 * h
            self.sx1 = self.sx0 + 1.0667 * h
            self.sy0, self.sy1 = 0.10 * h, 0.90 * h
        self.cw = (self.sx1 - self.sx0) / COLS
        self.ch = (self.sy1 - self.sy0) / ROWS

    def cell(self, row, col):
        x = self.sx0 + (col - 1) * self.cw
        y = self.sy0 + (row - 1) * self.ch
        return x, y, x + self.cw, y + self.ch


def glyph(ch, fg, italic, geo):
    """RGBA tile of one character cell (text only)."""
    cw, chh = int(round(geo.cw)) + 2, int(round(geo.ch)) + 2
    size = max(8, int(geo.ch * 0.74))
    big = Image.new("RGBA", (cw * 3, chh * 3), (0, 0, 0, 0))
    d = ImageDraw.Draw(big)
    big_font = ImageFont.truetype(build.FONT_U, size * 3)
    wch = d.textlength(ch, font=big_font)
    d.text(((cw * 3 - wch) / 2, chh * 3 * 0.10), ch, font=big_font, fill=RGB[fg] + (255,))
    if italic:
        big = big.transform(big.size, Image.AFFINE, (1, 0.25, -0.25 * big.size[1] / 2, 0, 1, 0), Image.BICUBIC)
    bbox = big.getbbox()
    if bbox and bbox[2] - bbox[0] > cw * 3 * 0.94:           # wide glyph (W, m ...): squeeze horizontally only
        w1 = int(cw * 3 * 0.94)
        piece = big.crop(bbox).resize((w1, bbox[3] - bbox[1]), Image.LANCZOS)
        big = Image.new("RGBA", (cw * 3, chh * 3), (0, 0, 0, 0))
        big.paste(piece, ((cw * 3 - w1) // 2, bbox[1]))
    return big.resize((cw, chh), Image.LANCZOS)


def draw_captions(img, grid, geo, flash_label=True):
    """Draw a displayed-memory snapshot onto an RGB PIL image."""
    base = img.convert("RGBA")
    boxes = Image.new("RGBA", base.size, (0, 0, 0, 0))
    bd = ImageDraw.Draw(boxes)
    text = Image.new("RGBA", base.size, (0, 0, 0, 0))
    flashes = []
    for ri, row in enumerate(grid, 1):
        run = None
        for ci, c in enumerate(row, 1):
            if not c:
                if run:
                    flashes.append(run)
                    run = None
                continue
            ch, fg, ul, it, bg, al, fl = c
            x0, y0, x1, y1 = geo.cell(ri, ci)
            if al == "o":
                bd.rectangle([x0, y0, x1 - 1, y1 - 1], fill=RGB[bg] + (255,))
            elif al == "s":
                bd.rectangle([x0, y0, x1 - 1, y1 - 1], fill=RGB[bg] + (128,))
            if ch != " ":
                text.alpha_composite(glyph(ch, fg, it, geo), (int(x0) - 1, int(y0) - 1))
            if ul:
                lw = max(2, int(geo.ch * 0.07))
                bd2 = ImageDraw.Draw(text)
                bd2.rectangle([x0, y1 - lw - 2, x1 - 1, y1 - 3], fill=RGB[fg] + (255,))
            if fl:
                if run and run[0] == ri:
                    run[2] = ci
                else:
                    if run:
                        flashes.append(run)
                    run = [ri, ci, ci]
            elif run:
                flashes.append(run)
                run = None
        if run:
            flashes.append(run)
    out = Image.alpha_composite(Image.alpha_composite(base, boxes), text)
    d = ImageDraw.Draw(out)
    lab = ImageFont.truetype(build.FONT_B, max(9, int(geo.ch * 0.34)))
    for ri, c0, c1 in flashes:                                # dashed marker: this region should flash
        x0, y0, _, _ = geo.cell(ri, c0)
        _, _, x1, y1 = geo.cell(ri, c1)
        for x in range(int(x0), int(x1), 8):
            d.line([x, y0 - 2, min(x + 4, x1), y0 - 2], fill=(255, 140, 0), width=3)
            d.line([x, y1 + 1, min(x + 4, x1), y1 + 1], fill=(255, 140, 0), width=3)
        for y in range(int(y0), int(y1), 8):
            d.line([x0 - 2, y, x0 - 2, min(y + 4, y1)], fill=(255, 140, 0), width=3)
            d.line([x1 + 1, y, x1 + 1, min(y + 4, y1)], fill=(255, 140, 0), width=3)
        d.text((x0, y0 - 2 - lab.size - 3), "FLASHES (rate unspecified)", font=lab, fill=(255, 140, 0))
    return out.convert("RGB")


# ---------------------------------------------------------------------------------------------- slides
def is_blank(grid):
    return not any(any(r) for r in grid)


def card_slides(seg_i, seg, starts, total, fields):
    """[(channel name, from_frame, to_frame, snapshot)] for one card: every caption state shown for at
    least MIN_STATE_FRAMES, in order; blank states count only after a caption has appeared."""
    f0 = sec2f(starts[seg_i])
    f1 = sec2f(starts[seg_i + 1]) if seg_i + 1 < len(starts) else total
    out = {}
    for name, (fi, ch) in {"CC1": (0, 1), "CC2": (0, 2), "CC3": (1, 1), "CC4": (1, 2)}.items():
        st = fields[fi].states[ch]
        items = []
        for i, (f, snap) in enumerate(st):
            end = st[i + 1][0] if i + 1 < len(st) else total
            a, b = max(f, f0), min(end, f1)
            if b - a >= MIN_STATE_FRAMES:
                items.append((a, b, snap))
        seen = False
        keep = []
        for a, b, snap in items:
            if is_blank(snap):
                if seen:
                    keep.append((a, b, snap))
            else:
                seen = True
                keep.append((a, b, snap))
        out[name] = keep
    want = ["CC1"]
    flags = lambda ks: [is_blank(x) for _, _, x in ks]          # noqa: E731
    if seg.id == "H01":
        want = ["CC1", "CC2", "CC3", "CC4"]
    elif seg.id == "G01" or flags(out["CC3"]) != flags(out["CC1"]):
        want = ["CC1", "CC3"]          # CC3 carries the same card; shown only where it differs (its own label, S04)
    return [(n, a, b, s) for n in want for a, b, s in out[n]] or [("CC1", f0, f1, out["CC1"] and out["CC1"][0][2] or
                                                                 tuple(tuple([None] * COLS) for _ in range(ROWS)))]


def tstr(frames):
    return f"{frames * FPS_D / FPS_N:.1f}"


def render_format(fmt_name, out_root, version):
    fmt = dict(build.FORMATS[fmt_name])
    import testplan
    testplan.apply_format(fmt_name)
    build.VERSION[0] = version
    f1, f2, starts, total, _ = build.schedule()
    fields = [FieldDecoder(f1.pairs), FieldDecoder(f2.pairs)]
    for fd in fields:
        fd.run()
    kind = fmt["kind"]
    cw, ch = fmt["canvas"]
    if kind == "4x3":
        cw, ch = cw * 2, ch * 2                      # the 480i canvas is small; draw the slides at 2x
    mk_grat, mk_base = ((build.graticule_16x9, build.make_base_16x9) if kind == "16x9"
                        else (build.graticule_4x3, build.make_base_4x3))
    grat = mk_grat(cw, ch)
    geo = Geometry(kind, cw, ch)
    outdir = os.path.join(out_root, fmt_name)
    os.makedirs(outdir, exist_ok=True)
    cards = {c["id"]: c for c in json.load(open(os.path.join(HERE, "cards.json")))["cards"]} \
        if os.path.exists(os.path.join(HERE, "cards.json")) else {}
    slides = []
    n = 0
    for si, seg in enumerate(testplan.SEGMENTS):
        base, tl = mk_base(grat, seg, si, len(testplan.SEGMENTS), cw, ch)
        base_img = Image.fromarray(base)
        tfont = ImageFont.truetype(build.FONT_B, tl["size"])
        x0, y0, x1, y1 = tl["box"]
        sl = card_slides(si, seg, starts, total, fields)
        f0 = sec2f(starts[si])
        for k, (name, a, b, snap) in enumerate(sl):
            n += 1
            img = base_img.copy()
            if is_blank(snap):
                what = "no caption displayed"
            else:
                img = draw_captions(img, snap, geo)
                what = "caption displayed"
            d = ImageDraw.Draw(img)
            d.rectangle([x0, y0, x1, y1], fill=(0, 0, 0))
            label = f"REFERENCE  {name}  card +{tstr(a - f0)} to +{tstr(b - f0)} s  ({what})"
            f = build.fit(d, label, build.FONT_B, tl["size"], x1 - x0 - 8)
            d.text((x0 + tl["origin"][0], y0 + tl["origin"][1]), label, font=f, fill=(255, 255, 255))
            fn = f"slide-{n:03d}-{seg.id}-{name}.png"
            img.save(os.path.join(outdir, fn), optimize=True)
            slides.append(dict(file=fn, num=si + 1, of_tests=len(testplan.SEGMENTS), id=seg.id, title=seg.title, group=seg.group, channel=name,
                               frm=tstr(a - f0), to=tstr(b - f0), blank=is_blank(snap),
                               expect=seg.expect, n=k + 1, of=len(sl)))
        print(f"  {seg.id}: {len(sl)} slide(s)")
    write_viewer(os.path.join(outdir, "index.html"), slides, fmt_name, version)
    return len(slides)


VIEWER = """<!doctype html>
<meta charset="utf-8">
<title>CEA-608 Conformance Suite - reference slides (__FORMAT__)</title>
<style>
 body{margin:0;background:#1b1f24;color:#ddd;font:15px -apple-system,Helvetica,Arial,sans-serif}
 #bar{display:flex;gap:8px;align-items:center;padding:8px 12px;background:#2b3138;position:sticky;top:0}
 select{flex:1;min-width:0;font-size:15px;padding:4px}
 button{font-size:15px;padding:4px 14px}
 #info{padding:6px 12px;color:#aab}
 #pic{display:block;max-width:100%;max-height:calc(100vh - 110px);margin:0 auto}
 small{color:#889}
 a{color:#8cd7ff}
 #bar a{white-space:nowrap}
</style>
<div id="bar">
 <a href="../index.html" title="Other stream format">&larr; all formats</a>
 <a href="__REPO__" title="Project page: streams, test list, source">Project</a>
 <button id="prev" title="Left arrow">&larr; Previous</button>
 <select id="sel"></select>
 <button id="next" title="Right arrow">Next &rarr;</button>
</div>
<div id="info"></div>
<img id="pic" alt="reference slide">
<script>
const SLIDES = __SLIDES__;
const sel = document.getElementById('sel'), pic = document.getElementById('pic'), info = document.getElementById('info');
let cur = 0;
const first = {};                               // test number -> index of its first slide
SLIDES.forEach((s, i) => { if (!(s.num in first)) first[s.num] = i; });
let group = null, og = null;
SLIDES.forEach((s, i) => {
  if (first[s.num] !== i) return;               // one entry per test
  if (s.group !== group) { group = s.group; og = document.createElement('optgroup'); og.label = group; sel.appendChild(og); }
  const o = document.createElement('option');
  o.value = i;
  o.textContent = `(${s.num}/${s.of_tests})  ${s.id}  ${s.title}`;
  og.appendChild(o);
});
function show(i) {
  i = Math.max(0, Math.min(SLIDES.length - 1, i));
  cur = i;
  const s = SLIDES[i];
  sel.value = first[s.num];
  pic.src = s.file;
  info.innerHTML = `Slide ${i + 1} of ${SLIDES.length} &middot; test ${s.num} of ${s.of_tests} <b>${s.id}</b> ${s.title} &middot; ${s.channel} &middot; ` +
                   `shown card +${s.frm} to +${s.to} s` + (s.of > 1 ? ` &middot; state ${s.n} of ${s.of}` : '') +
                   `<br><small>Expect: ${s.expect.replace(/&/g,'&amp;').replace(/</g,'&lt;')}</small>`;
  history.replaceState(null, '', '#' + (i + 1));
}
sel.onchange = () => show(+sel.value);
document.getElementById('prev').onclick = () => show(cur - 1);
document.getElementById('next').onclick = () => show(cur + 1);
document.addEventListener('keydown', e => {
  if (e.key === 'ArrowLeft') show(cur - 1);
  else if (e.key === 'ArrowRight' || e.key === ' ') { e.preventDefault(); show(cur + 1); }
});
show(parseInt(location.hash.slice(1) || '1', 10) - 1);
</script>
"""


def write_viewer(path, slides, fmt_name, version):
    page = VIEWER.replace("__REPO__", html.escape(build.META["repo_url"], quote=True)).replace(
        "__FORMAT__", html.escape(f"{fmt_name} {version}")).replace(
        "__SLIDES__", json.dumps(slides, ensure_ascii=False).replace("</", "<\\/"))
    with open(path, "w", encoding="utf-8") as f:
        f.write(page)


def write_top_index(path, formats, version):
    links = "\n".join(f'<li><a href="{f}/index.html">{f}</a></li>' for f in formats)
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"""<!doctype html><meta charset="utf-8"><title>CEA-608 Conformance Suite - reference slides</title>
<body style="font:16px -apple-system,Helvetica,Arial,sans-serif;max-width:40em;margin:3em auto">
<h2>CEA-608 Conformance Suite {html.escape(version)}: reference slides</h2>
<p>What each test card should look like when captions are rendered correctly. Open the set that matches
the stream you are testing, then step through the slides (or pick one from the list) while the stream plays.</p>
<ul>
{links}
</ul>
<p>These slides are the test author's reading of CTA-608-E, drawn by a small decoder model; see the project
README. Licensed CC BY-SA 4.0.</p>
<p>Project: <a href="{html.escape(build.META['repo_url'], quote=True)}">{html.escape(build.META['repo_url'])}</a>
(the test streams, the list of test cards, and the source of these slides).</p>
""")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--format", choices=sorted(build.FORMATS) + ["both"], default="both")
    ap.add_argument("--out", default=os.path.join(HERE, "out", "reference"))
    ap.add_argument("--version-label", default=None)
    ap.add_argument("--zip", metavar="DIR", default=None, help="also write the release zip into DIR")
    a = ap.parse_args()
    version = a.version_label or build.git_version()
    formats = sorted(build.FORMATS) if a.format == "both" else [a.format]
    for fmt in formats:
        print(f"{fmt}:")
        n = render_format(fmt, a.out, version)
        print(f"{fmt}: {n} slides -> {os.path.join(a.out, fmt)}/index.html")
    write_top_index(os.path.join(a.out, "index.html"), formats, version)
    if a.zip:
        import zipfile
        safe = re.sub(r"[^A-Za-z0-9._+-]", "_", version)
        top = f"CEA608-conformance-{safe}-reference"
        os.makedirs(a.zip, exist_ok=True)
        path = os.path.join(a.zip, top + ".zip")
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
            for root, _, files in os.walk(a.out):
                for fn in sorted(files):
                    full = os.path.join(root, fn)
                    z.write(full, os.path.join(top, os.path.relpath(full, a.out)))
        print("wrote", path)


if __name__ == "__main__":
    main()
