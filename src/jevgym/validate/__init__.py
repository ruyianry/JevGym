"""Leakage + split-integrity validation."""

from __future__ import annotations

from .leakage import (
    Violation,
    check_leakage,
    check_split_integrity,
    validate_all,
    validate_snapshots,
)

__all__ = [
    "Violation",
    "check_leakage",
    "check_split_integrity",
    "validate_snapshots",
    "validate_all",
]
