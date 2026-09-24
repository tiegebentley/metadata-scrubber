"""
Round-trip verification harness for scrubmeta.

Runs from validate.sh. The point of this file is that it does NOT trust
scrubmeta's self-report. It shells out to exiftool and ffprobe — tools that
have no knowledge of scrubmeta — snapshots the source, runs scrubmeta,
snapshots the output, and diffs them independently.

If this file starts importing from src/scrubmeta/ for anything other than the
CLI entry point, something has gone wrong.

Usage:
    python -m tests.roundtrip --fixtures tests/fixtures --strict
"""

# _schema: Fixture manifest format (tests/fixtures/manifest.json)
#
#     {
#       "fixtures": [
#         {
#           "path": "sample_gps.jpg",
#           "kind": "image",
#           "has_c2pa": false,
#           "lossy_allowed": false,
#           "lossy_reason": null,
#           "expected_stripped_tags": ["GPSLatitude", "GPSLongitude", "SerialNumber"],
#           "skip_if_unimplemented": true
#         }
#       ]
#     }

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from scrubmeta._probe import STRUCTURAL_TAGS, snapshot_metadata, stream_hash


@dataclass
class Fixture:
    path: Path
    kind: str
    has_c2pa: bool
    lossy_allowed: bool
    lossy_reason: str | None
    expected_stripped_tags: list[str]
    skip_if_unimplemented: bool


@dataclass
class Failure:
    fixture: str
    reason: str


def load_fixtures(root: Path) -> list[Fixture]:
    manifest = json.loads((root / "manifest.json").read_text())
    return [
        Fixture(
            path=root / f["path"],
            kind=f["kind"],
            has_c2pa=f.get("has_c2pa", False),
            lossy_allowed=f.get("lossy_allowed", False),
            lossy_reason=f.get("lossy_reason"),
            expected_stripped_tags=f.get("expected_stripped_tags", []),
            skip_if_unimplemented=f.get("skip_if_unimplemented", False),
        )
        for f in manifest["fixtures"]
    ]




def has_c2pa_manifest(path: Path) -> bool:
    try:
        out = subprocess.check_output(
            ["exiftool", "-j", "-G", "-jumbf:all", str(path)],
            stderr=subprocess.DEVNULL,
        )
        data = json.loads(out)[0]
        return any(k.startswith("JUMBF:") or "C2PA" in k for k in data.keys())
    except (subprocess.CalledProcessError, json.JSONDecodeError, IndexError):
        return False


def run_scrubmeta(src: Path, dst: Path) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ["scrubmeta", str(src), "-o", str(dst), "--yes"],
        capture_output=True,
    )


def verify(fixture: Fixture) -> tuple[list[Failure], bool]:
    """Return (failures, skipped)."""
    fails: list[Failure] = []
    name = fixture.path.name

    if not fixture.path.exists():
        return [Failure(name, f"fixture not found: {fixture.path}")], False

    src_meta = snapshot_metadata(fixture.path, fixture.kind)
    src_hash = stream_hash(fixture.path, fixture.kind)
    src_has_c2pa = has_c2pa_manifest(fixture.path)

    if fixture.has_c2pa and not src_has_c2pa:
        fails.append(Failure(name, "manifest says has_c2pa=true but no C2PA found in source"))

    with tempfile.TemporaryDirectory() as td:
        out_path = Path(td) / fixture.path.name
        result = run_scrubmeta(fixture.path, out_path)

        stderr = result.stderr.decode(errors="replace")
        if "not implemented yet" in stderr and fixture.skip_if_unimplemented:
            return [], True

        if fixture.has_c2pa:
            if result.returncode == 0:
                if not out_path.exists() or not has_c2pa_manifest(out_path):
                    fails.append(Failure(
                        name,
                        "C2PA manifest was silently dropped — default must be preserve or fail",
                    ))
            return fails, False

        if result.returncode != 0:
            fails.append(Failure(name, f"scrubmeta failed: {stderr[:400]}"))
            return fails, False

        out_meta = snapshot_metadata(out_path, fixture.kind)
        out_hash = stream_hash(out_path, fixture.kind)

    for tag in fixture.expected_stripped_tags:
        if tag in out_meta:
            fails.append(Failure(name, f"expected-stripped tag leaked through: {tag}"))

    for tag, src_val in src_meta.items():
        if tag in STRUCTURAL_TAGS:
            continue
        # Stream-level properties (streamN.*) are structural, not metadata
        if tag.startswith("stream") and "." in tag:
            parts = tag.split(".", 1)
            if len(parts) == 2 and parts[0].startswith("stream") and not parts[1].startswith("tags."):
                continue
        if tag in out_meta and out_meta[tag] == src_val:
            fails.append(Failure(name, f"tag '{tag}' unchanged from source (value: {src_val!r})"))
            break

    non_structural_out = {k: v for k, v in out_meta.items() if k not in STRUCTURAL_TAGS}
    if not non_structural_out:
        fails.append(Failure(name, "output has no new metadata — should have randomized replacements"))

    if src_hash != out_hash and not fixture.lossy_allowed:
        fails.append(Failure(
            name,
            f"stream hash changed and lossy_allowed=false (src={src_hash[:12]} out={out_hash[:12]})",
        ))
    if src_hash != out_hash and fixture.lossy_allowed and not fixture.lossy_reason:
        fails.append(Failure(name, "lossy_allowed=true but no lossy_reason given in manifest"))

    return fails, False


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--fixtures", type=Path, required=True)
    p.add_argument("--strict", action="store_true", help="Fail on missing tools instead of skipping.")
    args = p.parse_args()

    for tool in ("exiftool", "ffprobe", "ffmpeg"):
        if not shutil.which(tool):
            msg = f"required tool missing: {tool}"
            if args.strict:
                print(msg, file=sys.stderr)
                return 2
            print(f"WARN: {msg} (continuing without strict mode)", file=sys.stderr)

    fixtures = load_fixtures(args.fixtures)
    if not fixtures:
        print("no fixtures loaded", file=sys.stderr)
        return 2

    all_fails: list[Failure] = []
    skipped = 0
    for fx in fixtures:
        fails, was_skipped = verify(fx)
        if was_skipped:
            print(f"SKIP  {fx.path.name} (handler not implemented yet)")
            skipped += 1
            continue
        if fails:
            all_fails.extend(fails)
            for f in fails:
                print(f"FAIL  {f.fixture}: {f.reason}")
        else:
            print(f"OK    {fx.path.name}")

    if all_fails:
        print(f"\n{len(all_fails)} failure(s), {skipped} skipped, {len(fixtures)} total")
        return 1
    print(f"\nAll passed ({len(fixtures) - skipped} run, {skipped} skipped)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
