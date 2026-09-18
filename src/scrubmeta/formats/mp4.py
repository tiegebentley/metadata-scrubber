"""MP4/MOV/M4V scrub handler. Uses ffmpeg for stream copy (no re-encoding)."""

from __future__ import annotations

import hashlib
import subprocess
import tempfile
from pathlib import Path

from ..randomize import Replacement


def scrub(src: Path, dst: Path, replacement: Replacement) -> None:
    """Strip all metadata from MP4/MOV, write replacement tags, preserve streams.

    Uses a two-pass approach:
    1. Strip all container metadata with ffmpeg -map_metadata -1 -c copy
    2. Write replacement metadata tags to the moov/udta atoms

    Verifies pixel/audio stream integrity by comparing hashes of raw demuxed streams.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        stripped = tmp / "stripped.mp4"

        # Pass 1: Strip all container metadata without re-encoding
        strip_cmd = [
            "ffmpeg", "-y", "-v", "error", "-i", str(src),
            "-map_metadata", "-1",  # Drop all metadata
            "-c", "copy",            # Stream copy (no re-encoding)
            str(stripped),
        ]
        result = subprocess.run(strip_cmd, capture_output=True)
        if result.returncode != 0:
            raise RuntimeError(
                f"ffmpeg metadata strip failed: {result.stderr.decode(errors='replace')[:400]}"
            )

        # Capture source stream hash before metadata injection
        src_hash = _stream_hash(stripped)

        # Pass 2: Write replacement metadata
        # QuickTime/MP4 metadata fields:
        # - creation_time: ISO 8601 datetime
        # - make: camera manufacturer
        # - model: camera model
        # - location: GPS in ISO 6709 format (+DD.DDDD-DDD.DDDD/)
        metadata_args = [
            "-metadata", f"creation_time={replacement.quicktime_datetime()}",
            "-metadata", f"make={replacement.make}",
            "-metadata", f"model={replacement.model}",
        ]

        # Add GPS if provided (ISO 6709 format: +lat-lon/)
        if replacement.gps is not None:
            lat, lon = replacement.gps
            # Format: +latitude-longitude/ with signs
            location = f"{lat:+.4f}{lon:+.4f}/"
            metadata_args.extend(["-metadata", f"location={location}"])

        inject_cmd = [
            "ffmpeg", "-y", "-v", "error", "-i", str(stripped),
            *metadata_args,
            "-c", "copy",  # Stream copy preserves the stripped streams
            "-movflags", "use_metadata_tags",  # Write metadata to moov/udta atoms
            str(dst),
        ]
        result = subprocess.run(inject_cmd, capture_output=True)
        if result.returncode != 0:
            raise RuntimeError(
                f"ffmpeg metadata injection failed: {result.stderr.decode(errors='replace')[:400]}"
            )

        # Verify stream integrity: hash the output's raw streams
        dst_hash = _stream_hash(dst)

        if src_hash != dst_hash:
            raise RuntimeError(
                f"Stream data changed during MP4 scrub: {src.name} "
                f"(stripped: {src_hash[:12]}, output: {dst_hash[:12]}). "
                "This indicates re-encoding occurred."
            )


def _stream_hash(path: Path) -> str:
    """Hash all demuxed streams (video + audio) without metadata or container overhead.

    Uses NUT container format (-f nut) which is metadata-free and deterministic for
    stream-copy operations. This ensures we're comparing raw codec packets only.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        raw = Path(tmpdir) / "raw.nut"
        cmd = [
            "ffmpeg", "-y", "-v", "error", "-i", str(path),
            "-map", "0",             # Include all streams
            "-map_metadata", "-1",   # Strip metadata
            "-c", "copy",            # Stream copy
            "-f", "nut",             # NUT container (deterministic, metadata-free)
            str(raw),
        ]
        result = subprocess.run(cmd, capture_output=True)
        if result.returncode != 0:
            raise RuntimeError(
                f"ffmpeg stream extraction failed: {result.stderr.decode(errors='replace')[:400]}"
            )
        return hashlib.sha256(raw.read_bytes()).hexdigest()
