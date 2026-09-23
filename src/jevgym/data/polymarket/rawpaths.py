"""Relative paths inside the raw cache for Polymarket payloads."""

from __future__ import annotations

POLY_MARKETS = "polymarket/markets.jsonl"
POLY_PRICES_DIR = "polymarket/prices"


def poly_prices(condition_id: str) -> str:
    safe = str(condition_id).replace("/", "_")
    return f"{POLY_PRICES_DIR}/{safe}.json"
