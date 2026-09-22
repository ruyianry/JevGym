"""JevGym: a timestamped Kalshi benchmark + arena for Jev-style System One models.

Public surface is intentionally small; import submodules directly for internals.
"""

from __future__ import annotations

from .version import DATASET_VERSION, PARSER_VERSION, __version__

__all__ = ["__version__", "DATASET_VERSION", "PARSER_VERSION"]
