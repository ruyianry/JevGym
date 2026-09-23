"""Assemble canonical benchmark snapshots from normalized records.

For every resolved binary market we emit one snapshot per checkpoint, each containing the
separated ``public_state`` / ``market_state`` / ``outcome`` blocks. Evidence is attached
leakage-safely (``available_at <= checkpoint``). Chronological, event-grouped train/val/test
splits are assigned so no event is ever split across splits.
"""

from __future__ import annotations

import bisect
from collections import defaultdict

from ..config import Settings
from ..data.parse import load_markets, load_prices
from ..evidence import evidence_domain, load_evidence
from ..evidence.history import SeriesHistory
from ..io import read_model_jsonl, write_model_jsonl
from ..models import (
    EvidenceItem,
    Market,
    MarketState,
    Outcome,
    PricePoint,
    PublicState,
    Snapshot,
)
from ..sensitivity import difficulty_from_p, is_sensitive
from ..util import short_hash, utcnow
from .horizons import Checkpoint, checkpoints

SNAPSHOTS_FILE = "snapshots.jsonl"

DOMAIN_MAP = {
    "economics": "economics",
    "climate and weather": "weather",
    "weather": "weather",
    "crypto": "crypto",
    "cryptocurrencies": "crypto",
    "sports": "sports",
    "politics": "politics",
    "elections": "politics",  # gated / sensitive
    "financials": "financials",
    "companies": "companies",
    "science and technology": "science",
    "commodities": "commodities",
}


def domain_of(market: Market) -> str:
    cat = (market.category or "").strip().lower()
    if cat:
        return DOMAIN_MAP.get(cat, cat)
    # No category on the market payload — fall back to the curated series→domain registry.
    from ..data.categories import DOMAIN_BY_SERIES

    return DOMAIN_BY_SERIES.get(market.series_ticker or "", "other")


def _price_at_or_before(sorted_prices: list[PricePoint], ts) -> PricePoint | None:
    """Most recent price with timestamp <= ts (bisect on a pre-sorted list)."""
    if not sorted_prices:
        return None
    times = [p.timestamp for p in sorted_prices]
    idx = bisect.bisect_right(times, ts) - 1
    return sorted_prices[idx] if idx >= 0 else None


def _snapshot(
    market: Market,
    cp: Checkpoint,
    domain: str,
    price: PricePoint | None,
    evidence: list[EvidenceItem],
) -> Snapshot:
    p_market = price.mid if price else None
    market_state = MarketState(
        p_market=p_market,
        yes_bid=price.yes_bid if price else None,
        yes_ask=price.yes_ask if price else None,
        last_price=price.last_price if price else None,
        volume=price.volume if price else None,
        open_interest=price.open_interest if price else None,
    )
    public_state = PublicState(
        market_title=market.title or market.yes_sub_title or market.ticker,
        category=market.category,
        rules_primary=market.rules_primary,
        rules_secondary=market.rules_secondary,
        yes_sub_title=market.yes_sub_title,
        no_sub_title=market.no_sub_title,
        open_time=market.open_time,
        close_time=market.close_time,
        evidence=evidence,
    )
    outcome = Outcome(
        resolved=True,
        result=market.result,
        y=market.outcome_binary,
        settlement_ts=market.settlement_ts,
        settlement_value=market.settlement_value,
    )
    sid = short_hash(market.ticker, cp.label, cp.timestamp.isoformat())
    return Snapshot(
        snapshot_id=sid,
        market_ticker=market.ticker,
        event_ticker=market.event_ticker,
        series_ticker=market.series_ticker,
        domain=domain,
        timestamp=cp.timestamp,
        forecast_horizon=cp.label,
        horizon_seconds=cp.horizon_seconds,
        lifetime_fraction=cp.lifetime_fraction,
        candidates=["YES", "NO"],
        question_kind="binary",
        public_state=public_state,
        market_state=market_state,
        outcome=outcome,
        uncertainty_band=difficulty_from_p(p_market),
        sensitive=is_sensitive(domain, market.title, market.rules_primary),
        source_provider=market.source_provider,  # "kalshi" | "polymarket"
        source_endpoint="snapshot-builder",
        source_identifier=sid,
        retrieved_at=utcnow(),
        available_at=cp.timestamp,
    )


def _visible_evidence(
    market: Market,
    domain: str,
    ts,
    general_by_domain: dict[str, list[EvidenceItem]],
    by_market: dict[str, list[EvidenceItem]],
) -> list[EvidenceItem]:
    """Evidence available at/before ``ts`` for this market (leakage-safe)."""
    out = [e for e in general_by_domain.get(domain, []) if e.available_at <= ts]
    out += [e for e in by_market.get(market.ticker, []) if e.available_at <= ts]
    out.sort(key=lambda e: e.available_at)
    return out


def assign_splits(
    snapshots: list[Snapshot], train_frac: float = 0.70, val_frac: float = 0.15
) -> dict[str, int]:
    """Chronological split by event (never splitting an event across train/val/test)."""
    by_event: dict[str, list[Snapshot]] = defaultdict(list)
    for s in snapshots:
        by_event[s.event_ticker or s.market_ticker].append(s)

    def event_key(ev: str):
        ss = by_event[ev]
        closes = [s.public_state.close_time for s in ss if s.public_state.close_time]
        return (min(closes) if closes else max(s.timestamp for s in ss), ev)

    events = sorted(by_event, key=event_key)
    n = len(events)
    if n >= 3:
        n_test = max(1, round(n * val_frac))
        n_val = max(1, round(n * val_frac))
        n_train = max(1, n - n_val - n_test)
        # If rounding overshoots, trim from the tail categories.
        while n_train + n_val + n_test > n:
            if n_test > 1:
                n_test -= 1
            elif n_val > 1:
                n_val -= 1
            else:
                break
    else:
        n_train, n_val, n_test = n, 0, 0

    train_events = set(events[:n_train])
    val_events = set(events[n_train : n_train + n_val])
    counts = {"train": 0, "validation": 0, "test": 0}
    for ev, ss in by_event.items():
        split = "train" if ev in train_events else ("validation" if ev in val_events else "test")
        for s in ss:
            s.split = split
            counts[split] += 1
    return counts


def build_snapshots(settings: Settings) -> dict:
    markets = load_markets(settings)
    prices = load_prices(settings)
    evidence = load_evidence(settings)

    price_idx: dict[str, list[PricePoint]] = defaultdict(list)
    for p in prices:
        price_idx[p.market_ticker].append(p)
    for lst in price_idx.values():
        lst.sort(key=lambda p: p.timestamp)

    general_by_domain: dict[str, list[EvidenceItem]] = defaultdict(list)
    by_market: dict[str, list[EvidenceItem]] = defaultdict(list)
    for e in evidence:
        if e.market_ticker:
            by_market[e.market_ticker].append(e)
        else:
            dom = evidence_domain(e)
            if dom:
                general_by_domain[dom].append(e)

    # Prior-decisions enrichment: the series' own recent settled outcomes, leakage-safe.
    history = SeriesHistory(markets)

    snapshots: list[Snapshot] = []
    for m in markets:
        if m.outcome_binary is None or not (m.open_time and m.close_time):
            continue
        domain = domain_of(m)
        plist = price_idx.get(m.ticker, [])
        for cp in checkpoints(m.open_time, m.close_time):
            price = _price_at_or_before(plist, cp.timestamp)
            ev = _visible_evidence(m, domain, cp.timestamp, general_by_domain, by_market)
            hist = history.evidence_for(m, cp.timestamp, domain)
            if hist is not None:
                ev = sorted([*ev, hist], key=lambda e: e.available_at)
            snapshots.append(_snapshot(m, cp, domain, price, ev))

    split_counts = assign_splits(snapshots)
    settings.paths.snapshots.mkdir(parents=True, exist_ok=True)
    write_model_jsonl(settings.paths.snapshots / SNAPSHOTS_FILE, snapshots)
    return {"snapshots": len(snapshots), "markets": len(markets), "splits": split_counts}


def load_snapshots(settings: Settings) -> list[Snapshot]:
    return read_model_jsonl(settings.paths.snapshots / SNAPSHOTS_FILE, Snapshot)
