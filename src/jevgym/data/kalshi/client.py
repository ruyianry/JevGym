"""HTTP client for the Kalshi Trade API v2.

* Public reads need no auth; authenticated (higher-rate) access is optional and signed
  lazily (RSA-PSS) only if a key id + private key path are supplied.
* Cursor pagination and a simple token-bucket rate limiter are built in.
* Uses ``httpx`` so tests can intercept calls with ``respx`` without real network.
"""

from __future__ import annotations

import base64
import time
from collections.abc import Iterator
from urllib.parse import urlsplit

import httpx

from . import endpoints as ep


class RateLimiter:
    """Minimal spacing limiter. ``rate_per_sec <= 0`` disables waiting (used in tests)."""

    def __init__(self, rate_per_sec: float):
        self.min_interval = 1.0 / rate_per_sec if rate_per_sec and rate_per_sec > 0 else 0.0
        self._last = 0.0

    def wait(self) -> None:
        if self.min_interval <= 0:
            return
        now = time.monotonic()
        delta = now - self._last
        if delta < self.min_interval:
            time.sleep(self.min_interval - delta)
        self._last = time.monotonic()


class KalshiClient:
    def __init__(
        self,
        base_url: str,
        *,
        api_key_id: str | None = None,
        private_key_path: str | None = None,
        rate_limit_per_sec: float = 4.0,
        timeout: float = 30.0,
        max_retries: int = 6,
        transport: httpx.BaseTransport | None = None,
        client: httpx.Client | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self._route_prefix = urlsplit(self.base_url).path  # e.g. "/trade-api/v2"
        self.api_key_id = api_key_id
        self.private_key_path = private_key_path
        self._max_retries = max_retries
        self._limiter = RateLimiter(rate_limit_per_sec)
        self._client = client or httpx.Client(
            base_url=self.base_url, timeout=timeout, transport=transport
        )

    # --- lifecycle ---------------------------------------------------------
    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> KalshiClient:
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # --- auth (optional) ---------------------------------------------------
    def _auth_headers(self, method: str, path: str) -> dict[str, str]:
        if not (self.api_key_id and self.private_key_path):
            return {}
        # Lazy import so `cryptography` is not a hard dependency for public reads.
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding

        ts = str(int(time.time() * 1000))
        full_path = self._route_prefix + path
        message = (ts + method.upper() + full_path).encode()
        with open(self.private_key_path, "rb") as fh:
            key = serialization.load_pem_private_key(fh.read(), password=None)
        signature = key.sign(
            message,
            padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.DIGEST_LENGTH),
            hashes.SHA256(),
        )
        return {
            "KALSHI-ACCESS-KEY": self.api_key_id,
            "KALSHI-ACCESS-SIGNATURE": base64.b64encode(signature).decode(),
            "KALSHI-ACCESS-TIMESTAMP": ts,
        }

    # --- core --------------------------------------------------------------
    def get(self, path: str, params: dict | None = None) -> dict:
        """GET with a token-bucket wait + exponential backoff on 429/5xx.

        The public Kalshi tier throttles bursts; on ``429 Too Many Requests`` (or a transient
        5xx) we honor ``Retry-After`` when present, else back off exponentially, so a long crawl
        rides through rate limits instead of aborting.
        """
        delay = 0.75
        for attempt in range(self._max_retries + 1):
            self._limiter.wait()
            resp = self._client.get(path, params=params, headers=self._auth_headers("GET", path))
            if resp.status_code == 429 or resp.status_code >= 500:
                if attempt < self._max_retries:
                    retry_after = resp.headers.get("Retry-After")
                    sleep_s = float(retry_after) if (retry_after or "").isdigit() else delay
                    time.sleep(min(sleep_s, 30.0))
                    delay = min(delay * 2, 30.0)
                    continue
            resp.raise_for_status()
            return resp.json()
        resp.raise_for_status()  # retries exhausted
        return resp.json()

    def paginate(
        self,
        path: str,
        *,
        items_key: str,
        params: dict | None = None,
        max_items: int | None = None,
    ) -> Iterator[dict]:
        params = dict(params or {})
        got = 0
        while True:
            data = self.get(path, params=params)
            for item in data.get(items_key) or []:
                yield item
                got += 1
                if max_items is not None and got >= max_items:
                    return
            cursor = data.get("cursor")
            if not cursor:
                return
            params["cursor"] = cursor

    # --- catalog convenience ----------------------------------------------
    def iter_series(self, *, category: str | None = None, max_items: int | None = None) -> Iterator[dict]:
        params = {}
        if category:
            params["category"] = category
        yield from self.paginate(ep.SERIES, items_key="series", params=params, max_items=max_items)

    def iter_events(
        self,
        *,
        status: str | None = None,
        series_ticker: str | None = None,
        with_nested_markets: bool = False,
        limit: int = 200,
        max_items: int | None = None,
    ) -> Iterator[dict]:
        params: dict = {"limit": limit}
        if status:
            params["status"] = status
        if series_ticker:
            params["series_ticker"] = series_ticker
        if with_nested_markets:
            params["with_nested_markets"] = True
        yield from self.paginate(ep.EVENTS, items_key="events", params=params, max_items=max_items)

    def iter_markets(
        self,
        *,
        status: str | None = "settled",
        event_ticker: str | None = None,
        series_ticker: str | None = None,
        limit: int = 200,
        max_items: int | None = None,
    ) -> Iterator[dict]:
        params: dict = {"limit": limit}
        if status:
            params["status"] = status
        if event_ticker:
            params["event_ticker"] = event_ticker
        if series_ticker:
            params["series_ticker"] = series_ticker
        yield from self.paginate(ep.MARKETS, items_key="markets", params=params, max_items=max_items)

    def get_market(self, ticker: str) -> dict | None:
        return self.get(ep.market(ticker)).get("market")

    def get_market_candlesticks(
        self,
        series_ticker: str,
        ticker: str,
        *,
        start_ts: int,
        end_ts: int,
        period_interval: int = ep.PERIOD_1H,
        historical: bool = False,
    ) -> list[dict]:
        path = (
            ep.historical_market_candlesticks(ticker)
            if historical
            else ep.market_candlesticks(series_ticker, ticker)
        )
        data = self.get(
            path, {"start_ts": start_ts, "end_ts": end_ts, "period_interval": period_interval}
        )
        return data.get("candlesticks") or []
