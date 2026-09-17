# Factory Mission — Metadata Scrubber

This file defines what the AI software factory is allowed to build and how it should behave
for the `metadata-scrubber` project. See also `factory/RULES.md` (workflow mechanics) and
`factory/CODE_STRUCTURE.md` (code style).

## What this factory builds

A local CLI + Python library (`scrubmeta`) that takes an image or video file the user owns,
strips all embedded metadata, and writes out a new file with fresh, plausible, randomized
metadata so the output does not carry identifying traces of the source (camera serial,
GPS, original creation time, editing-software fingerprints, container-level tags).

Supported inputs (v1 scope):
- Images: JPEG, PNG, HEIC, WebP, TIFF (EXIF / XMP / IPTC / ICC / PNG text chunks)
- Video: MP4, MOV, MKV, WebM (container tags via ffmpeg; QuickTime `udta`, Matroska tags,
  ID3 in MP4)

Out of scope for v1 (require a new issue + MISSION update to enable):
- Re-encoding video or images beyond what is required to drop metadata
  (prefer stream copy / lossless rewrite).
- Any modification of pixel or audio data intended to defeat perceptual hashing
  (pHash, PhotoDNA, Content ID, etc.).
- Batch scraping of files the user did not provide themselves.
- Cloud upload, sharing, or network calls of any kind at runtime — this tool is local-only.

## Intended use and ethical scope

This tool exists for **personal privacy on files the user owns**: stripping GPS and
device fingerprints from photos before posting them, sanitizing home-video metadata
before sending to family, removing "Edited in <software>" tags from personal creative
work, and similar.

It is **not** built for:
- Evading platform moderation, trust-and-safety systems, or content-provenance
  standards (C2PA, IPTC-origin, watermarks).
- Defeating copyright detection or laundering third-party content.
- Concealing the origin of media in harassment, fraud, non-consensual intimate
  imagery, CSAM, or any other illegal use.

Concretely this means:

- Every issue the factory works on must be consistent with the personal-privacy framing
  above. If an issue asks for a feature whose primary purpose is evasion of moderation,
  provenance, or copyright systems (e.g. "strip C2PA manifests by default", "randomize
  pixels enough to break pHash", "spoof camera signatures to match a specific real
  device", "bulk-process a scraped dataset"), the factory must escalate with
  `needs-human` and not implement it.
- The CLI must print a one-line notice on first run per machine
  (`~/.config/scrubmeta/ack`) stating the intended-use scope, and require the user to
  acknowledge before proceeding. The library API must expose the same notice as a
  docstring on the top-level entry point.
- The README's first section is "Intended use", quoting the scope above verbatim.
- The tool must never actively fake provenance: randomized replacement metadata is
  drawn from a generic pool (e.g. `Make=Generic`, `Model=Camera`, timestamps within a
  user-supplied window) — it must not impersonate a specific real device, person, or
  location unless the user passes explicit `--identity` flags, and even then it prints
  a warning.
- C2PA / content-credential manifests are treated as provenance data, not metadata:
  the default behavior is to **preserve** them or fail loudly, never silently strip
  them. A `--strip-provenance` flag may exist but must require `--i-own-this-content`
  alongside it and log the action.

## Guardrails (mechanical)

- Never touch files under `infra/secrets/` or any `.env*` file.
- Never modify CI/CD config (`.github/workflows/`) itself.
- Never force-push, delete branches other than its own, or modify `main` directly.
- All changes go through a PR — no direct commits to the default branch.
- No new runtime network calls. The tool is offline. Adding a dependency that phones
  home is an automatic escalation.
- No new dependencies that are themselves designed for moderation evasion or
  anti-forensics (e.g. libraries whose README describes defeating PhotoDNA / C2PA).
- Keep changes scoped to the issue. Don't refactor unrelated code.
- Every PR must include tests that round-trip a sample file and assert:
  (a) all known metadata fields from the source are absent in the output,
  (b) the new metadata is present and differs from the source, and
  (c) pixel/audio streams are byte-identical to the source (or, if a lossless
  rewrite was required, that a documented, reviewed exception applies).
- If a change requires a decision outside the issue's stated scope — especially
  anything touching the ethical-scope section above — stop and label the PR/issue
  `needs-human` with an explanation instead of guessing.

## Priority rules

1. Ethical scope over feature completeness. When in doubt, escalate.
2. Correctness and safety over speed.
3. Small, reviewable PRs over large ones. Split an issue into multiple PRs if needed.
4. Preserve pixel/audio fidelity by default; document any exception in the PR body.
