"""Kalshi Trade API v2 endpoint paths (relative to the configured base URL).

Reference: https://docs.kalshi.com/api-reference . Base URL defaults to
``https://external-api.kalshi.com/trade-api/v2``. Public reads require no auth.
"""

from __future__ import annotations

SERIES = "/series"
EVENTS = "/events"
MARKETS = "/markets"


def market(ticker: str) -> str:
    return f"/markets/{ticker}"


def event(event_ticker: str) -> str:
    return f"/events/{event_ticker}"


def market_candlesticks(series_ticker: str, ticker: str) -> str:
    return f"/series/{series_ticker}/markets/{ticker}/candlesticks"


def historical_market_candlesticks(ticker: str) -> str:
    """For markets/candlesticks past the dynamic historical cutoff (archived/resolved)."""
    return f"/historical/markets/{ticker}/candlesticks"


# Period interval (minutes) accepted by the candlesticks endpoints.
PERIOD_1M = 1
PERIOD_1H = 60
PERIOD_1D = 1440

INTERVAL_LABEL = {PERIOD_1M: "1m", PERIOD_1H: "1h", PERIOD_1D: "1d"}
