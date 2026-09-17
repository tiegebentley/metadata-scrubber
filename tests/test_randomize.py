from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone

import pytest

from scrubmeta.randomize import (
    Identity,
    ImpersonationRefused,
    TimeWindow,
    generate_replacement_metadata,
)


def test_defaults_are_generic() -> None:
    r = generate_replacement_metadata("image", rng=random.Random(0))
    assert r.make == "Generic"
    assert r.model == "Camera"
    assert r.gps is None
    assert r.warnings == []


def test_timestamp_falls_within_window() -> None:
    start = datetime(2020, 1, 1, tzinfo=timezone.utc)
    end = start + timedelta(days=1)
    r = generate_replacement_metadata("image", window=TimeWindow(start, end), rng=random.Random(0))
    assert start <= r.timestamp <= end


def test_identity_without_opt_in_is_refused() -> None:
    with pytest.raises(ImpersonationRefused):
        generate_replacement_metadata("image", identity=Identity(make="Apple"))


def test_identity_with_opt_in_warns_on_real_make() -> None:
    r = generate_replacement_metadata(
        "image",
        identity=Identity(make="Apple", model="iPhone 14", explicit_impersonation=True),
    )
    assert r.make == "Apple"
    assert any("Impersonating" in w for w in r.warnings)


def test_gps_requires_explicit_opt_in() -> None:
    with pytest.raises(ImpersonationRefused):
        generate_replacement_metadata("image", identity=Identity(gps=(40.7, -74.0)))
