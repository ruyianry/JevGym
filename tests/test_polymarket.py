from __future__ import annotations


def test_polymarket_parses_into_normalized_records(settings):
    from jevgym.data.parse import load_markets, load_prices, parse_all
    from jevgym.data.polymarket.ingest import seed_from_fixtures

    seed_from_fixtures(settings)
    parse_all(settings)

    poly = {m.ticker: m for m in load_markets(settings) if m.source_provider == "polymarket"}
    assert len(poly) == 2
    assert poly["0xiran-nuclear-2026"].outcome_binary == 0  # resolved NO
    assert poly["0xbtc-150k-2026"].outcome_binary == 1  # resolved YES
    assert {m.category for m in poly.values()} == {"Politics", "Crypto"}

    prices = [p for p in load_prices(settings) if p.source_provider == "polymarket"]
    assert prices
    # Polymarket prices are already probability units in [0, 1].
    assert all(0.0 <= p.yes_bid <= 1.0 for p in prices if p.yes_bid is not None)


def test_polymarket_helpers():
    from jevgym.data.polymarket.ingest import is_binary, yes_token

    m = {"outcomes": '["Yes","No"]', "clobTokenIds": '["tokY","tokN"]'}
    assert is_binary(m)
    assert yes_token(m) == "tokY"
    assert not is_binary({"outcomes": '["A","B","C"]'})
