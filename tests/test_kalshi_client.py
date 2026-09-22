from __future__ import annotations

import httpx
import respx

from jevgym.data.kalshi.client import KalshiClient, RateLimiter

BASE = "https://api.test/trade-api/v2"


@respx.mock
def test_iter_markets_follows_cursor():
    def handler(request):
        if "cursor=C1" in str(request.url):
            return httpx.Response(200, json={"markets": [{"ticker": "B"}], "cursor": ""})
        return httpx.Response(200, json={"markets": [{"ticker": "A"}], "cursor": "C1"})

    respx.route(method="GET", path="/trade-api/v2/markets").mock(side_effect=handler)
    client = KalshiClient(BASE, rate_limit_per_sec=0)
    tickers = [m["ticker"] for m in client.iter_markets(status="settled")]
    assert tickers == ["A", "B"]


@respx.mock
def test_candlesticks():
    respx.route(method="GET", path__regex=r"/candlesticks$").mock(
        return_value=httpx.Response(200, json={"candlesticks": [{"end_period_ts": 1}, {"end_period_ts": 2}]})
    )
    client = KalshiClient(BASE, rate_limit_per_sec=0)
    candles = client.get_market_candlesticks("KXFED", "KXFED-X", start_ts=0, end_ts=10, period_interval=60)
    assert len(candles) == 2


def test_rate_limiter_disabled_is_noop():
    rl = RateLimiter(0)
    rl.wait()  # must not sleep / raise
    assert rl.min_interval == 0.0
