"""Deterministic offline weather fixtures: multi-year observations + daily-temp markets.

Not real data. Designed to exercise the curation invariants: clean easy-YES and easy-NO
contracts, a near-normal (not-easy) contract, a multi-bucket sibling event (the many-easy-NO
artifact), and an ineligible unknown-station contract. Prices are in cents (parser convention).
"""

from __future__ import annotations

import math
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from ..util import to_unix

_UTC = timezone.utc
_STATION_TZ = {"KNYC": "America/New_York", "KLAX": "America/Los_Angeles"}
_CLIMATE = {"KNYC": (55.0, 30.0), "KLAX": (72.0, 6.0)}  # (annual mean °F, amplitude)


def _seasonal_value(sid: str, d: date) -> float:
    mean, amp = _CLIMATE[sid]
    doy = d.timetuple().tm_yday
    seasonal = mean + amp * math.cos(2 * math.pi * (doy - 196) / 365.0)  # peak ~ mid-July
    noise = ((d.year * 7 + doy * 3) % 11) - 5  # deterministic -5..+5
    return round(seasonal + noise)


def build_observations() -> dict:
    """{station_id: {measurement: [{date,value,units}]}} for 2006-2025 around needed windows."""
    needs = {"KNYC": [196, 15, 201], "KLAX": [110]}  # day-of-year centers
    out: dict[str, dict[str, list]] = {}
    for sid, centers in needs.items():
        seen: dict[str, dict] = {}
        for year in range(2006, 2026):
            for center in centers:
                for dd in range(-20, 21):
                    d = date(year, 1, 1) + timedelta(days=center - 1 + dd)
                    seen[d.isoformat()] = {"date": d.isoformat(), "value": _seasonal_value(sid, d), "units": "F"}
        out[sid] = {"tmax": sorted(seen.values(), key=lambda o: o["date"])}
    return out


def _as_of_for(sid: str, target: date, offset_hours: int = 24) -> datetime:
    start_local = datetime(target.year, target.month, target.day, tzinfo=ZoneInfo(_STATION_TZ[sid]))
    return start_local.astimezone(_UTC) - timedelta(hours=offset_hours)


def _candles(ticker: str, series: str, sid: str, target: date, yes_prob: float) -> dict:
    yb = max(1, round((yes_prob - 0.01) * 100))
    ya = min(99, round((yes_prob + 0.01) * 100))
    pr = round(yes_prob * 100)

    def ohlc(v):
        return {"open": v, "high": v, "low": v, "close": v}

    ends: set[int] = set()
    candles = []
    # Fresh completed hourly candles bracketing BOTH the 24h and 6h horizons.
    for offset in (24, 6):
        anchor = _as_of_for(sid, target, offset)
        for h in range(-6, 2):
            ts = to_unix(anchor + timedelta(hours=h))
            if ts in ends:
                continue
            ends.add(ts)
            candles.append(
                {"end_period_ts": ts, "yes_bid": ohlc(yb), "yes_ask": ohlc(ya), "price": ohlc(pr),
                 "volume": 500, "open_interest": 2000}
            )
    candles.sort(key=lambda c: c["end_period_ts"])
    return {"market_ticker": ticker, "series_ticker": series, "period_interval": 60, "candlesticks": candles}


def _market(ticker, event, series, sid, target, strike_type, floor, cap, yes_sub, rules, result) -> dict:
    tz = ZoneInfo(_STATION_TZ[sid]) if sid in _STATION_TZ else ZoneInfo("America/New_York")
    close = datetime(target.year, target.month, target.day, 20, 0, tzinfo=tz)
    return {
        "ticker": ticker,
        "event_ticker": event,
        "series_ticker": series,
        "market_type": "binary",
        "category": "Climate and Weather",
        "title": yes_sub,
        "yes_sub_title": yes_sub,
        "no_sub_title": "Otherwise",
        "rules_primary": rules,
        "open_time": (close - timedelta(days=10)).isoformat(),
        "close_time": close.isoformat(),
        "expiration_time": (close + timedelta(hours=6)).isoformat(),
        "settlement_ts": (close + timedelta(hours=7)).isoformat(),
        "status": "settled",
        "result": result,
        "strike_type": strike_type,
        "floor_strike": floor,
        "cap_strike": cap,
        "volume": 30000,
        "open_interest": 5000,
    }


# (ticker, event, series, station, target, strike_type, floor, cap, yes_sub, rules, result, yes_prob)
_SPECS = [
    ("KXHIGHNY-26JUL15-T70", "KXHIGHNY-26JUL15", "KXHIGHNY", "KNYC", date(2026, 7, 15), "greater", 70.0, None,
     "New York (Central Park) daily high temperature above 70F on 2026-07-15",
     "Resolves YES if the highest temperature at New York Central Park (KNYC) on 2026-07-15 is above 70F.", "yes", 0.98),
    ("KXHIGHNY-26JAN15-T80", "KXHIGHNY-26JAN15", "KXHIGHNY", "KNYC", date(2026, 1, 15), "greater", 80.0, None,
     "New York (Central Park) daily high temperature above 80F on 2026-01-15",
     "Resolves YES if the highest temperature at New York Central Park (KNYC) on 2026-01-15 is above 80F.", "no", 0.02),
    ("KXHIGHLAX-26APR20-T72", "KXHIGHLAX-26APR20", "KXHIGHLAX", "KLAX", date(2026, 4, 20), "greater", 72.0, None,
     "Los Angeles (LAX) daily high temperature above 72F on 2026-04-20",
     "Resolves YES if the highest temperature at Los Angeles (KLAX) on 2026-04-20 is above 72F.", "yes", 0.55),
    # multi-bucket sibling event (many easy-NO, no clear winning bucket by odds)
    ("KXHIGHNY-26JUL20-U70", "KXHIGHNY-26JUL20", "KXHIGHNY", "KNYC", date(2026, 7, 20), "less", None, 70.0,
     "New York high temperature below 70F on 2026-07-20", "KNYC high below 70F on 2026-07-20.", "no", 0.01),
    ("KXHIGHNY-26JUL20-R7080", "KXHIGHNY-26JUL20", "KXHIGHNY", "KNYC", date(2026, 7, 20), "between", 70.0, 80.0,
     "New York high temperature between 70F and 80F on 2026-07-20", "KNYC high between 70 and 80F.", "no", 0.04),
    ("KXHIGHNY-26JUL20-R8090", "KXHIGHNY-26JUL20", "KXHIGHNY", "KNYC", date(2026, 7, 20), "between", 80.0, 90.0,
     "New York high temperature between 80F and 90F on 2026-07-20", "KNYC high between 80 and 90F.", "yes", 0.45),
    ("KXHIGHNY-26JUL20-R90100", "KXHIGHNY-26JUL20", "KXHIGHNY", "KNYC", date(2026, 7, 20), "between", 90.0, 100.0,
     "New York high temperature between 90F and 100F on 2026-07-20", "KNYC high between 90 and 100F.", "no", 0.45),
    ("KXHIGHNY-26JUL20-A100", "KXHIGHNY-26JUL20", "KXHIGHNY", "KNYC", date(2026, 7, 20), "greater", 100.0, None,
     "New York high temperature above 100F on 2026-07-20", "KNYC high above 100F.", "no", 0.05),
    # ineligible: unknown station -> must still be annotated (as ineligible), never silently hard
    ("KXHIGHSPR-26JUL15-T80", "KXHIGHSPR-26JUL15", "KXHIGHSPR", "KNYC", date(2026, 7, 15), "greater", 80.0, None,
     "Springfield daily high temperature above 80F on 2026-07-15",
     "Resolves YES if the high in Springfield exceeds 80F.", "yes", 0.9),
]


def build_weather_raw() -> dict:
    markets, candles = [], {}
    for (ticker, event, series, sid, target, st, floor, cap, yes_sub, rules, result, yp) in _SPECS:
        markets.append(_market(ticker, event, series, sid, target, st, floor, cap, yes_sub, rules, result))
        candles[ticker] = _candles(ticker, series, sid, target, yp)
    obs = build_observations()
    return {"markets": markets, "candlesticks": candles, "observations": obs}


def seed_weather_fixtures(settings) -> dict:
    from ..data.kalshi import rawpaths
    from ..data.kalshi.rawcache import RawCache

    raw = build_weather_raw()
    rc = RawCache(settings.paths.raw)
    rc.write_records(rawpaths.WEATHER_MARKETS, raw["markets"], endpoint="/markets")
    for ticker, blob in raw["candlesticks"].items():
        rc.write_blob(rawpaths.weather_candles(ticker), blob, endpoint="candlesticks")
    for sid, meas_map in raw["observations"].items():
        for meas, obs in meas_map.items():
            rc.write_blob(
                rawpaths.weather_obs(sid, meas),
                {"station_id": sid, "measurement": meas, "units": "F", "observations": obs},
                endpoint="observations",
            )
    return {"markets": len(raw["markets"]), "candles": len(raw["candlesticks"]), "obs_stations": len(raw["observations"])}


def load_fixture_obs_source(settings):
    """Build a FixtureObservationSource from seeded weather/obs/*.json."""
    from ..data.kalshi import rawpaths
    from ..data.kalshi.rawcache import RawCache
    from .weather_prior import DailyObs, FixtureObservationSource

    rc = RawCache(settings.paths.raw)
    data: dict[str, dict[str, list]] = {}
    for _name, blob in rc.iter_blobs(rawpaths.WEATHER_OBS_DIR):
        sid, meas = blob["station_id"], blob["measurement"]
        obs = [DailyObs(date=o["date"], value=float(o["value"]), units=o.get("units", "F")) for o in blob["observations"]]
        data.setdefault(sid, {})[meas] = obs
    return FixtureObservationSource(data)
