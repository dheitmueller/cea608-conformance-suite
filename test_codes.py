#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2026 Devin Heitmueller <devin.heitmueller@gmail.com>
"""Coverage check: byte pairs the cards must send, and what the reference model makes of them.

Each case below was found missing by comparing the stream with Rodrigo Madera's CEA-x08 EIA-608 stream
(https://github.com/madera/CEA-x08, MIT).  The test fails if the suite stops sending the code, or if the reference
model stops drawing the card as intended.   python test_codes.py
numpy and PIL are only needed by build.py for rendering and are stubbed here.
"""
import sys
import types

for _m in ("numpy", "PIL", "PIL.Image", "PIL.ImageDraw", "PIL.ImageFont"):
    try:
        __import__(_m)
    except ImportError:
        sys.modules[_m] = types.ModuleType(_m)
        if "." in _m:
            setattr(sys.modules[_m.split(".")[0]], _m.split(".")[1], sys.modules[_m])

import build  # noqa: E402
import reference  # noqa: E402
import testplan  # noqa: E402
from cea608 import sec2f  # noqa: E402

FAILS = []


def check(name, ok, detail=""):
    if not ok:
        FAILS.append(name)
    print(("ok   " if ok else "FAIL ") + name + ("" if ok else "  " + detail))


def main():
    testplan.apply_format("720p59")
    f1, f2, starts, total, _ = build.schedule()
    fields = [reference.FieldDecoder(f1.pairs), reference.FieldDecoder(f2.pairs)]
    for f in fields:
        f.run()
    ids = [s.id for s in testplan.SEGMENTS]
    sent = [{(a & 0x7F, b & 0x7F) for a, b in (p for p in f.pairs if p)} for f in (f1, f2)]

    def snapshot(cid, field=0, ch=1):
        i = ids.index(cid)
        t_end = sec2f(starts[i] + testplan.SEGMENTS[i].dur) - 1
        return [s for f, s in fields[field].states[ch] if f <= t_end][-1]

    def sends(name, a, b):
        for fi in (0, 1):
            check(f"{name} sent on field {fi + 1}", (a, b) in sent[fi], f"0x{a:02X} 0x{b:02X} never sent")

    # C02: transparent space 0x11 0x39 inside a run of red background
    sends("C02 transparent space 0x11 0x39", 0x11, 0x39)
    for fi in (0, 1):
        row = snapshot("C02", fi)[10]                      # row 11
        al = "".join(c[5] if c else "." for c in row[:12])
        check(f"C02 row 11 draws a gap in the red run (field {fi + 1})", al == "oo" + "t" + "o" + "t" + "o" + "." * 6, al)

    print(f"{len(FAILS)} failed")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
