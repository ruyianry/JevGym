from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone

from jevgym.curation.config import load_config
from jevgym.curation.difficulty import market_quote_at, mine
from jevgym.curation.schemas import FeatureSnapshot, ReviewPacket
from jevgym.models import PricePoint
from jevgym.util import utcnow

UTC = timezone.utc


def _seed(settings):
    from jevgym.curation.fixtures import load_fixture_obs_source, seed_weather_fixtures
    from jevgym.data.parse import parse_all

    seed_weather_fixtures(settings)
    parse_all(settings)
    return load_fixture_obs_source(settings)


def _mine(settings):
    obs = _seed(settings)
    return mine(settings, load_config(), obs)


# --- outcome-free structure -----------------------------------------------
# Forbid EVENTUAL-outcome fields. (favored_outcome / favored_outcomes_agree are pre-event
# direction fields — the prior's/market's favored side, not what actually happened.)
_FORBIDDEN = {"outcome", "y", "result", "resolved", "label", "final_price", "settlement_value", "settlement_ts"}


def test_mining_and_review_schemas_are_outcome_free():
    from jevgym.curation.schemas import QuoteQuality, WeatherContract, WeatherPriorResult

    for cls in (FeatureSnapshot, ReviewPacket, WeatherContract, QuoteQuality, WeatherPriorResult):
        for f in cls.model_fields:
            assert f not in _FORBIDDEN, f"{cls.__name__}.{f} leaks an outcome"
            assert "settlement" not in f, f"{cls.__name__}.{f} leaks settlement"


# --- nomination logic ------------------------------------------------------
def test_easy_nomination_aligned_and_selection(settings):
    anns, _feats, funnel = _mine(settings)
    assert funnel["easy_candidate_aligned"] >= 3
    cands = [a for a in anns if a.selection_status == "candidate"]
    assert any(a.market_probability >= 0.5 for a in cands)  # favored YES
    assert any(a.market_probability < 0.5 for a in cands)  # favored NO
    sel = [a for a in anns if a.selected]
    by_event = Counter((a.event_cluster_id, a.horizon_label) for a in sel)
    assert all(c == 1 for c in by_event.values())  # one per event per horizon
    assert all(a.difficulty == "unassigned" for a in anns)  # nothing auto-labeled easy


def test_weak_prior_or_low_odds_not_nominated(settings):
    anns, _, _ = _mine(settings)
    la = [a for a in anns if a.market_ticker.startswith("KXHIGHLAX")]
    assert la and all(a.selection_status != "candidate" for a in la)


def test_ineligible_stays_unassigned_never_hard(settings):
    anns, _, _ = _mine(settings)
    spr = [a for a in anns if a.market_ticker.startswith("KXHIGHSPR")]  # unknown station
    assert spr and all(a.selection_status == "ineligible" and a.difficulty == "unassigned" for a in spr)


def test_multibucket_is_not_a_resolved_categorical(settings):
    anns, _, _ = _mine(settings)
    bucket = [a for a in anns if a.market_ticker.startswith("KXHIGHNY-26JUL20")]
    cands = [a for a in bucket if a.selection_status == "candidate"]
    assert len(cands) >= 2  # several easy-NO siblings
    per_h = Counter(a.horizon_label for a in bucket if a.selected)
    assert per_h and all(c == 1 for c in per_h.values())  # at most one selected per horizon


# --- determinism + leakage invariants -------------------------------------
def test_repeated_runs_are_identical(settings):
    a1, _, f1 = _mine(settings)
    a2, _, f2 = _mine(settings)
    assert [x.model_dump(mode="json") for x in a1] == [x.model_dump(mode="json") for x in a2]
    assert f1 == f2


def test_outcome_flip_does_not_change_candidates(settings):
    from jevgym.curation.fixtures import load_fixture_obs_source
    from jevgym.data.parse import NORM_MARKETS, load_markets
    from jevgym.io import write_model_jsonl

    obs = _seed(settings)
    cfg = load_config()
    baseline = sorted((a.snapshot_id, a.selected, a.selection_status) for a in mine(settings, cfg, obs)[0])

    markets = load_markets(settings)
    for m in markets:
        m.result = "no" if (m.result or "").lower() == "yes" else "yes"  # flip every outcome
    write_model_jsonl(settings.paths.normalized / NORM_MARKETS, markets)

    flipped = sorted(
        (a.snapshot_id, a.selected, a.selection_status)
        for a in mine(settings, cfg, load_fixture_obs_source(settings))[0]
    )
    assert baseline == flipped  # mining never reads the outcome


# --- quote-quality unit tests ---------------------------------------------
def _pt(end, bid, ask):
    return PricePoint(
        market_ticker="T", timestamp=end, yes_bid=bid, yes_ask=ask,
        source_provider="kalshi", source_endpoint="c", source_identifier="T",
        retrieved_at=utcnow(), available_at=end,
    )


def test_candle_spanning_snapshot_is_rejected():
    cfg = load_config()
    as_of = datetime(2026, 7, 14, 4, 0, tzinfo=UTC)
    before = _pt(as_of - timedelta(minutes=30), 0.9, 0.92)
    spanning = _pt(as_of + timedelta(minutes=30), 0.9, 0.92)  # interval ends after as_of
    q = market_quote_at([before, spanning], as_of, cfg)
    assert q.status == "ok" and q.quote_timestamp == before.timestamp


def test_quote_quality_edge_cases():
    cfg = load_config()
    as_of = datetime(2026, 7, 14, 4, 0, tzinfo=UTC)
    q = market_quote_at([_pt(as_of, 0.0, 0.02)], as_of, cfg)  # zero is valid, not null
    assert q.status == "ok" and abs(q.market_confidence - 0.99) < 1e-9
    assert market_quote_at([_pt(as_of, 0.6, 0.5)], as_of, cfg).status == "crossed_quote"
    assert market_quote_at([_pt(as_of, None, 0.5)], as_of, cfg).status == "missing_bid_or_ask"
    assert market_quote_at([_pt(as_of, 0.5, 0.7)], as_of, cfg).status == "wide_spread"
    assert market_quote_at([_pt(as_of - timedelta(hours=5), 0.9, 0.92)], as_of, cfg).status == "stale_quote"
    assert market_quote_at([_pt(as_of + timedelta(hours=1), 0.9, 0.92)], as_of, cfg).status == "no_quote_before_snapshot"


# --- contract parsing ------------------------------------------------------
def test_weather_contract_parsing():
    from jevgym.curation.fixtures import _SPECS, _market
    from jevgym.curation.weather_contract import parse_weather_contract
    from jevgym.data.parse import _market_from_wrapper

    ticker, event, series, sid, target, st, floor, cap, yes_sub, rules, result, _yp = _SPECS[0]
    market = _market_from_wrapper(
        {"obj": _market(ticker, event, series, sid, target, st, floor, cap, yes_sub, rules, result), "endpoint": "/markets"}
    )
    c = parse_weather_contract(market)
    assert c.eligible
    assert c.station_id == "KNYC" and c.measurement == "tmax"
    assert c.threshold_op == "gt" and c.threshold_value == 70.0
    assert c.units == "F" and c.target_date.isoformat() == "2026-07-15"
    assert c.local_convention == "local_civil_day"
