"""Provider-agnostic decision types.

``CanonicalQuestion`` is what the renderer emits and what every provider consumes — the
frozen, semantically-identical question. ``DecisionResult`` is what every provider returns.
The evaluator only ever sees ``DecisionResult`` and cannot tell which model produced it.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field

from .base import JevBaseModel


class CanonicalQuestion(JevBaseModel):
    """The frozen forecasting/action question, identical across all models."""

    state: str
    question: str
    candidates: list[str]
    # Optional per-candidate descriptions for models that use typed criteria (Jev wire).
    candidate_descriptions: dict[str, str] = Field(default_factory=dict)
    kind: Literal["choice", "noul"] = "choice"
    # The historical "now": any tool (e.g. search) an agent uses must be bounded to this
    # timestamp so it cannot see the future. Set by the renderer from snapshot.timestamp.
    as_of: datetime | None = None


class DecisionResult(JevBaseModel):
    probabilities: dict[str, float]
    selected: str | None = None

    latency_ms: float | None = None
    raw_response: dict | None = None

    provider: str
    model_id: str

    def p(self, candidate: str) -> float:
        return float(self.probabilities.get(candidate, 0.0))

    @property
    def p_yes(self) -> float | None:
        return self.probabilities.get("YES")

    def normalized(self) -> DecisionResult:
        """Return a copy whose probabilities sum to 1 (defensive; providers should already
        return normalized distributions). Falls back to uniform if the mass is zero."""
        total = sum(max(0.0, v) for v in self.probabilities.values())
        if total <= 0:
            n = len(self.probabilities) or 1
            probs = {k: 1.0 / n for k in self.probabilities}
        else:
            probs = {k: max(0.0, v) / total for k, v in self.probabilities.items()}
        selected = max(probs, key=probs.get) if probs else None
        return self.model_copy(update={"probabilities": probs, "selected": selected})
