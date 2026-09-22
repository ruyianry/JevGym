"""Checkpoint horizons for replaying a market's lifetime.

Two families, both used because markets have very different durations:
* Canonical time-to-resolution horizons (30d ... 1h), included only when they fall inside
  the market's [open, close] window.
* Quantile-of-lifetime checkpoints (10% ... 90%), always well-defined.
"""

from __future__ import annotations

from datetime import datetime, timedelta

# label -> seconds before close
CANONICAL_HORIZONS: list[tuple[str, int]] = [
    ("30d", 30 * 86400),
    ("14d", 14 * 86400),
    ("7d", 7 * 86400),
    ("3d", 3 * 86400),
    ("24h", 24 * 3600),
    ("12h", 12 * 3600),
    ("6h", 6 * 3600),
    ("3h", 3 * 3600),
    ("1h", 1 * 3600),
]

LIFETIME_QUANTILES: list[float] = [0.10, 0.25, 0.50, 0.75, 0.90]


class Checkpoint:
    __slots__ = ("label", "timestamp", "horizon_seconds", "lifetime_fraction", "kind")

    def __init__(self, label, timestamp, horizon_seconds, lifetime_fraction, kind):
        self.label = label
        self.timestamp = timestamp
        self.horizon_seconds = horizon_seconds
        self.lifetime_fraction = lifetime_fraction
        self.kind = kind  # "horizon" | "quantile"

    def __repr__(self) -> str:  # pragma: no cover
        return f"Checkpoint({self.label}, {self.timestamp.isoformat()})"


def checkpoints(open_dt: datetime, close_dt: datetime) -> list[Checkpoint]:
    """Return de-duplicated checkpoints (by label) within [open, close], sorted by time."""
    lifetime = (close_dt - open_dt).total_seconds()
    out: list[Checkpoint] = []
    seen: set[str] = set()

    for label, secs in CANONICAL_HORIZONS:
        ts = close_dt - timedelta(seconds=secs)
        if ts < open_dt or label in seen:
            continue
        frac = (ts - open_dt).total_seconds() / lifetime if lifetime > 0 else None
        out.append(Checkpoint(label, ts, float(secs), frac, "horizon"))
        seen.add(label)

    for q in LIFETIME_QUANTILES:
        label = f"q{int(q * 100)}"
        if label in seen:
            continue
        ts = open_dt + timedelta(seconds=lifetime * q)
        secs_to_close = (close_dt - ts).total_seconds()
        out.append(Checkpoint(label, ts, secs_to_close, q, "quantile"))
        seen.add(label)

    out.sort(key=lambda c: c.timestamp)
    return out
