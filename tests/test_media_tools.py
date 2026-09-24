"""Unit tests for media_tools: argument validation and ffmpeg command shape."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from scrubmeta.media_tools import (
    MediaToolError,
    _atempo_chain,
    convert,
    extract_frame,
    make_clip,
    trim_video,
)


def test_convert_rejects_unknown_target(tmp_path: Path) -> None:
    src = tmp_path / "in.mp4"
    src.write_bytes(b"x")
    with pytest.raises(MediaToolError):
        convert(src, tmp_path / "out.bin", "bad")


@patch("scrubmeta.media_tools._run")
def test_convert_mp4_uses_stream_copy_free_h264(run: MagicMock, tmp_path: Path) -> None:
    convert(tmp_path / "a.mov", tmp_path / "a.mp4", "mp4", quality=90, fps=30, width=640)
    args = run.call_args.args[0]
    assert "libx264" in args
    assert "scale=640:-2,fps=30" in args


@patch("scrubmeta.media_tools._run")
def test_convert_gif_builds_palette(run: MagicMock, tmp_path: Path) -> None:
    convert(tmp_path / "a.mp4", tmp_path / "a.gif", "gif")
    args = run.call_args.args[0]
    assert any("palettegen" in a for a in args)


@patch("scrubmeta.media_tools._run")
def test_frame_command(run: MagicMock, tmp_path: Path) -> None:
    extract_frame(tmp_path / "a.mp4", tmp_path / "a.jpg", 3.5)
    args = run.call_args.args[0]
    assert "-frames:v" in args
    assert "3.5" in args


def test_frame_rejects_negative_time(tmp_path: Path) -> None:
    with pytest.raises(MediaToolError):
        extract_frame(tmp_path / "a.mp4", tmp_path / "a.jpg", -1)


@patch("scrubmeta.media_tools._run")
def test_clip_command(run: MagicMock, tmp_path: Path) -> None:
    make_clip(tmp_path / "a.mp4", tmp_path / "b.mp4", 2, 8)
    args = run.call_args.args[0]
    assert "-ss" in args
    assert "-t" in args


@patch("scrubmeta.media_tools._run")
def test_trim_validates_range(run: MagicMock, tmp_path: Path) -> None:
    with pytest.raises(MediaToolError):
        trim_video(tmp_path / "a.mp4", tmp_path / "b.mp4", 5, 2)
    run.assert_not_called()


@patch("scrubmeta.media_tools._run")
def test_trim_at_speed_adds_matching_audio_filter(run: MagicMock, tmp_path: Path) -> None:
    trim_video(tmp_path / "a.mp4", tmp_path / "b.mp4", 0, 10, speed=2.0)
    args = run.call_args.args[0]
    assert "setpts=PTS/2.0" in args
    assert "atempo=2" in args


def test_atempo_chain_covers_extremes() -> None:
    assert _atempo_chain(1.0) == "atempo=1"
    assert _atempo_chain(4.0) == "atempo=2,atempo=2"
    assert _atempo_chain(0.25) == "atempo=0.5,atempo=0.5"
