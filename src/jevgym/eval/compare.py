"""Paired, event-clustered bootstrap comparisons.

Snapshots from the same market/event are correlated, so we do NOT treat each timestamp as an
independent observation. Confidence intervals for Δ (challenger − reference) come from a
paired bootstrap that resamples whole events (clusters) with replacement.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Sequence

import numpy as np

from .metrics import brier_binary, logloss_binary
from .types import Prediction

MetricFn = Callable[[float, int], float]


def paired_delta_clustered(
    model_preds: Sequence[Prediction],
    ref_preds: Sequence[Prediction],
    metric: MetricFn,
    *,
    n_boot: int = 2000,
    seed: int = 0,
    ci: float = 0.95,
) -> dict | None:
    """Mean and bootstrap CI of per-snapshot (model − reference) loss, clustered by event.

    Negative mean => the challenger has lower loss than the reference. Returns ``None`` if the
    two sets share no snapshots.
    """
    m_loss = {p.snapshot_id: metric(p.p_yes, p.y) for p in model_preds}
    r_loss = {p.snapshot_id: metric(p.p_yes, p.y) for p in ref_preds}
    event_of = {p.snapshot_id: (p.event_ticker or p.market_ticker) for p in model_preds}

    common = [sid for sid in m_loss if sid in r_loss]
    if not common:
        return None

    clusters: dict[str, list[float]] = defaultdict(list)
    for sid in common:
        clusters[event_of[sid]].append(m_loss[sid] - r_loss[sid])

    cluster_vals = [np.asarray(v, dtype=float) for v in clusters.values()]
    all_diffs = np.concatenate(cluster_vals)
    mean = float(all_diffs.mean())

    rng = np.random.default_rng(seed)
    k = len(cluster_vals)
    boot = np.empty(n_boot, dtype=float)
    for b in range(n_boot):
        idx = rng.integers(0, k, k)
        boot[b] = np.concatenate([cluster_vals[i] for i in idx]).mean()

    lo = float(np.quantile(boot, (1 - ci) / 2))
    hi = float(np.quantile(boot, 1 - (1 - ci) / 2))
    return {
        "mean": mean,
        "ci_low": lo,
        "ci_high": hi,
        "n_snapshots": len(common),
        "n_events": k,
        "significant": (lo < 0 and hi < 0) or (lo > 0 and hi > 0),
    }


def delta_brier(model_preds, ref_preds, **kw) -> dict | None:
    return paired_delta_clustered(model_preds, ref_preds, brier_binary, **kw)


def delta_logloss(model_preds, ref_preds, **kw) -> dict | None:
    return paired_delta_clustered(model_preds, ref_preds, logloss_binary, **kw)
