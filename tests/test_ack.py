from __future__ import annotations

from pathlib import Path

import pytest

from scrubmeta import ack


def test_first_run_records_ack(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    assert not ack.has_acknowledged()

    lines: list[str] = []
    inputs = iter(["I own this content"])
    ok = ack.prompt_for_ack(
        input_fn=lambda _: next(inputs),
        output_fn=lines.append,
    )
    assert ok is True
    assert ack.has_acknowledged()


def test_wrong_phrase_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    inputs = iter(["nope"])
    ok = ack.prompt_for_ack(
        input_fn=lambda _: next(inputs),
        output_fn=lambda _: None,
    )
    assert ok is False
    assert not ack.has_acknowledged()
