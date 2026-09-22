"""Parse a Kalshi daily-temperature market into a typed ``WeatherContract``.

Extracts station, measurement, target date, units, exact threshold/range, and the observation
window (UTC + local convention). Ambiguous or unknown windows make a snapshot ineligible for
the strict track rather than being guessed. Tuned to documented Kalshi weather conventions and
the offline fixtures; unknown stations/units are reported, never silently substituted.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from ..models import Market
from ..util import short_hash
from .schemas import WeatherContract

# token -> (display name, station_id, IANA tz). Never substitute a nearby station silently.
STATIONS: dict[str, tuple[str, str, str]] = {}
# station_id -> (lat, lon) of the official observing site, for climatology lookups (Open-Meteo).
STATION_COORDS: dict[str, tuple[float, float]] = {}
# real Kalshi daily-temperature series ticker -> (display, station_id, IANA tz, measurement).
WEATHER_SERIES: dict[str, tuple[str, str, str, str]] = {}


def _reg(name: str, sid: str, tz: str, *tokens: str) -> None:
    for t in (sid, *tokens):
        STATIONS[t.upper().replace(" ", "")] = (name, sid, tz)


def _reg_series(
    series: str, name: str, sid: str, tz: str, measurement: str, lat: float, lon: float, *tokens: str
) -> None:
    _reg(name, sid, tz, *tokens)
    STATION_COORDS[sid] = (lat, lon)
    WEATHER_SERIES[series.upper()] = (name, sid, tz, measurement)


# Kalshi "Highest temperature in <city>" markets (series KXHIGH<CITY>). Coordinates are the
# official observing sites Kalshi settles against (e.g. NYC = Central Park / CLINYC). The market
# objects omit a category (it lives on the series), so we map by series ticker here.
_reg_series("KXHIGHNY", "New York (Central Park)", "KNYC", "America/New_York", "tmax", 40.7789, -73.9692, "nyc", "ny", "newyork", "centralpark")
_reg_series("KXHIGHLAX", "Los Angeles (LAX)", "KLAX", "America/Los_Angeles", "tmax", 33.9416, -118.4085, "lax", "la", "losangeles")
_reg_series("KXHIGHCHI", "Chicago (Midway)", "KMDW", "America/Chicago", "tmax", 41.786, -87.7524, "chi", "chicago", "kord", "ord", "kmdw", "mdw")
_reg_series("KXHIGHMIA", "Miami", "KMIA", "America/New_York", "tmax", 25.7959, -80.2870, "mia", "miami")
_reg_series("KXHIGHAUS", "Austin", "KAUS", "America/Chicago", "tmax", 30.1975, -97.6664, "aus", "austin")
_reg_series("KXHIGHDEN", "Denver", "KDEN", "America/Denver", "tmax", 39.8561, -104.6737, "den", "denver")
_reg_series("KXHIGHPHIL", "Philadelphia", "KPHL", "America/New_York", "tmax", 39.8744, -75.2424, "phil", "philadelphia", "phl")

_MONTHS = {m: i for i, m in enumerate(
    ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"], start=1)}
_TICKER_DATE = re.compile(r"-(\d{2})([A-Z]{3})(\d{2})(?:-|$)")


def _series_key(market: Market) -> str:
    s = market.series_ticker or (market.event_ticker or market.ticker or "").split("-")[0]
    return (s or "").upper()


def _ticker_date(*tickers: str) -> date | None:
    """Kalshi encodes the target day in the ticker (``...-26SEP20-...`` -> 2026-09-20). This is
    more reliable than ``close_time`` (which can roll into the next UTC/local day)."""
    for t in tickers:
        if not t:
            continue
        m = _TICKER_DATE.search(t.upper())
        if m:
            yy, mon, dd = m.groups()
            mo = _MONTHS.get(mon)
            if mo:
                try:
                    return date(2000 + int(yy), mo, int(dd))
                except ValueError:
                    pass
    return None


def _find_station(*texts: str) -> tuple[str, str, str] | None:
    blob = " ".join(t for t in texts if t)
    tokens = re.split(r"[^A-Za-z]+", blob.upper())
    # exact station-id/token match first (avoid 'la' matching inside words via the split)
    for tok in tokens:
        if tok in STATIONS:
            return STATIONS[tok]
    return None


def _measurement(*texts: str) -> str | None:
    blob = " ".join(t for t in texts if t).lower()
    if any(w in blob for w in ("high", "highest", "max temp", "maximum")):
        return "tmax"
    if any(w in blob for w in ("low", "lowest", "min temp", "minimum")):
        return "tmin"
    return None


_NUM = r"(-?\d+(?:\.\d+)?)"


def _parse_threshold(market: Market) -> tuple[str | None, float | None, float | None, float | None]:
    st = (market.strike_type or "").lower()
    floor, cap = market.floor_strike, market.cap_strike
    if st in ("between", "range") and floor is not None and cap is not None:
        return "range_in", None, floor, cap
    if st in ("greater",) and floor is not None:
        return "gt", floor, None, None
    if st in ("greater_or_equal", "greater_or_equal_to") and floor is not None:
        return "ge", floor, None, None
    if st in ("less",) and cap is not None:
        return "lt", cap, None, None
    if st in ("less_or_equal", "less_or_equal_to") and cap is not None:
        return "le", cap, None, None

    text = " ".join(t for t in (market.yes_sub_title, market.title, market.rules_primary) if t).lower()
    m = re.search(rf"between\s+{_NUM}\D+{_NUM}", text)
    if m:
        return "range_in", None, float(m.group(1)), float(m.group(2))
    m = re.search(rf"(>=|≥|at least|or (?:higher|above|more)|or above)\D*{_NUM}", text) or re.search(
        rf"{_NUM}\s*(?:°|deg)?\s*(?:or (?:higher|above|more))", text
    )
    if m:
        return "ge", float(m.groups()[-1]), None, None
    m = re.search(rf"(<=|≤|or (?:lower|below|less)|or below)\D*{_NUM}", text)
    if m:
        return "le", float(m.groups()[-1]), None, None
    m = re.search(rf"(?:>|above|greater than|hotter than|exceeds?|over)\D*{_NUM}", text)
    if m:
        return "gt", float(m.groups()[-1]), None, None
    m = re.search(rf"(?:<|below|less than|colder than|under)\D*{_NUM}", text)
    if m:
        return "lt", float(m.groups()[-1]), None, None
    return None, None, None, None


def parse_weather_contract(market: Market) -> WeatherContract:
    texts = (market.ticker, market.event_ticker or "", market.series_ticker or "", market.title or "", market.rules_primary or "")
    ws = WEATHER_SERIES.get(_series_key(market))
    if ws:  # known real Kalshi weather series: station + measurement are authoritative
        name, sid, tz_name, meas = ws
        station: tuple[str, str, str] | None = (name, sid, tz_name)
        measurement: str | None = meas
    else:
        station = _find_station(*texts)
        measurement = _measurement(market.title, market.rules_primary, market.yes_sub_title)
    units = "C" if ("celsius" in " ".join(t for t in texts if t).lower() or "°c" in (market.rules_primary or "").lower()) else "F"
    op, value, lo, hi = _parse_threshold(market)

    c = WeatherContract(
        market_ticker=market.ticker,
        event_cluster_id="",  # filled once we have station+date+measurement
        station=station[0] if station else "unknown",
        station_id=station[1] if station else None,
        measurement=measurement or "unknown",
        units=units,
        threshold_op=op,
        threshold_value=value,
        range_low=lo,
        range_high=hi,
    )

    target = _ticker_date(market.ticker, market.event_ticker or "")
    if station and (target is not None or market.close_time is not None):
        tz = ZoneInfo(station[2])
        if target is None:
            target = market.close_time.astimezone(tz).date()
        c.target_date = target
        c.local_timezone = station[2]
        c.local_convention = "local_civil_day"
        start_local = datetime(target.year, target.month, target.day, tzinfo=tz)
        c.obs_window_start_utc = start_local.astimezone(ZoneInfo("UTC"))
        c.obs_window_end_utc = (start_local + timedelta(days=1)).astimezone(ZoneInfo("UTC"))

    reasons = []
    if not station:
        reasons.append("unknown_station")
    if measurement is None:
        reasons.append("unknown_measurement")
    if c.target_date is None:
        reasons.append("unknown_target_date")
    if op is None:
        reasons.append("unparsed_threshold")
    if c.obs_window_start_utc is None:
        reasons.append("unknown_observation_window")
    c.eligible = not reasons
    c.ineligible_reason = None if c.eligible else ",".join(reasons)
    if station and c.target_date is not None and measurement:
        c.event_cluster_id = "wx-" + short_hash(station[1], c.target_date.isoformat(), measurement)
    else:
        c.event_cluster_id = "wx-" + short_hash(market.event_ticker or market.ticker)
    return c
