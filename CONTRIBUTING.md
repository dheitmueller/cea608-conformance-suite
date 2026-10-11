# Contributing

## Notice

The materials herein are provided with no warranty, expressed or implied.  They are distributed under open licenses with the hope that they are helpful both in commercial and non-commercial applications.  The test streams and documentation may be redistributed under the terms of the Creative Commons "BY-SA (Attribution-ShareAlike)" license, and the source code that generates them under the GNU General Public License version 2 or later (see the License section of the README).

The license aside, I would kindly ask the following:

* If you find bugs or make improvements, I would encourage you to submit them back to me for inclusion in the original project.  This is not a formal requirement, but minimizing fragmentation is in everyone's interest.
* If you create a derivative work, please make it prominent in the video (e.g. burn additional text into the video) that this is your specific variation of the test pattern, to avoid confusion.  I would also ask that you make the version numbers unique other than simply increasing the version number (e.g. changing "1.1" to "vendorXYZ v1.2", rather than changing it to "1.2").  This will hopefully help avoid confusion when I inevitably release updated versions.

## Reporting a problem

When you open an issue, it helps to include:

* the **card ID** (for example `D05`) and what you expected versus what you saw,
* the **stream** you used (version label, 720p59 or 480i59, H.264 or MPEG-2),
* the **player or decoder** and its version, and the **caption channel** you selected,
* a screenshot or short capture of the failing card if you can.

If you think an expected result is wrong, please cite the section and page of the specification
(CTA-608-E or CEA-CEB-10-A) that you read differently. The expected results are my reading of those
documents, and corrections are welcome.

## Sending changes

By submitting a change you agree that your code is licensed under the GNU GPL version 2 or later (as the rest of the
code is), and that the documents and streams generated from your changes may be distributed under CC BY-SA 4.0.

Build and test instructions, and how to add or change test cards, are in [DEVELOPING.md](DEVELOPING.md).
Before opening a pull request:

* rebuild and commit the regenerated `TESTS.md` with any change to `testplan.py` (the release
  workflow refuses to publish if they are out of date),
* check that the decoded captions still match what each card says (see "Checking a build" in DEVELOPING.md),
* describe what changed and, for a changed expectation, cite the specification section and page.

## Version labels and tags

The version burned into the picture comes from git: the **tag** if `HEAD` is tagged, otherwise the short
revision, with `+dirty` appended if the working tree has local changes.

For a **derivative stream**:

1. Tag your own repository with a label that is clearly yours (for example `vendorXYZ-v1.2`, not `v1.2`).
2. Rebuild, and check that the label shows in the bottom-right corner of every card.
3. Add your own text to the title card (see `build.py`) so it is prominent that this is your variation.

Tags of the form `vMAJOR.MINOR` are reserved for official releases of this project.

## Making a release (maintainers)

Releases are built by GitHub Actions (`.github/workflows/release.yml`):

```bash
git tag v1.1
git push origin v1.1          # the tag push starts the workflow
```

The workflow checks out the tag, installs ffmpeg and Python, builds **both formats** (H.264) so the picture
carries the tag, checks that `TESTS.md` matches the committed copy, and creates a GitHub
Release named after the tag. The release contains only what a user of the streams needs: the two `.ts`
files, `TESTS.md`, `LICENSE-CC-BY-SA-4.0.txt` (the license of the streams and documentation) and `SHA256SUMS`.

It can also be started by hand (Actions tab, "Run workflow"): that builds the streams and keeps them as workflow
artifacts for 14 days without making a release; the version label of such a build is the short revision.

The Action builds on Ubuntu with the distribution's ffmpeg and DejaVu fonts, so the picture's typeface differs
slightly from a macOS build. After a release, replace the README screenshot if the layout changed.
