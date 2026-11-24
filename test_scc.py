#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2026 Devin Heitmueller <devin.heitmueller@gmail.com>
"""Self-check of the SCC export (scc.py).   python test_scc.py

  * the drop-frame timecode: known values, the inverse, and that it follows the wall clock;
  * the file written for the stream's field 1 pairs carries exactly those pairs, at those frames: nothing lost,
    nothing added, no null or missing frame written;
  * every word has odd parity, except in the windows of cards S05 and S06, which have even parity data on purpose.
"""
import sys

import build
import scc
from cea608 import FPS_D, FPS_N, sec2f

failures = []


def check(ok, what):
    if not ok:
        failures.append(what)
        print("FAIL:", what)


def test_timecode():
    known = {0: "00:00:00;00", 29: "00:00:00;29", 30: "00:00:01;00", 1799: "00:00:59;29", 1800: "00:01:00;02",
             3597: "00:01:59;29", 3598: "00:02:00;02", 17981: "00:09:59;29", 17982: "00:10:00;00",
             17983: "00:10:00;01", 107892: "01:00:00;00"}
    for n, tc in known.items():
        check(scc.timecode(n) == tc, f"timecode({n}) = {scc.timecode(n)}, expected {tc}")
    check(all(scc.frame_of(scc.timecode(n)) == n for n in range(0, 130000)), "frame_of(timecode(n)) == n")
    # drop-frame follows the wall clock: the timecode is within two frames of the time of the frame
    def seconds(tc):
        hh, mm, ss, ff = (int(x) for x in tc.replace(";", ":").split(":"))
        return hh * 3600 + mm * 60 + ss + ff / 30

    worst = max(abs(seconds(scc.timecode(n)) - n * FPS_D / FPS_N) for n in range(0, 130000, 97))
    check(worst < 2.1 / 29.97, f"timecode drifts from the wall clock by {worst:.3f} s")


def test_stream():
    f1, f2, starts, total, _ = build.schedule()
    pairs = f1.pairs
    text = scc.to_scc(pairs)
    check(text.startswith("Scenarist_SCC V1.0\n\n"), "header")
    parsed = scc.parse(text)

    want = {n: tuple(p) for n, p in enumerate(pairs) if p is not None and tuple(p) != scc.NULL}
    check(parsed == want, f"the file has {len(parsed)} words, the stream has {len(want)} non-null pairs "
                          f"(differences at frames {sorted(set(parsed) ^ set(want))[:5]}...)")
    check(not any(tuple(p) == scc.NULL for p in parsed.values()), "a null pair was written")

    # runs: a line ends at a null or at a missing frame, never inside a run of pairs
    for start, run in scc.runs(pairs):
        check(all(pairs[start + i] is not None and tuple(pairs[start + i]) != scc.NULL for i in range(len(run))),
              f"the run at frame {start} has a null or a missing frame")

    ids = [s.id for s in build.SEGMENTS]
    wins = [(sec2f(starts[ids.index(c)]), sec2f(starts[ids.index(c)] + build.SEGMENTS[ids.index(c)].dur)) for c in ("S05", "S06")]
    lo, hi = wins[0]

    def odd(b):
        return bin(b).count("1") % 2 == 1

    bad = [n for n, (a, b) in parsed.items() if not (odd(a) and odd(b)) and not any(l <= n < h for l, h in wins)]
    check(not bad, f"words without odd parity outside cards S05 and S06, at frames {bad[:5]}")
    check(any(not (odd(a) and odd(b)) for n, (a, b) in parsed.items() if lo <= n < hi),
          "card S05 has no even parity data in the file")


def main():
    test_timecode()
    test_stream()
    print("SCC export: %d check(s) failed" % len(failures) if failures else "SCC export: all checks passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
