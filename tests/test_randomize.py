from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone

import pytest

from scrubmeta.randomize import (
    Identity,
    ImpersonationRefused,
    TimeWindow,
    generate_replacement_metadata,
)


def test_defaults_are_generic() -> None:
    r = generate_replacement_metadata("image", rng=random.Random(0))
    assert r.make == "Generic"
    assert r.model == "Camera"
    assert r.gps is None
    assert r.warnings == []


def test_timestamp_falls_within_window() -> None:
    start = datetime(2020, 1, 1, tzinfo=timezone.utc)
    end = start + timedelta(days=1)
    r = generate_replacement_metadata("image", window=TimeWindow(start, end), rng=random.Random(0))
    assert start <= r.timestamp <= end


def test_identity_without_opt_in_is_refused() -> None:
    with pytest.raises(ImpersonationRefused):
        generate_replacement_metadata("image", identity=Identity(make="Apple"))


def test_identity_with_opt_in_warns_on_real_make() -> None:
    r = generate_replacement_metadata(
        "image",
        identity=Identity(make="Apple", model="iPhone 14", explicit_impersonation=True),
    )
    assert r.make == "Apple"
    assert any("Impersonating" in w for w in r.warnings)


def test_gps_requires_explicit_opt_in() -> None:
    with pytest.raises(ImpersonationRefused):
        generate_replacement_metadata("image", identity=Identity(gps=(40.7, -74.0)))


def test_gps_latitude_out_of_range_positive() -> None:
    with pytest.raises(ValueError, match=r"Latitude out of range.*90\.5.*must be \|lat\| <= 90"):
        Identity(gps=(90.5, 0.0), explicit_impersonation=True)


def test_gps_latitude_out_of_range_negative() -> None:
    with pytest.raises(ValueError, match=r"Latitude out of range.*-91.*must be \|lat\| <= 90"):
        Identity(gps=(-91.0, 0.0), explicit_impersonation=True)


def test_gps_longitude_out_of_range_positive() -> None:
    with pytest.raises(ValueError, match=r"Longitude out of range.*180\.5.*must be \|lon\| <= 180"):
        Identity(gps=(0.0, 180.5), explicit_impersonation=True)


def test_gps_longitude_out_of_range_negative() -> None:
    with pytest.raises(ValueError, match=r"Longitude out of range.*-181.*must be \|lon\| <= 180"):
        Identity(gps=(0.0, -181.0), explicit_impersonation=True)


def test_gps_valid_boundary_values() -> None:
    # Should not raise
    Identity(gps=(90.0, 180.0), explicit_impersonation=True)
    Identity(gps=(-90.0, -180.0), explicit_impersonation=True)
    Identity(gps=(0.0, 0.0), explicit_impersonation=True)


def test_exif_datetime_format() -> None:
    """Test EXIF datetime format: YYYY:MM:DD HH:MM:SS."""
    ts = datetime(2023, 6, 15, 14, 30, 45, tzinfo=timezone.utc)
    r = generate_replacement_metadata("image", window=TimeWindow(ts, ts))
    exif_dt = r.exif_datetime()
    assert exif_dt == "2023:06:15 14:30:45"

    # Round-trip: parse back and verify
    parsed = datetime.strptime(exif_dt, "%Y:%m:%d %H:%M:%S")
    assert parsed.year == 2023
    assert parsed.month == 6
    assert parsed.day == 15
    assert parsed.hour == 14
    assert parsed.minute == 30
    assert parsed.second == 45


def test_iso8601_format() -> None:
    """Test ISO 8601 format with timezone."""
    ts = datetime(2023, 6, 15, 14, 30, 45, tzinfo=timezone.utc)
    r = generate_replacement_metadata("image", window=TimeWindow(ts, ts))
    iso_dt = r.iso8601()
    # Should be ISO format with timezone
    assert "2023-06-15" in iso_dt
    assert "14:30:45" in iso_dt
    assert "+" in iso_dt or "Z" in iso_dt or "-" in iso_dt.split("T")[1]

    # Round-trip: parse back and verify
    parsed = datetime.fromisoformat(iso_dt)
    assert parsed.year == 2023
    assert parsed.month == 6
    assert parsed.day == 15
    assert parsed.hour == 14
    assert parsed.minute == 30
    assert parsed.second == 45


def test_quicktime_datetime_format() -> None:
    """Test QuickTime UTC format: YYYY-MM-DDTHH:MM:SS.000000Z."""
    ts = datetime(2023, 6, 15, 14, 30, 45, 123456, tzinfo=timezone.utc)
    r = generate_replacement_metadata("image", window=TimeWindow(ts, ts))
    qt_dt = r.quicktime_datetime()
    assert qt_dt == "2023-06-15T14:30:45.123456Z"
    assert qt_dt.endswith("Z")
    assert "T" in qt_dt

    # Round-trip: parse back and verify
    # Remove 'Z' and parse as UTC
    parsed = datetime.strptime(qt_dt, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc)
    assert parsed.year == 2023
    assert parsed.month == 6
    assert parsed.day == 15
    assert parsed.hour == 14
    assert parsed.minute == 30
    assert parsed.second == 45
    assert parsed.microsecond == 123456


def test_quicktime_datetime_converts_to_utc() -> None:
    """Test QuickTime format always outputs UTC regardless of input timezone."""
    # Create a non-UTC timezone (e.g., EST = UTC-5)
    from datetime import timezone as tz

    est = tz(timedelta(hours=-5))
    ts = datetime(2023, 6, 15, 14, 30, 45, tzinfo=est)  # 2:30 PM EST
    r = generate_replacement_metadata("image", window=TimeWindow(ts, ts))
    qt_dt = r.quicktime_datetime()

    # Should be converted to UTC (19:30:45)
    assert qt_dt.endswith("Z")
    parsed = datetime.strptime(qt_dt, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc)
    assert parsed.hour == 19  # 14 + 5 = 19 UTC
    assert parsed.minute == 30
    assert parsed.second == 45


def test_png_text_chunks_generic() -> None:
    """Test PNG text chunks contain only generic, non-identifying values."""
    r = generate_replacement_metadata("image")
    chunks = r.png_text_chunks()

    assert isinstance(chunks, dict)
    assert "Software" in chunks
    assert "Comment" in chunks

    # Values must be generic (no real device names)
    assert chunks["Software"] == "Image Editor"
    assert chunks["Comment"] == "Processed image"

    # Should NOT include device make/model
    assert "make" not in chunks.get("Software", "").lower()
    assert "model" not in chunks.get("Software", "").lower()
    assert r.make not in chunks.get("Software", "")
    assert r.model not in chunks.get("Software", "")
