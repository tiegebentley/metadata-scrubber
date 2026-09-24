# scrubmeta

A local CLI and Python library that strips embedded metadata from images and
videos and writes out a new file with fresh, plausible, randomized metadata.

## Intended use

This tool exists for **personal privacy on files you own**: stripping GPS and
device fingerprints from photos before posting them, sanitizing home-video
metadata before sending to family, removing "Edited in <software>" tags from
personal creative work, and similar.

It is **not** built for evading platform moderation, trust-and-safety systems,
content-provenance standards (C2PA, IPTC-origin, watermarks), defeating
copyright detection, or concealing the origin of media in harassment, fraud,
non-consensual intimate imagery, CSAM, or any other illegal use.

See [`factory/MISSION.md`](factory/MISSION.md) for the full scope this
project's autonomous factory operates under.

## Install

```bash
pip install -e .[dev]
```

System dependencies: `exiftool`, `ffmpeg` (includes `ffprobe`), and optionally
ImageMagick (`magick`) for higher-fidelity pixel hashing in the round-trip
tests.

## Running on the VPS (HTTPS via Tailscale)

Both services bind to loopback; `tailscale serve` terminates TLS with a real
Let's Encrypt certificate for the machine's MagicDNS name and forwards to them.
Only devices on the tailnet can reach either.

    tailscale serve --bg --https=3443 http://127.0.0.1:3000   # UI
    tailscale serve --bg --https=8443 http://127.0.0.1:8770   # API

- UI:  https://ubuntu-16gb-ash-1.tail9b86f6.ts.net:3443
- API: https://ubuntu-16gb-ash-1.tail9b86f6.ts.net:8443

The API origin is baked into the UI bundle from `web/.env.production` at
`next build`; the API's allowed browser origin is set by `SCRUBMETA_CORS_ORIGINS`
in `deploy/scrubmeta-api.service`. Change either and rebuild/restart.
Port 443 is deliberately not used: Apache already owns it on this host.

Browser-level check after any UI change:

    CHROMIUM_PATH=... python3 deploy/e2e_review_copies.py https://<host>:3443 /path/video.mp4

## Usage

```bash
scrubmeta path/to/photo.jpg               # writes photo.scrubbed.jpg
scrubmeta path/to/video.mp4 -o clean.mp4
```

On first run, you'll be asked to type `I own this content` to acknowledge the
intended-use scope. This is recorded at `~/.config/scrubmeta/ack` and not
asked again on that machine.

## What it does NOT protect against

See [`docs/threat-model.md`](docs/threat-model.md). Briefly:

- Perceptual hashes on the pixels/audio themselves (pHash, PhotoDNA, Content
  ID). Scrubmeta touches metadata only.
- Filesystem timestamps on the containing directory.
- Watermarks encoded into the pixels.
- Network-level identifiers when you upload the file.
- C2PA content-credential manifests — these are **preserved by default**.
  Overriding requires two explicit flags and is logged locally.

## How this repo is built

The `factory/` directory is a copy of the AI Software Factory harness
configured for this project. Labeling a GitHub issue `factory-ready` triggers
the harness to implement the change in an isolated worktree, validate it,
and open a PR. See `factory/MISSION.md` and `ISSUES.md` for the initial
backlog.
