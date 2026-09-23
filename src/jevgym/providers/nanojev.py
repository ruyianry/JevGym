"""Adapter for NanoJev — an open Qwen3-0.6B decision model with a TypeSafe-compatible endpoint.

NanoJev is a third-party open System-One model. Serve its endpoint

    POST {base}/api/evaluate            (default port 8765)

and point ``NANOJEV_BASE`` at it. Its head is ``boolean`` (not ``noul``) and the gateway reads
``answer.probability``. We send a Jev-shaped questions payload and read back per-candidate
probabilities, with a boolean-probability fallback. The evaluator then treats NanoJev like any
other System-One provider (it cannot tell them apart).

Repo: https://github.com/TianyuCodings/NanoJev  (verified from README + docs, not executed here
— running it needs a GPU + a served checkpoint).
"""

from __future__ import annotations

import time

import httpx

from ..models import CanonicalQuestion, DecisionResult
from .prompt import parse_jev_answer


def _parse_nanojev(data: dict, question_id: str, candidates: list[str]) -> dict[str, float]:
    """NanoJev's boolean head returns ``answer.probability`` = P(YES) for a binary question.
    Fall back to the shared Jev-wire parser for choice-style distributions."""
    if isinstance(data, dict) and set(candidates) == {"YES", "NO"}:
        ans = (data.get("answers") or {}).get(question_id) or data.get("answer") or {}
        if isinstance(ans, dict) and ans.get("probability") is not None:
            p = min(1.0, max(0.0, float(ans["probability"])))
            return {"YES": p, "NO": 1.0 - p}
    return parse_jev_answer(data, question_id, candidates)


class NanoJevProvider:
    def __init__(
        self,
        *,
        name: str = "nanojev",
        model_id: str = "nanojev-0.6b",
        base_url: str = "http://127.0.0.1:8765",
        question_id: str = "q",
        timeout: float = 60.0,
        client: httpx.Client | None = None,
    ):
        self.name = name
        self.model_id = model_id
        self.base_url = base_url.rstrip("/")
        self.question_id = question_id
        self._timeout = timeout
        self._client = client
        self._owns_client = client is None

    def _get_client(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(timeout=self._timeout)
        return self._client

    def close(self) -> None:
        if self._owns_client and self._client is not None:
            self._client.close()
            self._client = None

    def decide(self, state: str, question: str, candidates: list[str]) -> DecisionResult:
        cq = CanonicalQuestion(
            state=state,
            question=question,
            candidates=candidates,
            candidate_descriptions={c: c for c in candidates},
        )
        return self.decide_question(cq)

    def decide_question(self, cq: CanonicalQuestion) -> DecisionResult:
        criteria = {c: cq.candidate_descriptions.get(c, c) for c in cq.candidates}
        qtype = "boolean" if set(cq.candidates) == {"YES", "NO"} else "choice"
        payload = {
            "model": self.model_id,
            "state": cq.state,
            "questions": {self.question_id: {"type": qtype, "instructions": cq.question, "criteria": criteria}},
        }
        t0 = time.perf_counter()
        resp = self._get_client().post(f"{self.base_url}/api/evaluate", json=payload)
        resp.raise_for_status()
        data = resp.json()
        latency_ms = (time.perf_counter() - t0) * 1000.0

        probs = _parse_nanojev(data, self.question_id, cq.candidates)
        selected = max(probs, key=probs.get) if probs else None
        return DecisionResult(
            probabilities=probs,
            selected=selected,
            latency_ms=latency_ms,
            raw_response=data if isinstance(data, dict) else None,
            provider=self.name,
            model_id=data.get("model", self.model_id) if isinstance(data, dict) else self.model_id,
        )
