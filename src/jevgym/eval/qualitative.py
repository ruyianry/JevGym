"""A readable, single-snapshot trace: what the model saw, what it said, what it did, and how
it turned out. Useful for eyeballing behavior before trusting aggregate numbers.
"""

from __future__ import annotations

from ..config import Settings
from ..providers import build_provider, decide_question, is_baseline
from ..snapshots.builder import load_snapshots
from ..snapshots.render import render
from .arena import _yes_ask, run_arena


def _pick(snaps, market=None, horizon=None, uncertainty=None):
    pool = list(snaps)
    if market:
        pool = [s for s in pool if s.market_ticker == market]
    if uncertainty:
        pool = [s for s in pool if s.uncertainty_band == uncertainty]
    if horizon:
        pool = [s for s in pool if s.forecast_horizon == horizon]
    pool = [s for s in pool if s.market_state.p_market is not None] or pool
    if not pool:
        return None
    for pref in ("q50", "7d", "3d", "24h"):
        for s in pool:
            if s.forecast_horizon == pref:
                return s
    return pool[len(pool) // 2]


def _indent(text: str) -> str:
    return "\n".join("  " + ln for ln in text.splitlines())


def qualitative_trace(
    settings: Settings,
    agent: str = "mock",
    *,
    market: str | None = None,
    horizon: str | None = None,
    uncertainty: str | None = None,
    reveal_market: bool = True,
    state_chars: int = 900,
) -> str:
    snaps = load_snapshots(settings)
    if not snaps:
        return "No snapshots. Run: jevgym ingest ... && parse && build-snapshots."
    s = _pick(snaps, market, horizon, uncertainty)
    if s is None:
        return "No matching snapshot for that filter."

    provider = build_provider(agent, settings)
    cq = render(s, reveal_market=reveal_market)
    dr = provider.predict(s) if is_baseline(provider) else decide_question(provider, cq).normalized()
    p = float(dr.probabilities.get("YES", 0.5))

    ar = None
    if not is_baseline(provider):
        try:
            ar = run_arena(provider, [x for x in snaps if x.market_ticker == s.market_ticker])[0]
        except Exception:
            ar = None

    pm = s.market_state.p_market
    ya = _yes_ask(s)
    right = (p >= 0.5) == (s.outcome.y == 1)
    lines = [
        f"agent: {agent}   model: {dr.model_id}   track: {'market-aware' if reveal_market else 'blind'}",
        f"market: {s.market_ticker}  ({s.source_provider} · {s.domain} · uncertainty={s.uncertainty_band})",
        f"checkpoint: {s.forecast_horizon} @ {s.timestamp.isoformat()}",
        "",
        "state shown to the model (excerpt):",
        _indent(cq.state[:state_chars] + ("\n  ..." if len(cq.state) > state_chars else "")),
        "",
        f"market p(YES) = {pm:.3f}" if pm is not None else "market p(YES) = n/a",
        f"model  p(YES) = {p:.3f}   edge(YES) = {p - ya:+.3f} (vs ask {ya:.3f})",
    ]
    if ar is not None:
        if ar.entered and ar.trade:
            lines.append(
                f"arena: bet {ar.trade.side.upper()} at {ar.trade.price:.3f} (step {ar.trade.step_index}) -> reward {ar.reward:+.3f}"
            )
        else:
            lines.append("arena: no positive-edge entry -> waited -> reward +0.000")
    lines.append(
        f"resolved: {'YES' if s.outcome.y == 1 else 'NO'}   model directionally {'right' if right else 'wrong'}"
    )
    return "\n".join(lines)
