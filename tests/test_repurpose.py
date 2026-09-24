"""Unit tests for repurpose module with _run patched."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from scrubmeta.media_tools import MediaToolError
from scrubmeta.repurpose import (
    MIN_STAMP_OPACITY,
    MIN_STAMP_SIZE_PCT,
    caption_variants,
    format_matrix,
    review_copies,
    subtitle_variants,
)


@pytest.fixture
def mock_run() -> MagicMock:
    """Patch _run to capture ffmpeg commands without actually running them."""
    with patch("scrubmeta.repurpose._run") as mock:
        yield mock


@pytest.fixture
def src(tmp_path: Path) -> Path:
    """Mock source video file."""
    src = tmp_path / "source.mp4"
    src.write_text("mock video")
    return src


def test_format_matrix_calls_export_variation_for_each_preset(tmp_path: Path, src: Path) -> None:
    """Format matrix should call export_variation for each selected preset."""
    with patch("scrubmeta.repurpose.export_variation") as mock_export:
        outputs = format_matrix(src, tmp_path, ["vertical", "square"], quality=80)
        assert len(outputs) == 2
        assert mock_export.call_count == 2
        # Check that each preset was passed
        calls = [call[0] for call in mock_export.call_args_list]
        presets_passed = [call[2] for call in calls]  # third arg is preset
        assert set(presets_passed) == {"vertical", "square"}


def test_format_matrix_rejects_unknown_preset(tmp_path: Path, src: Path) -> None:
    """Format matrix should reject presets not in PRESETS."""
    with pytest.raises(MediaToolError, match="Unknown preset"):
        format_matrix(src, tmp_path, ["vertical", "random"])


def test_format_matrix_enforces_cap(tmp_path: Path, src: Path) -> None:
    """Format matrix should reject more than 4 presets."""
    with pytest.raises(MediaToolError, match="capped at 4"):
        format_matrix(src, tmp_path, ["vertical", "square", "landscape", "hd", "extra"])


def test_caption_variants_escapes_drawtext_special_chars(tmp_path: Path, src: Path, mock_run: MagicMock) -> None:
    """Caption variants should escape special characters in drawtext filter."""
    outputs = caption_variants(src, tmp_path, ["Test: 50% off"], "top")
    assert len(outputs) == 1
    # Check that _run was called with escaped text
    call_args = mock_run.call_args[0][0]
    filter_arg = next((arg for i, arg in enumerate(call_args) if call_args[i - 1] == "-vf"), None)
    assert filter_arg is not None
    assert "Test\\: 50\\% off" in filter_arg


def test_caption_variants_positions_text_correctly(tmp_path: Path, src: Path, mock_run: MagicMock) -> None:
    """Caption variants should position text at top or bottom."""
    caption_variants(src, tmp_path, ["Top text"], "top")
    top_filter = mock_run.call_args[0][0]
    top_vf = next((arg for i, arg in enumerate(top_filter) if top_filter[i - 1] == "-vf"), None)
    assert "y=h*0.1" in top_vf

    mock_run.reset_mock()
    caption_variants(src, tmp_path, ["Bottom text"], "bottom")
    bottom_filter = mock_run.call_args[0][0]
    bottom_vf = next((arg for i, arg in enumerate(bottom_filter) if bottom_filter[i - 1] == "-vf"), None)
    assert "y=h*0.9" in bottom_vf


def test_caption_variants_enforces_cap(tmp_path: Path, src: Path) -> None:
    """Caption variants should reject more than 10 captions."""
    with pytest.raises(MediaToolError, match="capped at 10"):
        caption_variants(src, tmp_path, [f"Caption {i}" for i in range(11)], "top")


def test_subtitle_variants_uses_subtitles_filter(tmp_path: Path, src: Path, mock_run: MagicMock) -> None:
    """Subtitle variants should use subtitles filter with SRT file path."""
    srt1 = tmp_path / "talk.en.srt"
    srt1.write_text("1\n00:00:00,000 --> 00:00:02,000\nHello\n")

    outputs = subtitle_variants(src, tmp_path, [srt1])
    assert len(outputs) == 1
    assert outputs[0].name == "source.en.mp4"

    # Check that subtitles filter was used
    call_args = mock_run.call_args[0][0]
    filter_arg = next((arg for i, arg in enumerate(call_args) if call_args[i - 1] == "-vf"), None)
    assert filter_arg is not None
    assert "subtitles=" in filter_arg


def test_subtitle_variants_enforces_cap(tmp_path: Path, src: Path) -> None:
    """Subtitle variants should reject more than 10 SRT files."""
    srts = [tmp_path / f"sub{i}.srt" for i in range(11)]
    for srt in srts:
        srt.write_text("1\n00:00:00,000 --> 00:00:01,000\nText\n")

    with pytest.raises(MediaToolError, match="capped at 10"):
        subtitle_variants(src, tmp_path, srts)


def test_review_copies_includes_recipient_name_and_date(tmp_path: Path, src: Path, mock_run: MagicMock) -> None:
    """Review copies should include recipient handle and REVIEW · date in compact two-line stamp."""
    outputs = review_copies(src, tmp_path, ["@alicechen"], "tl")
    assert len(outputs) == 1
    # Filename should strip leading @ before sanitizing
    assert outputs[0].name == "review-alicechen.mp4"

    # Check drawtext filter contains required elements
    call_args = mock_run.call_args[0][0]
    filter_arg = next((arg for i, arg in enumerate(call_args) if call_args[i - 1] == "-vf"), None)
    assert filter_arg is not None
    # Should contain recipient handle and REVIEW ·, but NOT "Do not distribute"
    assert "@alicechen" in filter_arg
    assert "REVIEW ·" in filter_arg or "REVIEW \u00b7" in filter_arg  # Accept either · or unicode
    assert "Do not distribute" not in filter_arg


def test_review_copies_enforces_visibility_floor(tmp_path: Path, src: Path, mock_run: MagicMock) -> None:
    """Review copies should enforce minimum size and opacity even when passed smaller values."""
    # Try to pass values below the floor
    review_copies(src, tmp_path, ["Test User"], "tl", size_pct=1.0, opacity=0.3)

    # Check that the actual values used are at or above the floor
    call_args = mock_run.call_args[0][0]
    filter_arg = next((arg for i, arg in enumerate(call_args) if call_args[i - 1] == "-vf"), None)
    assert filter_arg is not None

    # Should use MIN_STAMP_SIZE_PCT (2.5) instead of 1.0
    assert f"fontsize=h*{MIN_STAMP_SIZE_PCT / 100}" in filter_arg
    # Should use MIN_STAMP_OPACITY (0.7) instead of 0.3
    assert f"white@{MIN_STAMP_OPACITY}" in filter_arg


def test_review_copies_positions_stamp_in_corners(tmp_path: Path, src: Path, mock_run: MagicMock) -> None:
    """Review copies should position stamp in the specified corner with padding."""
    corners = ["tl", "tr", "bl", "br"]
    # New positioning uses 20px padding (approximates 2% for common resolutions)
    expected_patterns = {
        "tl": ("x=20", "y=20"),
        "tr": ("x=w-text_w-20", "y=20"),
        "bl": ("x=20", "y=h-text_h-20"),
        "br": ("x=w-text_w-20", "y=h-text_h-20"),
    }

    for corner in corners:
        mock_run.reset_mock()
        review_copies(src, tmp_path, ["Tester"], corner)

        call_args = mock_run.call_args[0][0]
        filter_arg = next((arg for i, arg in enumerate(call_args) if call_args[i - 1] == "-vf"), None)
        assert filter_arg is not None

        x_expected, y_expected = expected_patterns[corner]
        # Check that first line (line 1) has the expected x position
        assert x_expected in filter_arg, f"Expected {x_expected} in filter for corner {corner}"
        # Y position varies between line 1 and line 2, just verify corner-appropriate positioning exists
        if corner in ("tl", "tr"):
            # Top corners: y should start at 20
            assert "y=20" in filter_arg or "y=h*0." in filter_arg
        else:
            # Bottom corners: y should be relative to h-text_h
            assert "y=h-text_h-20" in filter_arg or "y=h-text_h" in filter_arg


def test_review_copies_enforces_cap(tmp_path: Path, src: Path) -> None:
    """Review copies should reject more than 25 recipients."""
    with pytest.raises(MediaToolError, match="capped at 25"):
        review_copies(src, tmp_path, [f"Recipient {i}" for i in range(26)], "tl")


def test_review_copies_sanitizes_recipient_names_for_filenames(tmp_path: Path, src: Path, mock_run: MagicMock) -> None:
    """Review copies should sanitize recipient names for safe filenames and strip leading @."""
    # Test with leading @ - should be stripped before sanitization
    outputs = review_copies(src, tmp_path, ["@alicechen"], "tl")
    assert len(outputs) == 1
    assert outputs[0].name == "review-alicechen.mp4"

    # Test without @ and with special chars - should sanitize normally
    mock_run.reset_mock()
    outputs = review_copies(src, tmp_path, ["John Doe / Test <User>"], "tl")
    assert len(outputs) == 1
    assert "review-" in outputs[0].name
    # Should not contain special chars in filename
    assert "/" not in outputs[0].name
    assert "<" not in outputs[0].name
    assert ">" not in outputs[0].name
