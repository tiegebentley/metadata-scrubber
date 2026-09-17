# Threat model

What scrubmeta protects against, and what it deliberately does not.

## In scope

- **Container-level tags:** EXIF, XMP, IPTC, ICC profiles, PNG text chunks,
  QuickTime `udta`, Matroska tags, ID3-in-MP4.
- **Common identifying fields:** camera make/model/serial, lens serial, GPS,
  original creation timestamps, edit-software fingerprints, thumbnail
  embedded copies.

## Out of scope (deliberately)

- **Perceptual hashes on the pixels/audio.** pHash, PhotoDNA, YouTube Content
  ID, TikTok/Instagram similarity systems, and Apple's on-device CSAM
  detection all operate on the media itself, not its metadata. Scrubmeta will
  not defeat them, and issues asking for that will be rejected — see
  `factory/MISSION.md`.
- **Watermarks in the pixels.** Visible or steganographic watermarks are
  pixel-level and untouched.
- **Filesystem metadata.** The mtime/ctime/atime of the file and its parent
  directory are outside the file itself and not covered.
- **Network-level identifiers.** IP, User-Agent, session cookies, and
  telemetry attached by the upload target are the upload's problem, not the
  file's.
- **C2PA / content credentials.** These are provenance data. The default
  behavior is to preserve them or fail loudly. Overriding requires
  `--strip-provenance --i-own-this-content` and is logged locally.

## Non-goals with a safety rationale

- **No device impersonation by default.** Replacement `Make`/`Model` fields
  are generic (`Generic` / `Camera`) so scrubbed files aren't accidentally
  laundered as coming from a specific real device. Explicit override exists
  but requires opt-in and prints a warning.
- **No batch modes over scraped datasets.** The tool takes one file at a
  time and prompts once for the intended-use acknowledgment.
- **No network calls.** The tool is fully offline at runtime.
