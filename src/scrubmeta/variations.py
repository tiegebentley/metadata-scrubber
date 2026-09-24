"""Fixed-canvas export presets for user-owned media.

Each preset is a visible, deterministic choice (vertical, square, landscape,
HD). The whole source frame is preserved inside the target canvas by
scaling to fit and letterboxing; there is no cropping, no random offset, and
no per-run variation. Running the same input through the same preset twice
produces the same output.
"""

from __future__ import annotations

from pathlib import Path
from typing import TypedDict

from .media_tools import MediaToolError, _crf_for_quality, _run


class Preset(TypedDict):
    width: int
    height: int
    label: str


PRESETS: dict[str, Preset] = {
    "vertical": {"width": 1080, "height": 1920, "label": "Vertical 9:16"},
    "square": {"width": 1080, "height": 1080, "label": "Square 1:1"},
    "landscape": {"width": 1920, "height": 1080, "label": "Landscape 16:9"},
    "hd": {"width": 1280, "height": 720, "label": "HD 720p"},
}


def export_variation(
    src: Path,
    dst: Path,
    preset: str,
    quality: int = 90,
    fps: int | None = None,
) -> None:
    """Re-encode `src` onto the preset canvas, letterboxed, as H.264 MP4."""
    if preset not in PRESETS:
        raise MediaToolError("Unknown export preset.")
    p = PRESETS[preset]
    w, h = p["width"], p["height"]
    vf = (
        f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
        f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2"
    )
    if fps:
        vf += f",fps={max(1, min(120, fps))}"
    _run([
        "ffmpeg", "-y", "-i", str(src), "-vf", vf,
        "-c:v", "libx264", "-crf", _crf_for_quality(quality), "-preset", "medium",
        "-c:a", "aac", "-movflags", "+faststart", str(dst),
    ])
