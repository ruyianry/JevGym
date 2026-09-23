"""Deterministic synthetic demo data (Fed / macro vertical) for fully-offline runs.

This is *not* real Kalshi data — it is a small, self-contained, reproducible stand-in so the
entire pipeline (ingest -> parse -> snapshots -> validate -> hf-build -> eval/arena) runs
with no network, credentials, or GPU. Tests use the same generator. Prices are emitted in
cents (Kalshi candlestick convention) so the parser's cents->probability step is exercised.

Event close dates are staggered so chronological train/validation/test splits populate.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

from ..util import to_unix

_UTC = timezone.utc
LIFETIME_DAYS = 45


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _daily_candles(open_dt: datetime, close_dt: datetime, p_start: float, p_end: float) -> list[dict]:
    """Deterministic daily YES-price path from p_start to p_end with a mild wiggle."""
    days = max(1, (close_dt - open_dt).days)
    candles: list[dict] = []
    for i in range(days + 1):
        t = open_dt + timedelta(days=i)
        frac = i / days
        p = p_start + (p_end - p_start) * frac + 0.03 * math.sin(i * 0.7)
        p = min(0.98, max(0.02, p))
        yes_bid = max(1, round((p - 0.02) * 100))
        yes_ask = min(99, round((p + 0.02) * 100))
        price = round(p * 100)

        def ohlc(v: int) -> dict:
            return {"open": v, "high": v, "low": v, "close": v}

        candles.append(
            {
                "end_period_ts": to_unix(t),
                "yes_bid": ohlc(yes_bid),
                "yes_ask": ohlc(yes_ask),
                "price": ohlc(price),
                "volume": 1000 + 10 * i,
                "open_interest": 5000 + 20 * i,
            }
        )
    return candles


def _market(
    ticker: str,
    event_ticker: str,
    series_ticker: str,
    close_dt: datetime,
    yes_sub: str,
    no_sub: str,
    rules: str,
    result: str,
) -> dict:
    open_dt = close_dt - timedelta(days=LIFETIME_DAYS)
    return {
        "ticker": ticker,
        "event_ticker": event_ticker,
        "series_ticker": series_ticker,
        "market_type": "binary",
        "category": "Economics",
        "title": yes_sub,
        "yes_sub_title": yes_sub,
        "no_sub_title": no_sub,
        "rules_primary": rules,
        "rules_secondary": "Settlement per official source.",
        "created_time": _iso(open_dt - timedelta(days=1)),
        "open_time": _iso(open_dt),
        "close_time": _iso(close_dt),
        "expiration_time": _iso(close_dt + timedelta(hours=2)),
        "settlement_ts": _iso(close_dt + timedelta(hours=3)),
        "status": "settled",
        "result": result,
        "can_close_early": False,
        "strike_type": "custom",
        "volume": 45000,
        "open_interest": 9000,
        "liquidity": 0.0,
    }


# Staggered event close dates (older -> newer) to exercise chronological splits.
_FED_CLOSE = datetime(2026, 1, 28, 19, 0, tzinfo=_UTC)
_PAYROLLS_CLOSE = datetime(2026, 2, 6, 13, 30, tzinfo=_UTC)
_CPI_CLOSE = datetime(2026, 2, 11, 13, 30, tzinfo=_UTC)

_SERIES = [
    {"ticker": "KXFED", "title": "Fed Funds Rate Decision", "category": "Economics", "frequency": "per-meeting"},
    {"ticker": "KXPAYROLLS", "title": "US Nonfarm Payrolls", "category": "Economics", "frequency": "monthly"},
    {"ticker": "KXCPIYOY", "title": "US CPI Year-over-Year", "category": "Economics", "frequency": "monthly"},
]

_EVENTS = [
    {"event_ticker": "KXFED-26JAN", "series_ticker": "KXFED", "title": "FOMC decision, Jan 2026", "category": "Economics"},
    {"event_ticker": "KXPAYROLLS-26JAN", "series_ticker": "KXPAYROLLS", "title": "Nonfarm payrolls, Jan 2026", "category": "Economics"},
    {"event_ticker": "KXCPIYOY-26JAN", "series_ticker": "KXCPIYOY", "title": "CPI YoY, Jan 2026", "category": "Economics"},
]

# (ticker, event, series, close_dt, yes_sub, no_sub, rules, result, p_start, p_end)
_MARKET_SPECS = [
    ("KXFED-26JAN-CUT", "KXFED-26JAN", "KXFED", _FED_CLOSE,
     "The Fed cuts the target rate at the Jan 2026 meeting",
     "The Fed does not cut at the Jan 2026 meeting",
     "Resolves YES if the FOMC lowers the federal funds target range at its January 2026 meeting.",
     "yes", 0.35, 0.90),
    ("KXFED-26JAN-HOLD", "KXFED-26JAN", "KXFED", _FED_CLOSE,
     "The Fed holds the target rate at the Jan 2026 meeting",
     "The Fed changes the rate at the Jan 2026 meeting",
     "Resolves YES if the FOMC leaves the federal funds target range unchanged in January 2026.",
     "no", 0.55, 0.08),
    ("KXPAYROLLS-26JAN-A150", "KXPAYROLLS-26JAN", "KXPAYROLLS", _PAYROLLS_CLOSE,
     "January 2026 nonfarm payrolls exceed +150k",
     "January 2026 nonfarm payrolls are +150k or below",
     "Resolves YES if the BLS-reported change in nonfarm payrolls for January 2026 exceeds 150,000.",
     "yes", 0.50, 0.85),
    ("KXCPIYOY-26JAN-A3", "KXCPIYOY-26JAN", "KXCPIYOY", _CPI_CLOSE,
     "January 2026 CPI year-over-year exceeds 3.0%",
     "January 2026 CPI year-over-year is 3.0% or below",
     "Resolves YES if the BLS-reported CPI-U year-over-year for January 2026 exceeds 3.0%.",
     "no", 0.45, 0.12),
]


def _fred_series(series_id: str, title: str, units: str, points: list[tuple[str, str, str]]) -> dict:
    return {
        "series_id": series_id,
        "title": title,
        "units": units,
        "observations": [
            {"date": d, "value": v, "realtime_start": r, "release_date": r} for (d, v, r) in points
        ],
    }


_FRED = {
    "UNRATE": _fred_series(
        "UNRATE", "Unemployment Rate", "Percent",
        [("2025-10-01", "4.3", "2025-11-07"),
         ("2025-11-01", "4.2", "2025-12-05"),
         ("2025-12-01", "4.1", "2026-01-09")],
    ),
    "PAYEMS": _fred_series(
        "PAYEMS", "Nonfarm Payrolls (change, thousands)", "Thousands of Persons",
        [("2025-10-01", "158", "2025-11-07"),
         ("2025-11-01", "172", "2025-12-05"),
         ("2025-12-01", "181", "2026-01-09")],
    ),
    "CPIAUCSL": _fred_series(
        "CPIAUCSL", "CPI-U Year-over-Year", "Percent",
        [("2025-10-01", "3.1", "2025-11-13"),
         ("2025-11-01", "2.9", "2025-12-11"),
         ("2025-12-01", "2.8", "2026-01-13")],
    ),
}


def build_demo_raw() -> dict:
    """Return a dict of raw payloads mirroring what a live crawl would cache."""
    markets = []
    candlesticks = {}
    for (ticker, ev, series, close_dt, yes_sub, no_sub, rules, result, ps, pe) in _MARKET_SPECS:
        markets.append(_market(ticker, ev, series, close_dt, yes_sub, no_sub, rules, result))
        open_dt = close_dt - timedelta(days=LIFETIME_DAYS)
        candlesticks[ticker] = {
            "market_ticker": ticker,
            "series_ticker": series,
            "period_interval": 1440,
            "candlesticks": _daily_candles(open_dt, close_dt, ps, pe),
        }
    return {
        "series": list(_SERIES),
        "events": list(_EVENTS),
        "markets": markets,
        "candlesticks": candlesticks,
        "fred": _FRED,
    }
