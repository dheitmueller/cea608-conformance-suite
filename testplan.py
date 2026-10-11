# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2026 Devin Heitmueller <devin.heitmueller@gmail.com>
"""The CEA-608 renderer test cards (one Segment per card).

Each card carries:
  refs     - [(citation, level)] burned into the video and listed in TESTS.md
  purpose  - one-paragraph rationale for TESTS.md
Levels follow the source document's own labels:
  608-E   REGULATORY / NORMATIVE / PREFERRED / OPTIONAL / RECOMMENDED / INFORMATIVE
  10-A    10A-RECOMMENDATION  (CEA-CEB-10-A is a bulletin: recommendations, not mandatory,
                    unless it quotes an EIA-708-B 'shall')
  --      UNSPECIFIED (neither document defines the behavior; informational)
Citations use PRINTED page numbers of CTA-608-E (S-2019) and CEA-CEB-10-A (Dec 2002).

Scripts run once per channel in `chans` ("13" = CC1 and CC3 receive identical data;
field 1 doubles control codes, field 2 does not - 608-E D.2 p.78 / B.14 p.70).
"""
from cea608 import R, fallback, EXT12, EXT13, SPECIAL, COLOR_NAMES, sec2f

REG, NORM, PREF, OPT = "REGULATORY", "NORMATIVE", "PREFERRED", "OPTIONAL"
REC, INFO, R10A, UNSPEC = "RECOMMENDED", "INFORMATIVE", "10A-RECOMMENDATION", "UNSPECIFIED"


def E(sec, page, level):
    return (f"CTA-608-E {sec} p.{page}", level)


def A(sec, page, level=R10A):
    return (f"CEA-CEB-10-A {sec} p.{page}", level)


class Segment:
    def __init__(self, id, title, detail, expect, dur, refs, purpose, fn, chans, flashes, group, shown=None, variants=None):
        self.id, self.title, self.detail, self.expect, self.dur = id, title, detail, expect, dur
        self.refs, self.purpose, self.fn, self.chans = refs, purpose, fn, chans
        self.flashes, self.group, self.shown = flashes, group, shown
        self.variants = variants or {}       # {format: {field: override}} - see apply_format()
        self.base = None


SEGMENTS = []
_GROUP = [""]


def group(name):
    _GROUP[0] = name


def seg(id, title, detail, expect, dur, refs, purpose, chans="13", flashes=(), shown=None, variants=None):
    def deco(fn):
        SEGMENTS.append(Segment(id, title, detail, expect, dur, refs, purpose, fn, chans,
                                flashes, _GROUP[0], shown, variants))
        return fn
    return deco


def apply_format(fmt):
    """Select the per-format wording of the cards that differ between the 16:9 (720p59) and the
    4:3 (480i59) build (G02 safe area, S01 timing tolerance)."""
    for s in SEGMENTS:
        if s.base is None:
            s.base = {k: getattr(s, k) for k in ("expect", "refs", "purpose", "detail")}
        for k, v in s.base.items():
            setattr(s, k, v)
        for k, v in s.variants.get(fmt, {}).items():
            setattr(s, k, v)


# ---------------------------------------------------------------- helpers
def centered(row, text, **kw):
    return R(row, text, col=(32 - len(text)) // 2 + 1, **kw)


def ext_row(first, lo, hi):
    table = EXT12 if first == 0x12 else EXT13
    chars = table[lo - 0x20:hi - 0x20 + 1]
    markup = " ".join(f"{{x{first:02X}:{0x20 + table.index(c, lo - 0x20):02X}:{fallback(c)}}}"
                      for c in chars)
    return markup, " ".join(chars)


def rollup(c, t0, depth, base, lines, step=1.4, indents=None, styles=None):
    """608-E B.8.1 p.65: each row = RUn, CR, PAC, text."""
    c.at(t0)
    c.put(c.EDM())
    for i, text in enumerate(lines):
        c.at(t0 + 0.3 + i * step)
        kw = (styles or {}).get(i, {})
        ind = (indents or {}).get(i, 0)
        c.put(c.RU(depth) + c.CR() + c.pac(base, ind, **kw) + c.tokens(text))


def clear(c, t):
    c.at(t)
    c.put(c.EDM())


# ================================================================ GEOMETRY
group("Geometry and stream start")


@seg("G00", "CEA-608 Conformance Suite",
     "Original test content; each card names its test, expected result and spec reference",
     "Captions begin shortly. CC1 and CC3 carry the same tests; CC2/CC4 are used in card H01.",
     5.0, [],
     "Stream identification and lead-in. No captions are sent so a renderer can lock to the "
     "video before the first test. Carries the stream version, author and license.")
def g00(c, t0):
    c.at(0)
    c.put(c.EDM() + c.ENM())


@seg("G01", "Which caption channel is being rendered", "first caption: names the channel the renderer is displaying",
     "'Rendering on CC1' (or CC3). CC2/CC4 show their own label continuously (refreshed every 2 s)", 7.0,
     [E("B.4", 62, REC), E("C.7", 73, REG + "/" + PREF), E("B.13", 69, REC)],
     "First caption of the stream. Each service sends its own name so whoever is looking at a capture knows "
     "which caption channel the renderer selected: CC1 reads 'Rendering on CC1', CC3 reads 'Rendering on CC3'. "
     "CC2 and CC4 carry no tests except card H01, so they instead show 'Rendering on CC2' / 'Rendering on "
     "CC4' for the whole stream, re-sent every 2 s in idle gaps so the label is present even after seeking. "
     "Three centered rows using PAC indent plus Tab Offset, the technique 608-E B.4 gives for centering.")
def g01(c, t0):
    c.popon(t0, [centered(5, "CEA-608 CAPTION TEST"), centered(8, f"Rendering on {c.name}"),
                 centered(10, f"(field {c.field.idx + 1}, data channel {c.ch})")])


@seg("G02", "Safe caption area and 32x15 grid", "pop-on; markers at row 1/15, column 1/32",
     "A,B on row 1 and C,D on row 15 sit at the extreme left/right grid cells, inside the green FCC safe box",
     6.0, [E("C.22", 77, REG), E("C.13", 75, REG + "/" + NORM)],
     "Verifies the renderer maps the 32-column x 15-row grid into the FCC safe caption area "
     "(80% x 80% of the 4:3 picture, Table 46). Corner markers make clipping, wrong margins and "
     "wrong row mapping obvious against the graticule.",
     variants={
         "720p59": dict(
             expect="A,B (row 1) and C,D (row 15) at the grid edges, rows within 10-90% of height; note whether columns map to the green, cyan or another box",
             refs=[("CTA-608-E C.22 p.77: vertical band defined; horizontal placement for 16:9 unspecified", REG + " (vertical) / " + UNSPEC),
                   A("23.3", 38, INFO)],
             detail="pop-on; markers in rows 1/15, columns 1/32",
             purpose="The FCC safe caption area (C.22, Table 46) is defined only for a 4:3 picture: 80% of the picture height "
                     "by 80% of a 4:3 width, 10% in from the top. Rows 1-15 therefore span 10%-90% of the picture height at any "
                     "aspect ratio, which is checkable. How the 32 columns map horizontally onto a 16:9 picture is not specified "
                     "in CTA-608-E; CEA-CEB-10-A 23.3 only remarks that up-converted NTSC captions may have a 4:3 aspect ratio "
                     "within a 16:9 image. The green box (4:3 centered) and the cyan box (80% of the 16:9 frame) are shown as the "
                     "two common interpretations; this card records which one the decoder uses."),
         "480i59": dict(
             detail="pop-on; markers in rows 1/15, columns 1/32"),
     })
def g02(c, t0):
    c.popon(t0, [R(1, "A"), R(1, "B", col=32), R(15, "C"), R(15, "D", col=32)])


# ================================================================ CHARACTERS
group("Character sets")
for _n, (_lbl, _txt) in enumerate([
        ("0x20-0x3F", " !\"#$%&'()á+,-./0123456789:;<=>?"),
        ("0x40-0x5F", "@ABCDEFGHIJKLMNOPQRSTUVWXYZ[é]íó"),
        ("0x60-0x7F", "úabcdefghijklmnopqrstuvwxyzç÷Ññ■")], 1):
    def _mk(lbl, txt, n):
        @seg(f"C01{'abc'[n - 1]}", f"Basic characters {n}/3", f"standard set {lbl}; note a-acute at 0x2A etc.",
             txt, 5.0,
             [E("6.4.1", 18, NORM), E("Tables 49-50", "96-98", REG)],
             "The 112-character basic set every decoder shall support. 608 replaces several ASCII "
             "positions (0x2A, 0x5C, 0x5E-0x60, 0x7B-0x7F) with accented letters and symbols; a renderer "
             "using plain ASCII/Latin-1 mapping fails here.")
        def f(c, t0):
            c.popon(t0, [R(6, f"Basic character set {n}/3:"), R(8, txt)])
    _mk(_lbl, _txt, _n)


@seg("C02", "Special characters", "0x11 0x30-0x3F (0x19 on channel 2)",
     " ".join(SPECIAL.replace(" ", "")), 5.0,
     [E("F.1.1.1 Table 49", 96, REG)],
     "The 16 special characters sent as two-byte codes (registered, degree, half, inverted query, "
     "trademark, cent, pound, music note, accented a/e/i/o/u). The transparent space (0x39) is omitted from "
     "the visible row.")
def c02(c, t0):
    c.popon(t0, [R(6, "Special characters:"), R(8, " ".join(SPECIAL.replace(" ", "")))])


_LANGS = [
    ("C03a", "International characters - Spanish", "table 5: 0x12 0x20-0x27", 0x12, 0x20, 0x27, 5, 20,
     "¿Dónde está la biblioteca?", "¡Mañana, señor! — Ñandú"),
    ("C03b", "Miscellaneous symbols", "table 6: 0x12 0x28-0x2F", 0x12, 0x28, 0x2F, 6, 21,
     "© 2026 — “Quoted” • ‘single'", None),
    ("C03c", "International characters - French", "table 7: 0x12 0x30-0x3F", 0x12, 0x30, 0x3F, 7, 22,
     "Où est le garçon? À la plage!", None),
    ("C03d", "International characters - Portuguese", "table 8: 0x13 0x20-0x2F (incl. { } \\ ^ _ | ~)", 0x13, 0x20, 0x2F, 8, 23,
     "Informações: São João, não", None),
    ("C03e", "International characters - German", "table 9: 0x13 0x30-0x37", 0x13, 0x30, 0x37, 9, 24,
     "Größe: Fußgängerübergang", None),
    ("C03f", "International characters - Danish", "table 10: 0x13 0x38-0x3F (incl. box corners)", 0x13, 0x38, 0x3F, 10, 25,
     "Rød grød med fløde, Åse", None),
]
for _id, _t, _d, _first, _lo, _hi, _tbl, _pg, _phrase, _phrase2 in _LANGS:
    def _mk2(id, t, d, first, lo, hi, tbl, pg, phrase, phrase2):
        markup, shown = ext_row(first, lo, hi)

        @seg(id, t, d, shown, 6.0,
             [E(f"6.4.2 Table {tbl}", pg, OPT), E("6.4.2", 18, OPT)],
             f"Optional extended characters (Table {tbl}). Each extended character carries an automatic "
             "backspace, so the stream sends a fallback character first (as a legacy decoder would display); "
             "an extended-capable renderer must replace it. Row 7 shows the table, row 10+ a real phrase. "
             "A renderer that does not implement the optional set will show the fallback letters instead.")
        def f(c, t0):
            rows = [R(5, d.split(":")[0] + ":"), R(7, markup), R(10, phrase)]
            if phrase2:
                rows.append(R(12, phrase2))
            c.popon(t0, rows)
    _mk2(_id, _t, _d, _first, _lo, _hi, _tbl, _pg, _phrase, _phrase2)


@seg("C04", "Extended character automatic backspace", "pop-on; fallback + extended, and extended as first character",
     "row 6 reads ABCÁ (not ABCAÁ); row 8 shows Á in column 1 and nothing is lost to the left", 5.0,
     [E("6.4.2", 18, OPT)],
     "Edge cases of the automatic backspace: an extended character must erase the character to its left "
     "(here the fallback 'A'), but when it is the first character on a row there is nothing to erase and "
     "the cursor must not move left of column 1.")
def c04(c, t0):
    c.popon(t0, [R(6, "ABC{x12:20:A}"), R(8, "{X12:20}")])


# ================================================================ ADDRESSING
group("Addressing and attributes (PAC, mid-row, tab offsets)")
for _i, _rows in enumerate([[1, 2, 3, 4], [5, 6, 7, 8], [9, 10, 11, 12], [13, 14, 15]]):
    def _mk3(i, rows):
        @seg(f"A01{'abcd'[i]}", f"PAC rows {rows[0]}-{rows[-1]}", "preamble address codes select the row",
             "'Row N' appears on row N (grid row N in the graticule)", 4.0,
             [E("F.1.1.5 Table 53", 101, REG), E("C.5", 72, REG)],
             "All 15 rows addressable by PAC. Split into captions of at most four rows because the FCC "
             "requires only four simultaneous rows (C.5); rows 5-11 are the 'mid-screen' PACs added by the "
             "1991 FCC rules (B.2 p.61).")
        def f(c, t0):
            c.popon(t0, [R(r, f"Row {r}") for r in rows])
    _mk3(_i, _rows)


def _colors(first, ul):
    ks = "wgbcrym"[first:first + 4]
    return [R(5 + 2 * i, COLOR_NAMES[k] + (" UL" if ul else ""), color=k, ul=ul) for i, k in enumerate(ks)]


for _i, (_first, _ul) in enumerate([(0, False), (4, False), (0, True), (4, True)]):
    def _mk4(i, first, ul):
        names = " ".join(COLOR_NAMES[k] for k in "wgbcrym"[first:first + 4])

        @seg(f"A02{'abcd'[i]}", f"PAC colors{' underlined' if ul else ''} {i % 2 + 1}/2",
             "PAC color/italic/underline attributes",
             names + (" + White Italic" if first == 4 else "") + (" (all underlined)" if ul else ""), 4.0,
             [E("F.1.1.5 Table 53", 101, REG), E("C.2", 71, REG)],
             "Foreground color, italics and underline selected by non-indenting PACs. A monochrome decoder "
             "may ignore color but must still honor spacing/underline (C.2).")
        def f(c, t0):
            rows = _colors(first, ul)
            if first == 4:
                rows.append(R(13, "White Italic" + (" UL" if ul else ""), italic=True, ul=ul))
            c.popon(t0, rows)
    _mk4(_i, _first, _ul)


for _i, (_inds, _ul) in enumerate([((0, 4, 8, 12), False), ((16, 20, 24, 28), False),
                                   ((0, 4, 8, 12), True), ((16, 20, 24, 28), True)]):
    def _mk5(i, inds, ul):
        @seg(f"A03{'abcd'[i]}", f"PAC indents {inds[0]}-{inds[-1]}{' underlined' if ul else ''}",
             "indenting PAC: column = indent + 1", "numbers step right by 4 columns" + (", underlined" if ul else ""), 4.0,
             [E("F.1.1.5 Table 53", 101, REG), E("C.7", 73, REG + "/" + PREF)],
             "Indenting PACs (0, 4, ... 28 columns). An indenting PAC carries white, non-italic, and sets only underline.")
        def f(c, t0):
            c.popon(t0, [R(5 + 2 * k, str(n), col=n + 1, ul=ul) for k, n in enumerate(inds)])
    _mk5(_i, _inds, _ul)


@seg("A04", "Tab offsets TO1-TO3", "0x17 0x21-0x23 after an indenting PAC",
     "rows step right by one column each (columns 1, 2, 3); text is not erased", 5.0,
     [E("B.4", 62, REC), E("C.7", 73, REG + "/" + PREF)],
     "Tab offsets move the cursor 1-3 columns right without affecting the display (C.7); the rows "
     "start at PAC indent 0 plus TO0..TO2.")
def a04(c, t0):
    c.popon(t0, [R(4, "Tab offsets (cols 1,2,3):"), R(6, "TO0", col=1), R(7, "TO1", col=2), R(8, "TO2", col=3)])


_MRN = {"w": "White", "wu": "White UL", "g": "Green", "gu": "Green UL", "b": "Blue", "bu": "Blue UL",
        "c": "Cyan", "cu": "Cyan UL", "r": "Red", "ru": "Red UL", "y": "Yellow", "yu": "Yellow UL",
        "m": "Magenta", "mu": "Magenta UL", "i": "Italics", "iu": "Italics UL"}
for _i, _items in enumerate([("w", "wu", "g", "gu"), ("b", "bu", "c", "cu"), ("r", "ru", "y", "yu"),
                             ("m", "mu", "i", "iu")]):
    def _mk6(i, items):
        @seg(f"A05{'abcd'[i]}", f"Mid-row codes {i + 1}/4", "0x11 0x20-0x2F inside a row",
             "the named word in that style; the rest of the row is white (mid-row white resets)", 4.0,
             [E("F.1.1.3 Table 51", 99, REG)],
             "Mid-row codes change color/italics/underline mid-line and occupy one (space) column. "
             "Sixteen codes over four cards.")
        def f(c, t0):
            c.popon(t0, [R(5 + 2 * k, f"The{{{key}}}{_MRN[key]}{{w}}Mid-Row Code") for k, key in enumerate(items)])
    _mk6(_i, _items)


@seg("A06", "Attribute inheritance", "new character takes attributes of the character to its left",
     "row 6: GREENTEXT all green; row 8: UNDERLINED is underlined", 6.0,
     [E("C.7", 73, REG + "/" + PREF)],
     "608-E C.7: a character deposited next to an existing character assumes that character's attributes "
     "and the PAC's are ignored (row 6: green GREEN followed by an indent-4+TO2 white PAC at the next "
     "column). Conversely an indenting PAC with underline, then a Tab Offset, then text must underline (row 8).")
def a06(c, t0):
    c.popon(t0, [R(6, "{g}GREEN"), R(6, "TEXT", col=7), R(8, "UNDERLINED", col=9, ul=True)])


@seg("A07", "Right margin, tab clamp, backspace edges", "34 chars on a row; TO beyond col 32; BS at col 32 and col 1",
     "r6 ends in Y at col 32 | r8: lone Z at col 32 | r10: x at col 31 (col 32 either) | r12: Q at col 1", 8.0,
     [E("C.13", 75, REG + "/" + NORM), E("B.12", 69, REC)],
     "The cursor never passes column 32 (row 6: 32 letters then X, Y overwrite column 32, final Y). "
     "Tab offsets clamp at 32 (row 8: PAC indent 28 + TO1 + TO3 must stop at 32; Z is visible). A BS after a "
     "character in column 32 moves to column 31 and erases it (row 10: 'x' replaces column 31; column 32 may "
     "or may not be erased - both are legal). BS in column 1 is ignored (row 12: Q appears).")
def a07(c, t0):
    c.popon(t0, [R(6, "ABCDEFGHIJKLMNOPQRSTUVWXYZ012345XY", overflow=True),
                 R(8, "{TO1}{TO3}Z", col=29),
                 R(10, "ABCDEFGHIJKLMNOPQRSTUVWXYZ012345{BS}x", overflow=True),
                 R(12, "{BS}Q")])


@seg("A08", "Default attributes after CR", "roll-up row created by CR with no PAC",
     "row 1 yellow underlined; row 2 (no PAC) is white, not underlined, not italic", 7.0,
     [E("C.14", 75, NORM)],
     "When no attributes have been assigned the display shall be white, non-underlined, non-italic, "
     "non-flashing. A roll-up row started by CR with no PAC must not inherit the previous row's color.")
def a08(c, t0):
    c.at(t0)
    c.put(c.EDM() + c.RU(2) + c.CR() + c.pac(15, 0, color="y", ul=True) + c.tokens("Row 1: yellow underlined"))
    c.at(t0 + 2.0)
    c.put(c.CR() + c.tokens("Row 2: CR, no PAC: white"))


for _id, _t, _rows, _exp in [
        ("A09a", "Background colors (opaque)", ["{bg:r}Opaque red background", "{bg:g}Opaque green background",
                                                "{bg:b}Opaque blue background", "{bg:c}Opaque cyan background"],
         "colored box behind each row (white text)"),
        ("A09b", "Background colors (semi-transparent)", ["{bg:rs}Semi-transparent red", "{bg:gs}Semi-transparent green",
                                                          "{bg:bs}Semi-transparent blue", "{bg:ks}Semi-transparent black"],
         "video shows through the box (renderer may fall back to opaque)"),
        ("A09c", "Foreground black and transparent background", ["{bg:w}{FA}Black text on white", "{bg:y}{FA}Black text on yellow",
                                                                  "{BT}Transparent background", "{bg:k}Opaque black default"],
         "black text on light boxes; third row without any box")]:
    def _mk7(id, t, rows, exp):
        @seg(id, t, "background/foreground attribute codes (standard space + code with automatic BS)", exp, 5.0,
             [E("6.2", 16, OPT), E("Table 3", 17, OPT)],
             "Optional extended attribute codes. Each code is preceded by a standard space and carries an "
             "automatic backspace so a standard decoder shows one space and an extended decoder shows one "
             "colored space. Unsupported background colors should default to black (6.2).")
        def f(c, t0):
            c.popon(t0, [R(5 + 2 * k, txt) for k, txt in enumerate(rows)])
    _mk7(_id, _t, _rows, _exp)


@seg("A10", "Flash on (FON)", "0x14 0x28 (0x1C 0x28 on ch 2)", "the second half of row 6 flashes (rate unspecified)", 5.0,
     [E("F.1.1.4 Table 52", 99, REG), E("C.19", 76, OPT)],
     "Flash On is a spacing attribute. 608-E does not define the flash rate, and for flashing underlined "
     "text either only the characters or characters+underline may flash (C.19, optional).")
def a10(c, t0):
    c.popon(t0, [R(6, "Steady, then {FON}this flashes")])


# ================================================================ POP-ON
group("Pop-on style and memory control")


@seg("P01", "Pop-on: display, erase (EDM), display", "RCL / EOC / EDM",
     "caption A for 3 s, blank for 2 s, caption B", 8.0,
     [E("B.8.3", 65, REC), E("C.10", 74, REG), E("C.16", 75, NORM)],
     "The basic life cycle: load off-screen, flip with EOC (the first EOC lands exactly on the display frame, "
     "B.11.2), erase with EDM, load the next.")
def p01(c, t0):
    c.popon(t0, [centered(13, "Pop-on caption A"), centered(14, "(shown for 3 seconds)")])
    c.at(t0 + 3.0)
    c.put(c.EDM())
    c.popon(t0 + 5.0, [centered(13, "Pop-on caption B"), centered(14, "after a blank screen")])


@seg("P02", "Pop-on: loading is invisible until EOC", "RCL + text while another caption is displayed",
     "A, then B at +2.5 s, then C at +5 s; never partial text", 8.0,
     [E("C.10", 74, REG), E("B.11.2", 68, REC)],
     "RCL only selects pop-on; data goes to non-displayed memory and must not appear until EOC. "
     "Three captions swap on exact frames.")
def p02(c, t0):
    c.popon(t0, [R(13, "Caption A"), R(14, "(loading B off-screen)")])
    c.popon(t0 + 2.5, [R(13, "Caption B"), R(14, "(loading C off-screen)")])
    c.popon(t0 + 5.0, [R(13, "Caption C"), R(14, "(end of test)")])


@seg("P03", "ENM erases non-displayed memory", "0x14 0x2E",
     "'Visible' caption stays; BAD text never appears; then 'Correct' text", 8.0,
     [E("C.16", 75, NORM), E("B.8.3", 66, REC)],
     "ENM must clear the loading buffer unconditionally. BAD text is loaded then erased by ENM; the "
     "later EOC must show only the correct text.")
def p03(c, t0):
    c.popon(t0, [R(14, "Visible (before ENM test)")])
    c.at(t0 + 1.0)
    c.put(c.RCL() + c.pac(12) + c.tokens("BAD: this must never appear") + c.ENM())
    c.popon(t0 + 5.0, [R(14, "Correct: ENM cleared BAD text")])


@seg("P04", "EDM erases any style", "EDM after paint-on and after roll-up",
     "paint-on text vanishes at +3 s; roll-up text appears at +5 s and vanishes at +9 s", 11.0,
     [E("C.16", 75, NORM), E("B.11.4", 68, REC)],
     "EDM erases a displayed caption whatever style produced it; it stands alone with no preceding "
     "RCL/RDC (B.11.4).")
def p04(c, t0):
    c.at(t0)
    c.put(c.EDM() + c.RDC() + c.pac(14) + c.tokens("Paint-on: erased by EDM"))
    clear(c, t0 + 3.0)
    c.at(t0 + 5.0)
    c.put(c.RU(2) + c.CR() + c.pac(15) + c.tokens("Roll-up: erased by EDM"))
    clear(c, t0 + 9.0)


@seg("P05", "More than four rows", "pop-on with five rows (error condition)",
     "no crash or lost caption; as much text as possible, newer rows preferred over older (exact result varies)", 6.0,
     [E("C.6", 73, PREF), E("C.5", 72, REG)],
     "The FCC requires four simultaneous rows; a fifth is assumed to be an error. Decoders should never "
     "discard data and should replace earlier rows with newer ones. The exact display is implementation-"
     "defined; this card documents what each renderer does.")
def p05(c, t0):
    c.popon(t0, [R(3, "Row 1 of 5"), R(5, "Row 2 of 5"), R(7, "Row 3 of 5"), R(9, "Row 4 of 5"),
                 R(11, "Row 5 of 5 (error)")])


# ================================================================ ROLL-UP
group("Roll-up style")


@seg("R01", "Roll-up 3 rows, base row 15", "RU3 + CR + PAC per row",
     "max 3 rows, scrolling up (0.20-0.433 s smooth scroll preferred) as lines arrive", 13.0,
     [E("B.8.1", 65, REC), E("C.3", "71-72", PREF)],
     "Standard live-caption roll-up. Checks row depth, row discard order and (preferred) a smooth scroll "
     "lasting 0.20-0.433 s with characters visible during the scroll.")
def r01(c, t0):
    rollup(c, t0, 3, 15, ["Line 1 of a 3-row", "roll-up caption.", "Line 3: third row.",
                          "Line 4 pushes line 1 off", "Line 5 pushes line 2 off", "Line 6: last line."])


@seg("R02", "Roll-up 4 rows, base row 15", "RU4", "max 4 rows visible", 13.0,
     [E("B.8.1", 65, REC), E("C.5", 72, REG)],
     "Four rows is the FCC maximum simultaneous caption depth.")
def r02(c, t0):
    rollup(c, t0, 4, 15, ["Roll-up, 4 rows: row A", "row B", "row C", "row D (4 visible)",
                          "row E (A is gone)", "row F (B is gone)"])


@seg("R03", "Roll-up 2 rows, base row 15", "RU2", "max 2 rows visible", 11.0,
     [E("B.8.1", 65, REC)], "Two-row roll-up.")
def r03(c, t0):
    rollup(c, t0, 2, 15, ["Roll-up, 2 rows: row A", "row B", "row C (A is gone)", "row D (B is gone)"])


@seg("R04", "Roll-up with per-row indents", "PAC indent 0..16 on each new row",
     "each row indented 4 more columns than the previous", 13.0,
     [E("B.8.1", 65, REC), E("C.7", 73, REG + "/" + PREF)],
     "The indent of each rolled row comes from that row's PAC.")
def r04(c, t0):
    rollup(c, t0, 4, 15, ["Each row may use", "any of the indents", "like this", "and this", "and this too"],
           indents={0: 0, 1: 4, 2: 8, 3: 12, 4: 16})


@seg("R05", "Roll-up with per-row styles", "PAC color / italic / underline per row",
     "yellow underlined / white italics / magenta / white italics underlined", 13.0,
     [E("B.8.1", 65, REC), E("F.1.1.5 Table 53", 101, REG)],
     "Per-row attributes in roll-up come from each row's PAC.")
def r05(c, t0):
    rollup(c, t0, 4, 15, ["This row is yellow underlined.", "White italics.", "This row is magenta.",
                          "White italics underlined."],
           styles={0: dict(color="y", ul=True), 1: dict(italic=True), 2: dict(color="m"),
                   3: dict(italic=True, ul=True)}, step=1.6)


@seg("R06", "Roll-up base row 5 (RU3)", "base row selected by PAC row 5",
     "text occupies rows 3-5 (upper part of the screen)", 11.0,
     [E("B.5", 63, REC), E("F.1.1.5 Table 53", 101, REG)],
     "Movable base row (a 1991 FCC addition; mid-screen base rows are not recognized by TeleCaption I/II).")
def r06(c, t0):
    rollup(c, t0, 3, 5, ["Base row 5, 3 rows:", "rows 3-5 are used", "scrolling upward", "from row 5."])


@seg("R07", "PAC moves a displayed roll-up", "PAC with a different base row during roll-up",
     "three rows at base 15, then the block jumps to base row 8 at +6 s and continues there", 12.0,
     [E("C.7", 73, REG), E("B.8.1", 65, REC)],
     "Receiving a PAC for a different base row during roll-up moves the display immediately. (A PAC for the "
     "same base row only repositions the cursor.)")
def r07(c, t0):
    rollup(c, t0, 3, 15, ["Roll-up at base row 15", "second row", "third row"], step=1.4)
    c.at(t0 + 6.0)
    c.put(c.pac(8))
    c.at(t0 + 8.0)
    c.put(c.RU(3) + c.CR() + c.pac(8) + c.tokens("Now at base row 8"))


@seg("R08", "Roll-up depth vs base-row conflict", "RU3 then PAC for row 2 (error condition)",
     "preferred: depth wins, all 3 rows kept (base moves to row 3); alternative: rows above row 1 lost", 9.0,
     [E("C.4", 72, PREF), E("B.5", "63-64", REC)],
     "A 3-row roll-up cannot fit above base row 2. The FCC lets decoders choose depth or base row; 608-E "
     "recommends depth so no text is lost. Documents the choice each renderer makes.")
def r08(c, t0):
    rollup(c, t0, 3, 15, ["Conflict test row A", "row B", "row C"], step=1.0)
    c.at(t0 + 4.0)
    c.put(c.pac(2))


@seg("R09", "Default base row", "RU3 then text with no PAC",
     "text appears on row 15 at column 1", 5.0,
     [E("C.15", 75, PREF)],
     "With no PAC the roll-up base row defaults to row 15 and the cursor to column 1.")
def r09(c, t0):
    c.at(t0)
    c.put(c.EDM() + c.RU(3) + c.tokens("No PAC sent: base row 15"))


@seg("R10", "Roll-up depth change RU3 to RU2", "RU3 rows, then RU2 + CR",
     "final: two rows 'the caption has been' / 'displayed, like this.'", 13.0,
     [("608-E Annex C silent on resulting display", UNSPEC)],
     "Informational: reducing depth mid-caption. Neither document states the exact result; this card "
     "records renderer behavior (most keep the last two rows).")
def r10(c, t0):
    rollup(c, t0, 3, 15, ["A roll-up caption's depth", "can be decreased after", "the caption has been"], step=1.5)
    c.at(t0 + 5.0)
    c.put(c.RU(2) + c.CR() + c.pac(15) + c.tokens("displayed, like this."))


@seg("R11", "Three CRs = two rolls", "CR CR CR (three identical consecutive pairs) between two rows",
     "A is two rows above B (one blank row between)", 7.0,
     [E("B.14", 70, REC), E("D.2", 78, NORM + "/" + REG)],
     "Redundant-pair handling: of three identical consecutive control pairs, the second is a redundant "
     "copy of the first, so three CRs yield two carriage returns.")
def r11(c, t0):
    c.at(t0)
    c.put(c.EDM() + c.RU(4) + c.CR() + c.pac(15) + c.tokens("A"))
    c.at(t0 + 1.5)
    c.put(c.raw(0x2D, 3) + c.pac(15) + c.tokens("B"))


# ================================================================ PAINT-ON
group("Paint-on style and editing commands")


@seg("D01", "Paint-on: basic and mid-row", "RDC, text painted as received",
     "characters appear progressively; 'paint-on' cyan, 'include' blue, 'mid-row' italic underlined", 11.0,
     [E("B.7", 64, REC), E("B.8.2", 65, REC)],
     "Paint-on writes directly to the display as bytes arrive (sent slowly here so the progression is "
     "visible).")
def d01(c, t0):
    c.at(t0)
    c.put(c.EDM() + c.RDC() + c.pac(13) + c.tokens("These{c}paint-on{w}captions{b}include{w}"), pace=4)
    c.put(c.pac(14) + c.tokens("some{iu}mid-row{w}codes."), pace=4)


@seg("D02", "RDC leaves a roll-up in place", "RDC while a roll-up is displayed",
     "roll-up rows stay; painted text appears on row 8 above them", 9.0,
     [E("C.10", 74, REG), E("B.7", 64, REC)],
     "RDC selects paint-on and has no other effect: displayed roll-up captions are untouched and the "
     "four-row limit still applies.")
def d02(c, t0):
    rollup(c, t0, 2, 15, ["Roll-up row 1", "Roll-up row 2"], step=1.0)
    c.at(t0 + 3.0)
    c.put(c.RDC() + c.pac(8) + c.tokens("Painted over roll-up"), pace=3)


@seg("D03", "RCL leaves a displayed roll-up alone", "RCL + hidden load, then EOC",
     "roll-up stays; hidden text invisible until EOC at +6 s, when it replaces the roll-up", 11.0,
     [E("C.10", 74, REG), E("C.11", 74, REG)],
     "RCL has no effect on a displayed roll-up; the next data goes to non-displayed memory. The EOC flips "
     "memories and the roll-up moves to non-displayed memory.")
def d03(c, t0):
    rollup(c, t0, 2, 15, ["Roll-up before RCL", "still displayed during load"], step=1.0)
    c.popon(t0 + 6.0, [R(12, "Pop-on appears at EOC")], enm=True)


@seg("D04", "Backspace (BS)", "BS 0x14 0x21 (a single BS; repeated-command handling is card D09)",
     "final row: 'Backspace: Right' (a trailing '!' is typed, then erased by BS)", 9.0,
     [E("B.12", 69, REC)],
     "BS erases the character to the left and moves the cursor back one column.")
def d04(c, t0):
    c.at(t0)
    c.put(c.EDM() + c.RDC() + c.pac(14) + c.tokens("Backspace: Right!"), pace=5)
    c.at(t0 + 4.5)
    c.put(c.BS())


@seg("D05", "Delete to end of row (DER)", "DER at mid-row", "final row: 'DER keeps this part:' (REMOVE ME is erased at +5 s)", 9.0,
     [E("B.3", 62, REC), E("C.14", 75, NORM)],
     "DER deletes from the cursor to the end of the row.")
def d05(c, t0):
    kept = "DER keeps this part:"
    assert len(kept) % 4 == 0
    c.at(t0)
    c.put(c.EDM() + c.RDC() + c.pac(14) + c.tokens(kept + " REMOVE ME"), pace=3)
    c.at(t0 + 5.0)
    c.put(c.pac(14, len(kept)) + c.DER())


@seg("D06", "DER at column 1 frees a row", "4 rows painted, DER row A, paint a 5th row",
     "A is erased; B, C, D and E (five rows sent, four visible at a time) all remain", 10.0,
     [E("C.5", "72-73", REG), E("B.3", 62, REC)],
     "DER at column 1 erases the row AND de-allocates its memory, the only way to send a fifth row without "
     "erasing the screen. 608-E states all decoders shall implement this.")
def d06(c, t0):
    c.at(t0)
    c.put(c.EDM() + c.RDC() + c.pac(3) + c.tokens("Row A (will be deleted)") + c.pac(5) + c.tokens("Row B")
          + c.pac(7) + c.tokens("Row C") + c.pac(9) + c.tokens("Row D"), pace=2)
    c.at(t0 + 6.0)
    c.put(c.pac(3) + c.DER())
    c.at(t0 + 7.0)
    c.put(c.pac(11) + c.tokens("Row E (5th row)"), pace=2)


@seg("D07", "Pop-on then paint-on", "RDC does not erase a displayed pop-on", "row 13 pop-on text stays; row 14 painted below", 9.0,
     [E("C.10", 74, REG)],
     "Paint-on adds to whatever is displayed.")
def d07(c, t0):
    c.popon(t0, [R(13, "Here's a pop-on caption...")])
    c.at(t0 + 2.5)
    c.put(c.RDC() + c.pac(14) + c.tokens("...extended by paint-on."), pace=4)


@seg("D08", "Roll-up erases pop-on in both memories; EOC swaps roll-up",
     "pop-on A shown + B hidden; RU2 at +4 s; EOC at +8 s; EOC again at +11 s",
     "0-4s A | 4-8s roll-up only (A and hidden B erased) | 8-11s BLANK | 11s+ roll-up returns", 16.0,
     [E("C.10", 74, REG), E("C.11", 74, REG)],
     "Roll-up commands must erase pop-on/paint-on data in EITHER memory. An EOC while roll-up is selected "
     "swaps the whole roll-up caption into non-displayed memory (screen goes blank, since B was erased) and "
     "a second EOC brings it back in the same row order.")
def d08(c, t0):
    c.popon(t0, [R(13, "Pop-on A: erased by RU2")])
    c.at(t0 + 1.0)
    c.put(c.RCL() + c.ENM() + c.pac(12) + c.tokens("Hidden B: must never show"))
    c.at(t0 + 4.0)
    c.put(c.RU(2) + c.CR() + c.pac(15) + c.tokens("Roll-up: A and B erased"))
    c.at(t0 + 8.0)
    c.put(c.EOC())
    c.at(t0 + 11.0)
    c.put(c.EOC())


@seg("D09", "Redundant control pairs vs repeated commands", "BS BS (adjacent) vs BS, null, BS",
     "ABCDEF -> BS pair -> ABCDE -> G -> ABCDEG -> BS null BS -> ABCD -> H -> ABCDH", 10.0,
     [E("D.2", 78, NORM + "/" + REG), A("25.2.4", 41)],
     "A control code repeated in the very next frame is a redundant copy and must act once; the same code "
     "separated by a null frame is a new command. (10-A notes inserting a null can change interpretation of "
     "adjacent repeated codes.) Field 1 sends doubled pairs; field 2 sends single (B.14), so CC3 exercises "
     "the single-code path.")
def d09(c, t0):
    c.at(t0)
    c.put(c.EDM() + c.RDC() + c.pac(10) + c.tokens("ABCDEF"))
    c.at(t0 + 1.5)
    c.put(c.raw(0x21, 2))                 # adjacent pair: one BS
    c.at(t0 + 3.0)
    c.put(c.tokens("G"))
    c.at(t0 + 4.5)
    c.put(c.raw(0x21, 1))
    c.field.pad_to(c.field.cursor + 1, c.name)   # one null frame between
    c.put(c.raw(0x21, 1))                 # second BS is NOT redundant
    c.at(t0 + 6.5)
    c.put(c.tokens("H"))


# ================================================================ SIGNAL / TIMING
group("Signal, timing and channels")


@seg("S01", "Caption sync to video flash", "first EOC lands on the flash picture; 6 flashes 1 s apart",
     "'NOW n' appears on the flash picture or the next one (within one NTSC frame)", 8.0,
     [E("C.12", "74-75", REG), E("B.11.2", 68, REC), A("17.2.3", 33)],
     "Decoders shall act within one video frame of the code pair (C.12). Each white flash is exactly the picture "
     "carrying the first EOC. 10-A recommends total decode delay no more than two frames.",
     flashes=[1.0, 2.0, 3.0, 4.0, 5.0, 6.0],
     variants={
         "720p59": dict(
             expect="'NOW n' (CC1) appears on the flash picture or the next one; CC3 one picture later (<= 2 pictures = 1 NTSC frame)",
             purpose="Decoders shall act within one video frame of the code pair (C.12); at 59.94 fps a line-21 frame is two "
                     "pictures. Each white flash is exactly the picture carrying the first EOC of the CC1 pair (CC3's pair rides "
                     "the next picture). 10-A recommends total decode delay no more than two frames (four pictures)."),
         "480i59": dict(
             expect="'NOW n' appears on the flash picture or the next one (<= 1 frame); CC1 and CC3 are in the same picture",
             purpose="Decoders shall act within one video frame of the code pair (C.12). The picture is an interlaced frame "
                     "carrying both field pairs, and each white flash is exactly the frame carrying the first EOC of CC1 and CC3. "
                     "10-A recommends total decode delay no more than two frames."),
     })
def s01(c, t0):
    for k in range(6):
        c.popon(t0 + 1.0 + k, [centered(8, f"NOW {k + 1}")])


@seg("S02", "Caption persists on valid nulls", "caption shown, then 20 s of valid null pairs",
     "caption must stay for at least 16 s (erase at +20 s by explicit EDM)", 22.0,
     [E("C.9", 74, PREF), E("D.4", "78-79", INFO), A("25.2.1", "39-40"), A("31", 51, R10A + " (708 only)")],
     "Nulls are valid caption data and mean 'hold'. A decoder implementing automatic erasure must wait at "
     "least 16 s (608-E). 10-A notes this contrasts with loss of waveform, which erases (card S03).")
def s02(c, t0):
    c.popon(t0, [centered(8, "Persists on null pairs"), centered(10, "(must stay at least 16 s)")])
    clear(c, t0 + 20.0)


@seg("S03", "Loss of data erases captions; recovery", "cc_valid=0 for 3 s (no waveform), then a new caption",
     "A shown 0-3 s; erased after 45 frames (about 1.5 s) of no data; B appears at +8 s; A never returns", 14.0,
     [E("C.21", "76-77", REG), A("25.2.1", "39-40"), A("20.2.4", 35)],
     "608-E C.21: after 45 consecutive frames without valid data a decoder shall disable display and "
     "erase memory; on resumption it enables after 12-18 valid frames and displays the data received while "
     "counting. 10-A clarifies cc_valid=0 means 'no waveform' (decoder erases) as distinct from nulls (hold).")
def s03(c, t0):
    c.popon(t0, [R(13, "Caption A: before data loss")])
    c.at(t0 + 3.0)
    c.field.gap(90)
    c.popon(t0 + 8.0, [R(13, "Caption B: after data resumes")])


@seg("S04", "Field 2 loss only", "cc_valid=0 on field 2 for 3 s; field 1 continues",
     "CC1 caption stays; CC3 caption erased after 45 frames (check CC3 if your renderer offers it)", 12.0,
     [E("C.21", "76-77", REG), E("D.7", 79, REG + "/" + INFO), A("20.2.4", 35)],
     "Each field is evaluated independently; field 1 must remain valid whenever field 2 carries data (D.7).")
def s04(c, t0):
    c.popon(t0, [R(13, f"{c.name}: before field 2 loss")])
    if c.field.idx == 1:
        c.at(t0 + 3.0)
        c.field.gap(90)
    c.popon(t0 + 8.0, [R(13, f"{c.name}: still displayed" if c.field.idx == 0 else f"{c.name}: after loss")])


@seg("S05", "Invalid (even) parity data", "60 frames of zero-filled even-parity data on the waveform",
     "caption erased like a loss of valid data; later caption displays normally", 12.0,
     [E("C.21", "76-77", REG), A("A.1.1", 52, INFO)],
     "Data bytes failing odd parity count as 'no valid data' toward the 45-frame disable rule.")
def s05(c, t0):
    c.popon(t0, [R(13, "Caption A: before bad parity")])
    c.at(t0 + 3.0)
    c.field.bad(60)
    c.popon(t0 + 8.0, [R(13, "Caption B: after bad parity")])


@seg("H01", "Channel isolation CC1 / CC2 / CC3 / CC4", "field 1 ch 1/2, field 2 ch 1/2 (field 2 uses 0x15/0x1D)",
     "each service shows only its own line: CC1 row 4, CC2 row 6, CC3 row 9, CC4 row 11 (plus its 'Rendering on' label)", 11.0,
     [E("B.11.6", 69, REG), E("C.18", 76, INFO), A("23.2.2", 37)],
     "Four independent caption services. Field 2 uses 0x15/0x1D in miscellaneous control codes (B.11.6). "
     "CC2 and CC4 deliver their test line inside their regular 2-second label refresh. 10-A recommends "
     "decoders let the viewer select CC1-CC4 even without a caption_service_descriptor "
     "(build with --no-caption-descriptor for that variant).", chans="13", shown="CC1 CC2 CC3 CC4")
def h01(c, t0):
    row, text = (4, "CC1: field 1, data channel 1") if c.ch == 1 and c.field.idx == 0 else \
                (9, "CC3: field 2, data channel 1")
    c.popon(t0, [R(row, text)])
    clear(c, t0 + 9.0)


@seg("Z99", "End of test", "end of stream", "centered end message, then blank", 5.0, [],
     "Marks the end of the stream and clears the screen.")
def z99(c, t0):
    c.popon(t0, [centered(6, "End of Test"), centered(8, "Conformance Suite")])
    c.at(t0 + 3.5)
    c.put(c.EDM())
