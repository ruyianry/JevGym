"""The canonical benchmark snapshot.

Exactly ONE snapshot is stored per checkpoint, holding three separated blocks:

* ``public_state`` — what any model may see (market description, rules, and only the
  evidence whose ``available_at <= timestamp``).
* ``market_state`` — the contemporaneous crowd forecast p_K(t) and tradable prices. Shown
  only in the market-aware track / arena; the renderer controls visibility.
* ``outcome`` — the eventual resolution Y (the label). NEVER rendered to a model.

This single-snapshot + renderer design avoids duplicating blind vs. market-aware datasets.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from .base import JevBaseModel, ProvenanceMixin
from .evidence import EvidenceItem


class PublicState(JevBaseModel):
    market_title: str
    category: str | None = None
    rules_primary: str | None = None
    rules_secondary: str | None = None
    yes_sub_title: str | None = None
    no_sub_title: str | None = None
    open_time: datetime | None = None
    close_time: datetime | None = None
    # Only evidence available at/ before the snapshot timestamp (leakage-safe by construction).
    evidence: list[EvidenceItem] = Field(default_factory=list)


class MarketState(JevBaseModel):
    p_market: float | None = None  # p_K(t), YES probability in [0,1]
    yes_bid: float | None = None
    yes_ask: float | None = None
    last_price: float | None = None
    volume: float | None = None
    open_interest: float | None = None


class Outcome(JevBaseModel):
    resolved: bool = False
    result: str | None = None  # "yes" | "no"
    y: int | None = None  # binary label: 1 (YES) / 0 (NO)
    settlement_ts: datetime | None = None
    settlement_value: float | None = None


class Snapshot(ProvenanceMixin):
    snapshot_id: str
    market_ticker: str
    event_ticker: str | None = None
    series_ticker: str | None = None
    domain: str = "other"  # economics | weather | crypto | sports | politics | ...

    timestamp: datetime  # the "now" of this replay checkpoint
    forecast_horizon: str  # canonical label, e.g. "7d" or "q50"
    horizon_seconds: float | None = None  # seconds to resolution at this checkpoint
    lifetime_fraction: float | None = None  # position within [open, close] in [0,1]

    candidates: list[str] = Field(default_factory=lambda: ["YES", "NO"])
    question_kind: str = "binary"

    public_state: PublicState
    market_state: MarketState
    outcome: Outcome

    split: str | None = None  # "train" | "validation" | "test"
    # Market-implied uncertainty band (a confidence axis, NOT reasoning difficulty). Curated
    # reasoning-requirement difficulty lives in the separate difficulty_annotations table.
    uncertainty_band: str = "unknown"  # easy | medium | hard | unknown (by |p-0.5|)
    sensitive: bool = False  # politics / war / elections -> quarantined from default publish
