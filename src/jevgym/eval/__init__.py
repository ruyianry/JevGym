"""Evaluation: metrics, event-clustered comparisons, the arena, and the leaderboard."""

from __future__ import annotations

from .arena import (
    ARENA_MODES,
    ActionOneShotMode,
    EdgeOneShotMode,
    forecast_p_yes,
    one_shot_reward,
    run_arena,
)
from .compare import delta_brier, delta_logloss, paired_delta_clustered
from .leaderboard import build_leaderboard, render_leaderboard_text
from .metrics import (
    brier_binary,
    ece_binary,
    ece_of,
    logloss_binary,
    mean_brier,
    mean_logloss,
    summarize,
)
from .qualitative import qualitative_trace
from .runner import evaluate, run_forecast, valid_snapshots
from .types import TRACK_BLIND, TRACK_MARKET_AWARE, Prediction

__all__ = [
    "brier_binary",
    "logloss_binary",
    "ece_binary",
    "ece_of",
    "mean_brier",
    "mean_logloss",
    "summarize",
    "paired_delta_clustered",
    "delta_brier",
    "delta_logloss",
    "run_arena",
    "one_shot_reward",
    "forecast_p_yes",
    "EdgeOneShotMode",
    "ActionOneShotMode",
    "ARENA_MODES",
    "build_leaderboard",
    "render_leaderboard_text",
    "evaluate",
    "run_forecast",
    "valid_snapshots",
    "qualitative_trace",
    "Prediction",
    "TRACK_BLIND",
    "TRACK_MARKET_AWARE",
]
