"""Proper scoring rules and calibration error for binary forecasts.

Conventions: ``p`` is P(YES), ``y`` in {0,1}. Lower is better for Brier and log loss.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

import numpy as np

from .types import Prediction

EPS = 1e-15


def brier_binary(p_yes: float, y: int) -> float:
    return (p_yes - y) ** 2


def logloss_binary(p_yes: float, y: int) -> float:
    p = min(1.0 - EPS, max(EPS, p_yes))
    return -(y * math.log(p) + (1 - y) * math.log(1.0 - p))


def ece_binary(pairs: Sequence[tuple[float, int]], n_bins: int = 10) -> float:
    """Expected Calibration Error (equal-width bins on the YES probability)."""
    if not pairs:
        return float("nan")
    bins: list[list[tuple[float, int]]] = [[] for _ in range(n_bins)]
    for p, y in pairs:
        idx = min(n_bins - 1, max(0, int(p * n_bins)))
        bins[idx].append((p, y))
    n = len(pairs)
    ece = 0.0
    for b in bins:
        if not b:
            continue
        conf = sum(p for p, _ in b) / len(b)
        acc = sum(y for _, y in b) / len(b)
        ece += (len(b) / n) * abs(acc - conf)
    return ece


def mean_brier(preds: Sequence[Prediction]) -> float:
    return float(np.mean([brier_binary(p.p_yes, p.y) for p in preds])) if preds else float("nan")


def mean_logloss(preds: Sequence[Prediction]) -> float:
    return float(np.mean([logloss_binary(p.p_yes, p.y) for p in preds])) if preds else float("nan")


def ece_of(preds: Sequence[Prediction], n_bins: int = 10) -> float:
    return ece_binary([(p.p_yes, p.y) for p in preds], n_bins=n_bins)


def summarize(preds: Sequence[Prediction]) -> dict:
    lat = [p.latency_ms for p in preds if p.latency_ms is not None]
    return {
        "n": len(preds),
        "brier": mean_brier(preds),
        "logloss": mean_logloss(preds),
        "ece": ece_of(preds),
        "latency_ms": float(np.mean(lat)) if lat else None,
    }
