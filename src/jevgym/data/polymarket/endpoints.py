"""Polymarket API endpoints. Public reads need no auth.

* Gamma (metadata/resolution): https://gamma-api.polymarket.com
* CLOB (price history): https://clob.polymarket.com/prices-history
"""

from __future__ import annotations

GAMMA_BASE = "https://gamma-api.polymarket.com"
CLOB_BASE = "https://clob.polymarket.com"

MARKETS = "/markets"
EVENTS = "/events"
PRICES_HISTORY = "/prices-history"
