"""Assemble the leaderboard: per-provider/track metrics, Δ vs Jev, Δ vs Kalshi (with
event-clustered bootstrap CIs), arena reward, and domain/horizon breakdowns.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence

import numpy as np

from ..models import ArenaResult
from .compare import delta_brier, delta_logloss
from .metrics import mean_brier, summarize
from .types import Prediction


def _group_by_provider_track(preds: Sequence[Prediction]) -> dict:
    g: dict[tuple[str, str], list[Prediction]] = defaultdict(list)
    for p in preds:
        g[(p.provider, p.track)].append(p)
    return g


def _arena_agg(arena_results: Sequence[ArenaResult], provider: str) -> dict | None:
    rs = [a for a in arena_results if a.provider == provider]
    if not rs:
        return None
    rewards = [a.reward for a in rs]
    contracts = float(np.sum([a.contracts for a in rs]))
    return {
        "n_markets": len(rs),
        "mean_reward": float(np.mean(rewards)),
        "total_reward": float(np.sum(rewards)),
        "contracts": contracts,
        # Position-size-normalized headline: total P&L / total contracts. For one-shot this
        # equals mean_reward; for multi-day (several fills/market) it is the honest per-contract %.
        "return_per_contract": float(np.sum(rewards) / contracts) if contracts else 0.0,
        "entered_rate": float(np.mean([1.0 if a.entered else 0.0 for a in rs])),
    }


def _breakdown(preds: Sequence[Prediction], field: str) -> dict:
    g: dict[tuple[str, str, str], list[Prediction]] = defaultdict(list)
    for p in preds:
        g[(p.provider, p.track, getattr(p, field))].append(p)
    out: dict[str, dict] = defaultdict(dict)
    for (prov, track, val), ps in g.items():
        out[f"{prov}|{track}"][val] = mean_brier(ps)
    return {k: dict(v) for k, v in out.items()}


def build_leaderboard(
    predictions: Sequence[Prediction],
    arena_results: Sequence[ArenaResult] | None = None,
    *,
    reference: str = "jev",
    market_baseline: str = "kalshi_market",
    n_boot: int = 2000,
    seed: int = 0,
) -> dict:
    groups = _group_by_provider_track(predictions)
    providers = sorted({p.provider for p in predictions})
    tracks = sorted({p.track for p in predictions})
    ref_by_track = {t: groups.get((reference, t), []) for t in tracks}
    mkt_by_track = {t: groups.get((market_baseline, t), []) for t in tracks}

    out: dict = {
        "reference": reference,
        "market_baseline": market_baseline,
        "providers": {},
        "breakdowns": {},
    }

    for prov in providers:
        entry: dict = {"tracks": {}}
        for t in tracks:
            preds = groups.get((prov, t), [])
            if not preds:
                continue
            s = summarize(preds)
            use_jev = prov != reference and ref_by_track[t]
            use_mkt = prov != market_baseline and mkt_by_track[t]
            entry["tracks"][t] = {
                **s,
                "delta_brier_vs_jev": delta_brier(preds, ref_by_track[t], n_boot=n_boot, seed=seed) if use_jev else None,
                "delta_logloss_vs_jev": delta_logloss(preds, ref_by_track[t], n_boot=n_boot, seed=seed) if use_jev else None,
                "delta_brier_vs_kalshi": delta_brier(preds, mkt_by_track[t], n_boot=n_boot, seed=seed) if use_mkt else None,
                "delta_logloss_vs_kalshi": delta_logloss(preds, mkt_by_track[t], n_boot=n_boot, seed=seed) if use_mkt else None,
            }
        entry["arena"] = _arena_agg(arena_results, prov) if arena_results else None
        out["providers"][prov] = entry

    out["breakdowns"]["by_domain"] = _breakdown(predictions, "domain")
    out["breakdowns"]["by_horizon"] = _breakdown(predictions, "horizon")
    out["breakdowns"]["by_uncertainty"] = _breakdown(predictions, "uncertainty_band")

    adb: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))
    for a in arena_results or []:
        adb[a.provider][a.uncertainty_band or "unknown"].append(a.reward)
    out["arena_by_uncertainty"] = {
        prov: {d: {"n": len(v), "mean_reward": float(np.mean(v))} for d, v in dd.items()}
        for prov, dd in adb.items()
    }
    return out


# --- text rendering --------------------------------------------------------
def _fmt(x, nd=4):
    return "n/a" if x is None or (isinstance(x, float) and np.isnan(x)) else f"{x:.{nd}f}"


def _fmt_delta(d):
    if not d:
        return "—"
    star = "*" if d.get("significant") else " "
    return f"{d['mean']:+.4f}{star}[{d['ci_low']:+.3f},{d['ci_high']:+.3f}]"


def render_leaderboard_text(lb: dict) -> str:
    ref = lb["reference"]
    mkt = lb["market_baseline"]
    lines: list[str] = []

    # 1) HEADLINE: arena reward (P&L).
    arena_rows = [(p, e["arena"]) for p, e in lb["providers"].items() if e.get("arena")]
    lines.append("== ARENA — reward (P&L in $ per market), the headline metric ==")
    if arena_rows:
        ah = f"{'Provider':<16}{'Markets':>8}  {'MeanReward↑':>12}  {'Ret/contract↑':>14}  {'Contracts':>10}  {'EnteredRate':>12}"
        lines.append(ah)
        lines.append("-" * len(ah))
        for prov, a in sorted(arena_rows, key=lambda x: -x[1]["mean_reward"]):
            lines.append(
                f"{prov:<16}{a['n_markets']:>8}  {a['mean_reward']:>12.4f}  "
                f"{a.get('return_per_contract', 0.0):>14.4f}  {a.get('contracts', 0.0):>10.1f}  "
                f"{a['entered_rate']:>12.2f}"
            )
    else:
        lines.append("(no arena results — pass agents that trade, e.g. mock/llm/jev)")

    # 1b) Reward grouped by market-implied uncertainty (a confidence axis, not reasoning difficulty).
    adb = lb.get("arena_by_uncertainty") or {}
    if adb:
        order = ["easy", "medium", "hard", "unknown"]
        present = [d for d in order if any(d in v for v in adb.values())]
        lines.append("")
        lines.append("== Reward by market uncertainty — mean P&L $ (n) ==")
        hdr = f"{'Provider':<16}" + "".join(f"{d:>14}" for d in present)
        lines.append(hdr)
        lines.append("-" * len(hdr))
        for prov, v in sorted(adb.items()):
            row = f"{prov:<16}"
            for d in present:
                cell = v.get(d)
                txt = f"{cell['mean_reward']:+.3f} ({cell['n']})" if cell else "—"
                row += f"{txt:>14}"
            lines.append(row)

    # 2) Secondary: calibration.
    lines.append("")
    lines.append("== Calibration (secondary) ==")
    header = f"{'Provider':<16}{'Track':<14}{'N':>5}  {'Brier↓':>8}  {'LogLoss↓':>9}  {'ECE↓':>7}  {'Latency':>8}  {'ΔBrier vs '+ref:>26}  {'ΔBrier vs '+mkt:>26}"
    lines.append(header)
    lines.append("-" * len(header))
    for prov, entry in sorted(lb["providers"].items()):
        for track, m in sorted(entry["tracks"].items()):
            lat = _fmt(m.get("latency_ms"), 2)
            lines.append(
                f"{prov:<16}{track:<14}{m['n']:>5}  {_fmt(m['brier']):>8}  {_fmt(m['logloss']):>9}  "
                f"{_fmt(m['ece'],3):>7}  {lat:>8}  {_fmt_delta(m['delta_brier_vs_jev']):>26}  "
                f"{_fmt_delta(m['delta_brier_vs_kalshi']):>26}"
            )
    lines.append("")
    lines.append("(N differs across models when the knowledge-cutoff filter excludes pre-cutoff events.)")
    lines.append("(* = 95% bootstrap CI, clustered by event, excludes 0. Negative Δ = better than reference.)")
    return "\n".join(lines)
