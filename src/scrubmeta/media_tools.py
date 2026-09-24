"""Local media utility operations for the scrubmeta web UI.

Ordinary user-directed conversion and editing helpers, all backed by the
local ffmpeg/ffprobe binaries. They make no network calls and apply no hidden
transforms: every change to the output is one the user explicitly asked for
(target format, quality, size, frame rate, trim range, speed). Nothing here
alters media to affect moderation, provenance, or similarity-detection
systems; see factory/MISSION.md for the scope these tools operate within.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any


class MediaToolError(RuntimeError):
    """Raised when a media operation is invalid or the underlying tool fails."""


def _run(args: list[str]) -> None:
    try:
        subprocess.run(args, check=True, capture_output=True, text=True)
    except FileNotFoundError as exc:
        raise MediaToolError(f"Required program not installed: {args[0]}") from exc
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "media operation failed").strip()
        raise MediaToolError(detail[-1200:]) from exc


def _crf_for_quality(quality: int) -> str:
    """Map a 1-100 quality slider onto libx264's CRF scale (lower is better)."""
    q = max(1, min(100, quality))
    return str(round(35 - (q * 0.17)))


def _jpeg_q_for_quality(quality: int) -> str:
    """Map a 1-100 quality slider onto ffmpeg's mjpeg -q:v scale (2 best, 31 worst)."""
    q = max(1, min(100, quality))
    return str(max(2, round(31 - (q * 0.28))))


def probe(path: Path) -> dict[str, Any]:
    """Return container, stream, and tag information from ffprobe."""
    try:
        completed = subprocess.run(
            ["ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json", str(path)],
            check=True,
            capture_output=True,
            text=True,
        )
        data = json.loads(completed.stdout or "{}")
    except (FileNotFoundError, subprocess.CalledProcessError, json.JSONDecodeError) as exc:
        raise MediaToolError("Unable to inspect media with ffprobe.") from exc

    fmt = data.get("format", {})
    streams = data.get("streams", [])
    return {
        "filename": path.name,
        "size": int(fmt.get("size", path.stat().st_size)),
        "format_name": fmt.get("format_long_name") or fmt.get("format_name"),
        "duration": float(fmt["duration"]) if fmt.get("duration") else None,
        "bit_rate": int(fmt["bit_rate"]) if fmt.get("bit_rate") else None,
        "format_tags": fmt.get("tags", {}),
        "streams": [
            {
                "index": s.get("index"),
                "type": s.get("codec_type"),
                "codec": s.get("codec_name"),
                "width": s.get("width"),
                "height": s.get("height"),
                "frame_rate": s.get("avg_frame_rate"),
                "sample_rate": s.get("sample_rate"),
                "channels": s.get("channels"),
                "tags": s.get("tags", {}),
            }
            for s in streams
        ],
    }


def convert(
    src: Path,
    dst: Path,
    target: str,
    quality: int = 90,
    fps: int | None = None,
    width: int | None = None,
    height: int | None = None,
) -> None:
    """Convert to gif, mp4, or jpg with optional resize and frame-rate change."""
    vf: list[str] = []
    if width or height:
        vf.append(f"scale={width or -2}:{height or -2}")
    if fps:
        vf.append(f"fps={max(1, min(120, fps))}")

    common = ["ffmpeg", "-y", "-i", str(src)]
    if target == "mp4":
        args = common
        if vf:
            args += ["-vf", ",".join(vf)]
        args += [
            "-c:v", "libx264", "-crf", _crf_for_quality(quality), "-preset", "medium",
            "-c:a", "aac", "-movflags", "+faststart", str(dst),
        ]
    elif target == "gif":
        filters = vf + ["split[s0][s1];[s0]palettegen[p];[s1][p]paletteuse"]
        args = common + ["-vf", ",".join(filters), "-loop", "0", str(dst)]
    elif target in {"jpg", "jpeg"}:
        args = common + ["-frames:v", "1"]
        if vf:
            args += ["-vf", ",".join(vf)]
        args += ["-q:v", _jpeg_q_for_quality(quality), str(dst)]
    else:
        raise MediaToolError("Unsupported conversion target.")
    _run(args)


def _atempo_chain(speed: float) -> str:
    """ffmpeg's atempo filter only accepts 0.5..2.0; chain it to cover 0.25..4.0."""
    factors: list[float] = []
    remaining = speed
    while remaining > 2:
        factors.append(2.0)
        remaining /= 2
    while remaining < 0.5:
        factors.append(0.5)
        remaining /= 0.5
    factors.append(remaining)
    return ",".join(f"atempo={f:g}" for f in factors)


def trim_video(
    src: Path,
    dst: Path,
    start: float,
    end: float | None,
    quality: int = 90,
    speed: float = 1.0,
) -> None:
    """Trim to [start, end] and optionally change playback speed."""
    if start < 0 or (end is not None and end <= start):
        raise MediaToolError("Invalid trim range.")
    speed = max(0.25, min(4.0, speed))

    args = ["ffmpeg", "-y", "-ss", str(start), "-i", str(src)]
    if end is not None:
        args += ["-t", str(end - start)]
    if speed != 1.0:
        args += ["-vf", f"setpts=PTS/{speed}"]
    args += ["-c:v", "libx264", "-crf", _crf_for_quality(quality), "-preset", "medium"]
    if speed != 1.0:
        args += ["-af", _atempo_chain(speed)]
    args += ["-c:a", "aac", "-movflags", "+faststart", str(dst)]
    _run(args)


def extract_frame(src: Path, dst: Path, at: float) -> None:
    """Write the frame at `at` seconds as a JPEG."""
    if at < 0:
        raise MediaToolError("Frame time cannot be negative.")
    _run(["ffmpeg", "-y", "-ss", str(at), "-i", str(src), "-frames:v", "1", "-q:v", "2", str(dst)])


def make_clip(src: Path, dst: Path, start: float, duration: float) -> None:
    """Cut a clip of `duration` seconds starting at `start`."""
    if start < 0 or duration <= 0:
        raise MediaToolError("Invalid clip range.")
    _run([
        "ffmpeg", "-y", "-ss", str(start), "-i", str(src), "-t", str(duration),
        "-c:v", "libx264", "-crf", "20", "-preset", "medium",
        "-c:a", "aac", "-movflags", "+faststart", str(dst),
    ])
