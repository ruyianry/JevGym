from __future__ import annotations

import json
from datetime import datetime, timezone

from jevgym.models.decision import CanonicalQuestion
from jevgym.providers import ALL_PROVIDERS, build_provider
from jevgym.providers.llm import (
    LLMAgentProvider,
    LLMProvider,
    LLMToolCall,
    LLMTurn,
    MockLLMBackend,
    _to_anthropic_messages,
    _to_openai_messages,
    _to_openai_tools,
    parse_p_yes,
)
from jevgym.tools.search import SearchResult

UTC = timezone.utc


class SpySearch:
    name = "spy"

    def __init__(self):
        self.calls = []

    def search(self, query, as_of, k=5):
        self.calls.append(("search", query, as_of))
        return [SearchResult(title="Fed minutes", url="u", published_at=None)]

    def fetch(self, url, as_of):
        self.calls.append(("fetch", url, as_of))
        return "archived content"


def test_parse_p_yes_variants():
    assert abs(parse_p_yes('{"p_yes": 0.73}') - 0.73) < 1e-9
    assert abs(parse_p_yes("The probability is 0.9 based on the data.") - 0.9) < 1e-9
    assert parse_p_yes('{"p_yes": 1.5}') == 1.0  # clamped
    assert parse_p_yes("no number here") is None


def test_llm_provider_single_pass():
    backend = MockLLMBackend([LLMTurn(text='{"p_yes": 0.73, "rationale": "x"}')])
    dr = LLMProvider(backend).decide("state", "Which outcome?", ["YES", "NO"])
    assert abs(dr.probabilities["YES"] - 0.73) < 1e-9
    assert dr.selected == "YES"
    assert dr.provider == "llm"


def test_llm_agent_searches_then_submits_bounded_by_as_of():
    backend = MockLLMBackend(
        [
            LLMTurn(tool_calls=[LLMToolCall(id="t1", name="search", input={"query": "fed jan 2026"})]),
            LLMTurn(tool_calls=[LLMToolCall(id="t2", name="submit_forecast", input={"p_yes": 0.8, "rationale": "r"})]),
        ]
    )
    spy = SpySearch()
    cq = CanonicalQuestion(
        state="s", question="Which?", candidates=["YES", "NO"], as_of=datetime(2026, 1, 10, tzinfo=UTC)
    )
    dr = LLMAgentProvider(backend, spy).decide_question(cq)
    assert abs(dr.probabilities["YES"] - 0.8) < 1e-9
    # The agent actually searched, and the search was bounded to the snapshot's as_of.
    assert spy.calls and spy.calls[0][0] == "search"
    assert spy.calls[0][2] == cq.as_of


def test_llm_agent_without_as_of_falls_back_and_never_searches():
    backend = MockLLMBackend([LLMTurn(text='{"p_yes": 0.4}')])
    spy = SpySearch()
    cq = CanonicalQuestion(state="s", question="q", candidates=["YES", "NO"])  # no as_of
    dr = LLMAgentProvider(backend, spy).decide_question(cq)
    assert abs(dr.probabilities["YES"] - 0.4) < 1e-9
    assert spy.calls == []  # no temporal anchor -> no (leaky) search


def test_build_llm_providers_lazily():
    for name in ("llm", "llm_agent", "gpt", "gpt_agent", "qwen", "qwen_agent", "gemini", "gemini_agent"):
        assert name in ALL_PROVIDERS
    # Constructing must not require the anthropic/openai packages or a key (all lazy).
    assert build_provider("llm").name == "llm"
    assert build_provider("llm_agent").name == "llm_agent"


def test_openai_compatible_backbones_route_by_base_url():
    gpt = build_provider("gpt")
    qwen = build_provider("qwen")
    gemini = build_provider("gemini")
    assert (gpt.name, qwen.name, gemini.name) == ("gpt", "qwen", "gemini")
    # Qwen/Gemini route to their OpenAI-compatible endpoints; OpenAI uses the SDK default.
    assert "dashscope" in qwen.backend.base_url
    assert "generativelanguage.googleapis.com" in gemini.backend.base_url
    assert gpt.backend.base_url in (None, "")
    # Local Qwen servers ignore the key, so it defaults to a placeholder rather than erroring.
    assert qwen.backend.api_key
    # Aliases resolve to the canonical provider name.
    assert build_provider("chatgpt").name == "gpt"


def test_neutral_to_openai_message_translation():
    msgs = [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "", "tool_calls": [LLMToolCall(id="c1", name="search", input={"query": "q"})]},
        {"role": "tool", "tool_call_id": "c1", "content": "results"},
    ]
    out = _to_openai_messages("SYS", msgs)
    assert out[0] == {"role": "system", "content": "SYS"}
    assistant = out[2]
    assert assistant["tool_calls"][0]["function"]["name"] == "search"
    assert json.loads(assistant["tool_calls"][0]["function"]["arguments"]) == {"query": "q"}
    assert out[3] == {"role": "tool", "tool_call_id": "c1", "content": "results"}

    tools = _to_openai_tools([{"name": "search", "description": "d", "input_schema": {"type": "object"}}])
    assert tools[0]["type"] == "function" and tools[0]["function"]["name"] == "search"


def test_neutral_to_anthropic_message_translation_groups_tool_results():
    msgs = [
        {"role": "assistant", "content": "thinking", "tool_calls": [LLMToolCall(id="c1", name="search", input={"query": "q"})]},
        {"role": "tool", "tool_call_id": "c1", "content": "results"},
    ]
    out = _to_anthropic_messages(msgs)
    assert out[0]["role"] == "assistant"
    kinds = {b["type"] for b in out[0]["content"]}
    assert kinds == {"text", "tool_use"}
    assert out[1]["role"] == "user"
    assert out[1]["content"][0]["type"] == "tool_result"
    assert out[1]["content"][0]["tool_use_id"] == "c1"
