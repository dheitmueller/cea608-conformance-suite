#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2026 Devin Heitmueller <devin.heitmueller@gmail.com>
"""Self-check of the reference decoder model (reference.py).

For the static pop-on cards the generator's own row objects say what must be on screen (row, column, text,
color, underline, italics).  This replays the stream's caption pairs through the reference model and compares.
Roll-up, paint-on, erase and signal-loss cards are not covered here; their expectations are in TESTS.md and
are checked by reading the slides.   python test_reference.py
"""
import re
import sys

import build
import cea608
import reference
import testplan
from cea608 import Chan, Field, sec2f

STATIC = {"G01", "G02", "C01a", "C01b", "C01c", "C02", "C03a", "C03b", "C03c", "C03d", "C03e", "C03f", "C04",
          "A01a", "A01b", "A01c", "A01d", "A02a", "A02b", "A02c", "A02d", "A03a", "A03b", "A03c", "A03d",
          "A04", "A05a", "A05b", "A05c", "A05d", "A06", "A09a", "A09b", "A09c", "A10"}
# P05 (five rows) is left out: 608-E leaves the result implementation-defined; the model keeps the newest four.
MIDROW = {b: (b[0], b.endswith("u")) for b in "w wu g gu b bu c cu r ru y yu m mu".split()}


def intended():
    """{card_id: {channel: rows of its pop-on}} recorded while the plan is scheduled."""
    rec, cur = {}, [None]
    orig = Chan.popon

    def popon(self, show_at, rows, enm=True):
        rec.setdefault(cur[0], {})[self.name] = rows
        return orig(self, show_at, rows, enm)
    Chan.popon = popon
    f1, f2 = Field(0), Field(1)
    chans = {"CC1": Chan("CC1", f1, 1, True), "CC2": Chan("CC2", f1, 2, True),
             "CC3": Chan("CC3", f2, 1, False), "CC4": Chan("CC4", f2, 2, False)}
    t = 0.0
    for s in testplan.SEGMENTS:
        cur[0] = s.id
        for n in s.chans:
            s.fn(chans[f"CC{n}"], t)
        t += s.dur
    Chan.popon = orig
    return rec


def cells(rows, name):
    """{(row, col): (char, fg, ul, italic)} from generator rows; None if cursor-movement markup is used."""
    out = {}
    for r in rows:
        if re.search(r"\{(BS|TO\d)\}", r.text):
            return None
        col, fg, ul, it = r.col, (r.color or "w"), bool(r.ul), bool(r.italic)
        prev = out.get((r.row, col - 1))
        if prev and col > 1:                                   # C.7: a PAC next to a character inherits
            fg, ul, it = prev[1:]
        for part in re.split(r"(\{[^{}]+\})", r.text.replace("{c}", "{c}")):
            if not part:
                continue
            if part[0] == "{" and len(part) > 1:
                b = part[1:-1]
                m = re.match(r"[xX]([0-9A-F]{2}):([0-9A-F]{2})", b)
                if m:
                    t = cea608.EXT12 if int(m.group(1), 16) == 0x12 else cea608.EXT13
                    out[(r.row, col)] = (t[int(m.group(2), 16) - 0x20], fg, ul, it)
                elif b in MIDROW:
                    fg, ul = MIDROW[b]
                    it = False
                elif b in ("i", "iu"):
                    fg, ul, it = "w", b.endswith("u"), True
                elif b == "FA":
                    fg, ul = "k", False
                elif b.startswith(("bg:", "BT", "FON")):
                    pass
                else:
                    raise SystemExit(f"{name}: unmodelled markup {{{b}}}")
                col += 1
            else:
                for ch in part:
                    if ch != " ":
                        out[(r.row, col)] = (ch, fg, ul, it)
                    col += 1
    return out


def main():
    testplan.apply_format("720p59")
    want = intended()
    f1, f2, starts, total, _ = build.schedule()
    fields = [reference.FieldDecoder(f1.pairs), reference.FieldDecoder(f2.pairs)]
    for f in fields:
        f.run()
    ids = [s.id for s in testplan.SEGMENTS]
    bad = checked = 0
    for cid in sorted(STATIC, key=ids.index):
        i = ids.index(cid)
        t_end = sec2f(starts[i] + testplan.SEGMENTS[i].dur) - 1
        for name, (fi, ch) in {"CC1": (0, 1), "CC3": (1, 1)}.items():
            w = cells(want[cid][name], cid)
            if w is None:
                continue
            snap = [s for f, s in fields[fi].states[ch] if f <= t_end][-1]
            got = {(r + 1, c + 1): (x[0], x[1], x[2], x[3]) for r, row in enumerate(snap)
                   for c, x in enumerate(row) if x and x[0] != " "}
            checked += 1
            if got != w:
                bad += 1
                for k in sorted(set(got) | set(w)):
                    if got.get(k) != w.get(k):
                        print(f"{cid} {name} row {k[0]} col {k[1]}: model {got.get(k)} intended {w.get(k)}")
    print(f"{checked} card/channel layouts checked, {bad} differ")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
