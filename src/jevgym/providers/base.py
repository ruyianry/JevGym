"""Provider protocol + the small seam that keeps the evaluator model-agnostic.

* ``SystemOneProvider`` is the exact contract from the spec: text state + question +
  candidates in, a ``DecisionResult`` (calibrated distribution) out.
* ``Baseline`` is a *separate* interface for non-model references (e.g. the Kalshi crowd
  forecast) that read the snapshot directly rather than rendered text. Keeping it distinct is
  what stops us from ever treating the market as if it were a decision model.
* ``decide_question`` lets richer adapters use per-candidate descriptions without widening
  the minimal Protocol.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..models import CanonicalQuestion, DecisionResult


@runtime_checkable
class SystemOneProvider(Protocol):
    name: str
    model_id: str

    def decide(self, state: str, question: str, candidates: list[str]) -> DecisionResult: ...


@runtime_checkable
class Baseline(Protocol):
    name: str
    model_id: str

    def predict(self, snapshot) -> DecisionResult: ...


def is_baseline(provider: object) -> bool:
    return hasattr(provider, "predict") and not hasattr(provider, "decide")


def decide_question(provider: SystemOneProvider, cq: CanonicalQuestion) -> DecisionResult:
    """Prefer a provider's richer ``decide_question`` (with candidate descriptions); fall
    back to the minimal ``decide`` signature."""
    fn = getattr(provider, "decide_question", None)
    if callable(fn):
        return fn(cq)
    return provider.decide(cq.state, cq.question, cq.candidates)
