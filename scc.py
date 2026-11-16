# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2026 Devin Heitmueller <devin.heitmueller@gmail.com>
"""SCC (Scenarist Closed Caption) export of the caption data of a build.

The caption data of the test streams is generated as a list of line-21 byte pairs per field, one pair per 29.97 Hz
video frame (cea608.Field.pairs).  SCC is a text format for exactly that: field 1 only (CC1 and CC2), one word of two
bytes per pair, with a drop-frame timecode at the start of each run of words.  So the file written here carries the
same field 1 bytes as the transport streams, at the same times:

  * Field 2 (CC3 and CC4) cannot be carried in SCC and is not in the file.
  * The timecode is SMPTE drop-frame at 29.97 fps (the semicolon before the frame number), which follows the
    wall clock of the stream to within two frames: a card starts at the same time in the file and in the stream, up
    to that. The word that a decoder processes at a timecode is the pair that the stream carries at that frame.
  * Valid nulls (0x80 0x80) are not written: a run of captions ends at a null and the next run gets a timecode.
  * Frames without any waveform (cc_valid 0, the signal loss cards S03 and S04) cannot be represented either; they look
    the same as nulls in the file.  The even parity data of card S05 is written as it is (word 0000).
"""
import re

FPS = 30000 / 1001
NULL = (0x80, 0x80)       # parity(0), parity(0): a valid null pair
FRAMES_PER_10_MIN = 17982  # drop-frame: 10 * 60 * 29.97 = 17982 frames


def timecode(n):
    """SMPTE drop-frame timecode (29.97 fps) of frame number n: two frame numbers are skipped at the start of every
    minute that is not a multiple of ten."""
    tens, rest = divmod(n, FRAMES_PER_10_MIN)
    n += 18 * tens + (2 * ((rest - 2) // 1798) if rest >= 2 else 0)
    return "%02d:%02d:%02d;%02d" % (n // 108000, n // 1800 % 60, n // 30 % 60, n % 30)


def frame_of(tc):
    """Frame number of a drop-frame timecode (the inverse of timecode())."""
    hh, mm, ss, ff = (int(x) for x in re.split("[:;]", tc))
    total_minutes = 60 * hh + mm
    return (hh * 3600 + mm * 60 + ss) * 30 + ff - 2 * (total_minutes - total_minutes // 10)


def runs(pairs):
    """[(first frame, [pair, ...])]: the runs of consecutive pairs that are neither a null nor missing."""
    out, cur, start = [], [], 0
    for n, p in enumerate(pairs):
        if p is None or tuple(p) == NULL:
            if cur:
                out.append((start, cur))
                cur = []
            continue
        if not cur:
            start = n
        cur.append(tuple(p))
    if cur:
        out.append((start, cur))
    return out


def to_scc(pairs):
    """The text of the SCC file for field 1 pairs (a list with a pair, or None for no waveform, per frame)."""
    text = ["Scenarist_SCC V1.0", ""]
    for start, run in runs(pairs):
        text.append(timecode(start) + "\t" + " ".join("%02x%02x" % p for p in run))
        text.append("")
    return "\n".join(text)


def parse(text):
    """{frame: (byte 1, byte 2)} of the words of an SCC file; the inverse of to_scc() for the pairs it writes."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "Scenarist_SCC V1.0":
        raise ValueError("not an SCC file")
    frames = {}
    for line in lines[1:]:
        if not line.strip():
            continue
        tc, words = line.split("\t", 1)
        n = frame_of(tc.strip())
        for i, w in enumerate(words.split()):
            frames[n + i] = (int(w[:2], 16), int(w[2:], 16))
    return frames


def write(path, pairs):
    """Write the SCC file of field 1 pairs; returns the number of lines (runs) written."""
    text = to_scc(pairs)
    with open(path, "w", newline="\n") as f:
        f.write(text)
    return len(runs(pairs))
