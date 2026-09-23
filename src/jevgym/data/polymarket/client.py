"""HTTP client for Polymarket (Gamma catalog + CLOB price history).

Public reads require no auth. Gamma ``/markets`` paginates via ``limit``/``offset``; CLOB
``/prices-history`` returns ``{"history": [{"t": unix, "p": prob}, ...]}`` for a token id.
Resolved markets typically expose ≥12h granularity.
"""

from __future__ import annotations

from collections.abc import Iterator

import httpx

from ..kalshi.client import RateLimiter
from . import endpoints as ep


class PolymarketClient:
    def __init__(
        self,
        gamma_base: str = ep.GAMMA_BASE,
        clob_base: str = ep.CLOB_BASE,
        *,
        rate_limit_per_sec: float = 8.0,
        timeout: float = 30.0,
        client: httpx.Client | None = None,
    ):
        self.gamma_base = gamma_base.rstrip("/")
        self.clob_base = clob_base.rstrip("/")
        self._limiter = RateLimiter(rate_limit_per_sec)
        self._client = client or httpx.Client(timeout=timeout, follow_redirects=True)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> PolymarketClient:
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def _get(self, url: str, params: dict | None = None) -> object:
        self._limiter.wait()
        resp = self._client.get(url, params=params)
        resp.raise_for_status()
        return resp.json()

    def iter_markets(
        self, *, closed: bool = True, limit: int = 100, max_items: int | None = None, extra_params: dict | None = None
    ) -> Iterator[dict]:
        offset = 0
        got = 0
        while True:
            params = {"closed": str(closed).lower(), "limit": limit, "offset": offset}
            if extra_params:
                params.update(extra_params)
            data = self._get(self.gamma_base + ep.MARKETS, params)
            items = data if isinstance(data, list) else (data.get("data") or [])
            if not items:
                return
            for it in items:
                yield it
                got += 1
                if max_items is not None and got >= max_items:
                    return
            if len(items) < limit:
                return
            offset += limit

    def get_price_history(self, token_id: str, *, interval: str = "max", fidelity: int = 720) -> list[dict]:
        data = self._get(
            self.clob_base + ep.PRICES_HISTORY,
            {"market": token_id, "interval": interval, "fidelity": fidelity},
        )
        return data.get("history") or [] if isinstance(data, dict) else []
