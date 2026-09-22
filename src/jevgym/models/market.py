"""Kalshi catalog records: Series -> Event -> Market.

We model the documented Kalshi fields explicitly (rather than dropping them) and keep a
``metadata`` dict for the long tail. Raw payloads are NOT stored here — they live in the
raw cache and are referenced via provenance.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from .base import ProvenanceMixin


class Series(ProvenanceMixin):
    ticker: str
    title: str | None = None
    category: str | None = None
    frequency: str | None = None
    tags: list[str] = Field(default_factory=list)
    settlement_sources: list[str] = Field(default_factory=list)
    contract_url: str | None = None


class Event(ProvenanceMixin):
    event_ticker: str
    series_ticker: str | None = None
    title: str | None = None
    sub_title: str | None = None
    category: str | None = None
    market_tickers: list[str] = Field(default_factory=list)


class Market(ProvenanceMixin):
    # --- identifiers -------------------------------------------------------
    ticker: str
    event_ticker: str | None = None
    series_ticker: str | None = None
    market_type: str | None = None
    category: str | None = None

    # --- titles / descriptions --------------------------------------------
    title: str | None = None
    subtitle: str | None = None
    yes_sub_title: str | None = None
    no_sub_title: str | None = None

    # --- resolution rules --------------------------------------------------
    rules_primary: str | None = None
    rules_secondary: str | None = None

    # --- timing (all tz-aware UTC) ----------------------------------------
    created_time: datetime | None = None
    open_time: datetime | None = None
    close_time: datetime | None = None
    expiration_time: datetime | None = None
    settlement_ts: datetime | None = None

    # --- status / settlement ----------------------------------------------
    status: str | None = None  # unopened|open|paused|closed|settled
    result: str | None = None  # "yes" | "no" | "" (unsettled)
    can_close_early: bool | None = None
    settlement_value: float | None = None
    expiration_value: float | None = None

    # --- strike information -------------------------------------------------
    strike_type: str | None = None
    floor_strike: float | None = None
    cap_strike: float | None = None
    functional_strike: str | None = None
    custom_strike: dict | None = None

    # --- liquidity / activity ---------------------------------------------
    volume: float | None = None
    volume_24h: float | None = None
    open_interest: float | None = None
    liquidity: float | None = None

    @property
    def is_resolved(self) -> bool:
        return (self.status or "").lower() in {"settled", "finalized"} or bool(self.result)

    @property
    def outcome_binary(self) -> int | None:
        """1 if resolved YES, 0 if resolved NO, else None (unresolved / non-binary)."""
        r = (self.result or "").strip().lower()
        if r == "yes":
            return 1
        if r == "no":
            return 0
        return None
