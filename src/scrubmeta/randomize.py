"""Generate replacement metadata. Deliberately generic — see MISSION.md."""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Literal

Kind = Literal["image", "video"]


@dataclass
class Identity:
    """Explicit identity overrides. Impersonation requires opt-in."""

    make: str | None = None
    model: str | None = None
    gps: tuple[float, float] | None = None
    explicit_impersonation: bool = False


@dataclass
class TimeWindow:
    """Random timestamp will fall within [start, end]."""

    start: datetime
    end: datetime

    @classmethod
    def past_days(cls, days: int = 30) -> TimeWindow:
        now = datetime.now(timezone.utc)
        return cls(start=now - timedelta(days=days), end=now)


@dataclass
class Replacement:
    make: str
    model: str
    timestamp: datetime
    gps: tuple[float, float] | None = None
    warnings: list[str] = field(default_factory=list)


class ImpersonationRefused(ValueError):
    """Raised when caller asked to impersonate a real identity without opt-in."""


_KNOWN_REAL_MAKES = {"apple", "samsung", "google", "canon", "nikon", "sony", "fujifilm", "leica"}


def generate_replacement_metadata(
    kind: Kind,
    window: TimeWindow | None = None,
    identity: Identity | None = None,
    rng: random.Random | None = None,
) -> Replacement:
    """Return generic replacement metadata.

    Refuses to impersonate a real device or supply GPS unless the caller
    explicitly opts in via `Identity.explicit_impersonation=True`.
    """
    del kind  # currently identical for image/video; parameter kept for future divergence
    r = rng or random.Random()
    window = window or TimeWindow.past_days(30)

    make = "Generic"
    model = "Camera"
    gps: tuple[float, float] | None = None
    warnings: list[str] = []

    if identity is not None:
        if (identity.make or identity.model or identity.gps) and not identity.explicit_impersonation:
            raise ImpersonationRefused(
                "Identity overrides (make/model/gps) require explicit_impersonation=True. "
                "See MISSION.md ethical scope."
            )
        if identity.make and identity.make.lower() in _KNOWN_REAL_MAKES:
            warnings.append(
                f"Impersonating a real camera make: {identity.make!r}. This is discouraged "
                "outside personal-privacy use on files you own."
            )
        make = identity.make or make
        model = identity.model or model
        gps = identity.gps

    span = (window.end - window.start).total_seconds()
    ts = window.start + timedelta(seconds=r.random() * span)

    return Replacement(make=make, model=model, timestamp=ts, gps=gps, warnings=warnings)
