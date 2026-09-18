"""First-run acknowledgment flow. See MISSION.md ethical scope."""

from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path

from . import INTENDED_USE_NOTICE

_ACK_PHRASE = "I own this content"


def ack_path() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "scrubmeta" / "ack"


def has_acknowledged(path: Path | None = None) -> bool:
    return (path or ack_path()).exists()


def record_acknowledgment(path: Path | None = None) -> None:
    p = path or ack_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("acknowledged\n")


def prompt_for_ack(
    input_fn: Callable[[str], str] = input,
    output_fn: Callable[[str], None] = print,
    path: Path | None = None,
) -> bool:
    """Prompt the user; return True if they acknowledged."""
    output_fn(INTENDED_USE_NOTICE)
    output_fn(f"To continue, type exactly: {_ACK_PHRASE}")
    answer = input_fn("> ").strip()
    if answer == _ACK_PHRASE:
        record_acknowledgment(path)
        return True
    output_fn("Acknowledgment not given. Exiting.")
    return False
