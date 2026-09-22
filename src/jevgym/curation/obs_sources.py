"""Real historical-weather observation sources for the independent seasonal prior.

``OpenMeteoObservationSource`` pulls daily max/min temperatures from Open-Meteo's free
historical archive (no API key). It is an ``ObservationSource`` for
``SeasonalReferencePrior`` — it supplies *background climatology only*. It never reads the
market, any model, or the contract's resolution: the prior itself filters to complete years
strictly BEFORE the target year, so including recent years in the fetch cannot leak the
target-day outcome. Results are cached to ``data/raw/weather/obs_openmeteo/`` so a run is
reproducible and offline after the first fetch.
"""

from __future__ import annotations

import datetime as _dt
import json
from pathlib import Path

import httpx

from ..config import Settings
from .weather_contract import STATION_COORDS, STATIONS
from .weather_prior import DailyObs

ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
_MEASUREMENT = {"tmax": "temperature_2m_max", "tmin": "temperature_2m_min"}


class OpenMeteoObservationSource:
    """Daily station climatology from Open-Meteo's historical archive (Fahrenheit)."""

    name = "open-meteo"

    def __init__(
        self,
        cache_dir: str | Path,
        *,
        start_year: int = 2005,
        end_date: str | None = None,
        client: httpx.Client | None = None,
        timeout: float = 30.0,
    ):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.start_year = start_year
        # Archive lags real time by a few days; default to a safely-available end date.
        self.end_date = end_date or (_dt.date.today() - _dt.timedelta(days=5)).isoformat()
        self._client = client
        self._timeout = timeout
        self._mem: dict[str, list[dict]] = {}

    def _fetch(self, station_id: str, measurement: str) -> list[dict]:
        coords = STATION_COORDS.get(station_id)
        daily = _MEASUREMENT.get(measurement)
        if coords is None or daily is None:
            return []
        lat, lon = coords
        tz = STATIONS.get(station_id, ("", "", "UTC"))[2]
        params = {
            "latitude": lat,
            "longitude": lon,
            "start_date": f"{self.start_year}-01-01",
            "end_date": self.end_date,
            "daily": daily,
            "temperature_unit": "fahrenheit",
            "timezone": tz,
        }
        cli = self._client or httpx.Client(timeout=self._timeout)
        try:
            r = cli.get(ARCHIVE_URL, params=params)
            r.raise_for_status()
            payload = r.json()
        finally:
            if self._client is None:
                cli.close()
        d = payload.get("daily") or {}
        times, vals = d.get("time") or [], d.get(daily) or []
        return [
            {"date": t, "value": float(v), "units": "F"}
            for t, v in zip(times, vals, strict=False)
            if v is not None
        ]

    def get_daily(self, station_id: str, measurement: str) -> list[DailyObs]:
        key = f"{station_id}:{measurement}"
        if key not in self._mem:
            cache = self.cache_dir / f"{station_id}_{measurement}.json"
            if cache.exists():
                self._mem[key] = json.loads(cache.read_text())
            else:
                recs = self._fetch(station_id, measurement)
                cache.write_text(json.dumps(recs))
                self._mem[key] = recs
        return [DailyObs(**o) for o in self._mem[key]]


def open_meteo_source(settings: Settings, **kwargs) -> OpenMeteoObservationSource:
    return OpenMeteoObservationSource(settings.paths.raw / "weather" / "obs_openmeteo", **kwargs)
