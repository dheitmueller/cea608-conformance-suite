#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2026 Devin Heitmueller <devin.heitmueller@gmail.com>
"""Self-check of the CEA-708 up-converter (cea708.py) and the reference 708 decoder (cea708_decode.py).

  python test_cea708.py [-v]

1. The command encoders reproduce the byte examples of CTA-708-E 8.10.5 (DefineWindow, SetWindowAttributes,
   SetPenColor, SetPenLocation, ClearWindows ...).
2. The decoder interprets hand-written service data (windows, pens, roll-up, delete/toggle, CR and BS).
3. The packetiser's output is parsed back (sequence numbers, packet sizes, null block headers).
4. For both stream formats the generator's 608 pairs are up-converted, sent through the packetiser at the real
   per-picture bandwidth, decoded by the 708 decoder and compared, caption state by caption state, with the 608
   reference decoder of the suite (reference.py): every card, services 1-4.  Differences caused by bandwidth (the
   708 decoder runs a few frames behind and may show two 608 states in one step) are counted, not failed; anything
   else fails.

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
import cea708  # noqa: E402
import cea708_decode as dec  # noqa: E402
import reference  # noqa: E402
import testplan  # noqa: E402

FAILS = []


def check(name, ok, detail=""):
    if not ok:
        FAILS.append(name)
    print(("PASS " if ok else "FAIL ") + name + (("  " + detail) if detail and not ok else ""))


def encoders():
    check("DefineWindow example 8.10.5.2", cea708.df(2, 0, 8, 74, 209, 12, 16, 1, 2, 1).hex() == "9a384ad18b0f11")
    check("SetWindowAttributes example 8.10.5.8",
          cea708.swa(0, 0, 2, 2, 0, 2, (2, 1, 0), 1, 5, (1, 0, 3)).hex() == "9764538822")
    check("SetPenColor example 8.10.5.10", cea708.spc((3, 3, 3), 0, (0, 0, 0), 3, (1, 1, 1)).hex() == "913fc015")
    check("SetPenLocation example 8.10.5.11", cea708.spl(5, 8).hex() == "920508")
    check("ClearWindows example 8.10.5.3", cea708.window_map_cmd(cea708.CLW, 0x13).hex() == "8813")
    check("DeleteWindows example 8.10.5.4", cea708.window_map_cmd(cea708.DLW, 0xFE).hex() == "8cfe")
    check("G0/G1/G2 characters", cea708.text_bytes("A") == b"A" and cea708.text_bytes("♪") == b"\x7f"
          and cea708.text_bytes("á") == b"\xe1" and cea708.text_bytes("™") == b"\x10\x39")


def split_elements(data):
    """Cut service data into syntactic elements the way the decoder parses them (for the tests below only)."""
    sd = dec.ServiceDecoder(0, set())
    i, out = 0, []
    while i < len(data):
        n = sd.element(bytearray(data[i:]), 0.0)
        out.append(bytes(data[i:i + n]))
        i += n
    return out


def feed(d, svc, data, t=0.0):
    """Send ``data`` as one service block in one packet through the real packetiser and the decoder."""
    m = d.mux = getattr(d, "mux", None) or cea708.Mux()          # one sequence of packet numbers per decoder
    for el in split_elements(data):
        m.queue(svc, el)
    out = []
    while m.pending():
        out += m.picture(9)
    d.picture([(t_, 1, a, b) for t_, (a, b) in out], t)


def decoder_basics():
    d = dec.Decoder("4:3")
    data = (cea708.df(0, 0, 0, 5 * 13, 0, 2, 32, 1, 5, 1) + cea708.spl(1, 0) + b"hello" + b"\x0d" + b"x\x03")
    feed(d, 1, data)
    snap = d.snapshot(1)
    text = lambda r: "".join(c[0] if c else "." for c in snap[r - 1]).rstrip(".")
    check("decoder: roll-up window, CR scrolls", text(14) == "hello" and text(15) == "x", f"{text(14)!r} {text(15)!r}")
    feed(d, 1, bytes([cea708.CW0]) + cea708.spl(0, 1) + b"ab" + b"\x08" + b"Z")
    snap = d.snapshot(1)
    check("decoder: SetPenLocation and BS", text(14) == "haZlo", repr(text(14)))
    feed(d, 1, cea708.window_map_cmd(cea708.HDW, 1))
    check("decoder: HideWindows", not any(any(r) for r in d.snapshot(1)))
    feed(d, 1, cea708.window_map_cmd(cea708.TGW, 1))
    check("decoder: ToggleWindows", any(any(r) for r in d.snapshot(1)))
    feed(d, 1, cea708.window_map_cmd(cea708.DLW, 1))
    check("decoder: DeleteWindows", not any(any(r) for r in d.snapshot(1)))
    feed(d, 2, cea708.df(3, 0, 0, 0, 0, 1, 10, 1, 2, 1) + cea708.spc((3, 0, 0), 0, (0, 0, 3), 2) + b"Q")
    c = d.snapshot(2)[0][0]
    check("decoder: SetPenColor", c == ("Q", "r", False, False, "b", "s", False), repr(c))
    d.picture([], 0.0)
    feed(d, 2, bytes([cea708.RST]))
    check("decoder: Reset", not any(any(r) for r in d.snapshot(2)))


def packets():
    m = cea708.Mux()
    for n in range(40):
        m.queue(1, bytes([0x41 + n % 26]))
    m.queue(3, b"abc")
    seqs, sizes, body = [], [], bytearray()
    while m.pending():
        t = m.picture(5)
        seqs.append(t[0][1][0] >> 6)
        sizes.append(len(t))
        check_start = t[0][0] == 3 and all(x[0] == 2 for x in t[1:])
        if not check_start:
            check("packet triplet types", False)
        if len(t) != (t[0][1][0] & 0x3F):
            check("packet size code", False)
    check("packets: rolling sequence number", seqs == [i & 3 for i in range(len(seqs))], str(seqs))
    check("packets: every packet within the budget", max(sizes) <= 5, str(sizes))
    d = dec.Decoder()
    m = cea708.Mux()
    for el in split_elements(cea708.df(0, 0, 0, 0, 25, 1, 32, 1, 2, 1) + cea708.spl(0, 0)
                             + b"012345678901234567890123456789"):
        m.queue(1, el)
    t = 0.0
    while m.pending():
        d.picture([(a, 1, x, y) for a, (x, y) in m.picture(6)], t)
        t += 1 / 60
    check("packets: a long service block spans packets and arrives whole",
          "".join(c[0] for c in d.snapshot(1)[0] if c) == "012345678901234567890123456789")


def card_equivalence(fmt_name, verbose, swap="showhide"):
    testplan.apply_format(fmt_name)
    f1, f2, starts, total, _ = build.schedule()
    F = build.FORMATS[fmt_name]
    ppf, wide = F["ppf"], F["kind"] == "16x9"
    up = cea708.Upconverter("16:9" if wide else "4:3", swap=swap)
    pics = up.run(f1, f2, F["ppf"], F["cc_count"])
    check(f"{fmt_name} ({swap}): all 708 data is sent within the video (no queue left after the last picture)",
          len(pics) == max(len(f1.pairs), len(f2.pairs)) * ppf)
    aspect = "16:9" if wide else "4:3"
    d, seqs = dec.decode_pictures([[(t, 1, a, b) for t, (a, b) in items] for items in pics], ppf, aspect)
    ref = dec.reference_states(f1, f2)
    bounds = [round(st * 30000 / 1001) for st in starts]

    def card(frame):
        k = max(i for i, b in enumerate(bounds) if frame >= b)
        return testplan.SEGMENTS[k].id
    bad = co = tr = lag = 0
    for n in (1, 2, 3, 4):
        r = dec.compare_states(ref[n], seqs[n])
        lag = max(lag, r["lag"])
        co += len(r["coalesced"])
        tr += len(r["transient"])
        for i, fr, g, _ in r["mismatch"]:
            bad += 1
            print(f"   mismatch service {n} card {card(fr if fr is not None else g)} state {i} (608 frame {fr}, 708 frame {g})")
        if verbose:
            for i, fr, m in r["coalesced"]:
                print(f"   coalesced service {n} card {card(fr)} frame {fr}: {m} state(s) skipped while behind")
            for i, fr, m in r["transient"]:
                print(f"   transient service {n} card {card(fr)} frame {fr}: {m} intermediate state(s)")
    check(f"{fmt_name} ({swap}): 608 -> 708 -> decode equals the 608 reference decoder, all cards, services 1-4", bad == 0,
          f"{bad} mismatching states")
    check(f"{fmt_name} ({swap}): decoder reported no unmodelled feature", not d.issues, str(sorted(d.issues)))
    print(f"     {sum(len(v) for v in ref.values())} caption states compared; {up.mux.sent} packets; longest wait "
          f"{up.mux.max_wait} pictures; decoder lag up to {lag} frames; {co} coalesced, {tr} transient")


def main():
    verbose = "-v" in sys.argv
    encoders()
    decoder_basics()
    packets()
    for name in ("720p59", "480i59"):
        card_equivalence(name, verbose)
    card_equivalence("720p59", verbose, swap="toggle")
    print("FAILED: " + ", ".join(FAILS) if FAILS else "all passed")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
