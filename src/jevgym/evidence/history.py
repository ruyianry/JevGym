"""Prior-decisions evidence: the series' own recent history as leakage-safe context.

For recurring markets — monthly CPI/payrolls/unemployment, quarterly GDP, the Fed's meetings,
monthly tornado counts — how the *same series* resolved in the recent past is exactly the kind of
context a forecaster should weigh. This source summarizes the most recent settled outcomes of a
market's series that were **already public** at the checkpoint (``settlement_ts < checkpoint``),
so it can never leak the current outcome. The renderer folds it into the STATE block.

Computed directly from the ingested markets (no external call, no API key).
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from datetime import datetime

from ..models import EvidenceItem, Market
from ..util import short_hash, utcnow


class SeriesHistory:
    """Index settled markets by series so we can fetch the prior decisions before any moment."""

    def __init__(self, markets: Sequence[Market], *, max_prior: int = 5):
        self.max_prior = max_prior
        self.by_series: dict[str, list[Market]] = defaultdict(list)
        for m in markets:
            if m.series_ticker and m.settlement_ts is not None and m.outcome_binary is not None:
                self.by_series[m.series_ticker].append(m)
        for lst in self.by_series.values():
            lst.sort(key=lambda m: m.settlement_ts)

    def evidence_for(self, market: Market, ts: datetime, domain: str) -> EvidenceItem | None:
        """A single ``prior_decisions`` item for ``market``'s series, visible at ``ts``."""
        series = market.series_ticker
        if not series:
            return None
        prior = [
            m
            for m in self.by_series.get(series, [])
            if m.settlement_ts < ts and m.ticker != market.ticker
        ]
        if not prior:
            return None
        recent = prior[-self.max_prior :]
        decisions = [
            {
                "market": m.ticker,
                "title": (m.yes_sub_title or m.title or m.ticker),
                "result": (m.result or ("yes" if m.outcome_binary == 1 else "no")),
                "settled": m.settlement_ts.date().isoformat(),
            }
            for m in reversed(recent)  # most recent first
        ]
        yes = sum(1 for m in prior if m.outcome_binary == 1)
        available = recent[-1].settlement_ts  # latest included prior settlement (< ts)
        return EvidenceItem(
            evidence_id=short_hash("hist", series, ts.isoformat()),
            evidence_type="prior_decisions",
            payload={
                "domain": domain,
                "series": series,
                "n_prior": len(prior),
                "yes_rate": round(yes / len(prior), 3),
                "recent": decisions,
            },
            market_ticker=market.ticker,
            source_provider="jevgym",
            source_endpoint="series-history",
            source_identifier=series,
            retrieved_at=utcnow(),
            available_at=available,
        )


__all__ = ["SeriesHistory"]
