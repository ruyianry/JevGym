from __future__ import annotations

from jevgym.data.parse import load_markets, load_prices, price_to_prob


def test_price_to_prob_cents():
    assert price_to_prob(83, "cents") == 0.83
    assert price_to_prob(None) is None
    assert price_to_prob(0.83, "prob") == 0.83


def test_parse_produces_binary_markets(parsed):
    markets = load_markets(parsed)
    assert len(markets) == 4
    outcomes = {m.ticker: m.outcome_binary for m in markets}
    assert outcomes["KXFED-26JAN-CUT"] == 1
    assert outcomes["KXFED-26JAN-HOLD"] == 0
    assert all(m.category == "Economics" for m in markets)
    assert all(m.series_ticker for m in markets)


def test_price_points_are_probabilities_and_leakage_safe(parsed):
    prices = load_prices(parsed)
    assert prices, "expected price points"
    assert all(0.0 <= p.yes_bid <= 1.0 for p in prices if p.yes_bid is not None)
    # a price is public exactly at its candlestick timestamp
    assert all(p.available_at == p.timestamp for p in prices)
