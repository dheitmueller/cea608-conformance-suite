# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2026 Devin Heitmueller <devin.heitmueller@gmail.com>
"""Minimal CEA-608 (line 21) caption encoder used by the test stream generator.

Everything here produces *raw 7-bit byte pairs*; odd parity is applied when a
pair is committed to a Field stream.  One pair per field per video frame.
"""
import re
import unicodedata

FPS_N, FPS_D = 30000, 1001


def sec2f(s):
    return round(s * FPS_N / FPS_D)


def parity(b):
    b &= 0x7F
    return b | (0x80 if bin(b).count("1") % 2 == 0 else 0)


class Overrun(Exception):
    pass


# ---------------------------------------------------------------- tables
BASIC_SUBST = {0x2A: "á", 0x5C: "é", 0x5E: "í", 0x5F: "ó", 0x60: "ú",
               0x7B: "ç", 0x7C: "÷", 0x7D: "Ñ", 0x7E: "ñ", 0x7F: "■"}
BASIC_REV = {v: k for k, v in BASIC_SUBST.items()}
SPECIAL = "®°½¿™¢£♪à èâêîôû"                       # 0x11 0x30..0x3F
EXT12 = "ÁÉÓÚÜü‘¡*'—©℠•“”" "ÀÂÇÈÊËëÎÏïÔÙùÛ«»"            # 0x12 0x20..0x3F
EXT13 = "ÃãÍÌìÒòÕõ{}\\^_|~" "ÄäÖöß¥¤│ÅåØø┌┐└┘"           # 0x13 0x20..0x3F
CLASH = set("*\\^_{|}~")        # ASCII positions that 608 remaps
FALLBACK = {"ß": "s", "¥": "Y", "¤": "o", "│": "l", "Ø": "O", "ø": "o",
            "┌": "+", "┐": "+", "└": "+", "┘": "+", "‘": "'", "¡": "!",
            "*": ".", "—": "-", "©": "c", "℠": "S", "•": "o", "“": '"',
            "”": '"', "«": "<", "»": ">", "{": "(", "}": ")", "\\": "/",
            "^": "A", "_": "-", "|": "l", "~": "-", "'": "'"}

EXT_LOOKUP = {}
for _tbl, _chars in ((0x12, EXT12), (0x13, EXT13)):
    for _i, _c in enumerate(_chars):
        if ord(_c) < 0x80 and _c not in CLASH:
            continue
        EXT_LOOKUP[_c] = (_tbl, 0x20 + _i)


def fallback(ch):
    return FALLBACK.get(ch) or unicodedata.normalize("NFD", ch)[0]


COLORS = ["w", "g", "b", "c", "r", "y", "m"]
COLOR_NAMES = {"w": "White", "g": "Green", "b": "Blue", "c": "Cyan",
               "r": "Red", "y": "Yellow", "m": "Magenta"}
MIDROW = {}
for _i, _c in enumerate(COLORS):
    MIDROW[_c] = 0x20 + 2 * _i
    MIDROW[_c + "u"] = 0x21 + 2 * _i
MIDROW["i"], MIDROW["iu"] = 0x2E, 0x2F
PAC_ROW_FIRST = {1: 0x11, 2: 0x11, 3: 0x12, 4: 0x12, 5: 0x15, 6: 0x15,
                 7: 0x16, 8: 0x16, 9: 0x17, 10: 0x17, 11: 0x10, 12: 0x13,
                 13: 0x13, 14: 0x14, 15: 0x14}
PAC_ROW_BASE = {1: 0x40, 2: 0x60, 3: 0x40, 4: 0x60, 5: 0x40, 6: 0x60,
                7: 0x40, 8: 0x60, 9: 0x40, 10: 0x60, 11: 0x40, 12: 0x40,
                13: 0x60, 14: 0x40, 15: 0x60}
BG_COLORS = ["w", "g", "b", "c", "r", "y", "m", "k"]


class Field:
    """One line-21 field; pairs[f] is the pair sent with video frame f."""

    def __init__(self, idx):
        self.idx = idx
        self.pairs = []

    @property
    def cursor(self):
        return len(self.pairs)

    def pad_to(self, frame, who=""):
        if self.cursor > frame:
            raise Overrun(f"{who}: field {self.idx + 1} already at frame "
                          f"{self.cursor}, wanted {frame}")
        self.pairs.extend([(parity(0), parity(0))] * (frame - self.cursor))  # valid nulls

    def gap(self, frames):
        """No waveform: cc_valid=0 for these frames (608-E C.21, CEB-10-A 25.2.1)."""
        self.pairs.extend([None] * frames)

    def bad(self, frames):
        """Waveform with even-parity (zero-filled) data, CEB-10-A Annex A.1.1 (b)."""
        self.pairs.extend([(0x00, 0x00)] * frames)

    def emit(self, pairs, pace=1):
        for a, b in pairs:
            self.pairs.append((parity(a), parity(b)))
            if pace > 1 and a >= 0x20:        # only space out text pairs
                self.pairs.extend([(parity(0), parity(0))] * (pace - 1))


def pack(tokens):
    """ints (text bytes) are packed two per pair; tuples are whole pairs."""
    pairs, pend = [], None
    for t in tokens:
        if isinstance(t, int):
            if pend is None:
                pend = t
            else:
                pairs.append((pend, t))
                pend = None
        else:
            if pend is not None:
                pairs.append((pend, 0))
                pend = None
            pairs.append(t)
    if pend is not None:
        pairs.append((pend, 0))
    return pairs


class R:
    """A caption row: row 1-15, 1-based start column, optional PAC style."""

    def __init__(self, row, text, col=1, color=None, italic=False, ul=False, overflow=False):
        self.overflow = overflow
        self.row, self.text, self.col = row, text, col
        self.color, self.italic, self.ul = color, italic, ul


class Chan:
    def __init__(self, name, field, ch, double=True):
        self.name, self.field, self.ch, self.double = name, field, ch, double

    # ---- low level codes
    def _f(self, base):
        return base + (8 if self.ch == 2 else 0)

    def _rep(self, pair):
        return [pair] * (2 if self.double else 1)

    def misc(self, code):
        return self._rep((self._f(0x14 if self.field.idx == 0 else 0x15), code))

    def pac(self, row, indent=0, color=None, italic=False, ul=False):
        if indent and (color or italic):
            raise ValueError("PAC carries either indent or color/italic")
        if indent:
            code = 0x10 + 2 * (indent // 4)
        elif italic:
            code = 0x0E
        else:
            code = 2 * COLORS.index(color or "w")
        code += 1 if ul else 0
        return self._rep((self._f(PAC_ROW_FIRST[row]), PAC_ROW_BASE[row] + code))

    def tab(self, n):
        return self._rep((self._f(0x17), 0x20 + n)) if n else []

    def midrow(self, name):
        return self._rep((self._f(0x11), MIDROW[name]))

    def bg(self, color, semi=False):
        # 6.2 p.16: provider precedes each attribute code with a standard space;
        # the code carries an automatic backspace.
        return [0x20] + self._rep((self._f(0x10), 0x20 + 2 * BG_COLORS.index(color) + (1 if semi else 0)))

    def attr(self, code):          # 0x2D BT, 0x2E FA, 0x2F FAU (preceded by a space)
        return [0x20] + self._rep((self._f(0x17), code))

    def raw(self, code, n):
        """n identical consecutive misc control pairs, regardless of doubling policy."""
        return [(self._f(0x14 if self.field.idx == 0 else 0x15), code)] * n

    RCL = lambda s: s.misc(0x20)
    BS = lambda s: s.misc(0x21)
    DER = lambda s: s.misc(0x24)
    FON = lambda s: s.misc(0x28)
    RDC = lambda s: s.misc(0x29)
    CR = lambda s: s.misc(0x2D)
    ENM = lambda s: s.misc(0x2E)
    EDM = lambda s: s.misc(0x2C)
    EOC = lambda s: s.misc(0x2F)

    def RU(self, n):
        return self.misc(0x23 + n)

    # ---- text
    def char_tokens(self, ch):
        if ch in SPECIAL and ch != " ":
            return [(self._f(0x11), 0x30 + SPECIAL.index(ch))]
        if ch in EXT_LOOKUP:
            tbl, lo = EXT_LOOKUP[ch]
            return [ord(fallback(ch)), (self._f(tbl), lo)]
        if ch in BASIC_REV:
            return [BASIC_REV[ch]]
        if 0x20 <= ord(ch) < 0x7F and ch != "`":
            return [ord(ch)]
        raise ValueError(f"unencodable character {ch!r}")

    @staticmethod
    def width(text):
        return len(re.sub(r"\{[^{}]+\}", "#", text))

    def tokens(self, text, overflow=False):
        if self.width(text) > 32 and not overflow:
            raise ValueError(f"caption text exceeds 32 columns: {text!r}")
        out = []
        for part in re.split(r"(\{[^{}]+\})", text):
            if not part:
                continue
            if part[0] == "{" and len(part) > 1:
                body = part[1:-1]
                if body in MIDROW:
                    out += self.midrow(body)
                elif body.startswith("X"):       # {X12:2A} extended, no fallback char
                    tbl, lo = re.match(r"X([0-9A-F]{2}):([0-9A-F]{2})", body).groups()
                    out.append((self._f(int(tbl, 16)), int(lo, 16)))
                elif body.startswith("x"):       # {x12:2A:A} raw extended
                    tbl, lo, fb = re.match(
                        r"x([0-9A-F]{2}):([0-9A-F]{2}):(.)", body).groups()
                    out +=[ord(fb), (self._f(int(tbl, 16)), int(lo, 16))]
                elif body.startswith("s:"):      # {s:39} raw special
                    out.append((self._f(0x11), int(body[2:], 16)))
                elif body in ("TO1", "TO2", "TO3"):
                    out += self.tab(int(body[2]))
                elif body == "BS":
                    out += self.BS()
                elif body.startswith("bg:"):     # {bg:r} / {bg:rs}
                    out += self.bg(body[3], body.endswith("s") and len(body) > 4)
                elif body == "BT":
                    out += self.attr(0x2D)
                elif body == "FA":
                    out += self.attr(0x2E)
                elif body == "FON":
                    out += self.FON()
                else:
                    raise ValueError(f"bad markup {body}")
            else:
                for ch in part:
                    out += self.char_tokens(ch)
        return out

    def row_tokens(self, r):
        indent = ((r.col - 1) // 4) * 4
        tabn = (r.col - 1) - indent
        if r.col - 1 + self.width(r.text) > 32 and not r.overflow:
            raise ValueError(f"row text overflows 32 columns: {r.text!r} at col {r.col}")
        return (self.pac(r.row, indent, r.color, r.italic, r.ul)
                + self.tab(tabn) + self.tokens(r.text, overflow=True))

    # ---- stream placement
    def at(self, t):
        self.field.pad_to(sec2f(t), self.name)

    def put(self, tokens, pace=1):
        self.field.emit(pack(tokens), pace)

    def popon(self, show_at, rows, enm=True):
        """Load off-screen so the first EOC lands on the frame for show_at."""
        toks = self.RCL() + (self.ENM() if enm else [])
        for r in rows:
            toks += self.row_tokens(r)
        toks += self.EOC()
        pairs = pack(toks)
        flip = len(pairs) - (2 if self.double else 1)
        start = sec2f(show_at) - flip
        if start < self.field.cursor:
            raise Overrun(f"{self.name}: pop-on for t={show_at:.2f}s needs "
                          f"{flip} frames but field is busy until frame "
                          f"{self.field.cursor} (start {start})")
        self.field.pad_to(start, self.name)
        self.field.emit(pairs)


def burst_pairs(chan, rows):
    """Committed (parity-applied) pairs for a complete pop-on caption on `chan`
    (RCL, ENM, rows, EOC) without placing it in a stream."""
    toks = chan.RCL() + chan.ENM()
    for r in rows:
        toks += chan.row_tokens(r)
    toks += chan.EOC()
    return [(parity(a), parity(b)) for a, b in pack(toks)]
