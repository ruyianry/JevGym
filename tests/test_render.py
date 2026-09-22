from __future__ import annotations

from jevgym.models import ACTION_CANDIDATES
from jevgym.snapshots.builder import load_snapshots
from jevgym.snapshots.render import render, render_action


def test_blind_vs_market_aware(built):
    s = next(x for x in load_snapshots(built) if x.market_state.p_market is not None)
    blind = render(s, reveal_market=False)
    aware = render(s, reveal_market=True)

    assert blind.candidates == ["YES", "NO"]
    for section in ("STATE", "Resolution criteria:", "Information available at this timestamp:"):
        assert section in blind.state
    # the market probability is revealed only in the market-aware rendering
    assert "Contemporaneous Kalshi market probability" not in blind.state
    assert "Contemporaneous Kalshi market probability" in aware.state
    # the question text itself is identical (frozen)
    assert blind.question == aware.question


def test_action_render(built):
    s = next(x for x in load_snapshots(built) if x.market_state.p_market is not None)
    q = render_action(s)
    assert q.candidates == ACTION_CANDIDATES
    assert "tradable prices" in q.state.lower()
