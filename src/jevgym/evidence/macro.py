"""Macro-indicator evidence (FRED): unemployment, nonfarm payrolls, CPI.

Reads FRED observation blobs from the raw cache and emits one ``EvidenceItem`` per
observation, stamped with the figure's public release date as ``available_at`` (so a model
forecasting an FOMC market only ever sees macro prints that were actually published by the
checkpoint time). A live fetcher is included for populating the raw cache.

Note on point-in-time correctness: true vintage data uses FRED's releases/ALFRED endpoints.
Here we use each observation's ``realtime_start`` (or an explicit ``release_date``) as the
availability time — a reasonable proxy; upgrading to full ALFRED vintages is a later step.
"""

from __future__ import annotations

from ..config import Settings
from ..data.kalshi import rawpaths
from ..data.kalshi.rawcache import RawCache
from ..models import EvidenceItem
from ..util import parse_dt, short_hash, utcnow
from .base import register_evidence_source

# Default macro series (the trend context for economics markets): unemployment, payrolls, CPI,
# the fed funds rate, and real GDP — covering the CPI / payrolls / U-3 / Fed / GDP markets.
DEFAULT_FRED_SERIES = ["UNRATE", "PAYEMS", "CPIAUCSL", "FEDFUNDS", "GDPC1"]


@register_evidence_source
class MacroEvidenceSource:
    name = "macro_fred"
    domain = "economics"

    def __init__(self, series_ids: list[str] | None = None):
        self.series_ids = series_ids or DEFAULT_FRED_SERIES

    def build(self, settings: Settings) -> list[EvidenceItem]:
        rc = RawCache(settings.paths.raw)
        items: list[EvidenceItem] = []
        for series_id, blob in rc.iter_blobs(rawpaths.FRED_DIR):
            items.extend(self._items_from_blob(series_id, blob))
        return items

    def _items_from_blob(self, series_id: str, blob: dict) -> list[EvidenceItem]:
        title = blob.get("title")
        units = blob.get("units")
        retrieved = parse_dt(blob.get("retrieved_at")) or utcnow()
        endpoint = blob.get("endpoint", "fred/observations")
        out: list[EvidenceItem] = []
        for obs in blob.get("observations") or []:
            available = parse_dt(obs.get("release_date") or obs.get("realtime_start"))
            if available is None:
                # Without a release/vintage date we cannot guarantee leakage-safety; skip.
                continue
            out.append(
                EvidenceItem(
                    evidence_id=short_hash("fred", series_id, obs.get("date")),
                    evidence_type="macro_indicator",
                    payload={
                        "series_id": series_id,
                        "title": title,
                        "period": obs.get("date"),
                        "value": obs.get("value"),
                        "units": units,
                        "domain": "economics",
                    },
                    source_provider="fred",
                    source_endpoint=endpoint,
                    source_identifier=series_id,
                    retrieved_at=retrieved,
                    available_at=available,
                )
            )
        return out


def fetch_fred(settings: Settings, series_ids: list[str] | None = None) -> dict:
    """Live: fetch FRED observations into the raw cache (requires FRED_API_KEY).

    Uses ALFRED-style realtime output so ``realtime_start`` can serve as availability time.
    """
    import httpx

    if not settings.fred_api_key:
        raise RuntimeError("FRED_API_KEY is not set; cannot fetch live macro evidence.")
    series_ids = series_ids or DEFAULT_FRED_SERIES
    rc = RawCache(settings.paths.raw)
    n = 0
    with httpx.Client(base_url=settings.fred_api_base, timeout=30.0) as client:
        for sid in series_ids:
            params = {
                "series_id": sid,
                "api_key": settings.fred_api_key,
                "file_type": "json",
                "realtime_start": "1900-01-01",  # request vintages
            }
            resp = client.get("/series/observations", params=params)
            resp.raise_for_status()
            data = resp.json()
            rc.write_blob(
                rawpaths.fred_series(sid),
                {"series_id": sid, "observations": data.get("observations", [])},
                endpoint="/fred/series/observations",
            )
            n += 1
    return {"fred_series": n}
