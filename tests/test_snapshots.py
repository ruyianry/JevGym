from __future__ import annotations

from datetime import datetime, timedelta, timezone

from jevgym.snapshots.builder import load_snapshots
from jevgym.snapshots.horizons import checkpoints


def test_checkpoints_within_lifetime_and_labeled():
    open_dt = datetime(2026, 1, 1, tzinfo=timezone.utc)
    close_dt = open_dt + timedelta(days=45)
    cps = checkpoints(open_dt, close_dt)
    labels = {c.label for c in cps}
    # 30d fits in a 45d market; quantiles always present
    assert "30d" in labels and "1h" in labels
    assert {"q10", "q50", "q90"} <= labels
    assert all(open_dt <= c.timestamp <= close_dt for c in cps)
    # sorted ascending
    assert [c.timestamp for c in cps] == sorted(c.timestamp for c in cps)


def test_short_market_drops_far_horizons():
    open_dt = datetime(2026, 1, 1, tzinfo=timezone.utc)
    close_dt = open_dt + timedelta(hours=5)
    labels = {c.label for c in checkpoints(open_dt, close_dt)}
    assert "30d" not in labels and "7d" not in labels
    assert "3h" in labels  # 3h fits within a 5h market


def test_snapshots_have_separated_blocks_and_evidence(built):
    snaps = load_snapshots(built)
    assert len(snaps) == 56
    s = snaps[0]
    assert s.public_state.market_title
    assert s.outcome.y in (0, 1)
    # evidence attached to a snapshot never postdates it
    assert all(e.available_at <= s.timestamp for e in s.public_state.evidence)


def test_evidence_grows_over_time(built):
    snaps = [s for s in load_snapshots(built) if s.market_ticker == "KXFED-26JAN-CUT"]
    by_time = sorted(snaps, key=lambda s: s.timestamp)
    counts = [len(s.public_state.evidence) for s in by_time]
    assert counts == sorted(counts)  # monotonic non-decreasing as time advances
    assert counts[-1] >= counts[0]
