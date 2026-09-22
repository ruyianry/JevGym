from __future__ import annotations

from jevgym.models import DecisionResult, Market, PricePoint
from jevgym.util import utcnow


def _prov():
    now = utcnow()
    return dict(
        source_provider="kalshi",
        source_endpoint="/markets",
        source_identifier="X",
        retrieved_at=now,
        available_at=now,
    )


def test_market_outcome_binary():
    assert Market(ticker="X", result="yes", status="settled", **_prov()).outcome_binary == 1
    assert Market(ticker="X", result="no", status="settled", **_prov()).outcome_binary == 0
    m = Market(ticker="X", result="", status="open", **_prov())
    assert m.outcome_binary is None
    assert not m.is_resolved


def test_pricepoint_derived():
    p = PricePoint(market_ticker="X", timestamp=utcnow(), yes_bid=0.40, yes_ask=0.44, **_prov())
    assert abs(p.mid - 0.42) < 1e-9
    assert abs(p.no_ask - 0.60) < 1e-9


def test_decision_result_normalize():
    dr = DecisionResult(probabilities={"YES": 2.0, "NO": 2.0}, provider="p", model_id="m").normalized()
    assert abs(sum(dr.probabilities.values()) - 1.0) < 1e-9
    assert dr.probabilities["YES"] == 0.5
    # zero-mass falls back to uniform
    dr0 = DecisionResult(probabilities={"YES": 0.0, "NO": 0.0}, provider="p", model_id="m").normalized()
    assert dr0.probabilities == {"YES": 0.5, "NO": 0.5}
