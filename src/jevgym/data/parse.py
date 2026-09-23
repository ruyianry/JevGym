"""Normalize raw Kalshi payloads into typed, provenance-stamped records.

Raw cache -> ``data/normalized/{series,events,markets,price_history}.jsonl``. Prices are
converted from cents to probability units here (Kalshi candlesticks are quoted in cents).
"""

from __future__ import annotations

import json
from collections.abc import Iterator

from ..config import Settings
from ..io import read_model_jsonl, write_model_jsonl
from ..models import Event, Market, PricePoint, Series
from ..util import from_unix, parse_dt, utcnow
from .kalshi import rawpaths
from .kalshi.endpoints import INTERVAL_LABEL
from .kalshi.rawcache import RawCache
from .polymarket import rawpaths as poly_rawpaths

NORM_SERIES = "series.jsonl"
NORM_EVENTS = "events.jsonl"
NORM_MARKETS = "markets.jsonl"
NORM_PRICES = "price_history.jsonl"


def _num(x) -> float | None:
    if x is None or x == "":
        return None
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def price_to_prob(x, units: str = "cents") -> float | None:
    v = _num(x)
    if v is None:
        return None
    return v / 100.0 if units == "cents" else v


def _candle_prob(field) -> float | None:
    """Probability in [0,1] from a candlestick price field, across Kalshi schema variants.

    Live candlesticks nest dollar strings (``{"close_dollars": "0.0100", ...}`` == 1c == 0.01);
    the older/fixture schema nests cents (``{"close": 20}``) or a bare cents integer.
    """
    if isinstance(field, dict):
        for k in ("close_dollars", "mean_dollars", "open_dollars"):
            if field.get(k) not in (None, ""):
                v = _num(field[k])
                if v is not None:
                    return v  # already in dollars == probability units
        for k in ("close", "mean", "open"):
            if field.get(k) not in (None, ""):
                v = _num(field[k])
                if v is not None:
                    return v / 100.0  # cents -> probability
        return None
    return price_to_prob(field)


def _series_from_event(event_ticker: str | None) -> str | None:
    return event_ticker.split("-")[0] if event_ticker else None


# --- record builders -------------------------------------------------------
def _market_from_wrapper(w: dict) -> Market:
    o = w["obj"]
    retrieved = parse_dt(w.get("retrieved_at")) or utcnow()
    created = parse_dt(o.get("created_time"))
    open_t = parse_dt(o.get("open_time"))
    available = created or open_t or retrieved
    return Market(
        ticker=o["ticker"],
        event_ticker=o.get("event_ticker"),
        series_ticker=o.get("series_ticker") or _series_from_event(o.get("event_ticker")),
        market_type=o.get("market_type"),
        category=o.get("category"),
        title=o.get("title"),
        subtitle=o.get("subtitle"),
        yes_sub_title=o.get("yes_sub_title"),
        no_sub_title=o.get("no_sub_title"),
        rules_primary=o.get("rules_primary"),
        rules_secondary=o.get("rules_secondary"),
        created_time=created,
        open_time=open_t,
        close_time=parse_dt(o.get("close_time")),
        expiration_time=parse_dt(
            o.get("expiration_time")
            or o.get("latest_expiration_time")
            or o.get("expected_expiration_time")
        ),
        settlement_ts=parse_dt(o.get("settlement_ts") or o.get("settlement_time")),
        status=o.get("status"),
        result=o.get("result"),
        can_close_early=o.get("can_close_early"),
        settlement_value=_num(o.get("settlement_value") or o.get("settlement_value_dollars")),
        expiration_value=_num(o.get("expiration_value")),
        strike_type=o.get("strike_type"),
        floor_strike=_num(o.get("floor_strike")),
        cap_strike=_num(o.get("cap_strike")),
        functional_strike=o.get("functional_strike"),
        custom_strike=o.get("custom_strike") if isinstance(o.get("custom_strike"), dict) else None,
        volume=_num(o.get("volume") or o.get("volume_fp")),
        volume_24h=_num(o.get("volume_24h") or o.get("volume_24h_fp")),
        open_interest=_num(o.get("open_interest") or o.get("open_interest_fp")),
        liquidity=_num(o.get("liquidity") or o.get("liquidity_dollars")),
        source_provider="kalshi",
        source_endpoint=w.get("endpoint", "/markets"),
        source_identifier=o["ticker"],
        retrieved_at=retrieved,
        available_at=available,
    )


def _event_from_wrapper(w: dict) -> Event:
    o = w["obj"]
    retrieved = parse_dt(w.get("retrieved_at")) or utcnow()
    return Event(
        event_ticker=o["event_ticker"],
        series_ticker=o.get("series_ticker") or _series_from_event(o.get("event_ticker")),
        title=o.get("title"),
        sub_title=o.get("sub_title"),
        category=o.get("category"),
        market_tickers=[m.get("ticker") for m in (o.get("markets") or []) if m.get("ticker")],
        source_provider="kalshi",
        source_endpoint=w.get("endpoint", "/events"),
        source_identifier=o["event_ticker"],
        retrieved_at=retrieved,
        available_at=retrieved,
    )


def _series_from_wrapper(w: dict) -> Series:
    o = w["obj"]
    retrieved = parse_dt(w.get("retrieved_at")) or utcnow()
    return Series(
        ticker=o["ticker"],
        title=o.get("title"),
        category=o.get("category"),
        frequency=o.get("frequency"),
        tags=list(o.get("tags") or []),
        settlement_sources=[
            s.get("name", s) if isinstance(s, dict) else s for s in (o.get("settlement_sources") or [])
        ],
        contract_url=o.get("contract_url"),
        source_provider="kalshi",
        source_endpoint=w.get("endpoint", "/series"),
        source_identifier=o["ticker"],
        retrieved_at=retrieved,
        available_at=retrieved,
    )


def _price_points_from_blob(blob: dict) -> Iterator[PricePoint]:
    ticker = blob.get("market_ticker")
    if not ticker:
        return
    interval = INTERVAL_LABEL.get(blob.get("period_interval"), "1h")
    retrieved = parse_dt(blob.get("retrieved_at")) or utcnow()
    endpoint = blob.get("endpoint", "candlesticks")
    for c in blob.get("candlesticks") or []:
        t = from_unix(c.get("end_period_ts"))
        if t is None:
            continue
        yield PricePoint(
            market_ticker=ticker,
            timestamp=t,
            yes_bid=_candle_prob(c.get("yes_bid")),
            yes_ask=_candle_prob(c.get("yes_ask")),
            last_price=_candle_prob(c.get("price")),
            volume=_num(c.get("volume") or c.get("volume_fp")),
            open_interest=_num(c.get("open_interest") or c.get("open_interest_fp")),
            source_interval=interval,
            ohlc={"yes_bid": c.get("yes_bid"), "yes_ask": c.get("yes_ask"), "price": c.get("price")},
            source_provider="kalshi",
            source_endpoint=endpoint,
            source_identifier=ticker,
            retrieved_at=retrieved,
            available_at=t,  # a price is public exactly at its candlestick timestamp
        )


# --- polymarket normalization ---------------------------------------------
def _parse_strlist(s) -> list:
    if isinstance(s, list):
        return s
    if isinstance(s, str):
        try:
            return json.loads(s)
        except json.JSONDecodeError:
            return []
    return []


def _poly_result(outcomes: list, prices: list) -> str | None:
    if not outcomes or not prices or len(outcomes) != len(prices):
        return None
    try:
        fp = [float(x) for x in prices]
    except (TypeError, ValueError):
        return None
    if max(fp) < 0.99:  # not decisively resolved
        return None
    idx = fp.index(max(fp))
    return "yes" if str(outcomes[idx]).strip().lower() == "yes" else "no"


def _market_from_poly(w: dict) -> Market | None:
    o = w["obj"]
    outcomes = _parse_strlist(o.get("outcomes"))
    if {str(x).strip().lower() for x in outcomes} != {"yes", "no"}:
        return None  # binary only
    retrieved = parse_dt(w.get("retrieved_at")) or utcnow()
    start = parse_dt(o.get("startDate") or o.get("createdAt"))
    end = parse_dt(o.get("endDate"))
    cid = o.get("conditionId") or o.get("id") or o.get("slug")
    category = (o.get("category") or "").strip()
    return Market(
        ticker=cid,
        event_ticker=o.get("slug") or cid,
        series_ticker=None,
        market_type="binary",
        category=category.title() or None,
        title=o.get("question"),
        yes_sub_title="Yes",
        no_sub_title="No",
        rules_primary=o.get("description"),
        created_time=parse_dt(o.get("createdAt")),
        open_time=start,
        close_time=end,
        expiration_time=end,
        settlement_ts=end,
        status="settled" if o.get("closed") else "open",
        result=_poly_result(outcomes, _parse_strlist(o.get("outcomePrices"))),
        volume=_num(o.get("volume") or o.get("volumeNum")),
        liquidity=_num(o.get("liquidity") or o.get("liquidityNum")),
        source_provider="polymarket",
        source_endpoint=w.get("endpoint", "/markets"),
        source_identifier=cid,
        retrieved_at=retrieved,
        available_at=start or retrieved,
    )


def _price_points_from_poly_blob(blob: dict):
    ticker = blob.get("condition_id")
    if not ticker:
        return
    interval = blob.get("interval_label", "12h")
    retrieved = parse_dt(blob.get("retrieved_at")) or utcnow()
    endpoint = blob.get("endpoint", "/prices-history")
    for pt in blob.get("history") or []:
        t = from_unix(pt.get("t"))
        p = _num(pt.get("p"))  # already probability units [0,1]
        if t is None or p is None:
            continue
        yield PricePoint(
            market_ticker=ticker,
            timestamp=t,
            yes_bid=p,
            yes_ask=p,
            last_price=p,
            source_interval=interval,
            source_provider="polymarket",
            source_endpoint=endpoint,
            source_identifier=ticker,
            retrieved_at=retrieved,
            available_at=t,
        )


# --- orchestration ---------------------------------------------------------
def parse_all(settings: Settings) -> dict:
    rc = RawCache(settings.paths.raw)
    norm = settings.paths.normalized
    norm.mkdir(parents=True, exist_ok=True)

    markets = [_market_from_wrapper(w) for w in rc.read_records(rawpaths.KALSHI_MARKETS)]
    events = [_event_from_wrapper(w) for w in rc.read_records(rawpaths.KALSHI_EVENTS)]
    series = [_series_from_wrapper(w) for w in rc.read_records(rawpaths.KALSHI_SERIES)]

    prices: list[PricePoint] = []
    for _ticker, blob in rc.iter_blobs(rawpaths.KALSHI_CANDLES_DIR):
        prices.extend(_price_points_from_blob(blob))

    # Polymarket (combined into the same normalized tables; tagged source_provider).
    for w in rc.read_records(poly_rawpaths.POLY_MARKETS):
        m = _market_from_poly(w)
        if m is not None:
            markets.append(m)
    for _cid, blob in rc.iter_blobs(poly_rawpaths.POLY_PRICES_DIR):
        prices.extend(_price_points_from_poly_blob(blob))

    # Weather (Kalshi daily-temp markets; normalized like other Kalshi markets).
    for w in rc.read_records(rawpaths.WEATHER_MARKETS):
        markets.append(_market_from_wrapper(w))
    for _ticker, blob in rc.iter_blobs(rawpaths.WEATHER_CANDLES_DIR):
        prices.extend(_price_points_from_blob(blob))

    write_model_jsonl(norm / NORM_MARKETS, markets)
    write_model_jsonl(norm / NORM_EVENTS, events)
    write_model_jsonl(norm / NORM_SERIES, series)
    write_model_jsonl(norm / NORM_PRICES, prices)

    return {
        "markets": len(markets),
        "events": len(events),
        "series": len(series),
        "price_points": len(prices),
    }


# --- loaders (used by snapshots / hf export) -------------------------------
def load_markets(settings: Settings) -> list[Market]:
    return read_model_jsonl(settings.paths.normalized / NORM_MARKETS, Market)


def load_events(settings: Settings) -> list[Event]:
    return read_model_jsonl(settings.paths.normalized / NORM_EVENTS, Event)


def load_series(settings: Settings) -> list[Series]:
    return read_model_jsonl(settings.paths.normalized / NORM_SERIES, Series)


def load_prices(settings: Settings) -> list[PricePoint]:
    return read_model_jsonl(settings.paths.normalized / NORM_PRICES, PricePoint)
