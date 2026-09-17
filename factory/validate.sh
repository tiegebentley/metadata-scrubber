#!/usr/bin/env bash
# Validation gate for metadata-scrubber.
# The factory runs this independently after the agent claims it's done.
# Must exit non-zero on ANY failure — this is the hard stop the agent can't talk past.
set -euo pipefail

echo "==> Install package (editable) so scrubmeta CLI is on PATH"
# --break-system-packages is safe in the factory worktree / CI runner; on a
# dev laptop, run inside a venv instead.
if ! python3 -m pip install -e . -q 2>/dev/null; then
  python3 -m pip install -e . -q --break-system-packages
fi

echo "==> Lint"
if command -v ruff >/dev/null 2>&1; then
  ruff check .
else
  echo "ruff not installed" >&2; exit 1
fi

echo "==> Type check"
if command -v mypy >/dev/null 2>&1; then
  mypy src/
else
  echo "mypy not installed" >&2; exit 1
fi

echo "==> Unit + integration tests"
pytest -q

echo "==> Round-trip metadata assertions"
command -v exiftool >/dev/null 2>&1 || { echo "exiftool required" >&2; exit 1; }
command -v ffprobe  >/dev/null 2>&1 || { echo "ffprobe required"  >&2; exit 1; }
python3 -m tests.roundtrip --fixtures tests/fixtures --strict

echo "==> Ethical-scope guard"
BANNED_PATTERNS='phash-defeat|photodna-bypass|c2pa-strip|content-id-evade|perceptual-scrub'
if git ls-files | xargs grep -InE "$BANNED_PATTERNS" 2>/dev/null; then
  echo "Banned pattern found — see MISSION.md ethical scope." >&2
  exit 1
fi
if [ -f pyproject.toml ] && grep -InE "$BANNED_PATTERNS" pyproject.toml; then
  echo "Banned dependency in pyproject.toml — see MISSION.md ethical scope." >&2
  exit 1
fi

echo "==> All checks passed"
