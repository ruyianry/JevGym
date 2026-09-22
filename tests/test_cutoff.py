from __future__ import annotations

from datetime import datetime, timezone

from jevgym.eval.runner import valid_snapshots
from jevgym.models import MarketState, Outcome, PublicState, Snapshot
from jevgym.providers.cutoffs import release_date_for
from jevgym.util import utcnow

UTC = timezone.utc


def _snap(sid, resolve_dt):
    return Snapshot(
        snapshot_id=sid,
        market_ticker=sid,
        event_ticker=sid,
        domain="d",
        timestamp=resolve_dt,
        forecast_horizon="x",
        public_state=PublicState(market_title="m", close_time=resolve_dt),
        market_state=MarketState(p_market=0.5),
        outcome=Outcome(resolved=True, y=1, settlement_ts=resolve_dt),
        source_provider="k",
        source_endpoint="b",
        source_identifier=sid,
        retrieved_at=utcnow(),
        available_at=resolve_dt,
    )


class _FakeLLM:
    name = "fake"
    model_id = "fake"

    def __init__(self, release_date):
        self.release_date = release_date

    def decide(self, *a, **k):  # pragma: no cover
        raise NotImplementedError


class _NoRelease:
    name = "n"
    model_id = "n"

    def decide(self, *a, **k):  # pragma: no cover
        raise NotImplementedError


def test_release_date_registry():
    assert release_date_for("qwen2.5-72b-instruct").year == 2024  # longest match beats "qwen2"
    assert release_date_for("claude-opus-4-8").year == 2026
    assert release_date_for("gpt-4o").year == 2024
    assert release_date_for("totally-unknown-model") is None


def test_release_plus_buffer_excludes_pre_release_events():
    snaps = [_snap("pre", datetime(2024, 1, 1, tzinfo=UTC)), _snap("post", datetime(2026, 6, 1, tzinfo=UTC))]
    prov = _FakeLLM(datetime(2025, 1, 1, tzinfo=UTC))
    kept = [s.snapshot_id for s in valid_snapshots(prov, snaps)]  # default 90d buffer
    assert kept == ["post"]


def test_buffer_window_is_applied():
    prov = _FakeLLM(datetime(2026, 1, 1, tzinfo=UTC))  # +90d -> effective ~2026-04-01
    snaps = [_snap("within_buffer", datetime(2026, 2, 15, tzinfo=UTC)), _snap("after", datetime(2026, 6, 1, tzinfo=UTC))]
    kept = [s.snapshot_id for s in valid_snapshots(prov, snaps, buffer_days=90)]
    assert kept == ["after"]
    # A zero buffer keeps the event just after release.
    kept0 = [s.snapshot_id for s in valid_snapshots(prov, snaps, buffer_days=0)]
    assert set(kept0) == {"within_buffer", "after"}


def test_no_release_date_keeps_all():
    snaps = [_snap("a", datetime(2024, 1, 1, tzinfo=UTC))]
    assert len(valid_snapshots(_NoRelease(), snaps)) == 1


def test_global_resolves_after():
    snaps = [_snap("old", datetime(2025, 1, 1, tzinfo=UTC)), _snap("new", datetime(2026, 3, 1, tzinfo=UTC))]
    kept = [s.snapshot_id for s in valid_snapshots(_NoRelease(), snaps, resolves_after=datetime(2026, 1, 1, tzinfo=UTC))]
    assert kept == ["new"]
