"""Translate the canonical question to/from the Jev `/v1/systemone` wire format.

A binary market maps to a single ``choice`` question with YES/NO criteria — the most
portable typed form (every System-One model supports 2-option choice). ``noul`` answers are
also accepted on parse for models that answer yes/no natively.
"""

from __future__ import annotations

from ..models import CanonicalQuestion


def to_jev_questions(cq: CanonicalQuestion, question_id: str = "q") -> dict:
    criteria = {c: cq.candidate_descriptions.get(c, c) for c in cq.candidates}
    return {question_id: {"type": "choice", "instructions": cq.question, "criteria": criteria}}


def parse_jev_answer(data: dict, question_id: str, candidates: list[str]) -> dict[str, float]:
    """Extract a normalized distribution over ``candidates`` from a Jev-wire response.

    Handles ``probabilities`` as dict or list, and falls back to ``choice`` (one-hot) or
    ``noul`` (binary) if an explicit distribution is absent.
    """
    ans = (data.get("answers") or {}).get(question_id, {}) or {}
    probs = ans.get("probabilities")

    if isinstance(probs, dict):
        out = {c: float(probs.get(c, 0.0)) for c in candidates}
    elif isinstance(probs, list):
        out = {c: (float(probs[i]) if i < len(probs) else 0.0) for i, c in enumerate(candidates)}
    else:
        choice = ans.get("choice")
        noul = ans.get("noul")
        if choice in candidates:
            out = {c: (1.0 if c == choice else 0.0) for c in candidates}
        elif noul is not None and set(candidates) == {"YES", "NO"}:
            nv = float(noul)
            out = {"YES": nv, "NO": 1.0 - nv}
        else:
            out = {c: 1.0 / len(candidates) for c in candidates}

    total = sum(max(0.0, v) for v in out.values())
    if total <= 0:
        return {c: 1.0 / len(candidates) for c in candidates}
    return {c: max(0.0, v) / total for c, v in out.items()}
