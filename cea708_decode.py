# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2026 Devin Heitmueller <devin.heitmueller@gmail.com>
"""Reference CEA-708 (DTVCC) decoder model: the author's reading of CTA-708-E, written independently of the converter.

  from cea708_decode import Decoder
  d = Decoder(aspect="16:9")
  d.picture(triplets, t)                 # triplets: [(cc_type, cc_valid, b1, b2)] of one cc_data(); t in seconds
  d.snapshot(1)                          # service 1 as a 15 x 32 grid of cells (None or (char, fg, ul, it, bg, alpha, flash))

Layers (CTA-708-E): cc_data() triplets -> caption channel packets (4.3, 5.1: cc_type 3 starts, 2 continues; a new start,
a sequence jump or a short packet cuts one off) -> service blocks (6.2) -> one byte stream per service -> the command
interpreter of 8.10 (C0, C1, G0, G1, G2 code sets of 7.1; C2/C3/P16 are skipped by their implied length) with windows,
pens and the Delay command.  ``snapshot`` flattens the visible windows to the CEA-608 15 x 32 grid so that the result
can be compared with ``reference.Decoder`` and drawn by ``reference.draw_captions``; windows that do not sit on that
grid are reported in ``issues`` instead.

What is modelled (everything the upconverter and 10-A 27.2.2 use): window definition and update (8.10.5.2: an
unchanged definition is ignored, an update keeps text and pen), the predefined window and pen styles of Tables 26-27,
SetWindowAttributes, SetPenAttributes, SetPenColor, SetPenLocation, Clear/Delete/Display/Hide/Toggle windows, Delay and
DelayCancel (not pre-processed: they act when reached), Reset, the CR / HCR / BS / FF codes for horizontal print
directions, left justification, priority.  Not modelled: fade and wipe effects, borders, fonts and sizes (these do not
change which cell holds which character), vertical print directions (reported), justification other than left (reported).
"""
GRID_COLS, GRID_ROWS = 32, 15
COL = {(3, 3, 3): "w", (0, 3, 0): "g", (0, 0, 3): "b", (0, 3, 3): "c", (3, 0, 0): "r", (3, 3, 0): "y",
       (3, 0, 3): "m", (0, 0, 0): "k"}
ALPHA = {0: "o", 1: "o", 2: "s", 3: "t"}

G2 = {0x20: " ", 0x21: " ", 0x25: "…", 0x2A: "Š", 0x2C: "Œ", 0x30: "█", 0x31: "‘",
      0x32: "’", 0x33: "“", 0x34: "”", 0x35: "•", 0x39: "™", 0x3A: "š",
      0x3C: "œ", 0x3D: "℠", 0x3F: "Ÿ", 0x76: "⅛", 0x77: "⅜", 0x78: "⅝",
      0x79: "⅞", 0x7A: "│", 0x7B: "┐", 0x7C: "└", 0x7D: "─", 0x7E: "┘",
      0x7F: "┌"}
TRANSPARENT_SPACES = {0x20, 0x21}

# Table 26: justify, print, scroll, fill colour, fill opacity (word wrap is always off, display effect snap)
WSTYLE = {1: (0, 0, 3, 0), 2: (0, 0, 3, 3), 3: (2, 0, 3, 0), 4: (0, 0, 3, 0), 5: (0, 0, 3, 3), 6: (2, 0, 3, 0),
          7: (0, 2, 1, 0)}
# Table 27: font, edge type, bg opacity
PSTYLE = {1: (0, 0, 0), 2: (1, 0, 0), 3: (2, 0, 0), 4: (3, 0, 0), 5: (4, 0, 0), 6: (3, 3, 3), 7: (4, 3, 3)}


class Pen:
    def __init__(self, style=1):
        font, edge, bgop = PSTYLE[style]
        self.size, self.font, self.tag, self.offset = 1, font, 0, 1
        self.italic = self.underline = False
        self.edge = edge
        self.fg, self.fg_op, self.bg, self.bg_op, self.edge_color = (3, 3, 3), 0, (0, 0, 0), bgop, (0, 0, 0)

    def cell(self, ch):
        return (ch, self.fg, self.fg_op, self.bg, self.bg_op, self.underline, self.italic)


class Window:
    def __init__(self, wid):
        self.wid = wid
        self.params = None
        self.visible = False
        self.priority = self.ap = self.rel = self.av = self.ah = 0
        self.rows = self.cols = 1
        self.cells = [[None]]
        self.cur = (0, 0)
        self.pen = Pen()
        self.set_style(1)

    def set_style(self, ws):
        self.justify, self.pd, self.sd, op = WSTYLE[ws]
        self.fill, self.fill_op = (0, 0, 0), op
        self.ww = self.de = self.ed = self.es = 0
        self.border_type, self.border = 0, (0, 0, 0)

    def resize(self, rows, cols):
        old = self.cells
        self.cells = [[(old[r][c] if r < len(old) and c < len(old[0]) else None) for c in range(cols)]
                      for r in range(rows)]
        self.rows, self.cols = rows, cols

    def clear(self):
        self.cells = [[None] * self.cols for _ in range(self.rows)]
        self.cur = (0, 0)


class ServiceDecoder:
    def __init__(self, num, issues):
        self.num, self.issues = num, issues
        self.windows = [None] * 8
        self.cur = None
        self.buf = bytearray()
        self.delay_until = None
        self.dirty = True

    def reset(self):
        self.windows = [None] * 8
        self.cur = None
        self.buf = bytearray()
        self.delay_until = None
        self.dirty = True

    def feed(self, data, now):
        self.buf += data
        self.run(now)

    # -- interpreter
    def run(self, now):
        while self.buf:
            if self.delay_until is not None:
                if now < self.delay_until:
                    return
                self.delay_until = None
            n = self.element(self.buf, now)
            if n == 0:
                return
            del self.buf[:n]

    def win(self):
        return self.windows[self.cur] if self.cur is not None else None

    def element(self, b, now):
        """Interpret the element at the start of ``b``; return its length, or 0 if it is not complete yet."""
        c = b[0]
        if c < 0x20:                                                       # C0
            if c in (0x00, 0x03):
                return 1
            if c == 0x08:
                self.control_bs()
                return 1
            if c == 0x0C:
                w = self.win()
                if w:
                    w.clear()
                    self.dirty = True
                return 1
            if c == 0x0D:
                self.control_cr()
                return 1
            if c == 0x0E:
                w = self.win()
                if w:
                    w.cells[w.cur[0]] = [None] * w.cols
                    w.cur = (w.cur[0], 0)
                    self.dirty = True
                return 1
            if c == 0x10:
                return self.ext1(b)
            if c < 0x10:
                return 1
            n = 2 if c < 0x18 else 3
            return n if len(b) >= n else 0
        if c < 0x80:                                                       # G0
            self.put("♪" if c == 0x7F else chr(c))
            return 1
        if c >= 0xA0:                                                      # G1
            self.put(chr(c))
            return 1
        return self.c1(b, now)

    def ext1(self, b):
        if len(b) < 2:
            return 0
        c = b[1]
        if 0x20 <= c <= 0x7F:                                              # G2
            self.put(G2.get(c, "_"), transparent=c in TRANSPARENT_SPACES)
            return 2
        if c >= 0xA0:                                                      # G3
            self.put("_")
            return 2
        if c < 0x80:                                                       # C2: length from the code
            n = 2 + (0 if c < 0x08 else 1 if c < 0x10 else 2 if c < 0x18 else 3)
            return n if len(b) >= n else 0
        if c < 0x88:                                                       # C3 fixed
            n = 6
        elif c < 0x90:
            n = 7
        else:                                                              # C3 variable: header byte gives the length
            if len(b) < 3:
                return 0
            n = 3 + (b[2] & 0x1F)
        return n if len(b) >= n else 0

    def c1(self, b, now):
        c = b[0]
        need = {0x88: 2, 0x89: 2, 0x8A: 2, 0x8B: 2, 0x8C: 2, 0x8D: 2, 0x90: 3, 0x91: 4, 0x92: 3, 0x97: 5}.get(c)
        if need is None:
            need = 7 if c >= 0x98 else 1
        if len(b) < need:
            return 0
        if c <= 0x87:
            self.cur = c - 0x80 if self.windows[c - 0x80] is not None else None
            if self.cur is None:
                self.issues.add(f"svc{self.num}: SetCurrentWindow {c - 0x80} of an undefined window")
        elif c in (0x88, 0x89, 0x8A, 0x8B, 0x8C):
            self.window_map(c, b[1])
        elif c == 0x8D:
            self.delay_until = now + b[1] / 10.0
        elif c == 0x8E:
            self.delay_until = None
        elif c == 0x8F:
            self.reset()
        elif c == 0x90:
            w = self.win()
            if w:
                p = w.pen
                p.tag, p.offset, p.size = b[1] >> 4, (b[1] >> 2) & 3, b[1] & 3
                p.italic, p.underline, p.edge, p.font = bool(b[2] & 0x80), bool(b[2] & 0x40), (b[2] >> 3) & 7, b[2] & 7
        elif c == 0x91:
            w = self.win()
            if w:
                p = w.pen
                p.fg_op = b[1] >> 6
                p.fg = ((b[1] >> 4) & 3, (b[1] >> 2) & 3, b[1] & 3)
                p.bg_op = b[2] >> 6
                p.bg = ((b[2] >> 4) & 3, (b[2] >> 2) & 3, b[2] & 3)
                p.edge_color = ((b[3] >> 4) & 3, (b[3] >> 2) & 3, b[3] & 3)
        elif c == 0x92:
            w = self.win()
            if w:
                r, col = b[1] & 0x0F, b[2] & 0x3F
                if r >= w.rows or col >= w.cols:
                    self.issues.add(f"svc{self.num}: SetPenLocation {r},{col} outside a {w.rows}x{w.cols} window")
                    r, col = min(r, w.rows - 1), min(col, w.cols - 1)
                w.cur = (r, col)
        elif c == 0x97:
            w = self.win()
            if w:
                w.fill_op, w.fill = b[1] >> 6, ((b[1] >> 4) & 3, (b[1] >> 2) & 3, b[1] & 3)
                w.border_type = ((b[3] >> 7) << 2) | (b[2] >> 6)
                w.border = ((b[2] >> 4) & 3, (b[2] >> 2) & 3, b[2] & 3)
                w.ww, w.pd, w.sd, w.justify = (b[3] >> 6) & 1, (b[3] >> 4) & 3, (b[3] >> 2) & 3, b[3] & 3
                w.es, w.ed, w.de = b[4] >> 4, (b[4] >> 2) & 3, b[4] & 3
                self.dirty = True
        elif c >= 0x98:
            self.define(c - 0x98, b[1:7])
        return need

    def window_map(self, c, m):
        for i in range(8):
            if not m >> i & 1:
                continue
            w = self.windows[i]
            if c == 0x8C:                                                  # DeleteWindows
                if w is not None and self.cur == i:
                    self.cur = None
                self.windows[i] = None
            elif w is None:
                continue
            elif c == 0x88:
                w.clear()
            elif c == 0x89:
                w.visible = True
            elif c == 0x8A:
                w.visible = False
            elif c == 0x8B:
                w.visible = not w.visible
        self.dirty = True

    def define(self, i, p):
        v, rl, cl, pri = (p[0] >> 5) & 1, (p[0] >> 4) & 1, (p[0] >> 3) & 1, p[0] & 7
        rel, av, ah = p[1] >> 7, p[1] & 0x7F, p[2]
        ap, rows, cols = p[3] >> 4, (p[3] & 0x0F) + 1, (p[4] & 0x3F) + 1
        ws, ps = (p[5] >> 3) & 7, p[5] & 7
        key = (v, pri, rel, av, ah, ap, rows, cols, ws, ps)
        w = self.windows[i]
        if w is None:
            w = self.windows[i] = Window(i)
            w.set_style(ws or 1)
            w.pen = Pen(ps or 1)
            w.resize(rows, cols)
            w.cur = (0, 0)
        elif w.params == key:
            return                                                         # unchanged: ignored (8.10.5.2)
        else:
            if ws:
                w.set_style(ws)
            w.resize(rows, cols)
            w.cur = (min(w.cur[0], rows - 1), min(w.cur[1], cols - 1))
        w.params = key
        w.visible, w.priority, w.rel, w.av, w.ah, w.ap = bool(v), pri, rel, av, ah, ap
        self.cur = i
        self.dirty = True

    def put(self, ch, transparent=False):
        w = self.win()
        if w is None:
            self.issues.add(f"svc{self.num}: text with no current window")
            return
        if w.pd not in (0, 1):
            self.issues.add(f"svc{self.num}: vertical print direction not modelled")
            return
        if w.justify:
            self.issues.add(f"svc{self.num}: justification {w.justify} not modelled (treated as left)")
        r, c = w.cur
        w.cells[r][c] = None if transparent else w.pen.cell(ch)
        if w.pd == 0:
            c = min(c + 1, w.cols - 1) if c + 1 < w.cols else c           # last column: the character is replaced
        else:
            c = max(c - 1, 0)
        w.cur = (r, c)
        self.dirty = True

    def control_bs(self):
        w = self.win()
        if w and w.cur[1] > 0:
            r, c = w.cur
            w.cells[r][c - 1] = None
            w.cur = (r, c - 1)
            self.dirty = True

    def control_cr(self):
        """Table 24 for horizontal print directions with vertical scrolling."""
        w = self.win()
        if w is None:
            return
        r, c = w.cur
        if w.sd == 3:                                                      # bottom-to-top: increment the row
            if r + 1 >= w.rows:
                w.cells = w.cells[1:] + [[None] * w.cols]
                r = w.rows - 1
            else:
                r += 1
        elif w.sd == 2:                                                    # top-to-bottom: decrement the row
            if r == 0:
                w.cells = [[None] * w.cols] + w.cells[:-1]
            else:
                r -= 1
        else:
            self.issues.add(f"svc{self.num}: horizontal scroll direction not modelled")
        w.cur = (r, w.cols - 1 if w.pd == 1 else 0)
        self.dirty = True


class Decoder:
    """cc_data() -> packets -> service blocks -> services 1..63."""

    def __init__(self, aspect="16:9", sequence_reset=True):
        self.sequence_reset = sequence_reset      # 5.1: a jump in the sequence number resets every service
        self.col0 = 5 if aspect == "16:9" else 0               # first column of the 608 area in the 42/32 column grid
        self.cols = 42 if aspect == "16:9" else 32
        self.svc = {}
        self.issues = set()
        self.notes = set()          # tolerated deviations: relative positions rounded to the character grid, out of range values
        self.pkt = None
        self.seq = None
        self.packets = 0
        self.snap_cache = {}

    def service(self, n):
        if n not in self.svc:
            self.svc[n] = ServiceDecoder(n, self.issues)
        return self.svc[n]

    # -- transport
    def picture(self, triplets, now):
        for cc_type, valid, b1, b2 in triplets:
            if cc_type < 2 or not valid:
                continue
            if cc_type == 3:
                self.finish(now)
                seq, size = b1 >> 6, b1 & 0x3F
                if self.seq is not None and seq != (self.seq + 1) & 3:
                    self.issues.add("caption channel packet sequence number jumped")
                    self.jumps = getattr(self, "jumps", 0) + 1
                    if self.sequence_reset:
                        for s in self.svc.values():
                            s.reset()
                self.seq = seq
                self.pkt = [(128 if size == 0 else 2 * size), bytearray([b2])]
            elif self.pkt is not None:
                self.pkt[1] += bytes([b1, b2])
            if self.pkt is not None and len(self.pkt[1]) + 1 >= self.pkt[0]:
                self.finish(now)
        for s in self.svc.values():
            s.run(now)

    def finish(self, now):
        if self.pkt is None:
            return
        data = bytes(self.pkt[1][:self.pkt[0] - 1])
        self.pkt = None
        self.packets += 1
        i = 0
        while i < len(data):
            sn, bs = data[i] >> 5, data[i] & 0x1F
            i += 1
            if sn == 0:
                break
            if sn == 7 and bs:
                if i >= len(data):
                    break
                sn = data[i] & 0x3F
                i += 1
            self.service(sn).feed(data[i:i + bs], now)
            i += bs

    # -- display
    def snapshot(self, n):
        """Service n as the 15 x 32 grid of the 608 model; None where it is unchanged since the last call is not
        signalled - callers compare snapshots themselves."""
        s = self.svc.get(n)
        empty = tuple(tuple([None] * GRID_COLS) for _ in range(GRID_ROWS))
        if s is None:
            return empty
        if not s.dirty and n in self.snap_cache:
            return self.snap_cache[n]
        grid = [[None] * GRID_COLS for _ in range(GRID_ROWS)]
        for w in sorted((w for w in s.windows if w is not None and w.visible), key=lambda w: -w.priority):
            bw, bh = w.cols * 5, w.rows * 5
            if w.rel:
                # relative positioning (8.10.5.2): av, ah are percentages of the grid (0-99); the window is rounded to the
                # nearest character cell, which is what a decoder with 5-cell characters has to do
                if w.av > 99 or w.ah > 99:
                    self.notes.add(f"svc{n}: relative anchor {w.av},{w.ah} outside 0-99")
                ax, ay = w.ah / 100 * self.cols * 5, w.av / 100 * 75
                x0 = ax - {0: 0, 1: bw / 2, 2: bw}[w.ap % 3]
                y0 = ay - {0: 0, 1: bh / 2, 2: bh}[w.ap // 3]
                col0, row0 = round(x0 / 5) - self.col0, round(y0 / 5)
                if abs(x0 / 5 - round(x0 / 5)) > 0.01 or abs(y0 / 5 - round(y0 / 5)) > 0.01:
                    self.notes.add(f"svc{n}: relative position rounded to the character grid")
            else:
                x0 = w.ah - {0: 0, 1: bw // 2, 2: bw - 1}[w.ap % 3]
                y0 = w.av - {0: 0, 1: bh // 2, 2: bh - 1}[w.ap // 3]
                if x0 % 5 or y0 % 5:
                    self.issues.add(f"svc{n}: window {w.wid} is not on the character grid ({x0},{y0})")
                col0, row0 = x0 // 5 - self.col0, y0 // 5
            for r in range(w.rows):
                for c in range(w.cols):
                    cell = w.cells[r][c]
                    if cell is None:
                        continue
                    gr, gc = row0 + r, col0 + c
                    if not (0 <= gr < GRID_ROWS and 0 <= gc < GRID_COLS):
                        self.issues.add(f"svc{n}: window {w.wid} cell outside the 608 area")
                        continue
                    ch, fg, fg_op, bg, bg_op, ul, it = cell
                    grid[gr][gc] = (ch, COL.get(fg, fg), ul, it, COL.get(bg, bg), ALPHA[bg_op], fg_op == 1)
        snap = tuple(tuple(r) for r in grid)
        s.dirty = False
        self.snap_cache[n] = snap
        return snap


# ---------------------------------------------------------------------------------------------- comparison
SUBSTITUTE = {"\u25a0": "\u2588", "\u2014": "\u2500"}     # 608 characters that 708 has no code for, see cea708.NEAREST


def normalize(snap):
    """A 608 snapshot with the characters 708 cannot represent replaced by their documented nearest equivalents."""
    return tuple(tuple((SUBSTITUTE.get(c[0], c[0]),) + tuple(c[1:]) if c else None for c in row) for row in snap)


def compare_states(ref, got, coalesce=6, transient=2):
    """Compare the sequence of caption states of the 608 reference decoder (``ref``) with that of a 708 decoder
    (``got``); both are [(caption frame, snapshot)] listing every change.

    A 708 caption travels in service blocks that wait for bandwidth, so a 708 decoder may run behind and then show
    two 608 states in one step ("coalesced": the skipped states lay within ``coalesce`` frames), or pass through a
    state the 608 decoder never shows for more than ``transient`` frames ("transient": the 708 command sequence is not
    atomic).  Anything else is a mismatch, reported as (ref index, ref frame, got frame, got index).  Returns a dict with the lists of (index, frame, ...) findings and the
    largest lag in frames."""
    out = {"mismatch": [], "coalesced": [], "transient": [], "lag": 0}
    i = j = 0
    while i < len(ref) and j < len(got):
        if ref[i][1] == got[j][1]:
            out["lag"] = max(out["lag"], got[j][0] - ref[i][0])
            i += 1
            j += 1
            continue
        m = next((m for m in range(1, 6) if i + m < len(ref) and ref[i + m][1] == got[j][1]), None)
        if m and ref[i + m][0] - ref[i][0] <= coalesce:
            out["coalesced"].append((i, ref[i][0], m))
            i += m
            continue
        m = next((m for m in range(1, 6) if j + m < len(got) and got[j + m][1] == ref[i][1]), None)
        if m and got[j + m][0] - got[j][0] <= transient:
            out["transient"].append((i, got[j][0], m))
            j += m
            continue
        out["mismatch"].append((i, ref[i][0], got[j][0], j))
        # resynchronise on the next common state; every reference state skipped on the way is a mismatch too
        best = min(((a + b, a, b) for a in range(0, 8) for b in range(0, 8)
                    if (a or b) and i + a < len(ref) and j + b < len(got) and ref[i + a][1] == got[j + b][1]),
                   default=None)
        if best is None:
            i += 1
            j += 1
        else:
            for k in range(1, best[1]):
                out["mismatch"].append((i + k, ref[i + k][0], got[min(j + k, j + best[2] - 1)][0], min(j + k, j + best[2] - 1)))
            i += best[1]
            j += best[2]
    if i < len(ref) or j < len(got):
        out["mismatch"].append((i, ref[i][0] if i < len(ref) else None, got[j][0] if j < len(got) else None, j))
    return out


def decode_pictures(pictures, ppf, aspect="16:9", services=(1, 2, 3, 4), sequence_reset=True):
    """Run display-order pictures (each a list of (cc_type, cc_valid, b1, b2)) through a ``Decoder``.

    ``ppf`` is the number of pictures per 29.97 Hz caption frame (2 for 720p59, 1 for 480i59); states are sampled
    once per caption frame, like the 608 reference does.  Returns (decoder, {service: [(caption frame, snapshot)]})
    with an initial empty state at frame 0."""
    d = Decoder(aspect, sequence_reset)
    seqs = {n: [(0, d.snapshot(n))] for n in services}
    dt = 1001 / (60000 if ppf == 2 else 30000)
    for v, trip in enumerate(pictures):
        d.picture(trip, v * dt)
        if (v + 1) % ppf:
            continue
        for n in services:
            sn = d.snapshot(n)
            if sn != seqs[n][-1][1]:
                seqs[n].append((v // ppf, sn))
    return d, seqs


def reference_states(f1, f2):
    """The 608 reference decoder (reference.py) on both fields: {service 1-4: [(caption frame, snapshot)]}, with the
    characters 708 cannot represent replaced (``normalize``)."""
    import reference
    out = {}
    for fi, fld in enumerate((f1, f2)):
        fd = reference.FieldDecoder(fld.pairs)
        fd.run()
        for ch in (1, 2):
            out[fi * 2 + ch] = [(f, normalize(s)) for f, s in fd.states[ch]]
    return out
