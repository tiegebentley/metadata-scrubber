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
from pathlib import Path
from typing import TypedDict

from PIL import Image, ImageOps

HASH_SIZE = 16
HASH_BITS = HASH_SIZE * HASH_SIZE


class Match(TypedDict):
    a: str
    b: str
    similarity: float
    kind: str


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
                matches.append({"a": a.name, "b": b.name, "similarity": score, "kind": kind})

    return sorted(matches, key=lambda m: m["similarity"], reverse=True)
