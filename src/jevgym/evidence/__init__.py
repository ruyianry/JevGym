"""Evidence sources and the normalized evidence table."""

from __future__ import annotations

from ..config import Settings
from ..io import read_model_jsonl, write_model_jsonl
from ..models import EvidenceItem
from .base import (
    EVIDENCE_SOURCES,
    NORM_EVIDENCE,
    EvidenceSource,
    default_sources,
    evidence_domain,
    register_evidence_source,
)
from .macro import MacroEvidenceSource

__all__ = [
    "EvidenceSource",
    "EVIDENCE_SOURCES",
    "MacroEvidenceSource",
    "register_evidence_source",
    "default_sources",
    "evidence_domain",
    "build_all_evidence",
    "load_evidence",
]


def build_all_evidence(settings: Settings, sources: list[EvidenceSource] | None = None) -> list[EvidenceItem]:
    sources = sources if sources is not None else default_sources()
    items: list[EvidenceItem] = []
    for src in sources:
        items.extend(src.build(settings))
    settings.paths.normalized.mkdir(parents=True, exist_ok=True)
    write_model_jsonl(settings.paths.normalized / NORM_EVIDENCE, items)
    return items


def load_evidence(settings: Settings) -> list[EvidenceItem]:
    return read_model_jsonl(settings.paths.normalized / NORM_EVIDENCE, EvidenceItem)
