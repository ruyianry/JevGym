"""Difficulty-curation configuration: load, freeze, hash.

The config is a plain dict (loaded from YAML) wrapped in a typed accessor. Its content hash is
stamped onto every annotation so any result is reproducible against the exact frozen rules.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..util import sha256_str, stable_json

DEFAULT_CONFIG: dict = {
    "version": "difficulty_weather_v1",
    "domain": "weather",
    "horizons": {"primary_offset_hours": 24, "secondary_offset_hours": 6},
    "market_quality": {
        "min_market_confidence": 0.90,
        "max_yes_spread": 0.05,
        "max_quote_age_seconds": 3600,
        "require_verified_quote_freshness": True,
    },
    "prior": {"years_back": 20, "seasonal_window_days": 15, "min_years": 15, "smoothing_alpha": 1},
    "candidate": {"min_market_confidence": 0.90, "min_prior_confidence": 0.90},
    "selection": {"one_per_event_per_horizon": True, "seed": "jevgym-difficulty-weather-v1"},
    "rubric_version": "weather-easy-rubric-v1",
    "annotation_version": 1,
    "snapshot_policy_version": "weather-strict-v1",
}


def config_hash(cfg: dict) -> str:
    """Deterministic content hash of the frozen config (order-independent)."""
    return sha256_str(stable_json(cfg))[:16]


def load_config(path: str | Path | None = None) -> DifficultyConfig:
    cfg = dict(DEFAULT_CONFIG)
    if path is not None and Path(path).exists():
        import yaml

        loaded = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
        cfg = _deep_merge(cfg, loaded)
    return DifficultyConfig(cfg)


def _deep_merge(base: dict, over: dict) -> dict:
    out = dict(base)
    for k, v in over.items():
        out[k] = _deep_merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


@dataclass(frozen=True)
class DifficultyConfig:
    raw: dict

    @property
    def hash(self) -> str:
        return config_hash(self.raw)

    @property
    def version(self) -> str:
        return self.raw["version"]

    @property
    def rubric_version(self) -> str:
        return self.raw.get("rubric_version", "unversioned")

    @property
    def annotation_version(self) -> int:
        return int(self.raw.get("annotation_version", 1))

    @property
    def snapshot_policy_version(self) -> str:
        return self.raw.get("snapshot_policy_version", "unversioned")

    def horizons(self) -> list[tuple[str, int]]:
        h = self.raw["horizons"]
        out = [("primary_24h", int(h["primary_offset_hours"]))]
        if "secondary_offset_hours" in h:
            out.append(("secondary_6h", int(h["secondary_offset_hours"])))
        return out

    def mq(self, key: str):
        return self.raw["market_quality"][key]

    def prior_cfg(self, key: str):
        return self.raw["prior"][key]

    def cand(self, key: str):
        return self.raw["candidate"][key]

    def seed(self) -> str:
        return self.raw["selection"]["seed"]

    def one_per_event(self) -> bool:
        return bool(self.raw["selection"]["one_per_event_per_horizon"])
