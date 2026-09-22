from __future__ import annotations

from datetime import datetime, timedelta, timezone

from jevgym.eval.arena import one_shot_reward, run_arena
from jevgym.models import DecisionResult, MarketState, Outcome, PublicState, Snapshot, Trade
from jevgym.util import utcnow

UTC = timezone.utc


class ConstProb:
    """A provider that always reports the same P(YES) (market-aware)."""

    def __init__(self, p: float, name: str = "const"):
        self._p = p
        self.name = name
        self.model_id = name

    def decide(self, state, question, candidates):
        return DecisionResult(
            probabilities={"YES": self._p, "NO": 1.0 - self._p}, provider=self.name, model_id=self.model_id
        )


def _snap(ticker, ts, yes_bid, yes_ask, y):
    return Snapshot(
        snapshot_id=f"{ticker}-{ts.isoformat()}",
        market_ticker=ticker,
        event_ticker=ticker,
        domain="economics",
        timestamp=ts,
        forecast_horizon="x",
        public_state=PublicState(market_title="m"),
        market_state=MarketState(p_market=(yes_bid + yes_ask) / 2, yes_bid=yes_bid, yes_ask=yes_ask),
        outcome=Outcome(resolved=True, y=y),
        source_provider="kalshi",
        source_endpoint="b",
        source_identifier="s",
        retrieved_at=utcnow(),
        available_at=ts,
    )


def test_one_shot_reward_math():
    yes = Trade(step_index=0, timestamp=utcnow(), side="yes", price=0.4)
    assert abs(one_shot_reward(yes, 1) - 0.6) < 1e-9
    assert abs(one_shot_reward(yes, 0) - (-0.4)) < 1e-9
    no = Trade(step_index=0, timestamp=utcnow(), side="no", price=0.3)
    assert abs(one_shot_reward(no, 0) - 0.7) < 1e-9
    assert one_shot_reward(None, 1) == 0.0


def test_edge_trade_enters_yes_on_positive_edge():
    base = datetime(2026, 1, 1, tzinfo=UTC)
    snaps = [_snap("T", base, 0.38, 0.42, 1), _snap("T", base + timedelta(days=1), 0.58, 0.62, 1)]
    r = run_arena(ConstProb(0.95), snaps, mode="one_shot")[0]
    assert r.entered and r.trade.side == "yes" and r.trade.step_index == 0
    assert abs(r.trade.price - 0.42) < 1e-9  # bought YES at the ask
    assert abs(r.reward - 0.58) < 1e-9  # 1 - 0.42, resolves YES
    assert abs(r.model_p - 0.95) < 1e-9 and r.edge > 0


def test_edge_trade_enters_no_side():
    base = datetime(2026, 1, 1, tzinfo=UTC)
    # yes_ask=0.62, no_ask=1-0.58=0.42; a confident-NO model has edge on NO.
    snaps = [_snap("T", base, 0.58, 0.62, 0)]
    r = run_arena(ConstProb(0.05), snaps, mode="one_shot")[0]
    assert r.entered and r.trade.side == "no"
    assert abs(r.trade.price - 0.42) < 1e-9 and abs(r.reward - 0.58) < 1e-9


def test_no_edge_no_trade():
    base = datetime(2026, 1, 1, tzinfo=UTC)
    # zero spread + model agrees with the market -> no positive edge -> wait.
    snaps = [_snap("T", base, 0.5, 0.5, 1)]
    r = run_arena(ConstProb(0.5), snaps, mode="one_shot")[0]
    assert r.entered is False and r.reward == 0.0


def test_one_shot_records_one_contract():
    base = datetime(2026, 1, 1, tzinfo=UTC)
    snaps = [_snap("T", base, 0.38, 0.42, 1)]
    r = run_arena(ConstProb(0.95), snaps, mode="one_shot")[0]
    assert r.contracts == 1.0 and len(r.trades) == 1
    assert abs(r.return_per_contract - 0.58) < 1e-9


def test_repeated_mode_accumulates_contracts_over_week():
    base = datetime(2026, 1, 1, tzinfo=UTC)
    # five daily checkpoints, all cheap YES asks; a confident-YES model buys one each day.
    snaps = [_snap("T", base + timedelta(days=d), 0.38, 0.42, 1) for d in range(5)]
    r = run_arena(ConstProb(0.95), snaps, mode="repeated")[0]
    assert r.mode == "repeated"
    assert r.contracts == 5.0 and len(r.trades) == 5
    assert all(t.side == "yes" for t in r.trades)
    assert abs(r.reward - 5 * 0.58) < 1e-9  # each contract pays 1 - 0.42, resolves YES
    assert abs(r.return_per_contract - 0.58) < 1e-9  # normalized headline return


def test_repeated_mode_respects_max_days_window():
    base = datetime(2026, 1, 1, tzinfo=UTC)
    # ten daily checkpoints; max_days=3 keeps only those within 3 days of the last (days 6..9).
    snaps = [_snap("T", base + timedelta(days=d), 0.38, 0.42, 1) for d in range(10)]
    r = run_arena(ConstProb(0.95), snaps, mode="multi_day", max_days=3)[0]
    assert r.contracts == 4.0  # days 6,7,8,9 fall inside the 3-day window

    r_cap = run_arena(ConstProb(0.95), snaps, mode="repeated", max_contracts=2)[0]
    assert r_cap.contracts == 2.0  # position size capped even with more edge available


def test_repeated_mode_no_edge_no_trades():
    base = datetime(2026, 1, 1, tzinfo=UTC)
    snaps = [_snap("T", base + timedelta(days=d), 0.5, 0.5, 1) for d in range(5)]
    r = run_arena(ConstProb(0.5), snaps, mode="repeated")[0]
    assert r.entered is False and r.contracts == 0.0 and r.reward == 0.0
    assert r.return_per_contract == 0.0
