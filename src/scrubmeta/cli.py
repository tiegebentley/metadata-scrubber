"""CLI entry point. Parses args, dispatches to service layer. No logic here."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import INTENDED_USE_NOTICE, __version__
from .ack import has_acknowledged, prompt_for_ack
from .formats import UnsupportedFormatError, get_handler
from .provenance import ProvenanceStripRefused, has_c2pa_manifest
from .randomize import Identity, generate_replacement_metadata


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="scrubmeta",
        description=INTENDED_USE_NOTICE,
    )
    p.add_argument("input", type=Path, help="File to scrub.")
    p.add_argument("-o", "--output", type=Path, help="Output path. Defaults to <input>.scrubbed.<ext>.")
    p.add_argument("--yes", action="store_true", help="Skip the interactive acknowledgment (after first-run).")
    p.add_argument("--strip-provenance", action="store_true", help="Strip C2PA/content-credential manifests. Requires --i-own-this-content.")
    p.add_argument("--i-own-this-content", action="store_true", help="Required alongside --strip-provenance.")
    p.add_argument("--version", action="version", version=f"scrubmeta {__version__}")
    return p


def default_output(src: Path) -> Path:
    return src.with_name(f"{src.stem}.scrubbed{src.suffix}")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if not has_acknowledged() and not args.yes:
        if not prompt_for_ack():
            return 2

    src: Path = args.input
    if not src.exists():
        print(f"error: input file not found: {src}", file=sys.stderr)
        return 1

    if has_c2pa_manifest(src) and not args.strip_provenance:
        print(
            f"error: {src.name} contains a C2PA content-credential manifest. "
            "The default is to preserve provenance. Pass --strip-provenance "
            "AND --i-own-this-content if you're certain, and you own it.",
            file=sys.stderr,
        )
        return 3

    if args.strip_provenance and not args.i_own_this_content:
        raise ProvenanceStripRefused(
            "--strip-provenance requires --i-own-this-content. See MISSION.md."
        )

    dst: Path = args.output or default_output(src)

    try:
        handler = get_handler(src)
    except UnsupportedFormatError as e:
        print(f"error: {e}", file=sys.stderr)
        return 4

    replacement = generate_replacement_metadata(
        kind="image" if src.suffix.lower() in {".jpg", ".jpeg", ".png", ".heic", ".heif", ".tif", ".tiff"} else "video",
        identity=Identity(),
    )

    try:
        handler(src, dst, replacement)
    except NotImplementedError as e:
        print(f"error: {e}", file=sys.stderr)
        return 5

    print(f"wrote {dst}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
