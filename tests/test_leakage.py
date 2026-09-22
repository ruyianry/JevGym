from __future__ import annotations

from datetime import timedelta

from jevgym.snapshots.builder import load_snapshots
from jevgym.validate.leakage import validate_all, validate_snapshots


def test_clean_dataset_validates(built):
    report = validate_all(built)
    assert report["ok"], report["violations"]
    assert report["counts"]["temporal_leakage"] == 0
    assert report["counts"]["split_integrity"] == 0


def test_injected_future_evidence_is_caught(built):
    snaps = load_snapshots(built)
    victim = next(s for s in snaps if s.public_state.evidence)
    # move one evidence item to AFTER the snapshot timestamp
    victim.public_state.evidence[0].available_at = victim.timestamp + timedelta(days=1)
    report = validate_snapshots(snaps)
    assert not report["ok"]
    assert report["counts"]["temporal_leakage"] >= 1


def test_event_split_across_splits_is_caught(built):
    snaps = load_snapshots(built)
    # force one snapshot of an otherwise-train event into 'test'
    ev = snaps[0].event_ticker
    same = [s for s in snaps if s.event_ticker == ev]
    for s in same:
        s.split = "train"
    same[0].split = "test"
    report = validate_snapshots(snaps)
    assert report["counts"]["split_integrity"] >= 1
