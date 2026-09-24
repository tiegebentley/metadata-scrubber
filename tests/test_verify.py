"""Tests for verification report builder."""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

import pytest

from scrubmeta.verify import build_report


@pytest.fixture
def sample_gps_fixture() -> Path:
    """Path to the JPEG fixture with GPS metadata."""
    return Path(__file__).parent / "fixtures" / "sample_gps.jpg"


def test_build_report_jpeg_fixture(sample_gps_fixture: Path) -> None:
    """Test that build_report produces expected results on the JPEG fixture."""
    # Scrub the fixture using the CLI
    with tempfile.TemporaryDirectory() as td:
        temp_dir = Path(td)
        scrubbed = temp_dir / "scrubbed.jpg"

        # Run scrubmeta CLI
        result = subprocess.run(
            ["scrubmeta", str(sample_gps_fixture), "-o", str(scrubbed), "--yes"],
            capture_output=True,
        )
        assert result.returncode == 0, f"scrubmeta failed: {result.stderr.decode()}"
        assert scrubbed.exists(), "scrubbed file not created"

        # Build verification report
        report = build_report(sample_gps_fixture, scrubbed, "image")

        # Assertions per the issue spec
        assert report.pixel_identical is True, "pixels should be identical (JPEG handler is lossless)"
        assert report.stream_hash_algo == "sha256-decoded-pixels"
        assert report.metadata_removed >= 5, f"expected at least 5 removed tags, got {report.metadata_removed}"

        # Check that Make and Model are in replaced_tags (not removed)
        # The JPEG handler should replace these, not remove them
        assert "Make" in report.replaced_tags or "Model" in report.replaced_tags, (
            f"Expected Make or Model in replaced_tags, got removed={report.removed_tags}, "
            f"replaced={report.replaced_tags}"
        )

        # No warnings expected for lossless JPEG scrub
        assert len(report.warnings) == 0, f"unexpected warnings: {report.warnings}"


def test_build_report_to_dict() -> None:
    """Test that VerificationReport.to_dict() serializes correctly."""
    from scrubmeta.verify import VerificationReport

    report = VerificationReport(
        pixel_identical=True,
        stream_hash_algo="sha256-decoded-pixels",
        metadata_removed=10,
        metadata_replaced=2,
        metadata_kept_structural=5,
        removed_tags=["GPSLatitude", "GPSLongitude"],
        replaced_tags=["Make", "Model"],
        warnings=[],
    )

    d = report.to_dict()
    assert isinstance(d, dict)
    assert d["pixel_identical"] is True
    assert d["metadata_removed"] == 10
    assert d["removed_tags"] == ["GPSLatitude", "GPSLongitude"]
    assert d["replaced_tags"] == ["Make", "Model"]
