"""jpeg scrub handler. Implemented via a factory-ready issue — see ISSUES.md."""

from __future__ import annotations

from pathlib import Path

from ..randomize import Replacement


def scrub(src: Path, dst: Path, replacement: Replacement) -> None:
    """Strip metadata from src, write to dst with replacement values applied."""
    raise NotImplementedError(
        "jpeg handler is not implemented yet. File the corresponding factory-ready "
        "issue (see ISSUES.md) to have the factory build it."
    )
