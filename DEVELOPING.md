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
| `scc.py` | SCC export: the field 1 pairs of a build as an SCC file (drop-frame timecode); plain Python, no dependencies (`build.py --scc`, `--scc-only`) |
| `test_scc.py` | Checks the SCC export: the timecodes, that the file carries exactly the stream's field 1 pairs, and the parity (`python test_scc.py`) |
| `test_reference.py` | Checks that decoder model against the generator's own intended layout for the static pop-on cards (`python test_reference.py`); run it after changing `reference.py` or a card |
| `cea708.py` | The CEA-708 (DTVCC) encoder and the **608 -> 708 up-converter** (service blocks, caption channel packets, the window/pen mapping of each 608 caption style); pure Python, written from CTA-708-E and CEA-CEB-10-A (see "The CEA-708 variant" below) |
| `cea708_decode.py` | **Reference 708 decoder**: `cc_data` triplets to caption channel packets, service blocks, windows and pens; flattens the visible windows to the 608 15 x 32 grid so the result can be compared with `reference.py` |
| `test_cea708.py` | Checks both (`python test_cea708.py`, a few seconds): the byte examples of CTA-708-E 8.10.5, decoder unit tests, and for every card of both formats that 608 -> 708 -> decode equals the 608 reference decoder |
| `dtvcc_ts.py` | Reads the `cc_data` of a built stream (H.264 SEI or MPEG-2 user data) and decodes it with the reference decoder: `--check` (compare with the 608 reference per card), `--dump`, `--summary` |
| `TESTS.md` | Generated at every build from `testplan.py` (covering both formats). **Committed**, because the README links to it and it is browsable on GitHub: commit the regenerated copy with any change to the plan; the release workflow fails if it is stale |
| `cards.json` | Machine-readable card list (ids, start times, durations, channels, references, expected results, per-format variants), generated at every build. **Not committed** (git-ignored); the validation tooling reads it after a build |
| `screenshot.py` | Generates the annotated screenshot of the README from the build: the frame of a card (G02) drawn by the same code as the video, with the nine numbered callouts placed from the layout; `--check` tells whether the committed image shows the current cards (`python screenshot.py`, `python screenshot.py --check`) |
| `images/test-pattern-720p59.png` | The annotated screenshot used in the README (a frame from card G02, callouts added), made by `screenshot.py`. It has the card, the test number and the text of the banner it was made from in a PNG text chunk. **Committed**: regenerate it and commit it after changing the cards or the layout of the frame (the release workflow runs `--check`) |
| `requirements.txt` | Python packages |

## Dependencies

| | |
|---|---|
| Python 3 | developed with 3.14; plain Python 3 |
| Pillow, numpy | `pip install -r requirements.txt` (the graticule, labels and frames are drawn with Pillow). `cea708.py`, `cea708_decode.py`, `test_cea708.py` and `dtvcc_ts.py` need neither (they stub them when importing `build.py`) |
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
| `--scc` | also write the SCC file of the field 1 caption data (`CEA608-conformance-<version>-field1.scc`) next to the `.ts`; the same file for every format and codec |
| `--scc-only` | write only the SCC file: no video is rendered, ffmpeg is not needed, and `TESTS.md` and `cards.json` are not touched (the release workflow uses this once) |
| `--mp4` | also write a small constant-quality (CRF 21) H.264 + AAC `.mp4` next to the `.ts` (H.264 only). The captions stay in the H.264 SEI (no `c608`/`c708` track, no PMT descriptor); see "The MP4 version" in the README |
| `--dtvcc off\|both\|only` | CEA-708: **both** adds the 608 captions up-converted to DTVCC services 1-4 next to the 608 data; **only** leaves the 608 pairs out (a 708-only stream); default **off**. The file name gets `-dtvcc` / `-dtvcc-only`; see "The CEA-708 variant" |
| `--dtvcc-swap showhide\|toggle` | how the up-converter swaps the two pop-on window sets: HideWindows + DisplayWindows (default) or ToggleWindows |

A 720p59 build takes about a minute and a 480i59 build about half that. The output is a constant 4 Mbps
transport stream, so each is about 304 MB for the current 10:08 length. `out/` is git-ignored: publish the
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
| `cc_data` header | `0xC0 \| cc_count`, `0xFF` (CTA-708-E Table 2: reserved '1', process_cc_data_flag, zero_bit, `cc_count`, reserved 8 bits of 1), e.g. `CA FF` for `cc_count` 10, `D4 FF` for 20; the structure ends with `marker_bits` `0xFF` (ATSC A/53 Part 4:2009 Table 6.10, which defers `cc_data()` to CEA-708 Table 2). For H.264 the same structure is carried in an SEI `user_data_registered_itu_t_t35` (country code `0xB5`, provider code `0x0031`, `user_identifier` `GA94`, `user_data_type_code` `0x03`, `cc_data()` as defined in CTA-708, `marker_bits` `0xFF`; ANSI/SCTE 128-1:2020 section 8, Tables 12-15). For H.264 ffmpeg's libx264 wrapper writes `0x40 \| cc_count, 0x00` itself, so `build.py` rewrites those two bytes in the finished transport stream (`fix_h264_cc_header`) | same |
| Padding | `cc_valid=0 / cc_type=10` (`0xFA 0x00 0x00`) up to `cc_count`; the first one ends the CEA-608 data (CTA-708-E 4.3.5). `cc_valid=0` with `cc_type` 00/01 is *not* padding (it means no waveform, used only by cards S03-S05) | same |
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

### The CEA-708 variant (`--dtvcc`)

`build.py --dtvcc both` adds the same captions as CEA-708 (DTVCC) data to the stream; nothing else changes (picture,
cards, timing, the 608 data). It is an **up-conversion**: the byte pairs of the four 608 data channels are followed
exactly as `reference.py` follows them and each command is translated to the 708 commands that produce the same
picture. The expected result of every card is therefore the one on screen (and in `TESTS.md`); what is different is the
decoder path being tested. The converter (`cea708.py`) is written from the specification, not ported from another
converter, so that converters can be compared with it (their differences are findings, not necessarily bugs of either).

**Transport.** The DTVCC data follows the 608 pairs in the same `cc_data()` of every picture: `cc_type` 3 starts a
caption channel packet and `cc_type` 2 continues it (CTA-708-E 4.3), what is left of the 10 (720p59) or 20 (480i59)
triplets after the NTSC pairs is the bandwidth (the 608 data is part of the 9600 bps of 4.1). Per picture the
converter sends one packet (rolling sequence number, size in byte pairs, a null service block header when space is left)
with as many queued syntactic elements as fit, in service blocks of up to 31 bytes; an element is never split. A picture with nothing
to send carries only padding. `--dtvcc only` leaves out the NTSC pairs (and the PMT lists no 608 entry).

**Services.** CC1-CC4 are services 1-4. The PMT `caption_service_descriptor` gets one entry per service (`digital_cc` 1,
`caption_service_number`, `wide_aspect_ratio` 1 for 720p59 and 0 for 480i59) next to the 608 entry. Every service starts
with Reset (8.9.3).

**Mapping** (all windows left-justified, left-to-right, scroll up, snap, transparent fill: window styles 2 and 5 of Table 26,
pen style 1, so white text on a solid black character background like a 608 decoder; priority = window id):

| 608 | 708 |
|---|---|
| displayed / non-displayed memory | two sets of four windows (ids 0-3 and 4-7); the 608 four-row limit means a set never needs more. The end-of-caption command swaps them with HideWindows + DisplayWindows in one element (or ToggleWindows with `--dtvcc-swap toggle`) |
| a pop-on or paint-on row | its own 1-row, 32-column window at the 608 row, defined when the row is first written (10-A 27.2.2.2); ENM / EDM delete the windows of that memory; a fifth row deletes the window of the oldest |
| roll-up (RU2-4) | one window of *depth* rows whose bottom row is the base row; CR is the 708 CR code (the row is first selected with SetPenLocation, the window is defined again at every CR so a receiver can tune in at any row); a PAC that moves the base row moves the window with DefineWindow (an update keeps the text, 8.10.5.2); a depth change writes the new window hidden and swaps it in |
| column | window column 0 is 608 column 1; on 16:9 the 32 columns are centred in the 42-column grid (anchor horizontal 25, 708-E 8.2 and 8.5.1.1), on 4:3 the anchor horizontal is 0; a text row is 5 grid cells high and a column 5 wide (8.5.1.3 c) |
| PAC, mid-row code, background / foreground attribute code, FON | SetPenAttributes (italics, underline) and SetPenColor (foreground colour and flash, background colour and opacity); the codes that occupy a cell in 608 write a space after the pen command; PAC attribute inheritance (608-E C.7) is applied by the converter |
| tab offset, backspace | SetPenLocation when the next character is written; the 708 BS code where the pen is known to follow the character, else SetPenLocation + transparent space |
| DER | a one-row window is replaced by a hidden new one holding the kept part and swapped in; otherwise SetPenLocation + transparent spaces (or HCR at column 1) |
| text | G0, G1 and G2 (`cea708.text_bytes`); a character at column 32 is preceded by SetPenLocation (708 says only "replace or discard", 8.4.8); caption text not followed by a command ends with ETX (8.6) |
| loss of data (608-E C.21, 45 frames) | DeleteWindows of every window (`erase_on_loss`) |

**What 708 cannot say.** 608 characters without a 708 code point are mapped to the nearest one: the solid block
(608 `0x7F`) to G2 `0x30` and the em dash to G2 `0x7D` (a horizontal line); the 608 transparent space (`0x11 0x39`) is written as a space with a transparent pen background for that cell only.
`test_cea708.py` and `dtvcc_ts.py --check` treat those as equal. Nothing of 708 beyond the 608 feature set is generated
(no fonts, pen sizes, justification, borders, effects, Delay, more than one window style).

**Bandwidth and timing.** Elements wait for bandwidth, so the 708 caption can run a few frames behind the 608 one when
both channels of a card send bursts (the longest wait is reported by `build.py`; `test_cea708.py` prints the lag, 3 frames
at most today). The comparison calls a 708 state *coalesced* when a lagging decoder shows two 608 states in one step and
*transient* when a 708 command sequence passes through a state the 608 decoder never shows; both are counted, any other
difference is a failure.

**Checking.** `python test_cea708.py` (generator level) and `python dtvcc_ts.py STREAM.ts --check` (the finished
stream: H.264 SEI or MPEG-2 user data, display order from the pts / temporal reference). `ccextractor -svc 1` (0.96.5)
decodes service 1 of such a stream (it shows the pop-on captions only with the default HideWindows + DisplayWindows, not with
ToggleWindows; that is a ccextractor limitation, not a property of the stream).

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

* The caption data is written to an SCC file (`--scc`), which carries field 1 only. Writing it to an **MCC
  (MacCaption)** file - per-frame `cc_data` as text, which unlike SCC can carry both fields - and embedding that
  file in a separate step would also make field 2 inspectable and reusable.
* CEA-708 (DTVCC) is generated only as the up-conversion of the 608 captions (`--dtvcc`); native 708 features, XDS and Text mode are not generated.
* The annotated screenshot in `images/` is generated by `screenshot.py`, and the release workflow checks that the committed
  copy shows the current cards (card, test number, text of the banner), not the pixels. The check does not notice a change
  to the layout code: bump `LAYOUT` in `screenshot.py` when the drawing of the frame or of the callouts changes. The image
  carries the version label of the build that made it (the latest release when it is regenerated), and its look depends on the
  fonts: for the look of the released streams use DejaVu Sans (`CEA608_FONT`, `CEA608_FONT_BOLD`).
