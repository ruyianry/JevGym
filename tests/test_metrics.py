from __future__ import annotations

from jevgym.eval.compare import delta_brier
from jevgym.eval.metrics import brier_binary, ece_binary, logloss_binary, mean_brier
from jevgym.eval.types import Prediction


def test_brier_extremes():
    assert brier_binary(1.0, 1) == 0.0
    assert brier_binary(0.0, 1) == 1.0
    assert brier_binary(0.5, 1) == 0.25


def test_logloss_perfect_and_clipped():
    assert logloss_binary(1.0, 1) < 1e-9
    # clipping keeps it finite even for a confidently-wrong prediction
    assert logloss_binary(0.0, 1) < 40


def test_ece_perfectly_calibrated():
    pairs = [(0.0, 0), (0.0, 0), (1.0, 1), (1.0, 1)]
    assert ece_binary(pairs) == 0.0


def _pred(pid, ev, p, y, provider):
    return Prediction(
        provider=provider, model_id=provider, track="market_aware", snapshot_id=pid,
        market_ticker=ev, event_ticker=ev, domain="economics", horizon="7d", p_yes=p, y=y,
    )


def test_clustered_delta_sign_and_significance():
    # model always confident-correct; reference always 0.5 -> model strictly better
    model, ref = [], []
    for i in range(40):
        ev = f"E{i % 5}"
        y = i % 2
        model.append(_pred(f"s{i}", ev, float(y), y, "model"))
        ref.append(_pred(f"s{i}", ev, 0.5, y, "ref"))
    d = delta_brier(model, ref, n_boot=500, seed=0)
    assert d is not None
    assert d["mean"] < 0  # lower brier than reference
    assert d["ci_high"] < 0 and d["significant"]
    assert d["n_events"] == 5


def test_mean_brier_empty():
    import math

    assert math.isnan(mean_brier([]))
