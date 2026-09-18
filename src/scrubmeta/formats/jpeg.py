"""JPEG/TIFF scrub handler. Strips all metadata, writes replacement EXIF."""

from __future__ import annotations

import hashlib
from pathlib import Path

import piexif  # type: ignore[import-untyped]
from PIL import Image

from ..randomize import Replacement


def scrub(src: Path, dst: Path, replacement: Replacement) -> None:
    """Strip all metadata from JPEG/TIFF, write replacement EXIF, preserve pixels."""
    # Capture original decoded pixel hash for verification
    with Image.open(src) as img:
        original_pixels = img.tobytes()
        original_hash = hashlib.sha256(original_pixels).hexdigest()

    # Build minimal replacement EXIF
    exif_dict = {
        "0th": {
            piexif.ImageIFD.Make: replacement.make.encode("utf-8"),
            piexif.ImageIFD.Model: replacement.model.encode("utf-8"),
            piexif.ImageIFD.DateTime: replacement.exif_datetime().encode("ascii"),
        },
        "Exif": {
            piexif.ExifIFD.DateTimeOriginal: replacement.exif_datetime().encode("ascii"),
            piexif.ExifIFD.DateTimeDigitized: replacement.exif_datetime().encode("ascii"),
        },
    }

    # Only add GPS if provided
    if replacement.gps is not None:
        lat, lon = replacement.gps
        lat_deg = int(abs(lat))
        lat_min = int((abs(lat) - lat_deg) * 60)
        lat_sec = int(((abs(lat) - lat_deg) * 60 - lat_min) * 60 * 100)

        lon_deg = int(abs(lon))
        lon_min = int((abs(lon) - lon_deg) * 60)
        lon_sec = int(((abs(lon) - lon_deg) * 60 - lon_min) * 60 * 100)

        exif_dict["GPS"] = {
            piexif.GPSIFD.GPSVersionID: (2, 3, 0, 0),  # type: ignore[dict-item]
            piexif.GPSIFD.GPSLatitudeRef: b"N" if lat >= 0 else b"S",
            piexif.GPSIFD.GPSLatitude: ((lat_deg, 1), (lat_min, 1), (lat_sec, 100)),  # type: ignore[dict-item]
            piexif.GPSIFD.GPSLongitudeRef: b"E" if lon >= 0 else b"W",
            piexif.GPSIFD.GPSLongitude: ((lon_deg, 1), (lon_min, 1), (lon_sec, 100)),  # type: ignore[dict-item]
        }

    exif_bytes = piexif.dump(exif_dict)

    # Use piexif to remove all metadata and insert only replacement EXIF
    # This preserves the JPEG encoding without re-compression
    piexif.remove(str(src), str(dst))
    piexif.insert(exif_bytes, str(dst))

    # Verify decoded pixels are preserved
    with Image.open(dst) as result_img:
        result_pixels = result_img.tobytes()
        result_hash = hashlib.sha256(result_pixels).hexdigest()

        if result_hash != original_hash:
            raise RuntimeError(
                f"Pixel data changed during JPEG scrub: {src.name} "
                f"(original: {original_hash[:12]}, result: {result_hash[:12]}). "
                "This indicates lossy re-encoding occurred."
            )
