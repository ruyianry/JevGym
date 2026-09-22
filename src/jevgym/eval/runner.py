"""Run providers over snapshots (forecast tracks + arena) and assemble the leaderboard.

Per provider, snapshots are first filtered for **validity**: an LLM only forecasts events that
resolve *after* its knowledge cutoff (so it can't have memorized the outcome), and a global
``resolves_after`` can force a common cutoff for a fair head-to-head. Non-LLM providers (Jev,
kalshi_market, Jev-wire, mock) have no cutoff and see everything.

The runner renders the frozen question, collects ``DecisionResult``s, and never inspects which
model produced them. The **arena reward (P&L) is the headline metric.**
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import datetime, timedelta

from ..config import Settings, get_settings
from ..models import ArenaResult, Snapshot
from ..providers import build_provider, decide_question, is_baseline
from ..providers.cutoffs import DEFAULT_CUTOFF_BUFFER_DAYS
from ..snapshots.builder import load_snapshots
from ..snapshots.render import render
from .arena import run_arena
from .leaderboard import build_leaderboard, render_leaderboard_text
from .types import TRACK_BLIND, TRACK_MARKET_AWARE, Prediction


def _resolution_dt(s: Snapshot) -> datetime:
    return s.outcome.settlement_ts or s.public_state.close_time or s.timestamp


def valid_snapshots(
    provider,
    snapshots: Sequence[Snapshot],
    *,
    respect_cutoffs: bool = True,
    buffer_days: int = DEFAULT_CUTOFF_BUFFER_DAYS,
    resolves_after: datetime | None = None,
) -> list[Snapshot]:
    """Snapshots a provider may validly be scored on.

    An LLM is scored only on markets resolving after ``release_date + buffer_days`` (so it
    cannot have trained on the outcome), plus an optional global ``resolves_after`` floor.
    """
    out = list(snapshots)
    if resolves_after is not None:
        out = [s for s in out if _resolution_dt(s) > resolves_after]
    release = getattr(provider, "release_date", None) if respect_cutoffs else None
    if release is not None:
        effective = release + timedelta(days=buffer_days)
        out = [s for s in out if _resolution_dt(s) > effective]
    return out


def run_forecast(
    providers: dict[str, object],
    snapshots: Sequence[Snapshot],
    tracks: Sequence[str] = (TRACK_BLIND, TRACK_MARKET_AWARE),
    *,
    respect_cutoffs: bool = True,
    buffer_days: int = DEFAULT_CUTOFF_BUFFER_DAYS,
    resolves_after: datetime | None = None,
) -> list[Prediction]:
    preds: list[Prediction] = []
    for name, provider in providers.items():
        snaps = valid_snapshots(
            provider, snapshots, respect_cutoffs=respect_cutoffs, buffer_days=buffer_days, resolves_after=resolves_after
        )
        baseline = is_baseline(provider)
        for track in tracks:
            if baseline and track == TRACK_BLIND:
                continue  # a crowd forecast is market information; undefined "blind"
            reveal = track == TRACK_MARKET_AWARE
            for s in snaps:
                if s.outcome.y is None:
                    continue
                if baseline:
                    dr = provider.predict(s)
                else:
                    dr = decide_question(provider, render(s, reveal_market=reveal)).normalized()
                preds.append(
                    Prediction(
                        provider=name,
                        model_id=dr.model_id,
                        track=track,
                        snapshot_id=s.snapshot_id,
                        market_ticker=s.market_ticker,
                        event_ticker=s.event_ticker,
                        domain=s.domain,
                        horizon=s.forecast_horizon,
                        uncertainty_band=s.uncertainty_band,
                        split=s.split,
                        p_yes=float(dr.probabilities.get("YES", 0.5)),
                        y=int(s.outcome.y),
                        latency_ms=dr.latency_ms,
                    )
                )
    return preds


def evaluate(
    settings: Settings | None = None,
    agents: Sequence[str] = ("kalshi_market", "mock"),
    *,
    tracks: Sequence[str] = (TRACK_BLIND, TRACK_MARKET_AWARE),
    split: str | None = None,
    arena: bool = True,
    arena_mode: str = "one_shot",
    edge_threshold: float = 0.0,
    max_days: int = 7,
    max_contracts: int | None = None,
    respect_cutoffs: bool = True,
    cutoff_buffer_days: int = DEFAULT_CUTOFF_BUFFER_DAYS,
    resolves_after: datetime | None = None,
    reference: str = "jev",
    market_baseline: str = "kalshi_market",
    n_boot: int = 2000,
    seed: int = 0,
    persist: bool = True,
) -> dict:
    settings = settings or get_settings()
    snapshots = load_snapshots(settings)
    if split:
        snapshots = [s for s in snapshots if s.split == split]

    providers = {name: build_provider(name, settings) for name in agents}

    preds = run_forecast(
        providers,
        snapshots,
        tracks,
        respect_cutoffs=respect_cutoffs,
        buffer_days=cutoff_buffer_days,
        resolves_after=resolves_after,
    )

    arena_results: list[ArenaResult] = []
    if arena:
        for _name, provider in providers.items():
            if is_baseline(provider):
                continue  # baselines are references, not arena traders
            snaps = valid_snapshots(
                provider,
                snapshots,
                respect_cutoffs=respect_cutoffs,
                buffer_days=cutoff_buffer_days,
                resolves_after=resolves_after,
            )
            arena_results.extend(
                run_arena(
                    provider,
                    snaps,
                    mode=arena_mode,
                    edge_threshold=edge_threshold,
                    max_days=max_days,
                    max_contracts=max_contracts,
                )
            )

    lb = build_leaderboard(
        preds,
        arena_results,
        reference=reference,
        market_baseline=market_baseline,
        n_boot=n_boot,
        seed=seed,
    )
    text = render_leaderboard_text(lb)

    if persist:
        eval_dir = settings.paths.data_dir / "eval"
        eval_dir.mkdir(parents=True, exist_ok=True)
        from ..io import write_model_jsonl

        write_model_jsonl(eval_dir / "predictions.jsonl", preds)
        write_model_jsonl(eval_dir / "arena.jsonl", arena_results)
        (eval_dir / "leaderboard.json").write_text(json.dumps(lb, indent=2), encoding="utf-8")
        (eval_dir / "leaderboard.txt").write_text(text, encoding="utf-8")

    return {"predictions": preds, "arena": arena_results, "leaderboard": lb, "text": text}
