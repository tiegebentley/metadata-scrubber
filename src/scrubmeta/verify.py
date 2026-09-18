"""
Verification report builder for scrubmeta.

Compares source and scrubbed files using exiftool/ffprobe/ffmpeg (independent
third-party tools) to confirm:
1. Pixel/audio streams are byte-identical (decoded SHA-256)
2. Metadata was removed, replaced, or kept (structural only)
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

from ._probe import STRUCTURAL_TAGS, snapshot_metadata, stream_hash


@dataclass
class VerificationReport:
    """Verification report confirming scrub results without exposing original metadata values."""

    pixel_identical: bool  # decoded pixel/audio stream SHA-256 match
    stream_hash_algo: str  # "sha256-decoded-pixels" or "sha256-decoded-av"
    metadata_removed: int  # tags present in source, absent in output
    metadata_replaced: int  # tags present in both, different values
    metadata_kept_structural: int  # tags present in both, same value AND in STRUCTURAL_TAGS
    removed_tags: list[str]  # tag names only (no values)
    replaced_tags: list[str]  # tag names only (no values)
    warnings: list[str]  # e.g. "C2PA manifest preserved", "lossy rewrite required"

    def to_dict(self) -> dict[str, object]:
        """Serialize to JSON-compatible dict."""
        return asdict(self)


def build_report(src: Path, dst: Path, kind: Literal["image", "video"]) -> VerificationReport:
    """Build verification report by comparing source and scrubbed files.

    Args:
        src: Source file path
        dst: Scrubbed output file path
        kind: "image" or "video"

    Returns:
        VerificationReport with counts, tag names (no values), and warnings
    """
    # Hash decoded streams
    src_hash = stream_hash(src, kind)
    dst_hash = stream_hash(dst, kind)
    pixel_identical = src_hash == dst_hash

    # Determine algorithm name for report
    stream_hash_algo = "sha256-decoded-pixels" if kind == "image" else "sha256-decoded-av"

    # Snapshot metadata from both files
    src_meta = snapshot_metadata(src, kind)
    dst_meta = snapshot_metadata(dst, kind)

    # Classify tags
    removed_tags: list[str] = []
    replaced_tags: list[str] = []
    kept_structural: int = 0

    for tag, src_val in src_meta.items():
        # Skip structural tags in diff (they're expected to be preserved or changed by codec)
        if tag in STRUCTURAL_TAGS:
            if tag in dst_meta and dst_meta[tag] == src_val:
                kept_structural += 1
            continue

        # Skip stream-level structural properties (streamN.* but not streamN.tags.*)
        if tag.startswith("stream") and "." in tag:
            parts = tag.split(".", 1)
            if len(parts) == 2 and parts[0].startswith("stream") and not parts[1].startswith("tags."):
                continue

        if tag not in dst_meta:
            removed_tags.append(tag)
        elif dst_meta[tag] != src_val:
            replaced_tags.append(tag)

    # Warnings
    warnings: list[str] = []
    if not pixel_identical:
        warnings.append("Lossy rewrite required (stream hash changed)")

    # Check for C2PA manifest preservation (not a failure, but worth flagging)
    # We don't import provenance.py here to avoid circular deps; just check for known JUMBF tags
    if any("jumbf" in tag.lower() or "c2pa" in tag.lower() for tag in dst_meta.keys()):
        warnings.append("C2PA manifest preserved (provenance data intact)")

    return VerificationReport(
        pixel_identical=pixel_identical,
        stream_hash_algo=stream_hash_algo,
        metadata_removed=len(removed_tags),
        metadata_replaced=len(replaced_tags),
        metadata_kept_structural=kept_structural,
        removed_tags=removed_tags,
        replaced_tags=replaced_tags,
        warnings=warnings,
    )
