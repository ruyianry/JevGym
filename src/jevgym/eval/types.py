"""Shared eval record types."""

from __future__ import annotations

from ..models.base import JevBaseModel

TRACK_BLIND = "blind"
TRACK_MARKET_AWARE = "market_aware"


class Prediction(JevBaseModel):
    provider: str
    model_id: str
    track: str  # "blind" | "market_aware"

    snapshot_id: str
    market_ticker: str
    event_ticker: str | None = None
    domain: str = "other"
    horizon: str = ""
    uncertainty_band: str = "unknown"
    split: str | None = None

    p_yes: float
    y: int
    latency_ms: float | None = None
