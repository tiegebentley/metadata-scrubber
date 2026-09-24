"""One-source → many-outputs workspace for purposeful variants.

Each mode produces visibly different outputs that a human can tell apart:
- Format matrix: multiple canvas sizes (existing presets)
- Caption variants: user-supplied text burned in at different positions
- Subtitle localization: user-supplied SRT files burned in
- Review copies: visible recipient stamp with enforced size/opacity floors

All modes use visible, human-readable differences. No randomization, no
invisible watermarking, no steganography. See factory/MISSION.md boundary.
"""

from __future__ import annotations

import datetime
import zipfile
from pathlib import Path

from .media_tools import MediaToolError, _crf_for_quality, _run
from .variations import PRESETS, export_variation

# Enforced visibility floors for review-copy stamps
MIN_STAMP_SIZE_PCT = 2.5  # % of frame height
MIN_STAMP_OPACITY = 0.7  # alpha value
FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


def _escape_drawtext(text: str) -> str:
    """Escape special characters for ffmpeg's drawtext filter."""
    # Order matters: backslash first, then others
    return text.replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'").replace("%", "\\%")


def format_matrix(
    src: Path,
    out_dir: Path,
    presets: list[str],
    quality: int = 90,
) -> list[Path]:
    """Export to multiple canvas presets in one pass.

    Reuses variations.export_variation for each preset. All presets must be
    valid PRESETS keys.
    """
    if not presets:
        raise MediaToolError("At least one preset must be selected.")
    if len(presets) > 4:
        raise MediaToolError("Format matrix is capped at 4 presets.")
    unknown = [p for p in presets if p not in PRESETS]
    if unknown:
        raise MediaToolError(f"Unknown preset(s): {', '.join(unknown)}")

    outputs: list[Path] = []
    for preset in presets:
        dst = out_dir / f"{src.stem}.{preset}.mp4"
        export_variation(src, dst, preset, quality)
        outputs.append(dst)
    return outputs


def caption_variants(
    src: Path,
    out_dir: Path,
    captions: list[str],
    position: str,
    size_pct: float = 5.0,
    color: str = "white",
) -> list[Path]:
    """Burn user-supplied caption strings into separate outputs.

    Each caption becomes its own video with the text burned in via drawtext.
    Position is "top" or "bottom", size_pct is % of frame height.
    """
    if not captions:
        raise MediaToolError("At least one caption is required.")
    if len(captions) > 10:
        raise MediaToolError("Caption variants are capped at 10.")
    if position not in {"top", "bottom"}:
        raise MediaToolError("Position must be 'top' or 'bottom'.")

    # Color palette
    color_map = {
        "white": "white",
        "black": "black",
        "yellow": "yellow",
        "red": "red",
        "blue": "blue",
    }
    if color not in color_map:
        raise MediaToolError(f"Color must be one of: {', '.join(color_map.keys())}")

    outputs: list[Path] = []
    for i, caption in enumerate(captions):
        if not caption.strip():
            continue

        escaped = _escape_drawtext(caption.strip())
        # Position: top = 10% from top, bottom = 90% from top
        y_expr = "h*0.1" if position == "top" else "h*0.9"
        fontsize = f"h*{size_pct / 100}"

        drawtext = (
            f"drawtext=text='{escaped}':fontfile={FONT_PATH}:"
            f"fontsize={fontsize}:fontcolor={color_map[color]}:"
            f"x=(w-text_w)/2:y={y_expr}:box=1:boxcolor=black@0.6:boxborderw=5"
        )

        dst = out_dir / f"{src.stem}.caption-{i + 1}.mp4"
        _run([
            "ffmpeg", "-y", "-i", str(src), "-vf", drawtext,
            "-c:v", "libx264", "-crf", _crf_for_quality(90), "-preset", "medium",
            "-c:a", "copy", "-movflags", "+faststart", str(dst),
        ])
        outputs.append(dst)

    return outputs


def subtitle_variants(
    src: Path,
    out_dir: Path,
    srt_files: list[Path],
) -> list[Path]:
    """Burn in user-supplied SRT subtitle files into separate outputs.

    Each SRT file becomes its own output with subtitles burned in via the
    subtitles filter. Output filename carries the SRT stem.
    """
    if not srt_files:
        raise MediaToolError("At least one SRT file is required.")
    if len(srt_files) > 10:
        raise MediaToolError("Subtitle variants are capped at 10 SRT files.")

    outputs: list[Path] = []
    for srt_path in srt_files:
        if not srt_path.exists():
            raise MediaToolError(f"SRT file not found: {srt_path.name}")

        # Extract locale/lang code from stem (e.g., "talk.en" -> "en")
        stem_parts = srt_path.stem.split(".")
        locale_suffix = stem_parts[-1] if len(stem_parts) > 1 else srt_path.stem

        # Escape path for subtitles filter (Windows paths need special handling)
        # For subtitles filter, we need to escape : and \
        escaped_path = str(srt_path).replace("\\", "/").replace(":", "\\:")

        dst = out_dir / f"{src.stem}.{locale_suffix}.mp4"
        _run([
            "ffmpeg", "-y", "-i", str(src), "-vf", f"subtitles={escaped_path}",
            "-c:v", "libx264", "-crf", _crf_for_quality(90), "-preset", "medium",
            "-c:a", "copy", "-movflags", "+faststart", str(dst),
        ])
        outputs.append(dst)

    return outputs


def review_copies(
    src: Path,
    out_dir: Path,
    recipients: list[str],
    corner: str,
    size_pct: float = 3.0,
    opacity: float = 0.8,
) -> list[Path]:
    """Create per-recipient review copies with visible stamps.

    Each recipient gets an output with a stamp:
        REVIEW COPY · <name> · <YYYY-MM-DD> · Do not distribute

    The stamp is ALWAYS visible with enforced minimum size and opacity.
    Corner is "tl", "tr", "bl", or "br".
    """
    if not recipients:
        raise MediaToolError("At least one recipient name is required.")
    if len(recipients) > 25:
        raise MediaToolError("Review copies are capped at 25 recipients.")
    if corner not in {"tl", "tr", "bl", "br"}:
        raise MediaToolError("Corner must be one of: tl, tr, bl, br")

    # Enforce visibility floors
    size_pct = max(size_pct, MIN_STAMP_SIZE_PCT)
    opacity = max(opacity, MIN_STAMP_OPACITY)

    today = datetime.date.today().isoformat()

    outputs: list[Path] = []
    for recipient in recipients:
        if not recipient.strip():
            continue

        name = recipient.strip()
        stamp_text = f"REVIEW COPY · {name} · {today} · Do not distribute"
        escaped = _escape_drawtext(stamp_text)

        # Position based on corner
        corner_positions = {
            "tl": ("10", "10"),
            "tr": ("w-text_w-10", "10"),
            "bl": ("10", "h-text_h-10"),
            "br": ("w-text_w-10", "h-text_h-10"),
        }
        x_expr, y_expr = corner_positions[corner]

        fontsize = f"h*{size_pct / 100}"

        drawtext = (
            f"drawtext=text='{escaped}':fontfile={FONT_PATH}:"
            f"fontsize={fontsize}:fontcolor=white@{opacity}:"
            f"x={x_expr}:y={y_expr}:box=1:boxcolor=black@0.8:boxborderw=5"
        )

        # Sanitize recipient name for filename
        safe_name = "".join(c if c.isalnum() or c in " -_" else "_" for c in name)
        safe_name = safe_name.replace(" ", "-")[:50]  # cap length

        dst = out_dir / f"{src.stem}.review-{safe_name}.mp4"
        _run([
            "ffmpeg", "-y", "-i", str(src), "-vf", drawtext,
            "-c:v", "libx264", "-crf", _crf_for_quality(90), "-preset", "medium",
            "-c:a", "copy", "-movflags", "+faststart", str(dst),
        ])
        outputs.append(dst)

    return outputs


def create_zip(outputs: list[Path], zip_path: Path) -> None:
    """Pack all outputs into a single zip file."""
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in outputs:
            zf.write(path, path.name)
