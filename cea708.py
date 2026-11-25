# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2026 Devin Heitmueller <devin.heitmueller@gmail.com>
"""CEA-708 (DTVCC) encoder and CEA-608 -> CEA-708 up-converter used by the test stream generator.

Written from CTA-708-E and CEA-CEB-10-A section 27.2 (transcoding recommendations); it is *not* derived from any
existing converter, so that converters under test (GStreamer's cea608tocea708, ccextractor, ...) can be compared with
an independent reading of the specification.  Nothing here needs numpy or PIL.

Layers, bottom to top:

  * command and text encoders (CTA-708-E 7.1 and 8.10): ``df``, ``spa``, ``spc``, ``spl``, ``swa``, ``clw`` ...,
    ``text_bytes`` (G0/G1/G2 code sets);
  * ``Mux``: service blocks (6.2) inside caption channel packets (5.1) inside the ``cc_data()`` triplets of one picture
    (4.3), cc_type 3 for the start of a packet and 2 for its continuation, with whatever bandwidth the picture has left
    after the CEA-608 pairs (4.1: the 608 data is part of the 9600 bps allocation);
  * ``Service`` / ``Upconverter``: a 608 data channel (CC1..CC4) is followed byte pair by byte pair and every
    caption command is translated to the 708 commands that produce the same picture, following the sequences of
    CEA-CEB-10-A 27.2.2 (and 708-E 8.11): service 1..4 carry CC1..CC4.

How a 608 caption memory is mapped onto 708 windows (one 708 service per 608 channel, 8 windows per service):

  * **Memory = window set.**  The displayed and the non-displayed memory each own four window ids (0-3 and 4-7; the
    608 four-row limit means a memory never needs more).  The end-of-caption command swaps the two sets exactly like
    608 swaps its memories: HideWindows for the displayed set and DisplayWindows for the other in one queue element
    (``swap='showhide'``, the default, which every decoder tried copes with), or one ToggleWindows over every defined
    window (``swap='toggle'``, 10-A 27.2.2.3 option A).
  * **Pop-on and paint-on: one window per caption row**, 32 columns wide, defined at the row's 608 position when the row
    is first written (10-A 27.2.2.2), so vertical spacing is exact and the 12-row window limit never matters.  Window
    style 2 (708-E Table 26: left, left-to-right, bottom-to-top, snap, transparent fill) and pen style 1.
  * **Roll-up: one window of ``depth`` rows** whose bottom row is the 608 base row (window style 5, scroll up).  A carriage
    return is the 708 CR code; a preamble address code that moves the base row moves the window with DefineWindow
    (708-E 8.10.5.2 says an update keeps the text).
  * **Column**: the window's first column is 608 column 1.  On a 16:9 picture the 32 columns are centred in the 42-column
    grid (708-E 8.2 and 8.5.1.1; 10-A 23.3), which is anchor horizontal 25; on 4:3 it is 0.  A text row is 5 anchor
    grid cells high and a column is 5 wide (8.5.1.3 c).
  * **Attributes**: foreground colour, italics and underline are SetPenColor / SetPenAttributes; mid-row codes, background
    and foreground attribute codes occupy a cell in 608 and so write a space after the pen command.
  * **Things 708 has no code for** are written explicitly: delete-to-end-of-row writes transparent spaces, a character at
    column 32 is preceded by SetPenLocation (the 708 text says only "replace the final character or be discarded", 8.4.8).

``Upconverter`` mirrors the behaviour of ``reference.Decoder`` (the 608 model of the suite) so that 708 decoded by
``cea708_decode`` can be compared with the 608 reference slides; ``test_cea708.py`` does that for every card.
"""
from cea608 import BASIC_SUBST, COLORS, EXT12, EXT13, SPECIAL

ROWS, COLS = 15, 32
SERVICES = 4                     # CC1-CC4 become services 1-4
LOSS_FRAMES = 45                 # 608-E C.21: frames without valid data before the display is disabled

# ---------------------------------------------------------------------------------------------- code space
NUL, ETX, BS, FF, CR, HCR, EXT1 = 0x00, 0x03, 0x08, 0x0C, 0x0D, 0x0E, 0x10
CW0, CLW, DSW, HDW, TGW, DLW, DLY, DLC, RST = 0x80, 0x88, 0x89, 0x8A, 0x8B, 0x8C, 0x8D, 0x8E, 0x8F
SPA, SPC, SPL, SWA, DF0 = 0x90, 0x91, 0x92, 0x97, 0x98

RGB = {"w": (3, 3, 3), "g": (0, 3, 0), "b": (0, 0, 3), "c": (0, 3, 3), "r": (3, 0, 0),
       "y": (3, 3, 0), "m": (3, 0, 3), "k": (0, 0, 0)}
SOLID, FLASH, TRANSLUCENT, TRANSPARENT = 0, 1, 2, 3
OPACITY = {"o": SOLID, "s": TRANSLUCENT, "t": TRANSPARENT}

# G2 (reached with EXT1, 708-E Table 17); G3 holds only the caption icon.  Latin-1 is G1 (0xA0-0xFF).
G2 = {"█": 0x30, "‘": 0x31, "’": 0x32, "“": 0x33, "”": 0x34, "•": 0x35,
      "™": 0x39, "℠": 0x3D, "…": 0x25, "Š": 0x2A, "š": 0x3A, "Œ": 0x2C,
      "œ": 0x3C, "Ÿ": 0x3F, "│": 0x7A, "┐": 0x7B, "└": 0x7C, "─": 0x7D,
      "┘": 0x7E, "┌": 0x7F}
# 608 characters with no 708 code point: nearest equivalent (documented in DEVELOPING.md)
NEAREST = {"■": "█",       # 608 0x7F solid block -> G2 solid block
           "—": "─"}       # 608 em dash has no 708 code; G2 0x7D is a horizontal line


def text_bytes(ch):
    """The 708 bytes of one character: G0 (0x20-0x7E, 0x7F is the music note), G1 (Latin-1) or EXT1 + G2."""
    ch = NEAREST.get(ch, ch)
    o = ord(ch)
    if 0x20 <= o < 0x7F:
        return bytes([o])
    if ch == "♪":
        return bytes([0x7F])
    if 0xA0 <= o <= 0xFF:
        return bytes([o])
    if ch in G2:
        return bytes([EXT1, G2[ch]])
    raise ValueError(f"no CEA-708 code for {ch!r}")


def cw(wid):
    return bytes([CW0 + wid])


def window_map_cmd(code, wmap):
    return bytes([code, wmap & 0xFF])


def df(wid, priority, anchor_point, av, ah, rows, cols, visible, window_style, pen_style, relative=0):
    """DefineWindow (708-E 8.10.5.2): seven bytes.  ``rows``/``cols`` are counts (the code carries count - 1);
    row lock and column lock are 1 (reserved, decoders assume locked)."""
    return bytes([DF0 + wid,
                  (visible << 5) | (1 << 4) | (1 << 3) | priority,
                  (relative << 7) | av, ah,
                  (anchor_point << 4) | (rows - 1), cols - 1,
                  (window_style << 3) | pen_style])


def swa(justify=0, print_dir=0, scroll_dir=3, display_effect=0, effect_dir=0, effect_speed=0,
        fill=(0, 0, 0), fill_opacity=TRANSPARENT, border_type=0, border=(0, 0, 0)):
    return bytes([SWA,
                  (fill_opacity << 6) | (fill[0] << 4) | (fill[1] << 2) | fill[2],
                  ((border_type & 3) << 6) | (border[0] << 4) | (border[1] << 2) | border[2],
                  ((border_type >> 2) << 7) | (print_dir << 4) | (scroll_dir << 2) | justify,
                  (effect_speed << 4) | (effect_dir << 2) | display_effect])


def spa(pen_size=1, offset=1, text_tag=0, italic=False, underline=False, edge=0, font=0):
    return bytes([SPA, (text_tag << 4) | (offset << 2) | pen_size,
                  (italic << 7) | (underline << 6) | (edge << 3) | font])


def spc(fg, fg_opacity, bg, bg_opacity, edge=(0, 0, 0)):
    return bytes([SPC, (fg_opacity << 6) | (fg[0] << 4) | (fg[1] << 2) | fg[2],
                  (bg_opacity << 6) | (bg[0] << 4) | (bg[1] << 2) | bg[2],
                  (edge[0] << 4) | (edge[1] << 2) | edge[2]])


def spl(row, col):
    return bytes([SPL, row, col])


# ---------------------------------------------------------------------------------------------- transport
class Mux:
    """Service blocks -> caption channel packets -> cc_data triplets, picture by picture.

    ``queue(service, element)`` appends one syntactic element (708-E 6.3: it is never split across packets) to a
    service's FIFO.  ``picture(npairs)`` drains as much as fits into one caption channel packet of at most ``npairs``
    byte pairs and returns the triplets [(cc_type, (b1, b2))] (cc_type 3 first, then 2).  A service block holds up to 31
    bytes behind a one-byte header; the packet header carries the rolling sequence number and the size in byte pairs; a
    null block header (0x00) fills the last byte when space remains (6.2.5).  A picture that has nothing to send
    sends nothing (the generator pads with cc_valid=0 / cc_type 10)."""

    def __init__(self):
        self.q = {}
        self.seq = 0
        self.rot = -1
        self.sent = 0
        self.max_wait = 0                 # most pictures an element waited
        self.stamp = 0                    # current picture, set by the caller for the wait statistics

    def queue(self, service, element, stamp=None):
        if len(element) > 31:
            raise ValueError("a syntactic element must fit in one service block (31 bytes)")
        self.q.setdefault(service, []).append((element, self.stamp if stamp is None else stamp))

    def pending(self):
        return sum(len(v) for v in self.q.values())

    def picture(self, npairs, picno=0):
        room = 2 * npairs - 1                     # bytes of the packet after its header byte
        if npairs < 1 or not any(self.q.values()):
            return []
        body = bytearray()
        order = sorted(self.q)
        self.rot = (self.rot + 1) % max(1, len(order))
        for svc in order[self.rot:] + order[:self.rot]:           # rotate so that no service starves another
            fifo = self.q[svc]
            while fifo:
                blk, take = bytearray(), 0
                for el, _ in fifo:
                    if len(blk) + len(el) > 31 or len(body) + 1 + len(blk) + len(el) > room:
                        break
                    blk += el
                    take += 1
                if not blk:
                    break
                for _, st in fifo[:take]:
                    self.max_wait = max(self.max_wait, picno - st)
                del fifo[:take]
                body += bytes([(svc << 5) | len(blk)]) + blk
                if fifo and len(body) + 2 > room:
                    break
        if not body:
            raise ValueError("a queued element does not fit in a caption channel packet of %d byte pairs" % npairs)
        if len(body) < room:
            body.append(0x00)                      # null service block header
        if (len(body) + 1) % 2:
            body.append(0x00)
        size = (len(body) + 1) // 2
        data = bytes([(self.seq << 6) | (size & 0x3F)]) + bytes(body)
        self.seq = (self.seq + 1) & 3
        self.sent += 1
        pairs = [(data[i], data[i + 1]) for i in range(0, len(data), 2)]
        return [(3 if i == 0 else 2, p) for i, p in enumerate(pairs)]


# ---------------------------------------------------------------------------------------------- 608 -> 708
DEFAULT_STYLE = ("w", False, False, "k", "o", False)         # fg, underline, italic, bg, alpha, flash (as reference.py)


class Win:
    def __init__(self, wid, top, n):
        self.wid, self.top, self.n = wid, top, n
        self.pen = DEFAULT_STYLE                  # pen style 1: white on solid black
        self.cur = (0, 0)                         # pen location after DefineWindow (708-E 8.10.5.2)


class Mem:
    """What a 608 memory holds (cells as in reference.py) and the windows that show it."""

    def __init__(self, idx):
        self.idx = idx
        self.cells, self.seq, self.counter, self.wins = {}, {}, 0, []

    def used(self, row):
        return any(self.cells.get(row, {}).values())

    def cell(self, row, col):
        return self.cells.get(row, {}).get(col)


class Service:
    """One 608 data channel being converted to one 708 service."""

    def __init__(self, num, out, hoff, swap="showhide"):
        self.num, self.out, self.hoff, self.swap = num, out, hoff, swap
        self.mem = [Mem(0), Mem(1)]
        self.disp = 0
        self.mode = None                  # 'pop', 'paint', 'roll'
        self.depth, self.base = 2, ROWS
        self.row, self.col = ROWS, 1
        self.style = list(DEFAULT_STYLE)
        self.inherit = False
        self.curwin = None                # the window the 708 decoder has selected
        self.last_text = False

    # ---- output
    def emit(self, data):
        self.out(self.num, bytes(data))
        self.last_text = False

    def emit_text(self, data):
        self.out(self.num, bytes(data))
        self.last_text = True

    def end_pair(self):
        """708-E 8.6: caption text not followed by a command is terminated with ETX."""
        if self.last_text:
            self.out(self.num, bytes([ETX]))
            self.last_text = False

    # ---- windows
    def free_id(self, mem):
        used = {w.wid for w in mem.wins}
        return next(i for i in range(4 * mem.idx, 4 * mem.idx + 4) if i not in used)

    def anchor(self, win):
        return 5 * (win.top - 1), self.hoff

    def define(self, mem, win, roll=False, restyle=True, visible=None):
        """DefineWindow.  An update that moves a window passes style 0: "no parameters are changed" (8.10.5.2)."""
        av, ah = self.anchor(win)
        ws, ps = ((5 if roll else 2), 1) if restyle else (0, 0)
        vis = int(mem.idx == self.disp) if visible is None else visible
        self.emit(df(win.wid, win.wid, 0, av, ah, win.n, COLS, vis, ws, ps))
        self.curwin = win.wid

    def select(self, win):
        if self.curwin != win.wid:
            self.emit(cw(win.wid))
            self.curwin = win.wid

    def delete(self, wins, then=b""):
        """DeleteWindows; ``then`` is sent in the same queue element, so a caption channel packet boundary cannot
        fall between the two commands (a half-way picture would show nothing, or both captions)."""
        if not wins:
            if then:
                self.emit(then)
            return
        self.emit(window_map_cmd(DLW, sum(1 << w.wid for w in wins)) + then)
        for w in wins:
            for m in self.mem:
                if w in m.wins:
                    m.wins.remove(w)
            if self.curwin == w.wid:
                self.curwin = None

    def make_roll_window(self, mem, visible=None):
        win = Win(self.free_id(mem), self.base - self.depth + 1, self.depth)
        mem.wins.append(win)
        self.define(mem, win, roll=True, visible=visible)
        return win

    def window_for(self, mem, row):
        for w in mem.wins:
            if w.top <= row < w.top + w.n:
                return w
        if self.mode == "roll" and mem.idx == self.disp:
            return self.make_roll_window(mem)
        if len(mem.wins) >= 4:                       # reclaim windows whose rows were emptied (BS, DER)
            self.delete([w for w in mem.wins if not any(mem.used(r) for r in range(w.top, w.top + w.n))])
        win = Win(self.free_id(mem), row, 1)
        mem.wins.append(win)
        self.define(mem, win)
        return win

    # ---- 608 memories
    @property
    def target(self):
        return self.mem[1 - self.disp] if self.mode == "pop" else self.mem[self.disp]

    @property
    def shown(self):
        return self.mem[self.disp]

    @property
    def hidden(self):
        return self.mem[1 - self.disp]

    def erase(self, mem):
        self.delete(list(mem.wins))
        mem.cells, mem.seq, mem.counter = {}, {}, 0

    def erase_all(self):
        self.erase(self.mem[0])
        self.erase(self.mem[1])

    def clear_row(self, mem, row):
        mem.cells.pop(row, None)
        win = next((w for w in mem.wins if w.top <= row < w.top + w.n), None)
        if win is None:
            return
        if win.n == 1:
            self.delete([win])
            return
        self.select(win)
        self.emit(spl(row - win.top, 0))
        self.emit(bytes([HCR]))
        win.cur = (row - win.top, 0)

    def touch(self, mem, row):
        """608-E C.5/C.6: at most four rows; a fifth replaces the oldest (newer rows preferred)."""
        if not mem.used(row):
            used = [r for r in mem.cells if mem.used(r) and r != row]
            if len(used) >= 4:
                self.clear_row(mem, min(used, key=lambda r: mem.seq.get(r, 0)))
            mem.counter += 1
            mem.seq[row] = mem.counter

    def pen(self, win):
        """SetPenAttributes / SetPenColor for the style the 608 decoder would use for the next character."""
        fg, ul, it, bg, al, fl = self.style
        o_fg, o_ul, o_it, o_bg, o_al, o_fl = win.pen
        if (ul, it) != (o_ul, o_it):
            self.emit(spa(italic=it, underline=ul))
        if (fg, fl, bg, al) != (o_fg, o_fl, o_bg, o_al):
            self.emit(spc(RGB[fg], FLASH if fl else SOLID, RGB[bg], OPACITY[al]))
        win.pen = (fg, ul, it, bg, al, fl)

    def put(self, ch, al=None):
        """al: background opacity of this cell only (the 608 transparent space, 0x11 0x39)."""
        mem = self.target
        row = self.base if self.mode == "roll" else self.row
        if self.mode != "roll":
            self.touch(mem, row)
        if self.inherit and self.col > 1 and mem.cell(row, self.col - 1):          # C.7
            c = mem.cell(row, self.col - 1)
            self.style = [c[1], c[2], c[3], c[4], c[5], c[6]]
        self.inherit = False
        win = self.window_for(mem, row)
        self.select(win)
        pen_al = self.style[4]
        if al:
            self.style[4] = al
        self.pen(win)
        self.style[4] = pen_al
        want = (row - win.top, self.col - 1)
        if win.cur != want:
            self.emit(spl(*want))
        self.emit_text(text_bytes(ch))
        fg, ul, it, bg, pen_al, fl = self.style
        mem.cells.setdefault(row, {})[self.col] = (ch, fg, ul, it, bg, al or pen_al, fl)
        if self.col < COLS:
            self.col += 1
            win.cur = (want[0], want[1] + 1)
        else:
            win.cur = None                       # at the last column the 708 position is not defined (8.4.8)

    def spacing(self, **change):
        names = ("fg", "ul", "it", "bg", "al", "fl")
        for k, v in change.items():
            self.style[names.index(k)] = v
        self.put(" ")

    # ---- commands (same structure as reference.Decoder)
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
        """A PAC in roll-up moves the whole displayed block with the base row (R07)."""
        if base == self.base:
            return
        mem = self.shown
        top, bot = self.base - self.depth + 1, self.base
        rows = [mem.cells.pop(r, None) for r in range(top, bot + 1)]
        for i, cells in enumerate(rows):
            if cells:
                mem.cells[base - self.depth + 1 + i] = cells
        self.base = base
        for w in mem.wins:
            if w.n == self.depth and w.top == top:
                w.top = base - self.depth + 1
                self.define(mem, w, roll=True, restyle=False)   # an update keeps text, pen and location (8.10.5.2)

    def rebuild_roll(self, old_depth):
        """The roll-up depth changed: define a window of the new size and rewrite the rows that stay."""
        mem = self.shown
        old = [w for w in mem.wins if w.n == old_depth]
        win = self.make_roll_window(mem, visible=0)           # written hidden, then swapped in, so no half-drawn rows show
        for row in sorted(mem.cells):
            if win.top <= row < win.top + win.n:
                self.rewrite_row(mem, win, row)
        self.delete(old, window_map_cmd(DSW, 1 << win.wid))
        self.curwin = win.wid

    def rewrite_row(self, mem, win, row):
        cells = mem.cells[row]
        self.select(win)
        nxt = None
        for col in sorted(cells):
            fg, ul, it, bg, al, fl = cells[col][1:]
            self.style, saved = [fg, ul, it, bg, al, fl], self.style
            self.pen(win)
            self.style = saved
            if nxt != col:
                self.emit(spl(row - win.top, col - 1))
            self.emit_text(text_bytes(cells[col][0]))
            nxt = col + 1 if col < COLS else None
        win.cur = None
        self.end_pair()

    def der(self, mem, win, row, last):
        """Delete to end of row.  708 has no such code.  A one-row window is replaced by a new one that is written hidden
        and swapped in (the 608 result is instant); otherwise the cells are overwritten with transparent spaces."""
        kept = mem.cells.get(row)
        if win.n == 1 and not any(kept.values() if kept else []):
            self.delete([win])
            return
        if win.n == 1 and len(mem.wins) < 4:
            new = Win(self.free_id(mem), row, 1)
            mem.wins.append(new)
            self.define(mem, new, visible=0)
            self.rewrite_row(mem, new, row)
            self.delete([win], window_map_cmd(DSW, 1 << new.wid) if mem.idx == self.disp else b"")
            self.curwin = new.wid
            return
        self.select(win)
        if self.col == 1:
            self.emit(spl(row - win.top, 0))
            self.emit(bytes([HCR]))
        else:
            self.emit(spl(row - win.top, self.col - 1))
            for _ in range(self.col, last + 1):
                self.emit(bytes([EXT1, 0x20]))
        win.cur = None

    def misc(self, code):
        if code == 0x20:                                   # RCL
            self.mode = "pop"
        elif code == 0x21:                                 # BS
            if self.col > 1:
                self.col -= 1
            mem = self.target
            row = self.base if self.mode == "roll" else self.row
            if mem.cell(row, self.col):
                del mem.cells[row][self.col]
                win = next((w for w in mem.wins if w.top <= row < w.top + w.n), None)
                if win is not None:
                    self.select(win)
                    want = (row - win.top, self.col - 1)
                    if win.cur == (want[0], want[1] + 1) and want[1] + 1 < COLS - 1:
                        self.emit(bytes([BS]))             # moves back one position and erases it
                    else:
                        if win.cur != want:
                            self.emit(spl(*want))
                        self.emit(bytes([EXT1, 0x20]))     # transparent space
                    win.cur = None
        elif code == 0x24:                                 # DER
            mem = self.target
            row = self.base if self.mode == "roll" else self.row
            last = max([c for c, v in mem.cells.get(row, {}).items() if v and c >= self.col], default=None)
            if last is not None:
                win = next((w for w in mem.wins if w.top <= row < w.top + w.n), None)
                for c in range(self.col, COLS + 1):
                    mem.cells[row].pop(c, None)
                if win is not None:
                    self.der(mem, win, row, last)
        elif code in (0x25, 0x26, 0x27):                   # RU2-4
            old = self.depth
            was_roll = self.mode == "roll"
            if not was_roll:
                self.erase_all()
                self.base, self.col = ROWS, 1
                self.style = list(DEFAULT_STYLE)
            else:
                self.erase(self.hidden)
                if not any(any(v.values()) for v in self.shown.cells.values()):
                    self.base, self.col = ROWS, 1
                    self.style = list(DEFAULT_STYLE)
            depth = code - 0x23
            if was_roll and depth < self.depth:
                for r in [r for r in self.shown.cells if r <= self.base - depth]:
                    del self.shown.cells[r]
            self.depth = depth
            self.base = max(self.base, depth)
            self.mode = "roll"
            if was_roll and depth != old:
                self.rebuild_roll(old)
        elif code == 0x29:                                 # RDC
            self.mode = "paint"
        elif code == 0x28:                                 # FON
            self.spacing(fl=True)
        elif code == 0x2C:                                 # EDM
            self.erase(self.shown)
        elif code == 0x2D:                                 # CR
            if self.mode == "roll":
                mem = self.shown
                top = self.base - self.depth + 1
                for r in range(top, self.base):
                    if (r + 1) in mem.cells:
                        mem.cells[r] = mem.cells.pop(r + 1)
                    else:
                        mem.cells.pop(r, None)
                mem.cells.pop(self.base, None)
                win = next((w for w in mem.wins if w.top <= self.base < w.top + w.n), None)
                if win is None:
                    win = self.make_roll_window(mem)
                else:
                    self.define(mem, win, roll=True)       # repeated at every row: receivers may tune in at any time
                if win.cur is None or win.cur[0] != win.n - 1:
                    self.emit(spl(win.n - 1, 0))
                self.emit(bytes([CR]))
                win.cur = (win.n - 1, 0)
                self.col = 1
                self.style = list(DEFAULT_STYLE)
                self.inherit = False
        elif code == 0x2E:                                 # ENM
            self.erase(self.hidden)
        elif code == 0x2F:                                 # EOC
            both = self.mem[0].wins + self.mem[1].wins
            if both and self.swap == "toggle":
                self.emit(window_map_cmd(TGW, sum(1 << w.wid for w in both)))
            elif both:                                    # explicit HideWindows + DisplayWindows (no state assumed)
                m_old = sum(1 << w.wid for w in self.shown.wins)
                m_new = sum(1 << w.wid for w in self.hidden.wins)
                self.emit((window_map_cmd(HDW, m_old) if m_old else b"") + (window_map_cmd(DSW, m_new) if m_new else b""))
            self.disp = 1 - self.disp
            self.mode = "pop"

    def midrow(self, code):
        if code >= 0x2E:
            self.spacing(fg="w", it=True, ul=bool(code & 1), fl=False)
        else:
            self.spacing(fg=COLORS[(code - 0x20) // 2], it=False, ul=bool(code & 1), fl=False)

    def background(self, code):
        from cea608 import BG_COLORS
        i = (code - 0x20) // 2
        if self.col > 1:
            self.col -= 1                                  # 608-E 6.2: the code carries an automatic backspace
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


class FieldConverter:
    """Follows the byte pairs of one 608 field (two data channels) and feeds two ``Service`` objects."""

    def __init__(self, services, out, hoff, erase_on_loss=True, swap="showhide"):
        from cea608 import PAC_ROW_BASE, PAC_ROW_FIRST
        self.pac_row = {(PAC_ROW_FIRST[r], PAC_ROW_BASE[r] >= 0x60): r for r in PAC_ROW_FIRST}
        self.svc = {1: Service(services[0], out, hoff, swap), 2: Service(services[1], out, hoff, swap)}
        self.cur = None
        self.last = None
        self.bad = 0
        self.erase_on_loss = erase_on_loss

    def step(self, p):
        valid = p is not None and all(bin(b).count("1") % 2 == 1 for b in p)
        if not valid:
            self.bad += 1
            self.last = None
            if self.bad == LOSS_FRAMES and self.erase_on_loss:     # C.21: disable display, erase memory
                for s in self.svc.values():
                    s.erase_all()
                    s.end_pair()
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
        s = self.svc.get(self.cur)
        if s is None:
            return
        for x in (a, b):
            if x >= 0x20:
                s.put(BASIC_SUBST.get(x, chr(x)))
        s.end_pair()

    def control(self, a, b):
        ch = 2 if a & 0x08 else 1
        lo = a & 0x07
        s = self.svc[ch]
        if b >= 0x40:                                        # PAC
            row = self.pac_row.get((a & 0x17, b >= 0x60))
            if row:
                self.cur = ch
                s.pac(row, b & 0x1F)
            return
        if lo in (4, 5) and 0x20 <= b <= 0x2F:              # miscellaneous control
            self.cur = ch
            s.misc(b)
        elif lo == 1 and 0x20 <= b <= 0x2F:
            self.cur = ch
            s.midrow(b)
        elif lo == 1 and 0x30 <= b <= 0x3F:
            self.cur = ch
            if b == 0x39:                                  # transparent space: a cell with no background box
                s.put(" ", al="t")
            else:
                s.put(SPECIAL[b - 0x30])
        elif lo == 0 and 0x20 <= b <= 0x2F:
            self.cur = ch
            s.background(b)
        elif lo in (2, 3) and 0x20 <= b <= 0x3F:
            self.cur = ch
            s.extended(0x12 if lo == 2 else 0x13, b)
        elif lo == 7 and 0x21 <= b <= 0x23:
            self.cur = ch
            s.col = min(COLS, s.col + (b - 0x20))
        elif lo == 7 and 0x2D <= b <= 0x2F:
            self.cur = ch
            s.attribute(b)
        s.end_pair()


class Upconverter:
    """Both 608 fields -> 708 services 1..4 (CC1, CC2 on field 1; CC3, CC4 on field 2).

    ``run(f1, f2, ppf, npairs608, cc_count)`` returns the extra cc_data triplets of every display-order picture.
    ``aspect`` is '16:9' (the 32 columns centred in the 42-column grid) or '4:3'."""

    def __init__(self, aspect="16:9", erase_on_loss=True, mux=None, swap="showhide"):
        self.swap = swap
        self.hoff = 25 if aspect == "16:9" else 0
        self.mux = mux or Mux()
        self.erase_on_loss = erase_on_loss

    def run(self, f1, f2, ppf, cc_count, only=False):
        """``ppf`` pictures per caption frame (2: one pair per picture, field 1 on even pictures; 1: both pairs)."""
        out = self.mux.queue
        fc = [FieldConverter((1, 2), out, self.hoff, self.erase_on_loss, self.swap),
              FieldConverter((3, 4), out, self.hoff, self.erase_on_loss, self.swap)]
        n = max(len(f1.pairs), len(f2.pairs))
        get = lambda f, i: f.pairs[i] if i < len(f.pairs) else (0x80, 0x80)
        used = 0 if only else (1 if ppf == 2 else 2)
        pics = []
        for svc in (1, 2, 3, 4):
            self.mux.queue(svc, bytes([RST]), 0)             # 708-E 8.9.3: start every service from a known state
        for i in range(n):
            for k, fld in enumerate((f1, f2)):
                self.mux.stamp = i * ppf + (k if ppf == 2 else 0)
                fc[k].step(get(fld, i))
                if ppf == 2:
                    pics.append(self.mux.picture(cc_count - used, len(pics)))
            if ppf == 1:
                pics.append(self.mux.picture(cc_count - used, len(pics)))
        # whatever is still queued after the last caption frame goes into the following pictures (the caller checks that
        # the list is not longer than the video)
        while self.mux.pending():
            pics.append(self.mux.picture(cc_count - used, len(pics)))
        return pics
