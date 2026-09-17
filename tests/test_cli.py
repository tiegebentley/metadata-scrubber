from __future__ import annotations

from pathlib import Path

import pytest

from scrubmeta import ack, cli


def test_help_exits_zero(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as excinfo:
        cli.build_parser().parse_args(["--help"])
    assert excinfo.value.code == 0


def test_missing_input_returns_1(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    ack.record_acknowledgment()
    rc = cli.main([str(tmp_path / "does-not-exist.jpg"), "--yes"])
    assert rc == 1


def test_default_output_path() -> None:
    src = Path("/tmp/photo.jpg")
    assert cli.default_output(src) == Path("/tmp/photo.scrubbed.jpg")
