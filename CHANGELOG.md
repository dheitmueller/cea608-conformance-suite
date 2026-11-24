# Changelog

What changed between the released versions of the test streams. The cards themselves (the 70 tests, their timing and
their expected results) are the same in every release unless a version says otherwise, so a result you recorded
against an earlier release stays comparable.

## Upcoming

Not released yet.

* **MP4 version of each stream** (`build.py --mp4`, H.264 only). A constant-quality encode (CRF 21, about 0.4 Mbps, AAC
  audio) of the same captioned video, roughly a tenth of the size of the 4 Mbps constant-bit-rate transport stream
  (27 MB against 264 MB for the 720p59 stream). The captions are carried only in the H.264 SEI, as in the transport
  stream: there is no QuickTime `c608`/`c708` track.

## v1.2 (2026-10-14)

* **Fixed the `cc_data` padding and header** (CTA-708-E 4.3.5 and Table 2). Unused triplets were `F8 00 00`
  (`cc_valid` 0, `cc_type` 00), which that standard defines as "no CEA-608 waveform for this field" and not as padding,
  and which confused some downstream parsers; they are now `FA 00 00` (`cc_type` 10). The `cc_data` header was
  `0x40 | cc_count` (reserved bit clear) and, in H.264, a reserved byte of `0x00` written by ffmpeg's libx264 wrapper;
  Table 2 requires `0xC0 | cc_count` and `0xFF`. Both are corrected in the H.264 and MPEG-2 streams. The caption pairs
  themselves are unchanged, so no card changes.
* Developer documentation cites SCTE 128-1 and A/53 Part 4 for the caption wrapper and the marker bits.

## v1.1 (2026-10-13)

* **Reference slides** (new): for each format, a viewer (drop-down, Previous/Next) showing what every card should look
  like, drawn by a small CEA-608 decoder model from the stream's own caption data. Attached to each release as a
  `-reference.zip` and published at https://dheitmueller.github.io/cea608-conformance-suite/.
* Fixed the slide model for roll-up captions: with no caption on screen, the base row defaults to 15 (CTA-608-E C.15,
  p.75); the slides for card R09 showed row 3. The streams are unchanged.
* Documented the GitHub Pages setting that tag deployments need.

## v1.0 (2026-10-11)

* First stable release. Documentation screenshots updated (the 480i59 screenshot was removed); the streams are the same
  as v0.1.

## v0.1 (2026-10-11)

* Initial release: 70 test cards in two transport streams, 720p59 (16:9) and 480i59 (4:3 interlaced), H.264 or MPEG-2,
  with CEA-608 captions as ATSC A/53 `cc_data`.
