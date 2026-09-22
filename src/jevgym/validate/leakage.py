"""Leakage and split-integrity checks.

The cardinal invariant for a historical-replay benchmark: nothing a model can see may
postdate the checkpoint. We enforce ``evidence.available_at <= snapshot.timestamp`` for
every model-visible evidence item, and we enforce that no event is split across
train/validation/test. Sanity checks catch malformed labels/probabilities.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from ..config import Settings
from ..models import Snapshot


@dataclass
class Violation:
    kind: str
    detail: str
    snapshot_id: str | None = None

    def __str__(self) -> str:  # pragma: no cover
        loc = f" [{self.snapshot_id}]" if self.snapshot_id else ""
        return f"{self.kind}{loc}: {self.detail}"


def check_leakage(snapshots: list[Snapshot]) -> list[Violation]:
    out: list[Violation] = []
    for s in snapshots:
        for e in s.public_state.evidence:
            if e.available_at > s.timestamp:
                out.append(
                    Violation(
                        "temporal_leakage",
                        f"evidence {e.evidence_id} available_at {e.available_at.isoformat()} "
                        f"> snapshot timestamp {s.timestamp.isoformat()}",
                        s.snapshot_id,
                    )
                )
        if s.public_state.close_time and s.timestamp > s.public_state.close_time:
            out.append(
                Violation(
                    "checkpoint_after_close",
                    f"timestamp {s.timestamp.isoformat()} > close {s.public_state.close_time.isoformat()}",
                    s.snapshot_id,
                )
            )
    return out


def check_split_integrity(snapshots: list[Snapshot]) -> list[Violation]:
    by_event: dict[str, set[str | None]] = defaultdict(set)
    for s in snapshots:
        by_event[s.event_ticker or s.market_ticker].add(s.split)
    out: list[Violation] = []
    for ev, splits in by_event.items():
        real = {sp for sp in splits if sp}
        if len(real) > 1:
            out.append(
                Violation("event_split_across_splits", f"event {ev} spans splits {sorted(real)}")
            )
    return out


def check_sanity(snapshots: list[Snapshot]) -> list[Violation]:
    out: list[Violation] = []
    for s in snapshots:
        if s.outcome.y not in (0, 1):
            out.append(Violation("missing_label", f"outcome.y={s.outcome.y}", s.snapshot_id))
        if not s.candidates:
            out.append(Violation("no_candidates", "empty candidate list", s.snapshot_id))
        p = s.market_state.p_market
        if p is not None and not (0.0 <= p <= 1.0):
            out.append(Violation("p_market_out_of_range", f"p_market={p}", s.snapshot_id))
    return out


def validate_snapshots(snapshots: list[Snapshot]) -> dict:
    leakage = check_leakage(snapshots)
    splits = check_split_integrity(snapshots)
    sanity = check_sanity(snapshots)
    violations = leakage + splits + sanity
    return {
        "ok": not violations,
        "snapshot_count": len(snapshots),
        "counts": {
            "temporal_leakage": len(leakage),
            "split_integrity": len(splits),
            "sanity": len(sanity),
        },
        "violations": [str(v) for v in violations],
    }


def validate_all(settings: Settings) -> dict:
    from ..snapshots.builder import load_snapshots

    return validate_snapshots(load_snapshots(settings))
