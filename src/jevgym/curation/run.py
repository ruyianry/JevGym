"""File-IO orchestration for the difficulty CLI. Artifacts live under ``data/curation/``."""

from __future__ import annotations

import json
from pathlib import Path

from ..config import Settings
from ..io import iter_jsonl, read_model_jsonl, write_model_jsonl
from .audit import outcome_audit, render_report, selection_funnel
from .config import load_config
from .difficulty import mine
from .fixtures import load_fixture_obs_source
from .review import apply_decisions, build_review_packets
from .schemas import DifficultyAnnotation, FeatureSnapshot, ReviewDecision

ANN = "difficulty_annotations.jsonl"
FEAT = "feature_snapshots.jsonl"
EASY = "easy_candidates.jsonl"
FUNNEL = "selection_funnel.json"
REPORT = "difficulty_report.md"
PACKETS = "review_packets.jsonl"
DECISIONS = "review_decisions.jsonl"


def _dir(settings: Settings) -> Path:
    d = settings.paths.data_dir / "curation"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _load_raw(d: Path) -> dict:
    if (d / FUNNEL).exists():
        return json.loads((d / FUNNEL).read_text()).get("raw_funnel", {})
    return {}


def _save_funnel(d: Path, fobj: dict, raw: dict, config) -> None:
    (d / FUNNEL).write_text(json.dumps({"funnel": fobj, "raw_funnel": raw}, indent=2, default=str), encoding="utf-8")
    anns = read_model_jsonl(d / ANN, DifficultyAnnotation)
    (d / REPORT).write_text(render_report(fobj, anns, config), encoding="utf-8")


def _obs_source_for(settings: Settings, prior: str = "auto"):
    """Choose the prior's observation source. ``fixture`` = seeded offline obs; ``open-meteo`` =
    real climatology (free archive, no key); ``auto`` prefers seeded fixtures, else Open-Meteo."""
    from ..data.kalshi import rawpaths
    from ..data.kalshi.rawcache import RawCache

    if prior in ("open-meteo", "openmeteo", "open_meteo"):
        from .obs_sources import open_meteo_source

        return open_meteo_source(settings)
    if prior == "fixture":
        return load_fixture_obs_source(settings)
    rc = RawCache(settings.paths.raw)
    has_fixture = any(True for _ in rc.iter_blobs(rawpaths.WEATHER_OBS_DIR))
    if has_fixture:
        return load_fixture_obs_source(settings)
    from .obs_sources import open_meteo_source

    return open_meteo_source(settings)


def run_mine(settings: Settings, config_path: str | None = None, obs_source=None, prior: str = "auto") -> dict:
    config = load_config(config_path)
    obs = obs_source or _obs_source_for(settings, prior)
    anns, feats, raw = mine(settings, config, obs)
    d = _dir(settings)
    write_model_jsonl(d / ANN, anns)
    write_model_jsonl(d / FEAT, feats)
    write_model_jsonl(d / EASY, [a for a in anns if a.selection_status == "candidate" and a.selected])
    fobj = selection_funnel(raw, anns)
    _save_funnel(d, fobj, raw, config)
    return fobj


def run_export_review(settings: Settings, output: str | None = None, config_path: str | None = None) -> dict:
    config = load_config(config_path)
    d = _dir(settings)
    anns = read_model_jsonl(d / ANN, DifficultyAnnotation)
    feats = read_model_jsonl(d / FEAT, FeatureSnapshot)
    packets = build_review_packets(anns, feats, rubric_version=config.rubric_version)
    out = Path(output) if output else d / PACKETS
    write_model_jsonl(out, packets)
    return {"packets": len(packets), "output": str(out)}


def run_apply_review(settings: Settings, input_path: str | None = None, config_path: str | None = None) -> dict:
    config = load_config(config_path)
    d = _dir(settings)
    anns = read_model_jsonl(d / ANN, DifficultyAnnotation)
    inp = Path(input_path) if input_path else d / DECISIONS
    if not inp.exists():
        return {"applied": 0, "error": f"no decisions file at {inp}"}
    decisions = [ReviewDecision.model_validate(r) for r in iter_jsonl(inp)]
    applied = apply_decisions(anns, decisions)
    write_model_jsonl(d / ANN, anns)
    fobj = selection_funnel(_load_raw(d), anns)
    _save_funnel(d, fobj, _load_raw(d), config)
    return {"applied": applied, "reviewed_easy": fobj["reviewed_easy"]}


def run_report(settings: Settings, config_path: str | None = None) -> dict:
    config = load_config(config_path)
    d = _dir(settings)
    anns = read_model_jsonl(d / ANN, DifficultyAnnotation)
    fobj = selection_funnel(_load_raw(d), anns)
    _save_funnel(d, fobj, _load_raw(d), config)
    return fobj


def run_audit(settings: Settings, selected_only: bool = True) -> dict:
    """Post-selection: join realized outcomes to curated candidates; market vs independent prior."""
    from ..data.parse import load_markets

    d = _dir(settings)
    anns = read_model_jsonl(d / ANN, DifficultyAnnotation)
    feats = read_model_jsonl(d / FEAT, FeatureSnapshot)
    result = {m.ticker: m.outcome_binary for m in load_markets(settings) if m.outcome_binary is not None}
    out = outcome_audit(anns, feats, result, selected_only=selected_only)
    (d / "outcome_audit.json").write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    return out


def run_validate(settings: Settings) -> dict:
    d = _dir(settings)
    anns = read_model_jsonl(d / ANN, DifficultyAnnotation)
    violations: list[str] = []

    # 1) Outcome-free invariants (structural). favored_outcome(s) are pre-event *direction*
    # fields (prior/market favored side), not the eventual result — allowed.
    forbidden = {"outcome", "y", "result", "resolved", "label", "final_price", "settlement_value", "settlement_ts"}
    for cls in (FeatureSnapshot,):
        bad = [f for f in cls.model_fields if f in forbidden or "settlement" in f]
        if bad:
            violations.append(f"{cls.__name__} exposes outcome-like fields: {bad}")

    # 2) Annotation invariants.
    for a in anns:
        if a.difficulty not in ("easy", "medium", "hard", "unassigned"):
            violations.append(f"{a.snapshot_id}: bad difficulty {a.difficulty}")
        if a.selected and a.selection_status not in ("candidate", "approved"):
            violations.append(f"{a.snapshot_id}: selected but status {a.selection_status}")
        if "missing_prior" in a.reason_codes and a.difficulty == "hard":
            violations.append(f"{a.snapshot_id}: missing_prior labeled hard")

    return {"ok": not violations, "annotations": len(anns), "violations": violations}
