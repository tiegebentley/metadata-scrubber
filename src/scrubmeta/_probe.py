"""
Metadata probing and pixel-identity verification helpers.

Shared by both tests/roundtrip.py (independent harness) and src/scrubmeta/verify.py
(verification report builder). These functions shell out to exiftool/ffmpeg/ffprobe
rather than trusting scrubmeta's internal state.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

# Tags that describe file structure, not metadata. These are preserved or changed
# by encoding/container requirements, not by user choice.
STRUCTURAL_TAGS = frozenset({
    "FileName", "FileSize", "FileType", "FileTypeExtension", "MIMEType",
    "ImageWidth", "ImageHeight", "BitsPerSample", "ColorComponents",
    "EncodingProcess", "YCbCrSubSampling", "ExifByteOrder",
    "Directory", "FilePermissions", "FileModifyDate", "FileAccessDate",
    "FileInodeChangeDate", "ExifToolVersion", "SourceFile",
    "ImageSize", "Megapixels",  # exiftool computed fields (Composite group)
    "codec_name", "codec_type", "codec_tag_string", "codec_tag",
    "width", "height", "coded_width", "coded_height", "pix_fmt",
    "sample_fmt", "sample_rate", "channels", "channel_layout",
    "duration", "duration_ts", "nb_frames", "bit_rate", "time_base",
    "start_time", "start_pts", "r_frame_rate", "avg_frame_rate",
    "profile", "level", "refs", "is_avc", "nal_length_size",
    "format_name", "format_long_name", "nb_streams", "nb_programs",
    "probe_score", "size",
    # MP4/QuickTime container brand identifiers (preserved by ffmpeg -c copy)
    "format.tags.major_brand", "format.tags.minor_version", "format.tags.compatible_brands",
    "format.tags.encoder",  # ffmpeg automatically adds this
    # Stream-level structural properties (use pattern matching in verify())
    # Note: stream indices, codec info, etc. are structural
    # Stream handler tags (preserved by ffmpeg -c copy as they're structural)
    "stream0.tags.language", "stream0.tags.handler_name", "stream0.tags.vendor_id",
    "stream1.tags.language", "stream1.tags.handler_name", "stream1.tags.vendor_id",
    "stream2.tags.language", "stream2.tags.handler_name", "stream2.tags.vendor_id",
})


def snapshot_metadata(path: Path, kind: str) -> dict[str, object]:
    """Extract all metadata tags from a file using exiftool (image) or ffprobe (video).

    Args:
        path: File to probe
        kind: "image" or "video"

    Returns:
        Flat dict of tag_name -> value (tag names are de-duplicated across groups)
    """
    if kind == "image":
        out = subprocess.check_output(
            ["exiftool", "-j", "-G", "-a", "-u", "-n", str(path)],
            stderr=subprocess.DEVNULL,
        )
        data = json.loads(out)[0]
        stripped: dict[str, object] = {}
        for k, v in data.items():
            bare = k.split(":", 1)[-1]
            stripped[bare] = v
        return stripped
    if kind == "video":
        out = subprocess.check_output(
            [
                "ffprobe", "-v", "quiet", "-print_format", "json",
                "-show_format", "-show_streams", "-show_chapters", str(path),
            ],
        )
        probe = json.loads(out)
        flat: dict[str, object] = {}
        for k, v in (probe.get("format", {}) or {}).items():
            flat[k] = v
        for tag_k, tag_v in (probe.get("format", {}).get("tags", {}) or {}).items():
            flat[f"format.tags.{tag_k}"] = tag_v
        for i, stream in enumerate(probe.get("streams", []) or []):
            for k, v in stream.items():
                if k == "tags":
                    for tk, tv in (v or {}).items():
                        flat[f"stream{i}.tags.{tk}"] = tv
                else:
                    flat[f"stream{i}.{k}"] = v
        return flat
    raise ValueError(f"unknown kind: {kind}")


def stream_hash(path: Path, kind: str) -> str:
    """Compute SHA-256 of decoded pixel/audio stream.

    For images: uses ImageMagick if available, PIL.Image.tobytes() otherwise.
    For video: uses ffmpeg to strip metadata and hash raw NUT container.

    Args:
        path: File to hash
        kind: "image" or "video"

    Returns:
        Hex SHA-256 digest of the decoded stream
    """
    if kind == "image":
        if shutil.which("magick"):
            proc = subprocess.run(
                ["magick", str(path), "-strip", "RGB:-"],
                capture_output=True, check=True,
            )
            return hashlib.sha256(proc.stdout).hexdigest()
        from PIL import Image
        with Image.open(path) as im:
            return hashlib.sha256(im.tobytes()).hexdigest()
    if kind == "video":
        with tempfile.TemporaryDirectory() as td:
            raw = Path(td) / "raw.nut"
            subprocess.check_call(
                [
                    "ffmpeg", "-y", "-v", "error", "-i", str(path),
                    "-map", "0", "-map_metadata", "-1",
                    "-c", "copy", "-f", "nut", str(raw),
                ],
            )
            return hashlib.sha256(raw.read_bytes()).hexdigest()
    raise ValueError(f"unknown kind: {kind}")
