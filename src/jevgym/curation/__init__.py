"""Auditable difficulty curation.

Central invariant: historical odds *nominate* candidates; an independently-supported reasoning
requirement *determines* difficulty. Keep upsets, keep provenance, keep unknown cases unknown.
Mining input is outcome-free by construction; outcomes join only in evaluation/audit after
selection is frozen.
"""

from __future__ import annotations

from .config import DEFAULT_CONFIG, DifficultyConfig, config_hash, load_config

__all__ = ["DifficultyConfig", "load_config", "config_hash", "DEFAULT_CONFIG"]
