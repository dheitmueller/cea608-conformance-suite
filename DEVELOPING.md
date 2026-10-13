# Developing the CEA-608 Conformance Suite

This document is for people who want to **modify or regenerate** the test stream. If you only want to use the
stream to check a decoder, read [README.md](README.md) instead.

If you want to send changes back, make a release or label a derivative stream, see [CONTRIBUTING.md](CONTRIBUTING.md).

## Layout

| File | Purpose |
|---|---|
| `testplan.py` | The test cards: one `@seg` function per card (title, expected result, spec references, caption script) |
| `cea608.py` | The CEA-608 encoder: byte pairs, parity, control codes, character tables, scheduling helpers |
| `build.py` | Renders the picture, encodes the video, injects the captions, muxes and patches the PMT; also writes `TESTS.md` and `cards.json` (see below) |
| `reference.py` | Reference slides: replays the stream's caption pairs through a small CEA-608 decoder model written from CTA-608-E and draws what each card should look like, plus an HTML viewer (`python reference.py`, about 10 s, no ffmpeg needed). Output goes to `out/reference/` (git-ignored); `--zip DIR` makes the release zip |
| `test_reference.py` | Checks that decoder model against the generator's own intended layout for the static pop-on cards (`python test_reference.py`); run it after changing `reference.py` or a card |
| `TESTS.md` | Generated at every build from `testplan.py` (covering both formats). **Committed**, because the README links to it and it is browsable on GitHub: commit the regenerated copy with any change to the plan; the release workflow fails if it is stale |
| `cards.json` | Machine-readable card list (ids, start times, durations, channels, references, expected results, per-format variants), generated at every build. **Not committed** (git-ignored); the validation tooling reads it after a build |
| `images/test-pattern-720p59.png` | The annotated screenshot used in the README (a frame from card G02, callouts added). |
| `requirements.txt` | Python packages |

## Dependencies

| | |
|---|---|
| Python 3 | developed with 3.14; plain Python 3 |
| Pillow, numpy | `pip install -r requirements.txt` (the graticule, labels and frames are drawn with Pillow) |
| ffmpeg | developed with 8.1.1. Needs the encoders `libx264` (default codec), `mpeg2video` and `ac3`, the `mpegts` muxer and the `aevalsrc` source. `drawtext`/freetype is **not** needed |
| a TrueType font | with Latin-1 and symbol glyphs. Found automatically on macOS (Arial, Arial Unicode) and Linux (DejaVu, Liberation); otherwise set `CEA608_FONT` and `CEA608_FONT_BOLD` |
| git | optional; only for the burned-in version label |

## Building

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python build.py                          # 720p59 (16:9), H.264
.venv/bin/python build.py --format 480i59          # 480i59 (4:3 anamorphic), H.264
.venv/bin/python build.py --codec mpeg2            # MPEG-2 video instead of H.264
```

| Option | Effect |
|---|---|
| `--format 720p59\|480i59` | **720p59** (default): 1280x720 progressive 59.94 fps, 16:9. **480i59**: 720x480 interlaced (59.94 fields/s), 4:3, anamorphic. See "Formats" below |
| `--codec h264\|mpeg2` | video essence; **h264** is the default (High profile, HRD CBR) |
| `--size WxH` | square-pixel drawing size for quick low-resolution builds (e.g. `640x360` for 720p59, `320x240` for 480i59) |
| `--out FILE` | output path (default `out/CEA608-conformance-<version>-<format>-<codec>.ts`) |
| `--no-caption-descriptor` | leave the ATSC `caption_service_descriptor` out of the PMT (checks that a decoder still offers CC1-CC4, CEA-CEB-10-A 23.2.2) |
| `--version-label TEXT` | override the burned-in version label |

A 720p59 build takes about a minute and a 480i59 build about half that. The output is a constant 4 Mbps
transport stream, so each is about 264 MB for the current 8:48 length. `out/` is git-ignored: publish the
results as release assets (they are over GitHub's 100 MB file limit).

### The version label

The picture shows a version label: the **git tag** if `HEAD` is tagged, otherwise the **short revision**, with
`+dirty` appended if the working tree has local changes (`unversioned` outside a git checkout). Use
`--version-label TEXT` to override it. How to tag, publish a release and label a derivative stream is in
[CONTRIBUTING.md](CONTRIBUTING.md).

## How the stream is made

### The source caption data

The caption content is defined **only in code** - there is no intermediate caption file yet. The scripts in
`testplan.py` call the encoder in `cea608.py`, which produces **raw CEA-608 byte pairs** (7-bit characters
with odd parity) and places **one pair per line-21 frame per field** in two in-memory arrays. A `None` entry
means `cc_valid = 0` (no waveform); a pair of valid nulls (`0x80 0x80`) means "hold". That per-frame,
per-field byte-pair sequence is the canonical form of the captions that gets rendered.

Encoding rules that matter:

* Control codes (first byte `0x10`-`0x1F`) are sent **twice in successive frames** on field 1 (CTA-608-E D.2)
  and **once** on field 2 (B.14). A null frame between two identical codes makes them separate commands.
* Field 2 uses `0x15`/`0x1D` in the miscellaneous control codes (B.11.6); channel 2 of either field adds 8 to
  the first byte.
* Pop-on captions are loaded as `RCL, ENM, rows..., EOC`, with the **first** EOC landing exactly on the
  display frame (B.8.3, B.11.2).
* Every caption must be erased explicitly, and no caption has more than four rows or more than 32 columns
  (the encoder raises an error for a row that overflows 32 columns).

### Formats

Captions always keep their native line-21 timeline of 29.97 pairs per second per field (`sec2f()` in
`cea608.py` converts seconds to caption frames). The two formats differ in how that maps onto pictures
(`FORMATS` in `build.py`):

| | 720p59 | 480i59 |
|---|---|---|
| Picture | 1280x720 progressive, 59.94 fps, square pixels | 720x480 interlaced, 29.97 frames, top field first |
| Drawing | drawn at 1280x720 | drawn at 640x480 and scaled to 720x480 with pixel aspect ratio 8:9 (display aspect 4:3) |
| Pictures per caption frame | 2 | 1 |
| `cc_data` per picture | **one** NTSC pair: field 1 (`cc_type` 00) on even pictures, field 2 (`cc_type` 01) on odd ones; `cc_count` 10 (CEA-CEB-10-A 18.1 and 25.2.2) | **both** pairs, field 2 first because the video is top field first (708-B 4.4.2 as quoted in 10-A Annex B); `cc_count` 20 |
| Padding | one `cc_valid=0 / cc_type=11` end-of-packet marker, then `cc_valid=0 / cc_type=00` up to `cc_count` (10-A 26.3, Annex B) | same |
| H.264 level / GOP | 3.2, closed GOP of 30 | 3.0, closed GOP of 15 |
| Graticule | green 4:3-centered safe area, cyan 80% box, grey 4:3 outline; full banner | the frame *is* the 4:3 picture: green safe area (80%) and grid; compact banner kept in the 10% bands above and below the safe area so it never covers caption rows (references abbreviated: `CTA-608-E` is `608-E`, `REGULATORY` is `REG`) |

Two cards word their expectation per format (the `variants=` argument of `@seg`, applied by
`apply_format()`): **G02** (the FCC safe area is defined only for a 4:3 picture, so on 16:9 only the vertical band
is checkable) and **S01** (timing tolerance is one NTSC frame, which is two pictures at 59.94 fps). Both
wordings appear in `TESTS.md` and `cards.json`.

### The program table

The PMT carries an ATSC `caption_service_descriptor` (0x86) with a **single** entry for the CEA-608 data stream
(`digital_cc = 0`). A/65:2013 defines each entry as "one 708 service or one 608 data stream", CTA-708-E 4.5
allows at most one 608 stream to be signalled, and for a 608 entry `language`, `easy_reader` and
`wide_aspect_ratio` have no meaning (`line21_field` is not expected to be used by receivers), so they are set to
neutral values. CC1-CC4 are identified by the 608 data itself.

### The pipeline (`build.py`)

1. **Schedule** - run every card's script against the four channels (CC1/CC2 share field 1, CC3/CC4 share
   field 2). A script that tries to place data before the previous data has finished raises `Overrun`;
   lengthen the previous card.
2. **Channel labels** - `add_labels()` writes a `Rendering on CC2` / `CC4` label into idle runs of valid nulls
   every ~2 seconds (card S02 uses 8 seconds, and H01 adds its test lines), so the label is visible after any
   seek. It only uses runs that end in a control code, so it can never swallow following bare text.
3. **Render** the graticule, banner and status bar frame by frame with Pillow and pipe them to ffmpeg (anamorphic scaling for 480i59 happens in ffmpeg).
4. **Encode** the video (closed GOP, B-frames, CBR; interlaced for 480i59).
5. **Inject** the captions as A/53 `cc_data()` into every picture **in display order** (see Formats for what each picture carries).
6. **Mux** with AC-3 audio into an MPEG-TS at a constant 4,000,000 bps (null-packet padded), then **patch the
   PMT** with the ATSC `caption_service_descriptor` (0x86).

For **H.264**, step 4 first produces a near-lossless MPEG-2 *carrier* that is injected in step 5; libavcodec's
MPEG-2 decoder exports the `cc_data` as frame side data and libx264 re-emits it verbatim as the ITU-T T.35
SEI of each access unit, with correct timestamps for the B-frames. The carrier is never shipped.

Practical notes: raw elementary streams need `-fflags +genpts` when muxed; a closed GOP with MPEG-2 needs
`-sc_threshold 1000000000`.

## Adding or changing a test card

Cards live in `testplan.py`. A card is a function decorated with `@seg`:

```python
@seg("P01", "Pop-on: display, erase (EDM), display", "RCL / EOC / EDM",     # id, title, detail line
     "caption A for 3 s, blank for 2 s, caption B", 8.0,                   # expected result, duration (s)
     [E("B.8.3", 65, REC), E("C.10", 74, REG)],                            # references with levels
     "The basic life cycle: load off-screen, flip with EOC ...")           # purpose (goes in TESTS.md)
def p01(c, t0):                                                            # c: a caption channel, t0: card start
    c.popon(t0, [centered(13, "Pop-on caption A")])
    c.at(t0 + 3.0)
    c.put(c.EDM())
```

* A card runs once for CC1 and once for CC3 (`chans="13"`, the default); `chans="1234"` passes a dict of all
  four channels instead. `flashes=[...]` puts a white square on the picture that carries the first EOC of the
  CC1 pair, for timing checks.
* **Helpers** on a channel `c`: `popon(show_at, rows)`, `at(t)` (pad with nulls to a time), `put(tokens, pace)`,
  `tokens(text)`, `pac(row, indent, color, italic, ul)`, `RCL() ENM() EDM() EOC() RDC() CR() BS() DER() FON()`,
  `RU(n)`, `raw(code, n)` (n identical consecutive pairs). Rows are described with `R(row, text, col, color,
  italic, ul)`.
* **Text markup** inside strings: mid-row codes `{w} {wu} {g} {gu} {b} {bu} {c} {cu} {r} {ru} {y} {yu} {m} {mu}
  {i} {iu}`; raw extended characters `{x12:2A:A}` (with a fallback letter) and `{X12:2A}` (none); `{s:39}` raw
  special; `{BS}`, `{TO1}`-`{TO3}`, `{FON}`, `{bg:r}` / `{bg:rs}` (opaque / semi-transparent), `{BT}`, `{FA}`.
  Characters that 608 maps differently from ASCII (such as `*` and `\`) are encoded automatically.
* **References and levels.** `E(section, page, level)` cites CTA-608-E and `A(section, page)` cites
  CEA-CEB-10-A; pages are **printed** page numbers. Use the source document's own label as the level
  (`REG`, `NORM`, `PREF`, `OPT`, `REC`, `INFO`; CEA-CEB-10-A items are always `10A-RECOMMENDATION`, because that
  document is a bulletin, and a card with no specification statement uses `UNSPEC`). The reference and level
  are burned into the card and appear in `TESTS.md`.
* Keep at most **four rows per caption** (the FCC minimum, C.5/C.6) unless the card is explicitly testing that
  limit, and leave enough time before a card for the *next* pop-on to load.
* Rebuild and commit the regenerated `TESTS.md` with your change (`cards.json` is generated but not committed).

## Checking a build

* `ffprobe` shows the stream properties. The transport rate should be exactly 4,000,000 bps in every PCR
  interval, with PCR at most ~41 ms apart.
* Any independent caption decoder is a good sanity check of the data. For example, with ccextractor:
  `ccextractor X.ts -12 -o x.srt` (CC1 and CC3), `ccextractor X.ts -1 --cc2 -o x2.srt` (CC2), and
  `ccextractor X.ts -2 --cc2 -o x4.srt` (CC4).

## Known limitations and ideas

* The caption data exists only in memory. Writing it to an **MCC (MacCaption)** file - per-frame `cc_data` as
  text, which unlike SCC can carry both fields - and embedding that file in a separate step would make the
  data inspectable and reusable.
* CEA-708 (DTVCC) services, XDS and Text mode are not generated.
* The annotated screenshots in `images/` are stills from particular builds; refresh them if the layout changes.
