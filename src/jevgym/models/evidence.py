"""Domain evidence, timestamped by when it became public.

A single general abstraction covers all domains; ``payload`` holds the structured,
domain-specific content (e.g. a macro figure). ``available_at`` (from ProvenanceMixin) is
the public-release time and is enforced against snapshot timestamps by the leakage checker.
We never fabricate evidence for domains we lack real sources for.
"""

from __future__ import annotations

from .base import ProvenanceMixin


class EvidenceItem(ProvenanceMixin):
    evidence_id: str
    evidence_type: str  # e.g. "macro_indicator", "weather_forecast"

    market_ticker: str | None = None
    event_ticker: str | None = None

    payload: dict  # structured, domain-specific content
