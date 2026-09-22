"""The Kalshi crowd forecast as a *baseline* — explicitly NOT an oracle.

``kalshi_market`` reports p_K(t): the contemporaneous market-implied YES probability at the
checkpoint. The true oracle is the eventual resolution Y (``snapshot.outcome.y``), which this
class never reads. It is a ``Baseline`` (reads the snapshot's market_state), not a
``SystemOneProvider``, and it is undefined in the blind track (it *is* market information).
"""

from __future__ import annotations

from ..models import DecisionResult, Snapshot


class KalshiMarketBaseline:
    name = "kalshi_market"
    model_id = "kalshi_market"

    def predict(self, snapshot: Snapshot) -> DecisionResult:
        p = snapshot.market_state.p_market
        if p is None:
            p = 0.5
        p = min(1.0, max(0.0, float(p)))
        return DecisionResult(
            probabilities={"YES": p, "NO": 1.0 - p},
            selected="YES" if p >= 0.5 else "NO",
            latency_ms=0.0,
            provider=self.name,
            model_id=self.model_id,
        )
