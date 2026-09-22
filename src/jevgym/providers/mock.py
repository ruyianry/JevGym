"""Deterministic offline provider.

Produces a stable pseudo-distribution from a hash of (state, candidate) — it never sees the
outcome, so it is a genuine (unskilled) challenger. Its only jobs are to make the pipeline
runnable with no network/GPU and to give tests a real ``SystemOneProvider``.
"""

from __future__ import annotations

import math

from ..models import DecisionResult
from ..util import sha256_str


class MockProvider:
    def __init__(self, name: str = "mock", model_id: str = "mock-0.1", temperature: float = 2.0):
        self.name = name
        self.model_id = model_id
        self.temperature = temperature

    def _score(self, state: str, candidate: str) -> float:
        h = sha256_str(f"{state}|{candidate}")
        return (int(h[:8], 16) % 1000) / 1000.0

    def decide(self, state: str, question: str, candidates: list[str]) -> DecisionResult:
        scores = [self._score(state, c) for c in candidates]
        m = max(scores)
        exps = [math.exp((s - m) * self.temperature) for s in scores]
        z = sum(exps) or 1.0
        probs = {c: e / z for c, e in zip(candidates, exps, strict=True)}
        return DecisionResult(
            probabilities=probs,
            selected=max(probs, key=probs.get),
            latency_ms=0.01,
            provider=self.name,
            model_id=self.model_id,
        )
