"""Canonical relative paths inside the raw cache (shared by ingest / parse / evidence)."""

from __future__ import annotations

KALSHI_SERIES = "kalshi/series.jsonl"
KALSHI_EVENTS = "kalshi/events.jsonl"
KALSHI_MARKETS = "kalshi/markets.jsonl"
KALSHI_CANDLES_DIR = "kalshi/candlesticks"

FRED_DIR = "fred"

WEATHER_MARKETS = "weather/markets.jsonl"
WEATHER_CANDLES_DIR = "weather/candlesticks"
WEATHER_OBS_DIR = "weather/obs"


def kalshi_candles(ticker: str) -> str:
    return f"{KALSHI_CANDLES_DIR}/{ticker}.json"


def fred_series(series_id: str) -> str:
    return f"{FRED_DIR}/{series_id}.json"


def weather_candles(ticker: str) -> str:
    return f"{WEATHER_CANDLES_DIR}/{ticker}.json"


def weather_obs(station_id: str, measurement: str) -> str:
    return f"{WEATHER_OBS_DIR}/{station_id}_{measurement}.json"
