"""Independent background prior for weather contracts.

An empirical seasonal reference: its only predictive inputs are station, calendar season,
measurement, and the exact contract threshold. It must NOT read the current price, current
forecast, the target-day observation, the resolution, or any model output.

    p_prior = (k + alpha) / (n + 2*alpha)     confidence = max(p_prior, 1 - p_prior)

where n = valid historical observations in a +/- day-of-year window from earlier complete
years, and k = those satisfying the exact YES predicate. Nearby days are correlated, so we
report distinct-year count alongside n and never treat pooled days as independent trials.
Offline fixtures cannot verify historical availability, so results are marked
``retrospective_approximation`` and kept out of the strict temporal subset.
"""

from __future__ import annotations

from datetime import date
from typing import Protocol, runtime_checkable

from ..models.base import JevBaseModel
from .config import DifficultyConfig
from .schemas import WeatherContract, WeatherPriorResult


class DailyObs(JevBaseModel):
    date: str  # ISO "YYYY-MM-DD"
    value: float
    units: str = "F"


@runtime_checkable
class ObservationSource(Protocol):
    name: str

    def get_daily(self, station_id: str, measurement: str) -> list[DailyObs]: ...


class FixtureObservationSource:
    """In-memory / offline observations. ``data[station_id][measurement] -> [DailyObs]``."""

    name = "fixture"

    def __init__(self, data: dict[str, dict[str, list[DailyObs]]]):
        self._data = data

    def get_daily(self, station_id: str, measurement: str) -> list[DailyObs]:
        return list(self._data.get(station_id, {}).get(measurement, []))


def _to_units(v: float, frm: str, to: str) -> float:
    frm, to = (frm or "F")[0].upper(), (to or "F")[0].upper()
    if frm == to:
        return v
    if frm == "F" and to == "C":
        return (v - 32.0) * 5.0 / 9.0
    if frm == "C" and to == "F":
        return v * 9.0 / 5.0 + 32.0
    return v


def _doy_dist(a: int, b: int) -> int:
    d = abs(a - b)
    return min(d, 365 - d)


def _yes_predicate(value: float, c: WeatherContract) -> bool:
    op = c.threshold_op
    t, lo, hi = c.threshold_value, c.range_low, c.range_high
    if op == "gt":
        return value > t
    if op == "ge":
        return value >= t
    if op == "lt":
        return value < t
    if op == "le":
        return value <= t
    if op == "range_in":
        return (lo is not None and hi is not None) and (lo <= value <= hi)
    if op == "range_out":
        return (lo is not None and hi is not None) and (value < lo or value > hi)
    raise ValueError(f"unknown threshold_op: {op!r}")


class SeasonalReferencePrior:
    method_version = "seasonal_reference_v1"

    def __init__(self, source: ObservationSource, config: DifficultyConfig):
        self.source = source
        self.config = config

    def compute(self, contract: WeatherContract) -> WeatherPriorResult:
        base = WeatherPriorResult(
            method_version=self.method_version,
            station=contract.station,
            measurement=contract.measurement,
            source=getattr(self.source, "name", "unknown"),
            temporal_status="retrospective_approximation",
            retrospective_approximation=True,
            reliability_flags=["correlated_days"],
        )
        if not contract.station_id or contract.target_date is None or contract.threshold_op is None:
            base.missing = True
            base.reliability_flags.append("insufficient_contract")
            return base

        years_back = int(self.config.prior_cfg("years_back"))
        window = int(self.config.prior_cfg("seasonal_window_days"))
        min_years = int(self.config.prior_cfg("min_years"))
        alpha = float(self.config.prior_cfg("smoothing_alpha"))

        target_doy = contract.target_date.timetuple().tm_yday
        target_year = contract.target_date.year

        n = k = 0
        years: set[int] = set()
        yrs_seen: list[int] = []
        for obs in self.source.get_daily(contract.station_id, contract.measurement):
            try:
                d = date.fromisoformat(obs.date)
            except ValueError:
                continue
            if d.year >= target_year or d.year < target_year - years_back:
                continue  # only earlier complete years within the lookback
            if _doy_dist(d.timetuple().tm_yday, target_doy) > window:
                continue
            v = _to_units(float(obs.value), obs.units, contract.units)
            n += 1
            years.add(d.year)
            yrs_seen.append(d.year)
            if _yes_predicate(v, contract):
                k += 1

        base.valid_observation_count = n
        base.distinct_year_count = len(years)
        if n == 0:
            base.missing = True
            return base

        p = (k + alpha) / (n + 2.0 * alpha)
        base.probability_yes = p
        base.confidence = max(p, 1.0 - p)
        base.favored_outcome = "YES" if p >= 0.5 else "NO"
        base.historical_date_range = f"{min(yrs_seen)}-{max(yrs_seen)}"
        base.coverage_ok = len(years) >= min_years
        if not base.coverage_ok:
            base.reliability_flags.append("low_distinct_years")
        return base

    def coverage_summary(self, r: WeatherPriorResult) -> dict:
        return {
            "valid_observations": r.valid_observation_count,
            "distinct_years": r.distinct_year_count,
            "historical_date_range": r.historical_date_range,
            "coverage_ok": r.coverage_ok,
            "reliability_flags": list(r.reliability_flags),
            "temporal_status": r.temporal_status,
        }
