from __future__ import annotations

import httpx
import pytest
import respx

from jevgym.models import CanonicalQuestion
from jevgym.providers import build_provider, is_baseline
from jevgym.providers.prompt import parse_jev_answer, to_jev_questions


def test_mock_is_deterministic_and_normalized():
    p = build_provider("mock")
    a = p.decide("state-A", "q?", ["YES", "NO"])
    b = p.decide("state-A", "q?", ["YES", "NO"])
    assert a.probabilities == b.probabilities
    assert abs(sum(a.probabilities.values()) - 1.0) < 1e-9


def test_kalshi_market_is_baseline():
    km = build_provider("kalshi_market")
    assert is_baseline(km)
    assert not is_baseline(build_provider("mock"))


def test_to_and_from_jev_wire():
    cq = CanonicalQuestion(
        state="s", question="Which?", candidates=["YES", "NO"],
        candidate_descriptions={"YES": "yes desc", "NO": "no desc"},
    )
    payload = to_jev_questions(cq)
    assert payload["q"]["type"] == "choice"
    assert payload["q"]["criteria"] == {"YES": "yes desc", "NO": "no desc"}

    # dict probabilities
    d = {"answers": {"q": {"probabilities": {"YES": 0.7, "NO": 0.3}}}}
    assert parse_jev_answer(d, "q", ["YES", "NO"])["YES"] == 0.7
    # list probabilities
    d = {"answers": {"q": {"probabilities": [0.2, 0.8]}}}
    assert parse_jev_answer(d, "q", ["YES", "NO"])["NO"] == 0.8
    # noul fallback for binary
    d = {"answers": {"q": {"noul": 0.9}}}
    assert parse_jev_answer(d, "q", ["YES", "NO"])["YES"] == 0.9
    # choice one-hot fallback
    d = {"answers": {"q": {"choice": "NO"}}}
    assert parse_jev_answer(d, "q", ["YES", "NO"]) == {"YES": 0.0, "NO": 1.0}


@respx.mock
def test_jev_wire_provider_roundtrip():
    respx.post("http://127.0.0.1:8000/v1/systemone").mock(
        return_value=httpx.Response(
            200,
            json={
                "model": "von-1",
                "answers": {"q": {"choice": "YES", "probabilities": {"YES": 0.66, "NO": 0.34}}},
                "usage": {"input_tokens": 100, "output_tokens": 0},
            },
        )
    )
    p = build_provider("von")  # served via JevWireProvider
    dr = p.decide("state", "Which outcome?", ["YES", "NO"])
    assert dr.probabilities["YES"] == 0.66
    assert dr.model_id == "von-1"
    assert dr.latency_ms is not None


def test_roadmap_stub_raises_clearly():
    stub = build_provider("semif")  # still a roadmap stub (nanojev is now a real adapter)
    with pytest.raises(NotImplementedError) as e:
        stub.decide("s", "q", ["YES", "NO"])
    assert "semif" in str(e.value).lower()


def test_nanojev_is_a_real_adapter():
    from jevgym.providers.nanojev import NanoJevProvider, _parse_nanojev

    p = build_provider("nanojev")
    assert isinstance(p, NanoJevProvider)
    assert p.base_url.endswith(":8765") and p.model_id == "nanojev-0.6b"
    # boolean head: answer.probability == P(YES)
    probs = _parse_nanojev({"answers": {"q": {"probability": 0.7}}}, "q", ["YES", "NO"])
    assert abs(probs["YES"] - 0.7) < 1e-9 and abs(probs["NO"] - 0.3) < 1e-9


def test_unknown_provider():
    with pytest.raises(KeyError):
        build_provider("does-not-exist")
