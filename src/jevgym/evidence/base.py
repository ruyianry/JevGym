"""Evidence abstraction + registry.

An ``EvidenceSource`` turns some external/structured source into timestamped
``EvidenceItem`` records. Adding a new domain source is one class + one ``@register`` call
(extension-friendly by design). ``available_at`` on every item is the public-release time,
enforced later against snapshot timestamps by the leakage checker.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..config import Settings
from ..models import EvidenceItem

NORM_EVIDENCE = "evidence.jsonl"

# Which snapshot domain a given evidence_type informs (general, non-market-specific evidence).
EVIDENCE_TYPE_DOMAIN = {
    "macro_indicator": "economics",
    "weather_forecast": "weather",
    "weather_observation": "weather",
}


def evidence_domain(item: EvidenceItem) -> str | None:
    """Domain an item applies to: explicit payload domain wins, else type mapping."""
    dom = item.payload.get("domain") if isinstance(item.payload, dict) else None
    return dom or EVIDENCE_TYPE_DOMAIN.get(item.evidence_type)


@runtime_checkable
class EvidenceSource(Protocol):
    name: str
    domain: str

    def build(self, settings: Settings) -> list[EvidenceItem]:
        """Produce evidence items from the raw cache (or a live source)."""
        ...


EVIDENCE_SOURCES: dict[str, type] = {}


def register_evidence_source(cls: type) -> type:
    EVIDENCE_SOURCES[cls.name] = cls
    return cls


def default_sources() -> list[EvidenceSource]:
    return [cls() for cls in EVIDENCE_SOURCES.values()]
