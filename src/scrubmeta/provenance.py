"""C2PA / content-credential detection. See MISSION.md ethical scope."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path


def has_c2pa_manifest(path: Path) -> bool:
    """Return True if the file contains a C2PA/JUMBF manifest.

    Uses exiftool because it's the same tool the validation harness uses,
    so detection here is consistent with the gate that catches silent drops.
    """
    try:
        out = subprocess.check_output(
            ["exiftool", "-j", "-G", "-jumbf:all", str(path)],
            stderr=subprocess.DEVNULL,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False

    try:
        data = json.loads(out)[0]
    except (json.JSONDecodeError, IndexError):
        return False

    return any(k.startswith("JUMBF:") or "C2PA" in k for k in data.keys())


class ProvenanceStripRefused(RuntimeError):
    """Raised when caller tried to strip a C2PA manifest without proper opt-in."""
