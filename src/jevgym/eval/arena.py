"""The sequential trading arena — **reward (P&L) is the headline metric**.

Default mode = **edge one-shot**: the model states its own P(YES) (market-aware — it *sees*
the crowd price and adjusts), and a trade is taken only where the model's probability beats
the ask, i.e. positive expected value. It enters the better side at the first such checkpoint,
one contract, held to resolution. Reward = realized P&L in dollars.

    edge_yes = p_model - yes_ask      edge_no = (1 - p_model) - no_ask
    trade the side whose edge > threshold; else wait.

This ties the reward directly to the model's forecast — "trade on your probability's
adjustment of the market, then see the reward." An older action-tool mode is kept for
experiments. Modes are pluggable so repeated-bet / full-trading drop in later.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import timedelta

from ..models import ActionType, ArenaResult, Snapshot, Trade
from ..providers.base import decide_question
from ..snapshots.render import render, render_action


def _yes_ask(s: Snapshot) -> float:
    ms = s.market_state
    if ms.yes_ask is not None:
        return ms.yes_ask
    return ms.p_market if ms.p_market is not None else 0.5


def _no_ask(s: Snapshot) -> float:
    ms = s.market_state
    if ms.yes_bid is not None:
        return 1.0 - ms.yes_bid
    return (1.0 - ms.p_market) if ms.p_market is not None else 0.5


def one_shot_reward(trade: Trade | None, y: int) -> float:
    if trade is None:
        return 0.0
    win = (trade.side == "yes" and y == 1) or (trade.side == "no" and y == 0)
    return (1.0 - trade.price) if win else (-trade.price)


def forecast_p_yes(provider, snapshot: Snapshot) -> float:
    """The provider's market-aware P(YES) for this checkpoint."""
    if hasattr(provider, "predict") and not hasattr(provider, "decide"):
        dr = provider.predict(snapshot)
    else:
        dr = decide_question(provider, render(snapshot, reveal_market=True)).normalized()
    return float(dr.probabilities.get("YES", 0.5))


class EdgeOneShotMode:
    """One-shot timing driven by the model's probability edge vs. the market ask."""

    name = "edge_one_shot"

    def __init__(self, edge_threshold: float = 0.0):
        self.edge_threshold = edge_threshold

    def run_episode(self, provider, snapshots: list[Snapshot]) -> ArenaResult:
        snaps = sorted(snapshots, key=lambda s: s.timestamp)
        market = snaps[0].market_ticker
        domain = snaps[0].domain
        uncertainty_band = snaps[0].uncertainty_band
        y = snaps[-1].outcome.y

        trade: Trade | None = None
        model_p = None
        edge = None
        steps = 0
        if y is not None:
            for i, s in enumerate(snaps):
                p = forecast_p_yes(provider, s)
                steps += 1
                ya, na = _yes_ask(s), _no_ask(s)
                e_yes, e_no = p - ya, (1.0 - p) - na
                if e_yes >= e_no and e_yes > self.edge_threshold:
                    trade = Trade(step_index=i, timestamp=s.timestamp, side="yes", price=ya)
                    model_p, edge = p, e_yes
                    break
                if e_no > e_yes and e_no > self.edge_threshold:
                    trade = Trade(step_index=i, timestamp=s.timestamp, side="no", price=na)
                    model_p, edge = p, e_no
                    break

        reward = one_shot_reward(trade, y) if y is not None else 0.0
        return ArenaResult(
            market_ticker=market,
            domain=domain,
            uncertainty_band=uncertainty_band,
            provider=getattr(provider, "name", "unknown"),
            model_id=getattr(provider, "model_id", "unknown"),
            entered=trade is not None,
            trade=trade,
            trades=[trade] if trade is not None else [],
            contracts=trade.contracts if trade is not None else 0.0,
            outcome_y=y,
            reward=reward,
            steps=steps,
            model_p=model_p,
            edge=edge,
            mode=self.name,
        )


def _select_action(provider, snapshot: Snapshot) -> str:
    cq = render_action(snapshot)
    result = decide_question(provider, cq).normalized()
    return max(result.probabilities, key=result.probabilities.get)


class ActionOneShotMode:
    """Alternative: the model picks bet-YES / bet-NO / wait via a typed action question."""

    name = "action_one_shot"

    def run_episode(self, provider, snapshots: list[Snapshot]) -> ArenaResult:
        snaps = sorted(snapshots, key=lambda s: s.timestamp)
        market = snaps[0].market_ticker
        y = snaps[-1].outcome.y
        trade: Trade | None = None
        steps = 0
        if y is not None:
            for i, s in enumerate(snaps):
                action = _select_action(provider, s)
                steps += 1
                if action == ActionType.BET_YES.value:
                    trade = Trade(step_index=i, timestamp=s.timestamp, side="yes", price=_yes_ask(s))
                    break
                if action == ActionType.BET_NO.value:
                    trade = Trade(step_index=i, timestamp=s.timestamp, side="no", price=_no_ask(s))
                    break
        reward = one_shot_reward(trade, y) if y is not None else 0.0
        return ArenaResult(
            market_ticker=market,
            domain=snaps[0].domain,
            provider=getattr(provider, "name", "unknown"),
            model_id=getattr(provider, "model_id", "unknown"),
            entered=trade is not None,
            trade=trade,
            trades=[trade] if trade is not None else [],
            contracts=trade.contracts if trade is not None else 0.0,
            outcome_y=y,
            reward=reward,
            steps=steps,
            mode=self.name,
        )


def _window_by_days(snaps: list[Snapshot], max_days: int) -> list[Snapshot]:
    """Keep only checkpoints within ``max_days`` of resolution — the last-week trading window."""
    if not snaps or max_days <= 0:
        return snaps
    cutoff = snaps[-1].timestamp - timedelta(days=max_days)
    return [s for s in snaps if s.timestamp >= cutoff]


class RepeatedBetMode:
    """Multi-day repeated betting — the "trade every day for ~a week" horizon.

    Over the last ``max_days``-day window before resolution, the model re-forecasts at each
    daily checkpoint and adds **one** contract on its positive-edge side whenever its own
    P(YES) still beats the ask. Positions accumulate and are all held to resolution, so a
    conviction that persists as the market drifts compounds across the week. Reward = total
    realized P&L over every fill; ``return_per_contract`` normalizes by position size.
    """

    name = "repeated"

    def __init__(
        self, edge_threshold: float = 0.0, max_days: int = 7, max_contracts: int | None = None
    ):
        self.edge_threshold = edge_threshold
        self.max_days = max_days
        self.max_contracts = max_contracts

    def run_episode(self, provider, snapshots: list[Snapshot]) -> ArenaResult:
        snaps = sorted(snapshots, key=lambda s: s.timestamp)
        window = _window_by_days(snaps, self.max_days)
        y = snaps[-1].outcome.y

        trades: list[Trade] = []
        first_p = first_edge = None
        steps = 0
        if y is not None:
            for i, s in enumerate(window):
                if self.max_contracts is not None and len(trades) >= self.max_contracts:
                    break
                p = forecast_p_yes(provider, s)
                steps += 1
                ya, na = _yes_ask(s), _no_ask(s)
                e_yes, e_no = p - ya, (1.0 - p) - na
                if e_yes >= e_no and e_yes > self.edge_threshold:
                    trades.append(Trade(step_index=i, timestamp=s.timestamp, side="yes", price=ya))
                    if first_p is None:
                        first_p, first_edge = p, e_yes
                elif e_no > e_yes and e_no > self.edge_threshold:
                    trades.append(Trade(step_index=i, timestamp=s.timestamp, side="no", price=na))
                    if first_p is None:
                        first_p, first_edge = p, e_no

        reward = sum(one_shot_reward(t, y) for t in trades) if y is not None else 0.0
        contracts = sum(t.contracts for t in trades)
        return ArenaResult(
            market_ticker=snaps[0].market_ticker,
            domain=snaps[0].domain,
            uncertainty_band=snaps[0].uncertainty_band,
            provider=getattr(provider, "name", "unknown"),
            model_id=getattr(provider, "model_id", "unknown"),
            entered=bool(trades),
            trade=trades[0] if trades else None,
            trades=trades,
            contracts=contracts,
            outcome_y=y,
            reward=reward,
            steps=steps,
            model_p=first_p,
            edge=first_edge,
            mode=self.name,
        )


ARENA_MODES = ["one_shot", "edge_one_shot", "action", "action_one_shot", "repeated", "multi_day"]


def _make_mode(
    mode: str, edge_threshold: float, max_days: int = 7, max_contracts: int | None = None
):
    if mode in ("one_shot", "edge_one_shot", "edge"):
        return EdgeOneShotMode(edge_threshold)
    if mode in ("action", "action_one_shot"):
        return ActionOneShotMode()
    if mode in ("repeated", "multi_day", "week"):
        return RepeatedBetMode(edge_threshold, max_days=max_days, max_contracts=max_contracts)
    raise KeyError(f"Unknown arena mode '{mode}'. Known: {ARENA_MODES}")


def run_arena(
    provider,
    snapshots: list[Snapshot],
    mode: str = "one_shot",
    edge_threshold: float = 0.0,
    max_days: int = 7,
    max_contracts: int | None = None,
) -> list[ArenaResult]:
    engine = _make_mode(mode, edge_threshold, max_days=max_days, max_contracts=max_contracts)
    by_market: dict[str, list[Snapshot]] = defaultdict(list)
    for s in snapshots:
        by_market[s.market_ticker].append(s)
    return [engine.run_episode(provider, ss) for ss in by_market.values()]
