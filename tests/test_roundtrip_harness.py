"""
Tests that the round-trip verification harness itself catches broken outputs.

These tests run in-process with pytest, constructing synthetic fixtures and
mocking or patching run_scrubmeta to produce deliberately broken outputs, then
asserting that verify() detects the breakage.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from tests.roundtrip import Fixture, verify


@pytest.fixture
def synthetic_image(tmp_path: Path) -> Path:
    """Create a minimal PNG with some metadata using PIL and exiftool."""
    from PIL import Image  # type: ignore

    img = tmp_path / "source.png"
    # Create a proper 1x1 PNG using PIL
    im = Image.new("RGB", (1, 1), color=(255, 0, 0))
    im.save(img)

    # Add some metadata using exiftool
    subprocess.run(
        ["exiftool", "-overwrite_original", "-Software=TestApp", str(img)],
        check=True,
        capture_output=True,
    )
    return img


def test_detects_byte_identical_copy(synthetic_image: Path, tmp_path: Path) -> None:
    """
    Test that verify() catches when scrubmeta produces a byte-identical copy.

    Patch run_scrubmeta to simply copy the input to output unchanged.
    Assert that verify() returns a failure mentioning an unchanged tag.
    """
    fixture = Fixture(
        path=synthetic_image,
        kind="image",
        has_c2pa=False,
        lossy_allowed=False,
        lossy_reason=None,
        expected_stripped_tags=["Software"],
        skip_if_unimplemented=False,
    )

    def fake_scrubmeta_identity(src: Path, dst: Path) -> subprocess.CompletedProcess[bytes]:
        """Copy source to destination unchanged."""
        dst.write_bytes(src.read_bytes())
        return subprocess.CompletedProcess(
            args=["scrubmeta", str(src), "-o", str(dst), "--yes"],
            returncode=0,
            stdout=b"",
            stderr=b"",
        )

    with patch("tests.roundtrip.run_scrubmeta", side_effect=fake_scrubmeta_identity):
        failures, skipped = verify(fixture)

    assert not skipped, "Fixture should not be skipped"
    assert len(failures) > 0, "Should detect at least one failure"

    # Check that at least one failure mentions unchanged tag
    failure_reasons = [f.reason for f in failures]
    assert any("unchanged" in reason.lower() for reason in failure_reasons), (
        f"Expected a failure mentioning 'unchanged' tag, got: {failure_reasons}"
    )


def test_detects_empty_metadata_block(synthetic_image: Path, tmp_path: Path) -> None:
    """
    Test that verify() catches when scrubmeta produces output with empty metadata.

    Patch run_scrubmeta to produce a file with no metadata at all.
    Assert that verify() returns a failure mentioning "no new metadata".
    """
    fixture = Fixture(
        path=synthetic_image,
        kind="image",
        has_c2pa=False,
        lossy_allowed=False,
        lossy_reason=None,
        expected_stripped_tags=["Software"],
        skip_if_unimplemented=False,
    )

    def fake_scrubmeta_empty_metadata(src: Path, dst: Path) -> subprocess.CompletedProcess[bytes]:
        """Strip all metadata, leaving a bare file."""
        from PIL import Image  # type: ignore

        # Create a completely new image with no metadata, preserving just pixel data
        with Image.open(src) as im:
            im_copy = Image.new(im.mode, im.size)
            im_copy.putdata(list(im.getdata()))
            im_copy.save(dst, format="PNG")

        return subprocess.CompletedProcess(
            args=["scrubmeta", str(src), "-o", str(dst), "--yes"],
            returncode=0,
            stdout=b"",
            stderr=b"",
        )

    with patch("tests.roundtrip.run_scrubmeta", side_effect=fake_scrubmeta_empty_metadata):
        failures, skipped = verify(fixture)

    assert not skipped, "Fixture should not be skipped"
    assert len(failures) > 0, "Should detect at least one failure"

    # Check that at least one failure mentions no metadata or unchanged structural tags
    # (the harness may detect unchanged tags first before checking for no new metadata)
    failure_reasons = [f.reason for f in failures]
    assert any(
        "no new metadata" in reason.lower() or "unchanged" in reason.lower()
        for reason in failure_reasons
    ), f"Expected a failure mentioning 'no new metadata' or 'unchanged', got: {failure_reasons}"


def test_detects_c2pa_silent_drop(synthetic_image: Path, tmp_path: Path) -> None:
    """
    Test that verify() catches when scrubmeta silently drops C2PA manifest.

    With has_c2pa=True, fake scrubmeta returns exit 0 but drops the manifest.
    Assert that verify() returns a failure mentioning silent drop.
    """
    from PIL import Image  # type: ignore

    # Create a new image with XMP metadata that contains C2PA-like content
    img_with_c2pa = tmp_path / "with_c2pa.png"
    img_with_c2pa.write_bytes(synthetic_image.read_bytes())

    # Use XMP to add C2PA-like metadata that exiftool will recognize as JUMBF
    # We add a custom XMP tag that contains "C2PA" in its content
    subprocess.run(
        ["exiftool", "-overwrite_original", "-XMP:Description=C2PA_MANIFEST_DATA", str(img_with_c2pa)],
        check=True,
        capture_output=True,
    )

    fixture = Fixture(
        path=img_with_c2pa,
        kind="image",
        has_c2pa=True,
        lossy_allowed=False,
        lossy_reason=None,
        expected_stripped_tags=["Software"],
        skip_if_unimplemented=False,
    )

    def fake_scrubmeta_drop_manifest(src: Path, dst: Path) -> subprocess.CompletedProcess[bytes]:
        """Return success but strip C2PA manifest."""
        # Create a clean copy without any C2PA data
        with Image.open(src) as im:
            im_copy = Image.new(im.mode, im.size)
            im_copy.putdata(list(im.getdata()))
            im_copy.save(dst, format="PNG")

        return subprocess.CompletedProcess(
            args=["scrubmeta", str(src), "-o", str(dst), "--yes"],
            returncode=0,
            stdout=b"",
            stderr=b"",
        )

    with patch("tests.roundtrip.run_scrubmeta", side_effect=fake_scrubmeta_drop_manifest):
        failures, skipped = verify(fixture)

    assert not skipped, "Fixture should not be skipped"
    assert len(failures) > 0, "Should detect at least one failure"

    # Check that at least one failure mentions silent drop
    failure_reasons = [f.reason for f in failures]
    assert any("silently dropped" in reason.lower() for reason in failure_reasons), (
        f"Expected a failure mentioning 'silently dropped', got: {failure_reasons}"
    )
