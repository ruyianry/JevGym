"""Broad Kalshi ingestion into the raw cache.

Two entry points:
* ``ingest_kalshi`` — live crawl (series -> settled markets -> candlesticks).
* ``seed_from_fixtures`` — write the deterministic offline demo payloads (no network).

Data collection is deliberately separate from benchmark eligibility: we cache broadly here;
the snapshot builder narrows later.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import timedelta

from ...config import Settings
from ...util import parse_dt, to_unix
from .. import fixtures
from . import endpoints as ep
from . import rawpaths
from .client import KalshiClient
from .rawcache import RawCache


@dataclass
class IngestConfig:
    all_resolved: bool = False
    series_tickers: list[str] = field(default_factory=list)
    categories: list[str] = field(default_factory=lambda: ["Economics"])
    # series ticker -> category label to STAMP on markets (payloads omit it; it lives on the
    # series). Stamping preserves the domain so evidence attaches correctly.
    category_by_series: dict[str, str] = field(default_factory=dict)
    max_markets: int | None = 500
    period_interval: int = ep.PERIOD_1D
    use_historical_candles: bool = True


def _series_from_event(event_ticker: str | None) -> str | None:
    return event_ticker.split("-")[0] if event_ticker else None


def _unix_or_none(value) -> int | None:
    dt = parse_dt(value)
    return to_unix(dt) if dt else None


def ingest_kalshi(settings: Settings, config: IngestConfig | None = None, *, client: KalshiClient | None = None) -> dict:
    config = config or IngestConfig()
    rc = RawCache(settings.paths.raw)
    owns = client is None
    if client is None:
        client = KalshiClient(
            settings.kalshi_api_base,
            api_key_id=settings.kalshi_api_key_id,
            private_key_path=settings.kalshi_private_key_path,
        )
    try:
        # 1) series context (skipped for a firehose --all-resolved crawl)
        series: list[dict] = []
        if config.categories and not config.all_resolved:
            for cat in config.categories:
                series.extend(client.iter_series(category=cat))
        rc.write_records(rawpaths.KALSHI_SERIES, series, endpoint=ep.SERIES)

        # 2) settled markets
        markets: list[dict] = []
        if config.all_resolved:
            markets = list(client.iter_markets(status="settled", max_items=config.max_markets))
        elif config.series_tickers:
            for st in config.series_tickers:
                for m in client.iter_markets(status="settled", series_ticker=st, max_items=config.max_markets):
                    if not m.get("series_ticker"):
                        m["series_ticker"] = st
                    cat = config.category_by_series.get(st)
                    if cat and not m.get("category"):
                        m["category"] = cat  # stamp so the builder maps it to the right domain
                    markets.append(m)
        else:
            markets = list(client.iter_markets(status="settled", max_items=config.max_markets))
        rc.write_records(rawpaths.KALSHI_MARKETS, markets, endpoint=ep.MARKETS)

        # 3) per-market candlestick trajectories
        n_candles = 0
        for m in markets:
            ticker = m.get("ticker")
            series_ticker = m.get("series_ticker") or _series_from_event(m.get("event_ticker"))
            start_ts = _unix_or_none(m.get("open_time"))
            end_ts = _unix_or_none(m.get("close_time") or m.get("expiration_time"))
            if not (ticker and series_ticker and start_ts and end_ts):
                continue
            try:
                candles = client.get_market_candlesticks(
                    series_ticker,
                    ticker,
                    start_ts=start_ts,
                    end_ts=end_ts,
                    period_interval=config.period_interval,
                    historical=config.use_historical_candles,
                )
            except Exception:
                # Live vs historical candlestick availability varies across the cutoff; a
                # single market's candles failing should not abort the whole crawl.
                candles = []
            rc.write_blob(
                rawpaths.kalshi_candles(ticker),
                {
                    "market_ticker": ticker,
                    "series_ticker": series_ticker,
                    "period_interval": config.period_interval,
                    "candlesticks": candles,
                },
                endpoint="candlesticks",
            )
            n_candles += 1

        return {"series": len(series), "markets": len(markets), "candlestick_sets": n_candles}
    finally:
        if owns:
            client.close()


def _candle_mid(c: dict) -> float | None:
    """Mid price of a candlestick in [0,1], handling dollar-string and cents formats."""
    def _one(node):
        if not isinstance(node, dict):
            return None
        v = node.get("close_dollars")
        if v is None:
            v = node.get("close")
            if isinstance(v, (int, float)):
                v = v / 100.0
        try:
            return float(v)
        except (TypeError, ValueError):
            return None

    ya, yb, pr = _one(c.get("yes_ask")), _one(c.get("yes_bid")), _one(c.get("price"))
    vals = [x for x in (ya, yb) if x is not None]
    if vals:
        return sum(vals) / len(vals)
    return pr


def ingest_scaled(
    settings: Settings,
    categories: list[str] | None = None,
    *,
    target_events: int = 100,
    per_event_cap: int = 2,
    pool_per_series: int = 600,
    candle_window_days: int = 45,
    min_priced_candles: int = 1,
    min_entry: float = 0.03,
    max_entry: float = 0.97,
    max_candle_fetch_per_cat: int = 220,
    client: KalshiClient | None = None,
) -> dict:
    """Scale a bench: pool many settled markets, spread across DISTINCT events, and keep only the
    *significant* ones — those with a real daily price trajectory whose entry sits away from the
    0/1 tails (a liquidity/meaningfulness proxy, since this API exposes no settled volume). Aims
    for ``target_events`` distinct settlement events per category.
    """
    from ...util import to_unix
    from ..categories import category_by_series, series_for

    rc = RawCache(settings.paths.raw)
    owns = client is None
    if client is None:
        client = KalshiClient(
            settings.kalshi_api_base,
            api_key_id=settings.kalshi_api_key_id,
            private_key_path=settings.kalshi_private_key_path,
        )
    cbs = category_by_series(categories)
    try:
        # 1) pool settled markets per series, grouped by category
        pool: dict[str, list[dict]] = defaultdict(list)
        for st in series_for(categories):
            cat = cbs.get(st, "Economics")
            for m in client.iter_markets(status="settled", series_ticker=st, max_items=pool_per_series):
                if (m.get("result") or "").lower() not in ("yes", "no"):
                    continue
                if not m.get("series_ticker"):
                    m["series_ticker"] = st
                if not m.get("category"):
                    m["category"] = cat
                pool[cat].append(m)

        kept: list[dict] = []
        kept_candles: dict[str, list[dict]] = {}
        stats: dict[str, dict] = {}
        for cat, mkts in pool.items():
            by_event: dict[str, list[dict]] = defaultdict(list)
            for m in mkts:
                by_event[m.get("event_ticker") or m["ticker"]].append(m)
            # round-robin across events so early candidates maximize distinct-event coverage
            ordered: list[dict] = []
            for r in range(per_event_cap):
                for ms in by_event.values():
                    if r < len(ms):
                        ordered.append(ms[r])

            chosen, events, fetches = [], set(), 0
            for m in ordered:
                if len(events) >= target_events or fetches >= max_candle_fetch_per_cat:
                    break
                open_dt = parse_dt(m.get("open_time"))
                close_dt = parse_dt(m.get("close_time") or m.get("expiration_time"))
                if not (open_dt and close_dt):
                    continue
                end = to_unix(close_dt)
                # Fetch over the market's ACTUAL lifetime; hourly for short (intraday/daily)
                # markets, daily (capped) for long-horizon ones — else short crypto/sports get
                # no daily bar and are wrongly dropped.
                lifetime_days = max(0, (close_dt - open_dt).days)
                if lifetime_days <= 7:
                    interval, start = ep.PERIOD_1H, to_unix(open_dt)
                else:
                    interval, start = ep.PERIOD_1D, to_unix(close_dt - timedelta(days=candle_window_days))
                try:
                    candles = client.get_market_candlesticks(
                        m["series_ticker"], m["ticker"], start_ts=start,
                        end_ts=end, period_interval=interval, historical=False,
                    )
                except Exception:
                    candles = []
                fetches += 1
                priced = [c for c in candles if _candle_mid(c) is not None]
                if len(priced) < min_priced_candles:
                    continue
                entry = _candle_mid(priced[0])
                if entry is None or entry < min_entry or entry > max_entry:
                    continue  # dead 0/1 tail — not a significant question
                chosen.append(m)
                kept_candles[m["ticker"]] = candles
                events.add(m.get("event_ticker") or m["ticker"])
            kept.extend(chosen)
            stats[cat] = {"pool": len(mkts), "events": len(events), "kept": len(chosen), "candle_fetches": fetches}

        rc.write_records(rawpaths.KALSHI_MARKETS, kept, endpoint=ep.MARKETS)
        for m in kept:
            rc.write_blob(
                rawpaths.kalshi_candles(m["ticker"]),
                {"market_ticker": m["ticker"], "series_ticker": m["series_ticker"],
                 "period_interval": ep.PERIOD_1D, "candlesticks": kept_candles.get(m["ticker"], [])},
                endpoint="candlesticks",
            )
        return {"markets": len(kept), "by_category": stats}
    finally:
        if owns:
            client.close()


def ingest_categories(
    settings: Settings,
    categories: list[str] | None = None,
    *,
    max_markets: int = 200,
    client: KalshiClient | None = None,
) -> dict:
    """Expand the dataset: ingest every series in the given categories (stamping the category so
    the domain — and thus evidence attachment — is correct). Uses the curated registry."""
    from ..categories import category_by_series, series_for

    cbs = category_by_series(categories)
    cfg = IngestConfig(
        series_tickers=series_for(categories),
        category_by_series=cbs,
        max_markets=max_markets,
        period_interval=ep.PERIOD_1D,
        use_historical_candles=False,  # the /historical candles endpoint 404s; live candles work
    )
    out = ingest_kalshi(settings, cfg, client=client)
    out["categories"] = sorted(set(cbs.values()))
    return out


# Kalshi daily-temperature series ("Highest temperature in <city>"). These are the real,
# currently-listed weather markets; ingest pulls only these available options (no fabrication).
DEFAULT_WEATHER_SERIES = [
    "KXHIGHNY", "KXHIGHLAX", "KXHIGHCHI", "KXHIGHMIA", "KXHIGHAUS", "KXHIGHDEN", "KXHIGHPHIL",
]


def ingest_weather(
    settings: Settings,
    series_tickers: list[str] | None = None,
    *,
    status: str = "settled",
    max_markets: int = 60,
    period_interval: int = ep.PERIOD_1H,
    client: KalshiClient | None = None,
) -> dict:
    """Live-ingest real Kalshi weather markets + hourly candlesticks into the weather raw cache.

    Markets are pulled per weather series (available options only). The market objects omit a
    category (it lives on the series), so we stamp 'Climate and Weather' to preserve the domain.
    """
    series_tickers = series_tickers or DEFAULT_WEATHER_SERIES
    rc = RawCache(settings.paths.raw)
    owns = client is None
    if client is None:
        client = KalshiClient(
            settings.kalshi_api_base,
            api_key_id=settings.kalshi_api_key_id,
            private_key_path=settings.kalshi_private_key_path,
        )
    try:
        markets: list[dict] = []
        for st in series_tickers:
            for m in client.iter_markets(status=status, series_ticker=st, max_items=max_markets):
                if not m.get("series_ticker"):
                    m["series_ticker"] = st
                if not m.get("category"):
                    m["category"] = "Climate and Weather"
                markets.append(m)
        rc.write_records(rawpaths.WEATHER_MARKETS, markets, endpoint=ep.MARKETS)

        n_candles = 0
        for m in markets:
            ticker = m.get("ticker")
            series_ticker = m.get("series_ticker") or _series_from_event(m.get("event_ticker"))
            start_ts = _unix_or_none(m.get("open_time"))
            end_ts = _unix_or_none(m.get("close_time") or m.get("expiration_time"))
            if not (ticker and series_ticker and start_ts and end_ts):
                continue
            try:
                candles = client.get_market_candlesticks(
                    series_ticker, ticker, start_ts=start_ts, end_ts=end_ts,
                    period_interval=period_interval, historical=False,
                )
            except Exception:
                candles = []
            rc.write_blob(
                rawpaths.weather_candles(ticker),
                {"market_ticker": ticker, "series_ticker": series_ticker,
                 "period_interval": period_interval, "candlesticks": candles},
                endpoint="candlesticks",
            )
            n_candles += 1
        return {"series": len(series_tickers), "markets": len(markets), "candlestick_sets": n_candles}
    finally:
        if owns:
            client.close()


def seed_from_fixtures(settings: Settings, raw: dict | None = None) -> dict:
    """Write the deterministic demo payloads into the raw cache (offline)."""
    raw = raw or fixtures.build_demo_raw()
    rc = RawCache(settings.paths.raw)
    rc.write_records(rawpaths.KALSHI_SERIES, raw["series"], endpoint=ep.SERIES)
    rc.write_records(rawpaths.KALSHI_EVENTS, raw["events"], endpoint=ep.EVENTS)
    rc.write_records(rawpaths.KALSHI_MARKETS, raw["markets"], endpoint=ep.MARKETS)
    for ticker, blob in raw["candlesticks"].items():
        rc.write_blob(rawpaths.kalshi_candles(ticker), blob, endpoint="candlesticks")
    for series_id, blob in raw["fred"].items():
        rc.write_blob(rawpaths.fred_series(series_id), blob, endpoint="fred/observations")
    return {
        "series": len(raw["series"]),
        "events": len(raw["events"]),
        "markets": len(raw["markets"]),
        "candlestick_sets": len(raw["candlesticks"]),
        "fred_series": len(raw["fred"]),
    }
