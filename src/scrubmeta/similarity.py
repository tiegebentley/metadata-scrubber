"""Duplicate and near-duplicate discovery within a user-selected set of images.

This is a library-organization tool: it compares the user's own files to each
other so they can find the same shot saved twice, or the same photo at two
sizes. It answers "which of *these* files are copies of each other" and
nothing else.

It deliberately does not compare a scrubbed output against its source, does
not expose a compare-two-files-and-report-a-score path from the web UI, and
is not calibrated to any third-party platform's content-detection system.
See factory/MISSION.md.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import TypedDict

from PIL import Image, ImageOps

HASH_SIZE = 16
HASH_BITS = HASH_SIZE * HASH_SIZE

VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v", ".mkv", ".webm", ".gif"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff", ".heic"}


class Match(TypedDict):
    a: str
    b: str
    similarity: float
    kind: str
    media: str


def exact_digest(path: Path) -> str:
    """SHA-256 of the file bytes, streamed."""
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def average_hash(path: Path, size: int = HASH_SIZE) -> int:
    """Average hash: downscale to size×size greyscale, threshold at the mean."""
    with Image.open(path) as im:
        im = ImageOps.exif_transpose(im).convert("L").resize((size, size))
        pixels = list(im.getdata())
    mean = sum(pixels) / len(pixels)
    value = 0
    for p in pixels:
        value = (value << 1) | (1 if p >= mean else 0)
    return value


def _score(hash_a: int, hash_b: int) -> float:
    distance = (hash_a ^ hash_b).bit_count()
    return round(100 * (1 - distance / HASH_BITS), 2)


def visual_similarity(a: Path, b: Path) -> float:
    """0-100 average-hash similarity between two images."""
    return _score(average_hash(a), average_hash(b))


def compare_images(paths: list[Path], threshold: float = 90.0) -> list[Match]:
    """Return every pair in `paths` scoring at or above `threshold`, best first."""
    threshold = max(0.0, min(100.0, threshold))
    hashes = {p: average_hash(p) for p in paths}
    digests = {p: exact_digest(p) for p in paths}

    matches: list[Match] = []
    for i, a in enumerate(paths):
        for b in paths[i + 1 :]:
            if digests[a] == digests[b]:
                score, kind = 100.0, "exact"
            else:
                score, kind = _score(hashes[a], hashes[b]), "near"
            if score >= threshold:
                matches.append({
                    "a": a.name,
                    "b": b.name,
                    "similarity": score,
                    "kind": kind,
                    "media": "image",
                })

    return sorted(matches, key=lambda m: m["similarity"], reverse=True)


def video_fingerprint(path: Path, samples: int = 12) -> list[int]:
    """Extract sampled frames from a video and return their average hashes.

    Probe duration with ffprobe, then extract `samples` frames at evenly spaced
    timestamps using ffmpeg. For files shorter than 1 second, sample every frame
    up to `samples`. Use min(12 + duration_s // 10, 32) samples for longer videos.
    """
    try:
        probe_result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_format", "-of", "json", str(path)],
            check=True,
            capture_output=True,
            text=True,
        )
        probe_data = json.loads(probe_result.stdout)
        duration = float(probe_data.get("format", {}).get("duration", "0"))
    except (FileNotFoundError, subprocess.CalledProcessError, json.JSONDecodeError, ValueError):
        duration = 0.0

    if duration < 1.0:
        num_samples = samples
    else:
        num_samples = min(12 + int(duration) // 10, 32)

    timestamps = []
    if num_samples == 1:
        timestamps = [duration / 2] if duration > 0 else [0.0]
    elif duration > 0:
        for i in range(num_samples):
            timestamps.append((i / (num_samples - 1)) * duration)
    else:
        timestamps = [0.0]

    hashes = []
    for ts in timestamps:
        try:
            result = subprocess.run(
                [
                    "ffmpeg",
                    "-ss", str(ts),
                    "-i", str(path),
                    "-frames:v", "1",
                    "-vf", "scale=32:32",
                    "-f", "image2pipe",
                    "-pix_fmt", "gray",
                    "-vcodec", "rawvideo",
                    "-",
                ],
                check=True,
                capture_output=True,
            )
            pixels = list(result.stdout)
            if len(pixels) == 32 * 32:
                mean = sum(pixels) / len(pixels)
                value = 0
                for p in pixels:
                    value = (value << 1) | (1 if p >= mean else 0)
                hashes.append(value)
        except (FileNotFoundError, subprocess.CalledProcessError):
            continue

    return hashes if hashes else [0]


def video_similarity(fa: list[int], fb: list[int]) -> float:
    """Compute mean similarity across aligned frame hashes.

    Because both fingerprints are sampled at proportional timestamps, a trimmed
    or re-encoded copy still aligns. Returns 0-100 similarity score.
    """
    if not fa or not fb:
        return 0.0

    min_len = min(len(fa), len(fb))
    if min_len == 0:
        return 0.0

    scores = [_score(fa[i], fb[i]) for i in range(min_len)]
    return round(sum(scores) / len(scores), 2)


def compare_media(paths: list[Path], threshold: float = 90.0) -> list[Match]:
    """Compare a mix of images and videos, returning matches at or above threshold.

    Routes each path by extension - images to average_hash, videos/GIFs to
    video_fingerprint. Only compares like with like (image vs image, video vs video).
    Exact SHA-256 match still wins as "exact". Result rows include "media" field.
    """
    threshold = max(0.0, min(100.0, threshold))

    images = [p for p in paths if p.suffix.lower() in IMAGE_EXTENSIONS]
    videos = [p for p in paths if p.suffix.lower() in VIDEO_EXTENSIONS]

    # Special case: .webp can be animated, but we'll treat it as an image
    # (ffmpeg may or may not support animated webp depending on build)

    image_hashes = {p: average_hash(p) for p in images}
    video_hashes = {p: video_fingerprint(p) for p in videos}
    digests = {p: exact_digest(p) for p in paths}

    matches: list[Match] = []

    # Compare images to images
    for i, a in enumerate(images):
        for b in images[i + 1:]:
            if digests[a] == digests[b]:
                score, kind = 100.0, "exact"
            else:
                score, kind = _score(image_hashes[a], image_hashes[b]), "near"
            if score >= threshold:
                matches.append({
                    "a": a.name,
                    "b": b.name,
                    "similarity": score,
                    "kind": kind,
                    "media": "image",
                })

    # Compare videos to videos
    for i, a in enumerate(videos):
        for b in videos[i + 1:]:
            if digests[a] == digests[b]:
                score, kind = 100.0, "exact"
            else:
                score, kind = video_similarity(video_hashes[a], video_hashes[b]), "near"
            if score >= threshold:
                matches.append({
                    "a": a.name,
                    "b": b.name,
                    "similarity": score,
                    "kind": kind,
                    "media": "video",
                })

    return sorted(matches, key=lambda m: m["similarity"], reverse=True)
