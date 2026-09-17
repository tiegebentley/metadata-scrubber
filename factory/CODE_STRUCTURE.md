# Code Structure Standard

Guidelines the factory agent must follow when writing code, so output is
reviewable by a human or another agent with no prior context.

## Layout

    src/scrubmeta/
        __init__.py         — public API surface + intended-use docstring
        cli.py              — argparse entry point; NO business logic here
        ack.py              — first-run acknowledgment flow
        randomize.py        — replacement metadata generation
        provenance.py       — C2PA / content-credential detection
        formats/
            __init__.py     — dispatch table (extension → handler)
            jpeg.py         — one file per format, one responsibility each
            png.py
            heic.py
            mp4.py
            mkv.py
    tests/
        roundtrip.py        — the independent verification harness (do NOT import scrubmeta here)
        fixtures/
            manifest.json
            <sample files>
        test_cli.py, test_randomize.py, ...

## Rules

- **Service-layer separation.** `cli.py` parses args and calls into `formats/` and
  `randomize.py`. It contains no format-specific logic. A format handler exposes
  a single `scrub(src: Path, dst: Path, replacement: dict) -> None` function.
- **One format per file.** JPEG code lives in `jpeg.py` and nowhere else.
- **Format handlers do not import from each other.** Shared helpers go in a
  new module (e.g. `formats/common.py`) rather than reaching across siblings.
- **No dead code.** No commented-out blocks, unused imports, or "just in case" params.
- **No duplication.** Extract when it recurs, don't pre-abstract for hypothetical futures.
- **Naming over comments.** `strip_exif_segments()` beats `# strip the exif`.
- **Explicit dependencies.** Every new package added to `pyproject.toml` gets a
  one-line comment explaining why. A dep whose README describes moderation
  evasion or anti-forensics is an automatic escalation, not a PR.
- **No network at runtime.** No `requests`, `urllib`, `httpx`, no dep that phones home.
  Test/lint tooling in dev deps is fine.
- **Type hints on public functions.** mypy runs in strict-ish mode on `src/`.
- **Errors are exceptions, not exit codes.** Only `cli.py` translates to `sys.exit`.

A second agent or human with zero context on this repo should open any single
file and understand what it does in under a minute.
