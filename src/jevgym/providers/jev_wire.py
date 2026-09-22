"""One adapter for every model that speaks the Jev `/v1/systemone` wire format.

This single class serves the official reference (TypeSafe Jev, with a Bearer key) **and**
the open challengers that expose the identical endpoint — Von, Decider (server mode), and
razorback16/OpenJev — differing only by ``base_url`` and ``model_id``. That is the whole
point of the abstraction: the evaluator cannot tell them apart.
"""

from __future__ import annotations

import time

import httpx

from ..models import CanonicalQuestion, DecisionResult
from .prompt import parse_jev_answer, to_jev_questions


class JevWireProvider:
    def __init__(
        self,
        *,
        name: str,
        model_id: str,
        base_url: str,
        api_key: str | None = None,
        question_id: str = "q",
        timeout: float = 60.0,
        client: httpx.Client | None = None,
    ):
        self.name = name
        self.model_id = model_id
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
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
        payload = {
            "model": self.model_id,
            "state": cq.state,
            "questions": to_jev_questions(cq, self.question_id),
        }
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}

        t0 = time.perf_counter()
        resp = self._get_client().post(
            f"{self.base_url}/v1/systemone", json=payload, headers=headers
        )
        resp.raise_for_status()
        data = resp.json()
        latency_ms = (time.perf_counter() - t0) * 1000.0

        probs = parse_jev_answer(data, self.question_id, cq.candidates)
        selected = max(probs, key=probs.get) if probs else None
        return DecisionResult(
            probabilities=probs,
            selected=selected,
            latency_ms=latency_ms,
            raw_response=data if isinstance(data, dict) else None,
            provider=self.name,
            model_id=data.get("model", self.model_id) if isinstance(data, dict) else self.model_id,
        )
