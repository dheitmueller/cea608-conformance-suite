#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2026 Devin Heitmueller <devin.heitmueller@gmail.com>
"""Read the CEA-708 (DTVCC) data of a suite transport stream and decode it with the reference 708 decoder.

  python dtvcc_ts.py STREAM.ts --check             compare services 1-4 with the 608 reference decoder, card by card
  python dtvcc_ts.py STREAM.ts --dump [--service N]  list every caption state (time, rows) of the services
  python dtvcc_ts.py STREAM.ts --summary           what the cc_data carries (cc_type counts, packets, services)

The stream is demultiplexed with ffmpeg/ffprobe (copy, no decode); the A/53 ``cc_data()`` is taken from the H.264
SEI (ITU-T T.35, 'GA94', user_data_type_code 3) or the MPEG-2 picture user data, put in display order (H.264: the
packets' pts; MPEG-2: temporal_reference) and handed to ``cea708_decode.Decoder``.  ``--check`` needs the suite's own
stream (it replays the generator's schedule); numpy and PIL are not needed (they are stubbed).
"""
import argparse
import json
import re
import subprocess
import sys
import types

for _m in ("numpy", "PIL", "PIL.Image", "PIL.ImageDraw", "PIL.ImageFont"):
    try:
        __import__(_m)
    except ImportError:
        sys.modules[_m] = types.ModuleType(_m)
        if "." in _m:
            setattr(sys.modules[_m.split(".")[0]], _m.split(".")[1], sys.modules[_m])

import cea708_decode as dec  # noqa: E402


def probe(path):
    """(codec, frame rate as (n, d), packets in decode order [(pts, dts)])."""
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                        "stream=codec_name,r_frame_rate:packet=pts,dts", "-of", "json", path],
                       capture_output=True, text=True, check=True)
    j = json.loads(r.stdout)
    st = j["streams"][0]
    n, d = map(int, st["r_frame_rate"].split("/"))
    return st["codec_name"], (n, d), [(int(p["pts"]), int(p["dts"])) for p in j["packets"]]


def elementary(path, codec):
    fmt = {"h264": "h264", "mpeg2video": "mpeg2video"}[codec]
    return subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-map", "0:v:0", "-c", "copy", "-f", fmt, "-"],
                          capture_output=True, check=True).stdout


def triplets(cc):
    """cc_data() bytes (process_cc_data_flag/cc_count, 0xFF, triplets, marker) -> [(cc_type, cc_valid, b1, b2)]."""
    if len(cc) < 2 or not cc[0] & 0x40:
        return []
    n = cc[0] & 0x1F
    out = []
    for i in range(n):
        b = cc[2 + 3 * i:5 + 3 * i]
        if len(b) < 3:
            break
        out.append((b[0] & 3, (b[0] >> 2) & 1, b[1], b[2]))
    return out


def h264_access_units(es):
    """cc_data of each access unit in decode order (None if it has none); access units start at an AUD (NAL 9)."""
    starts = [m.start() for m in re.finditer(rb"\x00\x00\x01", es)]
    aus, cur = [], None
    for k, p in enumerate(starts):
        end = starts[k + 1] if k + 1 < len(starts) else len(es)
        nal = es[p + 3:end].rstrip(b"\x00")
        t = nal[0] & 0x1F
        if t == 9:
            cur = None
            aus.append(None)
        elif t == 6 and aus:
            rbsp = bytes(nal[1:]).replace(b"\x00\x00\x03", b"\x00\x00")
            i = 0
            while i + 2 < len(rbsp):
                pt = 0
                while rbsp[i] == 0xFF:
                    pt += 255
                    i += 1
                pt += rbsp[i]
                i += 1
                sz = 0
                while rbsp[i] == 0xFF:
                    sz += 255
                    i += 1
                sz += rbsp[i]
                i += 1
                body = rbsp[i:i + sz]
                i += sz
                if pt == 4 and body[:3] == b"\xb5\x00\x31" and body[3:7] == b"GA94" and body[7] == 3:
                    aus[-1] = body[8:]
    return aus


def mpeg2_pictures(es):
    """[(display index, cc_data)] of an MPEG-2 elementary stream (GOP base + temporal_reference)."""
    out, gop_base, count, cur = [], 0, 0, None
    for m in re.finditer(rb"\x00\x00\x01([\x00\xb8\xb2])", es):
        code, pos = m.group(1)[0], m.start()
        if code == 0xB8:
            gop_base += count
            count = 0
        elif code == 0x00:
            cur = gop_base + ((es[pos + 4] << 2) | (es[pos + 5] >> 6))
            count += 1
        elif code == 0xB2 and cur is not None and es[pos + 4:pos + 8] == b"GA94" and es[pos + 8] == 3:
            end = es.find(b"\x00\x00\x01", pos + 4)
            out.append((cur, es[pos + 9:end]))
            cur = None
    return out


def pictures(path):
    """(display-order [triplets of each picture], codec, (n, d) frame rate)."""
    codec, rate, packets = probe(path)
    es = elementary(path, codec)
    if codec == "h264":
        aus = h264_access_units(es)
        if len(aus) != len(packets):
            raise SystemExit(f"{len(aus)} access units but {len(packets)} packets")
        order = {pts: i for i, pts in enumerate(sorted(p for p, _ in packets))}
        pics = [[] for _ in aus]
        for au, (pts, _) in zip(aus, packets):
            pics[order[pts]] = triplets(au) if au else []
        return pics, codec, rate
    found = dict(mpeg2_pictures(es))
    return [triplets(found.get(i, b"")) for i in range(len(packets))], codec, rate


def text(snap):
    return [f"{r:2d}|" + "".join(c[0] if c else " " for c in row).rstrip() for r, row in enumerate(snap, 1) if any(row)]


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("stream")
    ap.add_argument("--check", action="store_true", help="compare with the 608 reference decoder, per card")
    ap.add_argument("--dump", action="store_true")
    ap.add_argument("--summary", action="store_true")
    ap.add_argument("--service", type=int, action="append", help="service number (default 1-4)")
    ap.add_argument("--aspect", choices=("16:9", "4:3"), help="default: from the frame rate (59.94 = 16:9)")
    a = ap.parse_args()
    pics, codec, rate = pictures(a.stream)
    ppf = 2 if rate[0] / rate[1] > 40 else 1
    aspect = a.aspect or ("16:9" if ppf == 2 else "4:3")
    services = tuple(a.service or (1, 2, 3, 4))
    d, seqs = dec.decode_pictures(pics, ppf, aspect, services)
    if a.summary or not (a.check or a.dump):
        kinds = {}
        for p in pics:
            for t, v, _, _ in p:
                kinds[(t, v)] = kinds.get((t, v), 0) + 1
        print(f"{codec} {rate[0]}/{rate[1]}: {len(pics)} pictures, {d.packets} DTVCC packets, services "
              f"{sorted(d.svc)}, cc_type/cc_valid counts {dict(sorted(kinds.items()))}")
        print("decoder notes:", sorted(d.issues) or "none")
    if a.dump:
        t0 = 1001 / 30000
        for n in services:
            for f, snap in seqs[n]:
                print(f"service {n}  {f * t0:9.3f}s  frame {f}")
                for line in text(snap):
                    print("    " + line)
    if a.check:
        sys.path.insert(0, ".")
        import build
        import testplan
        testplan.apply_format("720p59" if ppf == 2 else "480i59")
        f1, f2, starts, total, _ = build.schedule()
        ref = dec.reference_states(f1, f2)
        bounds = [round(st * 30000 / 1001) for st in starts]
        bad = 0
        for n in services:
            r = dec.compare_states(ref[n], seqs[n])
            for i, fr, g, _ in r["mismatch"]:
                k = max(j for j, b in enumerate(bounds) if (fr if fr is not None else g) >= b)
                print(f"service {n} card {testplan.SEGMENTS[k].id}: state {i} differs (608 frame {fr}, 708 frame {g})")
                bad += 1
            print(f"service {n}: {len(ref[n])} states, {len(r['mismatch'])} mismatches, {len(r['coalesced'])} coalesced, "
                  f"{len(r['transient'])} transient, lag up to {r['lag']} frames")
        print("decoder notes:", sorted(d.issues) or "none")
        return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
