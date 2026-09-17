# First batch of `factory-ready` issues

File these against this repo in order. #1–#3 are the scaffold; after those merge, #4–#10
can run in parallel.

## Issue 1 — Project scaffold and CLI skeleton
Already partially in place. Verify: `pip install -e .[dev]`, `scrubmeta --help`,
first-run ack flow with `XDG_CONFIG_HOME` overridden. Confirm ruff, mypy, pytest pass.

## Issue 2 — Round-trip test harness
Already scaffolded in `tests/roundtrip.py` with a dummy PNG fixture that skips-if-unimplemented.
This issue is: remove the skip-if-unimplemented behavior once #4 lands, and confirm the
harness fails on a synthetic broken output.

## Issue 3 — Randomized-metadata generator
Already scaffolded in `src/scrubmeta/randomize.py` with tests. This issue: extend to emit
container-specific formats (EXIF ASCII date, ISO 8601, QuickTime date) rather than raw datetime.

## Issue 4 — JPEG/TIFF EXIF stripping and rewrite  (depends on 1–3)
Implement `src/scrubmeta/formats/jpeg.py` with `piexif` + `Pillow`. Strip EXIF/XMP/IPTC/ICC;
write back randomized values. Pixel bytes identical. Add a JPEG-with-GPS fixture.

## Issue 5 — PNG text-chunk stripping  (depends on 1–3)
Strip tEXt/iTXt/zTXt/eXIf/tIME. Rewrite with new minimal tEXt. IDAT byte-identical.
Add PNG fixture with `Software` and `eXIf`.

## Issue 6 — HEIC/HEIF handling  (depends on 1–3)
Handle via `pyheif` or exiftool shell-out. Strip EXIF/XMP boxes. Live Photo pairing key:
both preserved or both stripped, never mismatched.

## Issue 7 — MP4/MOV container rewrite (stream copy)  (depends on 1–3)
`ffmpeg -map_metadata -1 -c copy` plus a follow-up write of new udta tags. Extracted raw
stream hash must match source. No re-encoding.

## Issue 8 — MKV/WebM Matroska tag rewrite  (depends on 1–3)
Same as #7 for Matroska. Strip Tags element, write new ones.

## Issue 9 — C2PA preservation guard  (depends on 4, 5, 7)
Detect C2PA manifests in JPEG/PNG/MP4. Default: preserve. `--strip-provenance` refused
without `--i-own-this-content`. Log to `~/.local/state/scrubmeta/provenance.log`.

## Issue 10 — Docs + first-run notice hardening  (depends on 1)
Round out README, threat model, and confirm first-run ack shows intended-use verbatim.

## Filing them with gh

```bash
gh issue create --title "Project scaffold and CLI skeleton" --body-file <(sed -n '/^## Issue 1/,/^## Issue 2/p' ISSUES.md) --label factory-ready
# ... etc
```
