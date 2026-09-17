"""
Round-trip verification harness for scrubmeta.

Runs from validate.sh. The point of this file is that it does NOT trust
scrubmeta's self-report. It shells out to exiftool and ffprobe — tools that
have no knowledge of scrubmeta — snapshots the source, runs scrubmeta,
snapshots the output, and diffs them independently.

If this file starts importing from src/scrubmeta/ for anything other than the
CLI entry point, something has gone wrong.

Fixture manifest format (tests/fixtures/manifest.json):

    {
      "fixtures": [
        {
          "path": "sample_gps.jpg",
          "kind": "image",
          "has_c2pa": false,
          "lossy_allowed": false,
          "lossy_reason": null,
          "expected_stripped_tags": ["GPSLatitude", "GPSLongitude", "SerialNumber"],
          "skip_if_unimplemented": true
        }
      ]
    }

Usage:
    python -m tests.roundtrip --fixtures tests/fixtures --strict
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

STRUCTURAL_TAGS = frozenset({
    "FileName", "FileSize", "FileType", "FileTypeExtension", "MIMEType",
    "ImageWidth", "ImageHeight", "BitsPerSample", "ColorComponents",
    "EncodingProcess", "YCbCrSubSampling", "ExifByteOrder",
    "Directory", "FilePermissions", "FileModifyDate", "FileAccessDate",
    "FileInodeChangeDate", "ExifToolVersion", "SourceFile",
    "codec_name", "codec_type", "codec_tag_string", "codec_tag",
    "width", "height", "coded_width", "coded_height", "pix_fmt",
    "sample_fmt", "sample_rate", "channels", "channel_layout",
    "duration", "duration_ts", "nb_frames", "bit_rate", "time_base",
    "start_time", "start_pts", "r_frame_rate", "avg_frame_rate",
    "profile", "level", "refs", "is_avc", "nal_length_size",
    "format_name", "format_long_name", "nb_streams", "nb_programs",
    "probe_score", "size",
})


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


def snapshot_metadata(path: Path, kind: str) -> dict[str, object]:
    if kind == "image":
        out = subprocess.check_output(
            ["exiftool", "-j", "-G", "-a", "-u", "-n", str(path)],
            stderr=subprocess.DEVNULL,
        )
        data = json.loads(out)[0]
        stripped: dict[str, object] = {}
        for k, v in data.items():
            bare = k.split(":", 1)[-1]
            stripped[bare] = v
        return stripped
    if kind == "video":
        out = subprocess.check_output(
            [
                "ffprobe", "-v", "quiet", "-print_format", "json",
                "-show_format", "-show_streams", "-show_chapters", str(path),
            ],
        )
        probe = json.loads(out)
        flat: dict[str, object] = {}
        for k, v in (probe.get("format", {}) or {}).items():
            flat[k] = v
        for tag_k, tag_v in (probe.get("format", {}).get("tags", {}) or {}).items():
            flat[f"format.tags.{tag_k}"] = tag_v
        for i, stream in enumerate(probe.get("streams", []) or []):
            for k, v in stream.items():
                if k == "tags":
                    for tk, tv in (v or {}).items():
                        flat[f"stream{i}.tags.{tk}"] = tv
                else:
                    flat[f"stream{i}.{k}"] = v
        return flat
    raise ValueError(f"unknown fixture kind: {kind}")


def stream_hash(path: Path, kind: str) -> str:
    if kind == "image":
        if shutil.which("magick"):
            proc = subprocess.run(
                ["magick", str(path), "-strip", "RGB:-"],
                capture_output=True, check=True,
            )
            return hashlib.sha256(proc.stdout).hexdigest()
        from PIL import Image  # type: ignore
        with Image.open(path) as im:
            return hashlib.sha256(im.tobytes()).hexdigest()
    if kind == "video":
        with tempfile.TemporaryDirectory() as td:
            raw = Path(td) / "raw.nut"
            subprocess.check_call(
                [
                    "ffmpeg", "-y", "-v", "error", "-i", str(path),
                    "-map", "0", "-map_metadata", "-1",
                    "-c", "copy", "-f", "nut", str(raw),
                ],
            )
            return hashlib.sha256(raw.read_bytes()).hexdigest()
    raise ValueError(kind)


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
