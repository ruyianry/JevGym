"""Polymarket ingestion into the raw cache (live crawl or offline fixtures).

Stores binary resolved markets + the YES-token price history. Downstream parsing normalizes
these into the same ``Market``/``PricePoint`` records as Kalshi (tagged
``source_provider='polymarket'``), so snapshots, eval, and the HF dataset combine both sources.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from ...config import Settings
from ..kalshi.rawcache import RawCache
from . import endpoints as ep
from . import fixtures, rawpaths
from .client import PolymarketClient


@dataclass
class PolymarketIngestConfig:
    closed: bool = True
    max_markets: int | None = 500
    categories: list[str] = field(default_factory=list)


def _parse_strlist(s) -> list:
    if isinstance(s, list):
        return s
    if isinstance(s, str):
        try:
            return json.loads(s)
        except json.JSONDecodeError:
            return []
    return []


def is_binary(o: dict) -> bool:
    outs = {str(x).strip().lower() for x in _parse_strlist(o.get("outcomes"))}
    return outs == {"yes", "no"}


def yes_token(o: dict) -> str | None:
    outcomes = _parse_strlist(o.get("outcomes"))
    tokens = _parse_strlist(o.get("clobTokenIds"))
    if len(outcomes) == len(tokens):
        for oc, tk in zip(outcomes, tokens, strict=True):
            if str(oc).strip().lower() == "yes":
                return tk
    return tokens[0] if tokens else None


def ingest_polymarket(settings: Settings, config: PolymarketIngestConfig | None = None, *, client: PolymarketClient | None = None) -> dict:
    config = config or PolymarketIngestConfig()
    rc = RawCache(settings.paths.raw)
    owns = client is None
    client = client or PolymarketClient()
    try:
        markets: list[dict] = []
        n_prices = 0
        for m in client.iter_markets(closed=config.closed, max_items=config.max_markets):
            if not is_binary(m):
                continue
            markets.append(m)
            cid = m.get("conditionId") or m.get("id") or m.get("slug")
            tok = yes_token(m)
            if cid and tok:
                try:
                    hist = client.get_price_history(tok)
                except Exception:
                    hist = []
                rc.write_blob(
                    rawpaths.poly_prices(cid),
                    {"condition_id": cid, "token_id": tok, "interval_label": "12h", "history": hist},
                    endpoint="/prices-history",
                )
                n_prices += 1
        rc.write_records(rawpaths.POLY_MARKETS, markets, endpoint=ep.MARKETS)
        return {"markets": len(markets), "price_sets": n_prices}
    finally:
        if owns:
            client.close()


def seed_from_fixtures(settings: Settings, raw: dict | None = None) -> dict:
    raw = raw or fixtures.build_polymarket_demo_raw()
    rc = RawCache(settings.paths.raw)
    rc.write_records(rawpaths.POLY_MARKETS, raw["markets"], endpoint=ep.MARKETS)
    for cid, blob in raw["prices"].items():
        rc.write_blob(rawpaths.poly_prices(cid), blob, endpoint="/prices-history")
    return {"markets": len(raw["markets"]), "price_sets": len(raw["prices"])}
