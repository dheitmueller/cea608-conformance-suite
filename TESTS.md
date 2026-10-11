# CEA-608 Conformance Suite - test cards

By Devin Heitmueller. Licensed CC BY-SA 4.0 (https://creativecommons.org/licenses/by-sa/4.0/).

70 cards, 08:47.99 long. Two formats are built from the same cards: **720p59** (1280x720 progressive, 59.94 fps, 16:9) and **480i59** (720x480 anamorphic interlaced, 59.94 fields/s, 4:3), each as H.264 (default) or MPEG-2 at 3.5 Mbps CBR with AC-3 (128 kbps) in a 4 Mbps CBR MPEG-TS. Caption data: CEA-608 in ATSC A/53 `cc_data`; field 1 = CC1 (+CC2), field 2 = CC3 (+CC4). CC1 and CC3 carry identical tests; CC2 and CC4 show a continuous `Rendering on CCn` label (refreshed every 2 s) and are used by card H01. Two cards word their expectation differently per format and say so below.

Each card's name, expected result and spec reference with its level are burned into the video, over a graticule showing the FCC safe caption area and the 15 x 32 grid.

## How to read the "level" tags

Every card names the specification section it exercises and says **how binding** the expected
behavior is, using the source document's own wording:

| Tag | Source | Meaning |
|---|---|---|
| `REGULATORY` | CTA-608-E | Required by the FCC rules (47 CFR 15.119) as reproduced/clarified in 608-E. A conforming caption decoder shall do this. |
| `NORMATIVE` | CTA-608-E | Normative text of 608-E (including section 6.4 character sets and Annex C/D "shall" statements). |
| `PREFERRED` | CTA-608-E | 608-E states a preferred option; other reasonable choices are permitted "with no significant degradation of service" (C.1). |
| `OPTIONAL` | CTA-608-E | Optional decoder feature (extended characters, background/foreground attributes). If implemented it shall behave as described. A renderer that omits it is not non-conforming. |
| `RECOMMENDED` | CTA-608-E | Recommended practice addressed mainly to caption providers/encoders (Annex B); shown because the card checks the decoder against that practice. |
| `INFORMATIVE` | either | Context, not a requirement. |
| `10A-RECOMMENDATION` | CEA-CEB-10-A | CEA-CEB-10-A is a **bulletin**: its recommendations are best practice and are **not mandatory**. (It is written for EIA-708-B; only the sections on 608 carried in `cc_data` are used here.) |
| `UNSPECIFIED` | none | Neither document defines the result; the card records what a renderer does. |

Citations use **printed** page numbers (not PDF page numbers). A card with two levels
(e.g. `REGULATORY/PREFERRED`) reproduces the section's own heading.

## Specifications

* **CTA-608-E** (ANSI/CTA-608-E S-2019), *Line 21 Data Services*.
* **CEA-CEB-10-A** (Dec 2002), *EIA-708-B Implementation Guidance*.
* **ATSC A/65:2013** (descriptor syntax) and **CTA-708-E** are consulted for the program-table signalling and the 16:9 behavior of DTVCC.

## Geometry and stream start

### G00 - CEA-608 Conformance Suite

*Starts 00:00.00, lasts 5 s, channels: CC1, CC3*

**Purpose.** Stream identification and lead-in. No captions are sent so a renderer can lock to the video before the first test. Carries the stream version, author and license.

**Test.** Original test content; each card names its test, expected result and spec reference.

**Expected.** Captions begin shortly. CC1 and CC3 carry the same tests; CC2/CC4 are used in card H01.

### G01 - Which caption channel is being rendered

*Starts 00:05.00, lasts 7 s, channels: CC1, CC3*

**Purpose.** First caption of the stream. Each service sends its own name so whoever is looking at a capture knows which caption channel the renderer selected: CC1 reads 'Rendering on CC1', CC3 reads 'Rendering on CC3'. CC2 and CC4 carry no tests except card H01, so they instead show 'Rendering on CC2' / 'Rendering on CC4' for the whole stream, re-sent every 2 s in idle gaps so the label is present even after seeking. Three centered rows using PAC indent plus Tab Offset, the technique 608-E B.4 gives for centering.

**Test.** first caption: names the channel the renderer is displaying.

**Expected.** 'Rendering on CC1' (or CC3). CC2/CC4 show their own label continuously (refreshed every 2 s)

**References.**

* CTA-608-E B.4 p.62 - `RECOMMENDED`
* CTA-608-E C.7 p.73 - `REGULATORY/PREFERRED`
* CTA-608-E B.13 p.69 - `RECOMMENDED`

### G02 - Safe caption area and 32x15 grid

*Starts 00:12.00, lasts 6 s, channels: CC1, CC3*

**Purpose.** Verifies the renderer maps the 32-column x 15-row grid into the FCC safe caption area (80% x 80% of the 4:3 picture, Table 46). Corner markers make clipping, wrong margins and wrong row mapping obvious against the graticule.

**Test.** pop-on; markers at row 1/15, column 1/32.

**Expected.** A,B on row 1 and C,D on row 15 sit at the extreme left/right grid cells, inside the green FCC safe box

**References.**

* CTA-608-E C.22 p.77 - `REGULATORY`
* CTA-608-E C.13 p.75 - `REGULATORY/NORMATIVE`

*720p59 (16:9) differs:* **Expected.** A,B (row 1) and C,D (row 15) at the grid edges, rows within 10-90% of height; note whether columns map to the green, cyan or another box **Purpose.** The FCC safe caption area (C.22, Table 46) is defined only for a 4:3 picture: 80% of the picture height by 80% of a 4:3 width, 10% in from the top. Rows 1-15 therefore span 10%-90% of the picture height at any aspect ratio, which is checkable. How the 32 columns map horizontally onto a 16:9 picture is not specified in CTA-608-E; CEA-CEB-10-A 23.3 only remarks that up-converted NTSC captions may have a 4:3 aspect ratio within a 16:9 image. The green box (4:3 centered) and the cyan box (80% of the 16:9 frame) are shown as the two common interpretations; this card records which one the decoder uses. **References.** CTA-608-E C.22 p.77: vertical band defined; horizontal placement for 16:9 unspecified - `REGULATORY (vertical) / UNSPECIFIED`; CEA-CEB-10-A 23.3 p.38 - `INFORMATIVE`

## Character sets

### C01a - Basic characters 1/3

*Starts 00:18.00, lasts 5 s, channels: CC1, CC3*

**Purpose.** The 112-character basic set every decoder shall support. 608 replaces several ASCII positions (0x2A, 0x5C, 0x5E-0x60, 0x7B-0x7F) with accented letters and symbols; a renderer using plain ASCII/Latin-1 mapping fails here.

**Test.** standard set 0x20-0x3F; note a-acute at 0x2A etc..

**Expected.**  !"#$%&'()á+,-./0123456789:;<=>?

**References.**

* CTA-608-E 6.4.1 p.18 - `NORMATIVE`
* CTA-608-E Tables 49-50 p.96-98 - `REGULATORY`

### C01b - Basic characters 2/3

*Starts 00:23.00, lasts 5 s, channels: CC1, CC3*

**Purpose.** The 112-character basic set every decoder shall support. 608 replaces several ASCII positions (0x2A, 0x5C, 0x5E-0x60, 0x7B-0x7F) with accented letters and symbols; a renderer using plain ASCII/Latin-1 mapping fails here.

**Test.** standard set 0x40-0x5F; note a-acute at 0x2A etc..

**Expected.** @ABCDEFGHIJKLMNOPQRSTUVWXYZ[é]íó

**References.**

* CTA-608-E 6.4.1 p.18 - `NORMATIVE`
* CTA-608-E Tables 49-50 p.96-98 - `REGULATORY`

### C01c - Basic characters 3/3

*Starts 00:28.00, lasts 5 s, channels: CC1, CC3*

**Purpose.** The 112-character basic set every decoder shall support. 608 replaces several ASCII positions (0x2A, 0x5C, 0x5E-0x60, 0x7B-0x7F) with accented letters and symbols; a renderer using plain ASCII/Latin-1 mapping fails here.

**Test.** standard set 0x60-0x7F; note a-acute at 0x2A etc..

**Expected.** úabcdefghijklmnopqrstuvwxyzç÷Ññ■

**References.**

* CTA-608-E 6.4.1 p.18 - `NORMATIVE`
* CTA-608-E Tables 49-50 p.96-98 - `REGULATORY`

### C02 - Special characters

*Starts 00:33.00, lasts 5 s, channels: CC1, CC3*

**Purpose.** The 16 special characters sent as two-byte codes (registered, degree, half, inverted query, trademark, cent, pound, music note, accented a/e/i/o/u). The transparent space (0x39) is omitted from the visible row.

**Test.** 0x11 0x30-0x3F (0x19 on channel 2).

**Expected.** ® ° ½ ¿ ™ ¢ £ ♪ à è â ê î ô û

**References.**

* CTA-608-E F.1.1.1 Table 49 p.96 - `REGULATORY`

### C03a - International characters - Spanish

*Starts 00:38.00, lasts 6 s, channels: CC1, CC3*

**Purpose.** Optional extended characters (Table 5). Each extended character carries an automatic backspace, so the stream sends a fallback character first (as a legacy decoder would display); an extended-capable renderer must replace it. Row 7 shows the table, row 10+ a real phrase. A renderer that does not implement the optional set will show the fallback letters instead.

**Test.** table 5: 0x12 0x20-0x27.

**Expected.** Á É Ó Ú Ü ü ‘ ¡

**References.**

* CTA-608-E 6.4.2 Table 5 p.20 - `OPTIONAL`
* CTA-608-E 6.4.2 p.18 - `OPTIONAL`

### C03b - Miscellaneous symbols

*Starts 00:44.00, lasts 6 s, channels: CC1, CC3*

**Purpose.** Optional extended characters (Table 6). Each extended character carries an automatic backspace, so the stream sends a fallback character first (as a legacy decoder would display); an extended-capable renderer must replace it. Row 7 shows the table, row 10+ a real phrase. A renderer that does not implement the optional set will show the fallback letters instead.

**Test.** table 6: 0x12 0x28-0x2F.

**Expected.** * ' — © ℠ • “ ”

**References.**

* CTA-608-E 6.4.2 Table 6 p.21 - `OPTIONAL`
* CTA-608-E 6.4.2 p.18 - `OPTIONAL`

### C03c - International characters - French

*Starts 00:50.00, lasts 6 s, channels: CC1, CC3*

**Purpose.** Optional extended characters (Table 7). Each extended character carries an automatic backspace, so the stream sends a fallback character first (as a legacy decoder would display); an extended-capable renderer must replace it. Row 7 shows the table, row 10+ a real phrase. A renderer that does not implement the optional set will show the fallback letters instead.

**Test.** table 7: 0x12 0x30-0x3F.

**Expected.** À Â Ç È Ê Ë ë Î Ï ï Ô Ù ù Û « »

**References.**

* CTA-608-E 6.4.2 Table 7 p.22 - `OPTIONAL`
* CTA-608-E 6.4.2 p.18 - `OPTIONAL`

### C03d - International characters - Portuguese

*Starts 00:56.00, lasts 6 s, channels: CC1, CC3*

**Purpose.** Optional extended characters (Table 8). Each extended character carries an automatic backspace, so the stream sends a fallback character first (as a legacy decoder would display); an extended-capable renderer must replace it. Row 7 shows the table, row 10+ a real phrase. A renderer that does not implement the optional set will show the fallback letters instead.

**Test.** table 8: 0x13 0x20-0x2F (incl. { } \ ^ _ | ~).

**Expected.** Ã ã Í Ì ì Ò ò Õ õ { } \ ^ _ | ~

**References.**

* CTA-608-E 6.4.2 Table 8 p.23 - `OPTIONAL`
* CTA-608-E 6.4.2 p.18 - `OPTIONAL`

### C03e - International characters - German

*Starts 01:02.00, lasts 6 s, channels: CC1, CC3*

**Purpose.** Optional extended characters (Table 9). Each extended character carries an automatic backspace, so the stream sends a fallback character first (as a legacy decoder would display); an extended-capable renderer must replace it. Row 7 shows the table, row 10+ a real phrase. A renderer that does not implement the optional set will show the fallback letters instead.

**Test.** table 9: 0x13 0x30-0x37.

**Expected.** Ä ä Ö ö ß ¥ ¤ │

**References.**

* CTA-608-E 6.4.2 Table 9 p.24 - `OPTIONAL`
* CTA-608-E 6.4.2 p.18 - `OPTIONAL`

### C03f - International characters - Danish

*Starts 01:08.00, lasts 6 s, channels: CC1, CC3*

**Purpose.** Optional extended characters (Table 10). Each extended character carries an automatic backspace, so the stream sends a fallback character first (as a legacy decoder would display); an extended-capable renderer must replace it. Row 7 shows the table, row 10+ a real phrase. A renderer that does not implement the optional set will show the fallback letters instead.

**Test.** table 10: 0x13 0x38-0x3F (incl. box corners).

**Expected.** Å å Ø ø ┌ ┐ └ ┘

**References.**

* CTA-608-E 6.4.2 Table 10 p.25 - `OPTIONAL`
* CTA-608-E 6.4.2 p.18 - `OPTIONAL`

### C04 - Extended character automatic backspace

*Starts 01:14.00, lasts 5 s, channels: CC1, CC3*

**Purpose.** Edge cases of the automatic backspace: an extended character must erase the character to its left (here the fallback 'A'), but when it is the first character on a row there is nothing to erase and the cursor must not move left of column 1.

**Test.** pop-on; fallback + extended, and extended as first character.

**Expected.** row 6 reads ABCÁ (not ABCAÁ); row 8 shows Á in column 1 and nothing is lost to the left

**References.**

* CTA-608-E 6.4.2 p.18 - `OPTIONAL`

## Addressing and attributes (PAC, mid-row, tab offsets)

### A01a - PAC rows 1-4

*Starts 01:19.00, lasts 4 s, channels: CC1, CC3*

**Purpose.** All 15 rows addressable by PAC. Split into captions of at most four rows because the FCC requires only four simultaneous rows (C.5); rows 5-11 are the 'mid-screen' PACs added by the 1991 FCC rules (B.2 p.61).

**Test.** preamble address codes select the row.

**Expected.** 'Row N' appears on row N (grid row N in the graticule)

**References.**

* CTA-608-E F.1.1.5 Table 53 p.101 - `REGULATORY`
* CTA-608-E C.5 p.72 - `REGULATORY`

### A01b - PAC rows 5-8

*Starts 01:23.00, lasts 4 s, channels: CC1, CC3*

**Purpose.** All 15 rows addressable by PAC. Split into captions of at most four rows because the FCC requires only four simultaneous rows (C.5); rows 5-11 are the 'mid-screen' PACs added by the 1991 FCC rules (B.2 p.61).

**Test.** preamble address codes select the row.

**Expected.** 'Row N' appears on row N (grid row N in the graticule)

**References.**

* CTA-608-E F.1.1.5 Table 53 p.101 - `REGULATORY`
* CTA-608-E C.5 p.72 - `REGULATORY`

### A01c - PAC rows 9-12

*Starts 01:27.00, lasts 4 s, channels: CC1, CC3*

**Purpose.** All 15 rows addressable by PAC. Split into captions of at most four rows because the FCC requires only four simultaneous rows (C.5); rows 5-11 are the 'mid-screen' PACs added by the 1991 FCC rules (B.2 p.61).

**Test.** preamble address codes select the row.

**Expected.** 'Row N' appears on row N (grid row N in the graticule)

**References.**

* CTA-608-E F.1.1.5 Table 53 p.101 - `REGULATORY`
* CTA-608-E C.5 p.72 - `REGULATORY`

### A01d - PAC rows 13-15

*Starts 01:31.00, lasts 4 s, channels: CC1, CC3*

**Purpose.** All 15 rows addressable by PAC. Split into captions of at most four rows because the FCC requires only four simultaneous rows (C.5); rows 5-11 are the 'mid-screen' PACs added by the 1991 FCC rules (B.2 p.61).

**Test.** preamble address codes select the row.

**Expected.** 'Row N' appears on row N (grid row N in the graticule)

**References.**

* CTA-608-E F.1.1.5 Table 53 p.101 - `REGULATORY`
* CTA-608-E C.5 p.72 - `REGULATORY`

### A02a - PAC colors 1/2

*Starts 01:35.00, lasts 4 s, channels: CC1, CC3*

**Purpose.** Foreground color, italics and underline selected by non-indenting PACs. A monochrome decoder may ignore color but must still honor spacing/underline (C.2).

**Test.** PAC color/italic/underline attributes.

**Expected.** White Green Blue Cyan

**References.**

* CTA-608-E F.1.1.5 Table 53 p.101 - `REGULATORY`
* CTA-608-E C.2 p.71 - `REGULATORY`

### A02b - PAC colors 2/2

*Starts 01:39.00, lasts 4 s, channels: CC1, CC3*

**Purpose.** Foreground color, italics and underline selected by non-indenting PACs. A monochrome decoder may ignore color but must still honor spacing/underline (C.2).

**Test.** PAC color/italic/underline attributes.

**Expected.** Red Yellow Magenta + White Italic

**References.**

* CTA-608-E F.1.1.5 Table 53 p.101 - `REGULATORY`
* CTA-608-E C.2 p.71 - `REGULATORY`

### A02c - PAC colors underlined 1/2

*Starts 01:43.00, lasts 4 s, channels: CC1, CC3*

**Purpose.** Foreground color, italics and underline selected by non-indenting PACs. A monochrome decoder may ignore color but must still honor spacing/underline (C.2).

**Test.** PAC color/italic/underline attributes.

**Expected.** White Green Blue Cyan (all underlined)

**References.**

* CTA-608-E F.1.1.5 Table 53 p.101 - `REGULATORY`
* CTA-608-E C.2 p.71 - `REGULATORY`

### A02d - PAC colors underlined 2/2

*Starts 01:47.00, lasts 4 s, channels: CC1, CC3*

**Purpose.** Foreground color, italics and underline selected by non-indenting PACs. A monochrome decoder may ignore color but must still honor spacing/underline (C.2).

**Test.** PAC color/italic/underline attributes.

**Expected.** Red Yellow Magenta + White Italic (all underlined)

**References.**

* CTA-608-E F.1.1.5 Table 53 p.101 - `REGULATORY`
* CTA-608-E C.2 p.71 - `REGULATORY`

### A03a - PAC indents 0-12

*Starts 01:51.00, lasts 4 s, channels: CC1, CC3*

**Purpose.** Indenting PACs (0, 4, ... 28 columns). An indenting PAC carries white, non-italic, and sets only underline.

**Test.** indenting PAC: column = indent + 1.

**Expected.** numbers step right by 4 columns

**References.**

* CTA-608-E F.1.1.5 Table 53 p.101 - `REGULATORY`
* CTA-608-E C.7 p.73 - `REGULATORY/PREFERRED`

### A03b - PAC indents 16-28

*Starts 01:55.00, lasts 4 s, channels: CC1, CC3*

**Purpose.** Indenting PACs (0, 4, ... 28 columns). An indenting PAC carries white, non-italic, and sets only underline.

**Test.** indenting PAC: column = indent + 1.

**Expected.** numbers step right by 4 columns

**References.**

* CTA-608-E F.1.1.5 Table 53 p.101 - `REGULATORY`
* CTA-608-E C.7 p.73 - `REGULATORY/PREFERRED`

### A03c - PAC indents 0-12 underlined

*Starts 01:59.00, lasts 4 s, channels: CC1, CC3*

**Purpose.** Indenting PACs (0, 4, ... 28 columns). An indenting PAC carries white, non-italic, and sets only underline.

**Test.** indenting PAC: column = indent + 1.

**Expected.** numbers step right by 4 columns, underlined

**References.**

* CTA-608-E F.1.1.5 Table 53 p.101 - `REGULATORY`
* CTA-608-E C.7 p.73 - `REGULATORY/PREFERRED`

### A03d - PAC indents 16-28 underlined

*Starts 02:03.00, lasts 4 s, channels: CC1, CC3*

**Purpose.** Indenting PACs (0, 4, ... 28 columns). An indenting PAC carries white, non-italic, and sets only underline.

**Test.** indenting PAC: column = indent + 1.

**Expected.** numbers step right by 4 columns, underlined

**References.**

* CTA-608-E F.1.1.5 Table 53 p.101 - `REGULATORY`
* CTA-608-E C.7 p.73 - `REGULATORY/PREFERRED`

### A04 - Tab offsets TO1-TO3

*Starts 02:07.00, lasts 5 s, channels: CC1, CC3*

**Purpose.** Tab offsets move the cursor 1-3 columns right without affecting the display (C.7); the rows start at PAC indent 0 plus TO0..TO2.

**Test.** 0x17 0x21-0x23 after an indenting PAC.

**Expected.** rows step right by one column each (columns 1, 2, 3); text is not erased

**References.**

* CTA-608-E B.4 p.62 - `RECOMMENDED`
* CTA-608-E C.7 p.73 - `REGULATORY/PREFERRED`

### A05a - Mid-row codes 1/4

*Starts 02:12.00, lasts 4 s, channels: CC1, CC3*

**Purpose.** Mid-row codes change color/italics/underline mid-line and occupy one (space) column. Sixteen codes over four cards.

**Test.** 0x11 0x20-0x2F inside a row.

**Expected.** the named word in that style; the rest of the row is white (mid-row white resets)

**References.**

* CTA-608-E F.1.1.3 Table 51 p.99 - `REGULATORY`

### A05b - Mid-row codes 2/4

*Starts 02:16.00, lasts 4 s, channels: CC1, CC3*

**Purpose.** Mid-row codes change color/italics/underline mid-line and occupy one (space) column. Sixteen codes over four cards.

**Test.** 0x11 0x20-0x2F inside a row.

**Expected.** the named word in that style; the rest of the row is white (mid-row white resets)

**References.**

* CTA-608-E F.1.1.3 Table 51 p.99 - `REGULATORY`

### A05c - Mid-row codes 3/4

*Starts 02:20.00, lasts 4 s, channels: CC1, CC3*

**Purpose.** Mid-row codes change color/italics/underline mid-line and occupy one (space) column. Sixteen codes over four cards.

**Test.** 0x11 0x20-0x2F inside a row.

**Expected.** the named word in that style; the rest of the row is white (mid-row white resets)

**References.**

* CTA-608-E F.1.1.3 Table 51 p.99 - `REGULATORY`

### A05d - Mid-row codes 4/4

*Starts 02:24.00, lasts 4 s, channels: CC1, CC3*

**Purpose.** Mid-row codes change color/italics/underline mid-line and occupy one (space) column. Sixteen codes over four cards.

**Test.** 0x11 0x20-0x2F inside a row.

**Expected.** the named word in that style; the rest of the row is white (mid-row white resets)

**References.**

* CTA-608-E F.1.1.3 Table 51 p.99 - `REGULATORY`

### A06 - Attribute inheritance

*Starts 02:28.00, lasts 6 s, channels: CC1, CC3*

**Purpose.** 608-E C.7: a character deposited next to an existing character assumes that character's attributes and the PAC's are ignored (row 6: green GREEN followed by an indent-4+TO2 white PAC at the next column). Conversely an indenting PAC with underline, then a Tab Offset, then text must underline (row 8).

**Test.** new character takes attributes of the character to its left.

**Expected.** row 6: GREENTEXT all green; row 8: UNDERLINED is underlined

**References.**

* CTA-608-E C.7 p.73 - `REGULATORY/PREFERRED`

### A07 - Right margin, tab clamp, backspace edges

*Starts 02:34.00, lasts 8 s, channels: CC1, CC3*

**Purpose.** The cursor never passes column 32 (row 6: 32 letters then X, Y overwrite column 32, final Y). Tab offsets clamp at 32 (row 8: PAC indent 28 + TO1 + TO3 must stop at 32; Z is visible). A BS after a character in column 32 moves to column 31 and erases it (row 10: 'x' replaces column 31; column 32 may or may not be erased - both are legal). BS in column 1 is ignored (row 12: Q appears).

**Test.** 34 chars on a row; TO beyond col 32; BS at col 32 and col 1.

**Expected.** r6 ends in Y at col 32 | r8: lone Z at col 32 | r10: x at col 31 (col 32 either) | r12: Q at col 1

**References.**

* CTA-608-E C.13 p.75 - `REGULATORY/NORMATIVE`
* CTA-608-E B.12 p.69 - `RECOMMENDED`

### A08 - Default attributes after CR

*Starts 02:42.00, lasts 7 s, channels: CC1, CC3*

**Purpose.** When no attributes have been assigned the display shall be white, non-underlined, non-italic, non-flashing. A roll-up row started by CR with no PAC must not inherit the previous row's color.

**Test.** roll-up row created by CR with no PAC.

**Expected.** row 1 yellow underlined; row 2 (no PAC) is white, not underlined, not italic

**References.**

* CTA-608-E C.14 p.75 - `NORMATIVE`

### A09a - Background colors (opaque)

*Starts 02:49.00, lasts 5 s, channels: CC1, CC3*

**Purpose.** Optional extended attribute codes. Each code is preceded by a standard space and carries an automatic backspace so a standard decoder shows one space and an extended decoder shows one colored space. Unsupported background colors should default to black (6.2).

**Test.** background/foreground attribute codes (standard space + code with automatic BS).

**Expected.** colored box behind each row (white text)

**References.**

* CTA-608-E 6.2 p.16 - `OPTIONAL`
* CTA-608-E Table 3 p.17 - `OPTIONAL`

### A09b - Background colors (semi-transparent)

*Starts 02:54.00, lasts 5 s, channels: CC1, CC3*

**Purpose.** Optional extended attribute codes. Each code is preceded by a standard space and carries an automatic backspace so a standard decoder shows one space and an extended decoder shows one colored space. Unsupported background colors should default to black (6.2).

**Test.** background/foreground attribute codes (standard space + code with automatic BS).

**Expected.** video shows through the box (renderer may fall back to opaque)

**References.**

* CTA-608-E 6.2 p.16 - `OPTIONAL`
* CTA-608-E Table 3 p.17 - `OPTIONAL`

### A09c - Foreground black and transparent background

*Starts 02:59.00, lasts 5 s, channels: CC1, CC3*

**Purpose.** Optional extended attribute codes. Each code is preceded by a standard space and carries an automatic backspace so a standard decoder shows one space and an extended decoder shows one colored space. Unsupported background colors should default to black (6.2).

**Test.** background/foreground attribute codes (standard space + code with automatic BS).

**Expected.** black text on light boxes; third row without any box

**References.**

* CTA-608-E 6.2 p.16 - `OPTIONAL`
* CTA-608-E Table 3 p.17 - `OPTIONAL`

### A10 - Flash on (FON)

*Starts 03:04.00, lasts 5 s, channels: CC1, CC3*

**Purpose.** Flash On is a spacing attribute. 608-E does not define the flash rate, and for flashing underlined text either only the characters or characters+underline may flash (C.19, optional).

**Test.** 0x14 0x28 (0x1C 0x28 on ch 2).

**Expected.** the second half of row 6 flashes (rate unspecified)

**References.**

* CTA-608-E F.1.1.4 Table 52 p.99 - `REGULATORY`
* CTA-608-E C.19 p.76 - `OPTIONAL`

## Pop-on style and memory control

### P01 - Pop-on: display, erase (EDM), display

*Starts 03:09.00, lasts 8 s, channels: CC1, CC3*

**Purpose.** The basic life cycle: load off-screen, flip with EOC (the first EOC lands exactly on the display frame, B.11.2), erase with EDM, load the next.

**Test.** RCL / EOC / EDM.

**Expected.** caption A for 3 s, blank for 2 s, caption B

**References.**

* CTA-608-E B.8.3 p.65 - `RECOMMENDED`
* CTA-608-E C.10 p.74 - `REGULATORY`
* CTA-608-E C.16 p.75 - `NORMATIVE`

### P02 - Pop-on: loading is invisible until EOC

*Starts 03:17.00, lasts 8 s, channels: CC1, CC3*

**Purpose.** RCL only selects pop-on; data goes to non-displayed memory and must not appear until EOC. Three captions swap on exact frames.

**Test.** RCL + text while another caption is displayed.

**Expected.** A, then B at +2.5 s, then C at +5 s; never partial text

**References.**

* CTA-608-E C.10 p.74 - `REGULATORY`
* CTA-608-E B.11.2 p.68 - `RECOMMENDED`

### P03 - ENM erases non-displayed memory

*Starts 03:25.00, lasts 8 s, channels: CC1, CC3*

**Purpose.** ENM must clear the loading buffer unconditionally. BAD text is loaded then erased by ENM; the later EOC must show only the correct text.

**Test.** 0x14 0x2E.

**Expected.** 'Visible' caption stays; BAD text never appears; then 'Correct' text

**References.**

* CTA-608-E C.16 p.75 - `NORMATIVE`
* CTA-608-E B.8.3 p.66 - `RECOMMENDED`

### P04 - EDM erases any style

*Starts 03:33.00, lasts 11 s, channels: CC1, CC3*

**Purpose.** EDM erases a displayed caption whatever style produced it; it stands alone with no preceding RCL/RDC (B.11.4).

**Test.** EDM after paint-on and after roll-up.

**Expected.** paint-on text vanishes at +3 s; roll-up text appears at +5 s and vanishes at +9 s

**References.**

* CTA-608-E C.16 p.75 - `NORMATIVE`
* CTA-608-E B.11.4 p.68 - `RECOMMENDED`

### P05 - More than four rows

*Starts 03:44.00, lasts 6 s, channels: CC1, CC3*

**Purpose.** The FCC requires four simultaneous rows; a fifth is assumed to be an error. Decoders should never discard data and should replace earlier rows with newer ones. The exact display is implementation-defined; this card documents what each renderer does.

**Test.** pop-on with five rows (error condition).

**Expected.** no crash or lost caption; as much text as possible, newer rows preferred over older (exact result varies)

**References.**

* CTA-608-E C.6 p.73 - `PREFERRED`
* CTA-608-E C.5 p.72 - `REGULATORY`

## Roll-up style

### R01 - Roll-up 3 rows, base row 15

*Starts 03:50.00, lasts 13 s, channels: CC1, CC3*

**Purpose.** Standard live-caption roll-up. Checks row depth, row discard order and (preferred) a smooth scroll lasting 0.20-0.433 s with characters visible during the scroll.

**Test.** RU3 + CR + PAC per row.

**Expected.** max 3 rows, scrolling up (0.20-0.433 s smooth scroll preferred) as lines arrive

**References.**

* CTA-608-E B.8.1 p.65 - `RECOMMENDED`
* CTA-608-E C.3 p.71-72 - `PREFERRED`

### R02 - Roll-up 4 rows, base row 15

*Starts 04:03.00, lasts 13 s, channels: CC1, CC3*

**Purpose.** Four rows is the FCC maximum simultaneous caption depth.

**Test.** RU4.

**Expected.** max 4 rows visible

**References.**

* CTA-608-E B.8.1 p.65 - `RECOMMENDED`
* CTA-608-E C.5 p.72 - `REGULATORY`

### R03 - Roll-up 2 rows, base row 15

*Starts 04:16.00, lasts 11 s, channels: CC1, CC3*

**Purpose.** Two-row roll-up.

**Test.** RU2.

**Expected.** max 2 rows visible

**References.**

* CTA-608-E B.8.1 p.65 - `RECOMMENDED`

### R04 - Roll-up with per-row indents

*Starts 04:27.00, lasts 13 s, channels: CC1, CC3*

**Purpose.** The indent of each rolled row comes from that row's PAC.

**Test.** PAC indent 0..16 on each new row.

**Expected.** each row indented 4 more columns than the previous

**References.**

* CTA-608-E B.8.1 p.65 - `RECOMMENDED`
* CTA-608-E C.7 p.73 - `REGULATORY/PREFERRED`

### R05 - Roll-up with per-row styles

*Starts 04:40.00, lasts 13 s, channels: CC1, CC3*

**Purpose.** Per-row attributes in roll-up come from each row's PAC.

**Test.** PAC color / italic / underline per row.

**Expected.** yellow underlined / white italics / magenta / white italics underlined

**References.**

* CTA-608-E B.8.1 p.65 - `RECOMMENDED`
* CTA-608-E F.1.1.5 Table 53 p.101 - `REGULATORY`

### R06 - Roll-up base row 5 (RU3)

*Starts 04:53.00, lasts 11 s, channels: CC1, CC3*

**Purpose.** Movable base row (a 1991 FCC addition; mid-screen base rows are not recognized by TeleCaption I/II).

**Test.** base row selected by PAC row 5.

**Expected.** text occupies rows 3-5 (upper part of the screen)

**References.**

* CTA-608-E B.5 p.63 - `RECOMMENDED`
* CTA-608-E F.1.1.5 Table 53 p.101 - `REGULATORY`

### R07 - PAC moves a displayed roll-up

*Starts 05:04.00, lasts 12 s, channels: CC1, CC3*

**Purpose.** Receiving a PAC for a different base row during roll-up moves the display immediately. (A PAC for the same base row only repositions the cursor.)

**Test.** PAC with a different base row during roll-up.

**Expected.** three rows at base 15, then the block jumps to base row 8 at +6 s and continues there

**References.**

* CTA-608-E C.7 p.73 - `REGULATORY`
* CTA-608-E B.8.1 p.65 - `RECOMMENDED`

### R08 - Roll-up depth vs base-row conflict

*Starts 05:16.00, lasts 9 s, channels: CC1, CC3*

**Purpose.** A 3-row roll-up cannot fit above base row 2. The FCC lets decoders choose depth or base row; 608-E recommends depth so no text is lost. Documents the choice each renderer makes.

**Test.** RU3 then PAC for row 2 (error condition).

**Expected.** preferred: depth wins, all 3 rows kept (base moves to row 3); alternative: rows above row 1 lost

**References.**

* CTA-608-E C.4 p.72 - `PREFERRED`
* CTA-608-E B.5 p.63-64 - `RECOMMENDED`

### R09 - Default base row

*Starts 05:25.00, lasts 5 s, channels: CC1, CC3*

**Purpose.** With no PAC the roll-up base row defaults to row 15 and the cursor to column 1.

**Test.** RU3 then text with no PAC.

**Expected.** text appears on row 15 at column 1

**References.**

* CTA-608-E C.15 p.75 - `PREFERRED`

### R10 - Roll-up depth change RU3 to RU2

*Starts 05:30.00, lasts 13 s, channels: CC1, CC3*

**Purpose.** Informational: reducing depth mid-caption. Neither document states the exact result; this card records renderer behavior (most keep the last two rows).

**Test.** RU3 rows, then RU2 + CR.

**Expected.** final: two rows 'the caption has been' / 'displayed, like this.'

**References.**

* 608-E Annex C silent on resulting display - `UNSPECIFIED`

### R11 - Three CRs = two rolls

*Starts 05:43.00, lasts 7 s, channels: CC1, CC3*

**Purpose.** Redundant-pair handling: of three identical consecutive control pairs, the second is a redundant copy of the first, so three CRs yield two carriage returns.

**Test.** CR CR CR (three identical consecutive pairs) between two rows.

**Expected.** A is two rows above B (one blank row between)

**References.**

* CTA-608-E B.14 p.70 - `RECOMMENDED`
* CTA-608-E D.2 p.78 - `NORMATIVE/REGULATORY`

## Paint-on style and editing commands

### D01 - Paint-on: basic and mid-row

*Starts 05:50.00, lasts 11 s, channels: CC1, CC3*

**Purpose.** Paint-on writes directly to the display as bytes arrive (sent slowly here so the progression is visible).

**Test.** RDC, text painted as received.

**Expected.** characters appear progressively; 'paint-on' cyan, 'include' blue, 'mid-row' italic underlined

**References.**

* CTA-608-E B.7 p.64 - `RECOMMENDED`
* CTA-608-E B.8.2 p.65 - `RECOMMENDED`

### D02 - RDC leaves a roll-up in place

*Starts 06:01.00, lasts 9 s, channels: CC1, CC3*

**Purpose.** RDC selects paint-on and has no other effect: displayed roll-up captions are untouched and the four-row limit still applies.

**Test.** RDC while a roll-up is displayed.

**Expected.** roll-up rows stay; painted text appears on row 8 above them

**References.**

* CTA-608-E C.10 p.74 - `REGULATORY`
* CTA-608-E B.7 p.64 - `RECOMMENDED`

### D03 - RCL leaves a displayed roll-up alone

*Starts 06:10.00, lasts 11 s, channels: CC1, CC3*

**Purpose.** RCL has no effect on a displayed roll-up; the next data goes to non-displayed memory. The EOC flips memories and the roll-up moves to non-displayed memory.

**Test.** RCL + hidden load, then EOC.

**Expected.** roll-up stays; hidden text invisible until EOC at +6 s, when it replaces the roll-up

**References.**

* CTA-608-E C.10 p.74 - `REGULATORY`
* CTA-608-E C.11 p.74 - `REGULATORY`

### D04 - Backspace (BS)

*Starts 06:21.00, lasts 9 s, channels: CC1, CC3*

**Purpose.** BS erases the character to the left and moves the cursor back one column.

**Test.** BS 0x14 0x21 (a single BS; repeated-command handling is card D09).

**Expected.** final row: 'Backspace: Right' (a trailing '!' is typed, then erased by BS)

**References.**

* CTA-608-E B.12 p.69 - `RECOMMENDED`

### D05 - Delete to end of row (DER)

*Starts 06:30.00, lasts 9 s, channels: CC1, CC3*

**Purpose.** DER deletes from the cursor to the end of the row.

**Test.** DER at mid-row.

**Expected.** final row: 'DER keeps this part:' (REMOVE ME is erased at +5 s)

**References.**

* CTA-608-E B.3 p.62 - `RECOMMENDED`
* CTA-608-E C.14 p.75 - `NORMATIVE`

### D06 - DER at column 1 frees a row

*Starts 06:39.00, lasts 10 s, channels: CC1, CC3*

**Purpose.** DER at column 1 erases the row AND de-allocates its memory, the only way to send a fifth row without erasing the screen. 608-E states all decoders shall implement this.

**Test.** 4 rows painted, DER row A, paint a 5th row.

**Expected.** A is erased; B, C, D and E (five rows sent, four visible at a time) all remain

**References.**

* CTA-608-E C.5 p.72-73 - `REGULATORY`
* CTA-608-E B.3 p.62 - `RECOMMENDED`

### D07 - Pop-on then paint-on

*Starts 06:49.00, lasts 9 s, channels: CC1, CC3*

**Purpose.** Paint-on adds to whatever is displayed.

**Test.** RDC does not erase a displayed pop-on.

**Expected.** row 13 pop-on text stays; row 14 painted below

**References.**

* CTA-608-E C.10 p.74 - `REGULATORY`

### D08 - Roll-up erases pop-on in both memories; EOC swaps roll-up

*Starts 06:58.00, lasts 16 s, channels: CC1, CC3*

**Purpose.** Roll-up commands must erase pop-on/paint-on data in EITHER memory. An EOC while roll-up is selected swaps the whole roll-up caption into non-displayed memory (screen goes blank, since B was erased) and a second EOC brings it back in the same row order.

**Test.** pop-on A shown + B hidden; RU2 at +4 s; EOC at +8 s; EOC again at +11 s.

**Expected.** 0-4s A | 4-8s roll-up only (A and hidden B erased) | 8-11s BLANK | 11s+ roll-up returns

**References.**

* CTA-608-E C.10 p.74 - `REGULATORY`
* CTA-608-E C.11 p.74 - `REGULATORY`

### D09 - Redundant control pairs vs repeated commands

*Starts 07:14.00, lasts 10 s, channels: CC1, CC3*

**Purpose.** A control code repeated in the very next frame is a redundant copy and must act once; the same code separated by a null frame is a new command. (10-A notes inserting a null can change interpretation of adjacent repeated codes.) Field 1 sends doubled pairs; field 2 sends single (B.14), so CC3 exercises the single-code path.

**Test.** BS BS (adjacent) vs BS, null, BS.

**Expected.** ABCDEF -> BS pair -> ABCDE -> G -> ABCDEG -> BS null BS -> ABCD -> H -> ABCDH

**References.**

* CTA-608-E D.2 p.78 - `NORMATIVE/REGULATORY`
* CEA-CEB-10-A 25.2.4 p.41 - `10A-RECOMMENDATION`

## Signal, timing and channels

### S01 - Caption sync to video flash

*Starts 07:24.00, lasts 8 s, channels: CC1, CC3*

**Purpose.** Decoders shall act within one video frame of the code pair (C.12). Each white flash is exactly the picture carrying the first EOC. 10-A recommends total decode delay no more than two frames.

**Test.** first EOC lands on the flash picture; 6 flashes 1 s apart.

**Expected.** 'NOW n' appears on the flash picture or the next one (within one NTSC frame)

**References.**

* CTA-608-E C.12 p.74-75 - `REGULATORY`
* CTA-608-E B.11.2 p.68 - `RECOMMENDED`
* CEA-CEB-10-A 17.2.3 p.33 - `10A-RECOMMENDATION`

*720p59 (16:9) differs:* **Expected.** 'NOW n' (CC1) appears on the flash picture or the next one; CC3 one picture later (<= 2 pictures = 1 NTSC frame) **Purpose.** Decoders shall act within one video frame of the code pair (C.12); at 59.94 fps a line-21 frame is two pictures. Each white flash is exactly the picture carrying the first EOC of the CC1 pair (CC3's pair rides the next picture). 10-A recommends total decode delay no more than two frames (four pictures).

*480i59 (4:3) differs:* **Expected.** 'NOW n' appears on the flash picture or the next one (<= 1 frame); CC1 and CC3 are in the same picture **Purpose.** Decoders shall act within one video frame of the code pair (C.12). The picture is an interlaced frame carrying both field pairs, and each white flash is exactly the frame carrying the first EOC of CC1 and CC3. 10-A recommends total decode delay no more than two frames.

### S02 - Caption persists on valid nulls

*Starts 07:32.00, lasts 22 s, channels: CC1, CC3*

**Purpose.** Nulls are valid caption data and mean 'hold'. A decoder implementing automatic erasure must wait at least 16 s (608-E). 10-A notes this contrasts with loss of waveform, which erases (card S03).

**Test.** caption shown, then 20 s of valid null pairs.

**Expected.** caption must stay for at least 16 s (erase at +20 s by explicit EDM)

**References.**

* CTA-608-E C.9 p.74 - `PREFERRED`
* CTA-608-E D.4 p.78-79 - `INFORMATIVE`
* CEA-CEB-10-A 25.2.1 p.39-40 - `10A-RECOMMENDATION`
* CEA-CEB-10-A 31 p.51 - `10A-RECOMMENDATION (708 only)`

### S03 - Loss of data erases captions; recovery

*Starts 07:54.00, lasts 14 s, channels: CC1, CC3*

**Purpose.** 608-E C.21: after 45 consecutive frames without valid data a decoder shall disable display and erase memory; on resumption it enables after 12-18 valid frames and displays the data received while counting. 10-A clarifies cc_valid=0 means 'no waveform' (decoder erases) as distinct from nulls (hold).

**Test.** cc_valid=0 for 3 s (no waveform), then a new caption.

**Expected.** A shown 0-3 s; erased after 45 frames (about 1.5 s) of no data; B appears at +8 s; A never returns

**References.**

* CTA-608-E C.21 p.76-77 - `REGULATORY`
* CEA-CEB-10-A 25.2.1 p.39-40 - `10A-RECOMMENDATION`
* CEA-CEB-10-A 20.2.4 p.35 - `10A-RECOMMENDATION`

### S04 - Field 2 loss only

*Starts 08:08.00, lasts 12 s, channels: CC1, CC3*

**Purpose.** Each field is evaluated independently; field 1 must remain valid whenever field 2 carries data (D.7).

**Test.** cc_valid=0 on field 2 for 3 s; field 1 continues.

**Expected.** CC1 caption stays; CC3 caption erased after 45 frames (check CC3 if your renderer offers it)

**References.**

* CTA-608-E C.21 p.76-77 - `REGULATORY`
* CTA-608-E D.7 p.79 - `REGULATORY/INFORMATIVE`
* CEA-CEB-10-A 20.2.4 p.35 - `10A-RECOMMENDATION`

### S05 - Invalid (even) parity data

*Starts 08:20.00, lasts 12 s, channels: CC1, CC3*

**Purpose.** Data bytes failing odd parity count as 'no valid data' toward the 45-frame disable rule.

**Test.** 60 frames of zero-filled even-parity data on the waveform.

**Expected.** caption erased like a loss of valid data; later caption displays normally

**References.**

* CTA-608-E C.21 p.76-77 - `REGULATORY`
* CEA-CEB-10-A A.1.1 p.52 - `INFORMATIVE`

### H01 - Channel isolation CC1 / CC2 / CC3 / CC4

*Starts 08:32.00, lasts 11 s, channels: CC1-CC4*

**Purpose.** Four independent caption services. Field 2 uses 0x15/0x1D in miscellaneous control codes (B.11.6). CC2 and CC4 deliver their test line inside their regular 2-second label refresh. 10-A recommends decoders let the viewer select CC1-CC4 even without a caption_service_descriptor (build with --no-caption-descriptor for that variant).

**Test.** field 1 ch 1/2, field 2 ch 1/2 (field 2 uses 0x15/0x1D).

**Expected.** each service shows only its own line: CC1 row 4, CC2 row 6, CC3 row 9, CC4 row 11 (plus its 'Rendering on' label)

**References.**

* CTA-608-E B.11.6 p.69 - `REGULATORY`
* CTA-608-E C.18 p.76 - `INFORMATIVE`
* CEA-CEB-10-A 23.2.2 p.37 - `10A-RECOMMENDATION`

### Z99 - End of test

*Starts 08:43.00, lasts 5 s, channels: CC1, CC3*

**Purpose.** Marks the end of the stream and clears the screen.

**Test.** end of stream.

**Expected.** centered end message, then blank

