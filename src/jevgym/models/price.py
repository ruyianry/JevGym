"""Normalized market price observations (one per market x timestamp x interval).

Prices are stored in **probability units** ([0, 1]) rather than cents/dollars, so a YES
price reads directly as the market-implied probability p_K(t). Multiple temporal
resolutions are retained separately (``source_interval``) rather than collapsing to daily
closes — the sequential arena depends on fine-grained trajectories.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from .base import ProvenanceMixin


class PricePoint(ProvenanceMixin):
    market_ticker: str
    timestamp: datetime

    yes_bid: float | None = None  # probability units [0,1]
    yes_ask: float | None = None
    last_price: float | None = None

    volume: float | None = None
    open_interest: float | None = None

    source_interval: str = "1h"  # "1m" | "1h" | "1d"

    # Full OHLC (per side) retained when available, for later trading realism.
    ohlc: dict = Field(default_factory=dict)

    @property
    def mid(self) -> float | None:
        if self.yes_bid is not None and self.yes_ask is not None:
            return (self.yes_bid + self.yes_ask) / 2.0
        return self.last_price

    @property
    def no_ask(self) -> float | None:
        """Ask to *buy NO* ≈ 1 - yes_bid (buying NO means selling YES at the bid)."""
        return None if self.yes_bid is None else 1.0 - self.yes_bid
