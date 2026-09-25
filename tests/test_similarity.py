"""Tests for the duplicate finder."""

from __future__ import annotations

import subprocess
from pathlib import Path

from PIL import Image

from scrubmeta.similarity import (
    compare_images,
    compare_media,
    video_fingerprint,
    video_similarity,
    visual_similarity,
)


def test_identical_images_are_100_percent(tmp_path: Path) -> None:
    a = tmp_path / "a.png"
    b = tmp_path / "b.png"
    Image.new("RGB", (20, 20), (20, 40, 60)).save(a)
    b.write_bytes(a.read_bytes())

    assert visual_similarity(a, b) == 100.0
    matches = compare_images([a, b], 99)
    assert len(matches) == 1
    assert matches[0]["kind"] == "exact"


def test_resized_copy_is_near_duplicate(tmp_path: Path) -> None:
    a = tmp_path / "a.png"
    b = tmp_path / "b.png"
    im = Image.new("L", (64, 64), 0)
    for x in range(32):
        for y in range(64):
            im.putpixel((x, y), 255)
    im.save(a)
    im.resize((32, 32)).save(b)

    matches = compare_images([a, b], 90)
    assert len(matches) == 1
    assert matches[0]["kind"] == "near"
    assert matches[0]["similarity"] >= 90


def test_threshold_filters(tmp_path: Path) -> None:
    a = tmp_path / "a.png"
    b = tmp_path / "b.png"
    im = Image.new("L", (16, 16), 0)
    im.putpixel((0, 0), 255)
    im.save(a)
    im2 = Image.new("L", (16, 16), 255)
    im2.putpixel((0, 0), 0)
    im2.save(b)

    assert compare_images([a, b], 100) == []


def test_results_sorted_best_first(tmp_path: Path) -> None:
    base = Image.new("L", (32, 32), 0)
    for x in range(16):
        for y in range(32):
            base.putpixel((x, y), 255)
    a = tmp_path / "a.png"
    b = tmp_path / "b.png"
    c = tmp_path / "c.png"
    base.save(a)
    base.save(b)  # exact copy
    noisy = base.copy()
    for y in range(32):
        noisy.putpixel((16, y), 255)  # shift the edge one column
    noisy.save(c)

    matches = compare_images([a, b, c], 0)
    assert matches[0]["kind"] == "exact"
    assert matches[0]["similarity"] == 100.0
    assert all(
        matches[i]["similarity"] >= matches[i + 1]["similarity"] for i in range(len(matches) - 1)
    )


def test_video_fingerprint_and_similarity(tmp_path: Path) -> None:
    """Generate two test videos and verify video_similarity scores them highly."""
    v1 = tmp_path / "video1.mp4"
    v2_reencoded = tmp_path / "video2_reencoded.mp4"
    v3_different = tmp_path / "video3_different.mp4"

    # Generate 3-second test video with testsrc2
    subprocess.run(
        [
            "ffmpeg", "-f", "lavfi", "-i", "testsrc2=duration=3:size=640x480:rate=30",
            "-c:v", "libx264", "-crf", "23", "-pix_fmt", "yuv420p", str(v1),
        ],
        check=True,
        capture_output=True,
    )

    # Re-encode at different CRF and scale to 480p
    subprocess.run(
        [
            "ffmpeg", "-i", str(v1), "-c:v", "libx264", "-crf", "28",
            "-vf", "scale=640:480", str(v2_reencoded),
        ],
        check=True,
        capture_output=True,
    )

    # Generate different video with smptebars
    subprocess.run(
        [
            "ffmpeg", "-f", "lavfi", "-i", "smptebars=duration=3:size=640x480:rate=30",
            "-c:v", "libx264", "-crf", "23", "-pix_fmt", "yuv420p", str(v3_different),
        ],
        check=True,
        capture_output=True,
    )

    # Test fingerprinting
    fp1 = video_fingerprint(v1)
    fp2 = video_fingerprint(v2_reencoded)
    fp3 = video_fingerprint(v3_different)

    assert len(fp1) > 0
    assert len(fp2) > 0
    assert len(fp3) > 0

    # Test similarity: v1 and v2 should be highly similar
    sim_12 = video_similarity(fp1, fp2)
    sim_13 = video_similarity(fp1, fp3)

    assert sim_12 >= 90.0, f"Re-encoded video similarity {sim_12} should be >= 90"
    assert sim_13 < 60.0, f"Different video similarity {sim_13} should be < 60"


def test_gif_scores_high_against_source_video(tmp_path: Path) -> None:
    """GIF made from a video should score >= 85 against the source."""
    video = tmp_path / "source.mp4"
    gif = tmp_path / "from_video.gif"

    # Generate source video
    subprocess.run(
        [
            "ffmpeg", "-f", "lavfi", "-i", "testsrc2=duration=2:size=320x240:rate=10",
            "-c:v", "libx264", "-crf", "23", "-pix_fmt", "yuv420p", str(video),
        ],
        check=True,
        capture_output=True,
    )

    # Convert to GIF
    subprocess.run(
        [
            "ffmpeg", "-i", str(video),
            "-vf", "fps=10,scale=320:240:flags=lanczos,split[s0][s1];[s0]palettegen[p];[s1][p]paletteuse",
            "-loop", "0", str(gif),
        ],
        check=True,
        capture_output=True,
    )

    fp_video = video_fingerprint(video)
    fp_gif = video_fingerprint(gif)

    sim = video_similarity(fp_video, fp_gif)
    assert sim >= 85.0, f"GIF similarity to source video {sim} should be >= 85"


def test_compare_media_separates_images_and_videos(tmp_path: Path) -> None:
    """compare_media should only match like types (image-image, video-video)."""
    img = tmp_path / "test.png"
    vid = tmp_path / "test.mp4"

    # Create a simple image
    Image.new("RGB", (100, 100), (128, 128, 128)).save(img)

    # Create a simple video
    subprocess.run(
        [
            "ffmpeg", "-f", "lavfi", "-i", "color=c=gray:s=100x100:d=1",
            "-c:v", "libx264", "-crf", "23", "-pix_fmt", "yuv420p", str(vid),
        ],
        check=True,
        capture_output=True,
    )

    matches = compare_media([img, vid], threshold=0)
    # Should have zero matches because we don't cross-compare image vs video
    assert len(matches) == 0


def test_compare_media_matches_videos(tmp_path: Path) -> None:
    """compare_media should find near matches between videos."""
    v1 = tmp_path / "vid1.mp4"
    v2 = tmp_path / "vid2.mp4"

    # Generate two similar videos
    subprocess.run(
        [
            "ffmpeg", "-f", "lavfi", "-i", "testsrc2=duration=2:size=320x240:rate=10",
            "-c:v", "libx264", "-crf", "23", "-pix_fmt", "yuv420p", str(v1),
        ],
        check=True,
        capture_output=True,
    )

    # Re-encode
    subprocess.run(
        [
            "ffmpeg", "-i", str(v1), "-c:v", "libx264", "-crf", "28", str(v2),
        ],
        check=True,
        capture_output=True,
    )

    matches = compare_media([v1, v2], threshold=90)
    assert len(matches) == 1
    assert matches[0]["media"] == "video"
    assert matches[0]["kind"] == "near"
    assert matches[0]["similarity"] >= 90.0
