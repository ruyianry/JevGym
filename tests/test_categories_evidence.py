from __future__ import annotations

from datetime import datetime, timedelta, timezone

from jevgym.data.categories import (
    DOMAIN_BY_SERIES,
    category_by_series,
    series_for,
)
from jevgym.evidence.history import SeriesHistory
from jevgym.models import EvidenceItem, Market, MarketState, Outcome, PublicState, Snapshot
from jevgym.snapshots.builder import domain_of
from jevgym.snapshots.render import render
from jevgym.util import utcnow

UTC = timezone.utc


def _prov():
    now = utcnow()
    return dict(
        source_provider="kalshi", source_endpoint="/x", source_identifier="x",
        retrieved_at=now, available_at=now,
    )


def _mkt(ticker, series, settled_day, result):
    base = datetime(2026, 1, 1, tzinfo=UTC)
    st = base + timedelta(days=settled_day)
    return Market(
        ticker=ticker, series_ticker=series, title=f"{series} question", yes_sub_title=f"{ticker} bracket",
        result=result, status="settled", open_time=base, close_time=st, settlement_ts=st, **_prov()
    )


# --- registry --------------------------------------------------------------
def test_category_registry():
    assert "KXCPIYOY" in series_for(["Economics"])
    assert "KXBTCD" in series_for(["Cryptocurrencies"])
    assert DOMAIN_BY_SERIES["KXCPIYOY"] == "economics"
    assert DOMAIN_BY_SERIES["KXBTCD"] == "crypto"
    assert DOMAIN_BY_SERIES["KXTORNADO"] == "weather"
    assert category_by_series(["Economics"])["KXFED"] == "Economics"
    # expanded categories
    assert "KXSPOT" in series_for(["Companies"]) and DOMAIN_BY_SERIES["KXSPOT"] == "companies"
    assert DOMAIN_BY_SERIES["KXNZDUSD"] == "financials"
    assert DOMAIN_BY_SERIES["KXOPENSHARE"] == "science"
    assert DOMAIN_BY_SERIES["KXAAAGASM"] == "commodities"
    assert DOMAIN_BY_SERIES["KXLNBPGAME"] == "sports"


def test_gated_categories_are_opt_in():
    # Elections/geopolitics is sensitive: excluded from the default set, included only by name.
    default = series_for()
    assert "KXTRUMPNUMSTATES" not in default
    assert "KXTRUMPNUMSTATES" in series_for(["Elections"])
    assert DOMAIN_BY_SERIES["KXTRUMPNUMSTATES"] == "politics"  # -> sensitive downstream


def test_domain_of_uses_series_registry_when_category_missing():
    m = Market(ticker="KXCPIYOY-26SEP-T2.5", series_ticker="KXCPIYOY", status="settled", **_prov())
    assert domain_of(m) == "economics"  # no category -> series fallback
    m2 = Market(ticker="X", series_ticker="KXBTCD", category="Cryptocurrencies", status="settled", **_prov())
    assert domain_of(m2) == "crypto"  # explicit category wins


# --- prior-decisions evidence ---------------------------------------------
def test_series_history_prior_decisions_leakage_safe():
    base = datetime(2026, 1, 1, tzinfo=UTC)
    m1 = _mkt("S-1", "KXU3", 10, "yes")
    m2 = _mkt("S-2", "KXU3", 20, "no")
    m3 = _mkt("S-3", "KXU3", 40, "yes")  # settles AFTER the checkpoint below
    target = _mkt("S-T", "KXU3", 45, "no")
    hist = SeriesHistory([m1, m2, m3, target])
    ts = base + timedelta(days=30)  # between m2 and m3

    ev = hist.evidence_for(target, ts, "economics")
    assert ev is not None and ev.evidence_type == "prior_decisions"
    assert ev.available_at <= ts  # leakage-safe
    tickers = [d["market"] for d in ev.payload["recent"]]
    assert "S-1" in tickers and "S-2" in tickers
    assert "S-3" not in tickers  # future settlement excluded
    assert "S-T" not in tickers  # never include self
    assert ev.payload["n_prior"] == 2
    assert ev.payload["recent"][0]["market"] == "S-2"  # most recent first


def test_series_history_none_when_no_prior():
    base = datetime(2026, 1, 1, tzinfo=UTC)
    first = _mkt("S-1", "KXU3", 10, "yes")
    hist = SeriesHistory([first])
    assert hist.evidence_for(first, base + timedelta(days=5), "economics") is None


# --- rendering -------------------------------------------------------------
def test_render_includes_prior_decisions():
    now = utcnow()
    ev = EvidenceItem(
        evidence_id="e1", evidence_type="prior_decisions",
        payload={
            "domain": "economics", "series": "KXCPIYOY", "n_prior": 3, "yes_rate": 0.667,
            "recent": [{"market": "KXCPIYOY-26AUG-T2.5", "title": "CPI YoY > 2.5%", "result": "yes", "settled": "2026-08-15"}],
        },
        **_prov(),
    )
    snap = Snapshot(
        snapshot_id="s1", market_ticker="KXCPIYOY-26SEP-T2.5", event_ticker="e", domain="economics",
        timestamp=now, forecast_horizon="7d",
        public_state=PublicState(market_title="Will CPI YoY exceed 2.5%?", rules_primary="Resolves YES if...", evidence=[ev]),
        market_state=MarketState(p_market=0.5), outcome=Outcome(resolved=True, y=1), **_prov(),
    )
    state = render(snap, reveal_market=False).state
    assert "Prior decisions in KXCPIYOY" in state
    assert "CPI YoY > 2.5%" in state and "YES" in state
