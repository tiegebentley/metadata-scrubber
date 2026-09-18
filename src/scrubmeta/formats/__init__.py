"""Format dispatch. One handler per file, one file per format."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from ..randomize import Replacement

Handler = Callable[[Path, Path, Replacement], None]


class UnsupportedFormatError(RuntimeError):
    pass


def get_handler(path: Path) -> Handler:
    """Return the scrub handler for the given file, based on extension."""
    ext = path.suffix.lower()
    # Handlers are imported lazily so a missing optional dep for one format
    # doesn't break the CLI for the others.
    if ext in {".jpg", ".jpeg", ".tif", ".tiff"}:
        from . import jpeg
        return jpeg.scrub
    if ext == ".png":
        from . import png
        return png.scrub
    if ext in {".heic", ".heif"}:
        from . import heic
        return heic.scrub
    if ext in {".mp4", ".mov", ".m4v"}:
        from . import mp4
        return mp4.scrub
    if ext in {".mkv", ".webm"}:
        from . import mkv
        return mkv.scrub
    raise UnsupportedFormatError(f"No handler for extension: {ext}")
