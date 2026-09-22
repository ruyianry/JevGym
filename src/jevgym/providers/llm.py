"""LLM-backbone providers — wrap a general LLM as a System One decision model.

Two providers, both implementing the ``SystemOneProvider`` contract so the evaluator can't
tell them from Jev or NanoJev:

* ``LLMProvider`` — single forward pass: the LLM reads the frozen state/question and returns a
  calibrated P(YES).
* ``LLMAgentProvider`` — an agentic forecaster that may call a **time-bounded** ``search`` /
  ``fetch_url`` tool (bounded to ``cq.as_of`` so it can never see the future), then calls
  ``submit_forecast``. This mirrors "LLM-as-Jev-backbone" harnesses (e.g. JevHarness).

Backends sit behind a small ``LLMBackend`` seam using a **provider-neutral** message format,
so one loop drives every model:

* ``AnthropicBackend`` — Claude via the official SDK.
* ``OpenAIBackend`` — the OpenAI-compatible wire (``openai`` SDK + ``base_url``). One class
  covers **ChatGPT** (OpenAI), **Qwen** (DashScope / local vLLM / Ollama), and **Gemini**
  (Google's OpenAI-compatibility endpoint) — they differ only by ``base_url`` + ``model``.
* ``MockLLMBackend`` — scripted, offline.
"""

from __future__ import annotations

import json
import re
import time
from typing import Protocol, runtime_checkable

from ..models import DecisionResult
from ..models.base import JevBaseModel
from ..models.decision import CanonicalQuestion
from ..util import iso

# --- backend seam ----------------------------------------------------------


class LLMToolCall(JevBaseModel):
    id: str
    name: str
    input: dict


class LLMTurn(JevBaseModel):
    text: str = ""
    tool_calls: list[LLMToolCall] = []
    stop_reason: str = "end_turn"
    input_tokens: int | None = None


@runtime_checkable
class LLMBackend(Protocol):
    name: str
    model_id: str

    def generate(
        self, *, system: str, messages: list[dict], tools: list[dict] | None = None, max_tokens: int = 1024
    ) -> LLMTurn: ...


# Neutral message shape used across all backends:
#   {"role": "user"|"assistant"|"tool", "content": str,
#    "tool_calls": [LLMToolCall]  (assistant only),
#    "tool_call_id": str          (tool only)}
# Tools use the Anthropic shape {name, description, input_schema}; each backend translates.


def _to_anthropic_messages(messages: list[dict]) -> list[dict]:
    out: list[dict] = []
    pending: list[dict] = []

    def flush() -> None:
        nonlocal pending
        if pending:
            out.append({"role": "user", "content": pending})
            pending = []

    for m in messages:
        role = m["role"]
        if role == "tool":
            pending.append(
                {"type": "tool_result", "tool_use_id": m.get("tool_call_id", ""), "content": m.get("content", "")}
            )
            continue
        flush()
        if role == "user":
            out.append({"role": "user", "content": m.get("content", "")})
        elif role == "assistant":
            blocks: list[dict] = []
            if m.get("content"):
                blocks.append({"type": "text", "text": m["content"]})
            for tc in m.get("tool_calls", []) or []:
                blocks.append({"type": "tool_use", "id": tc.id, "name": tc.name, "input": tc.input})
            out.append({"role": "assistant", "content": blocks if blocks else (m.get("content") or "")})
    flush()
    return out


def _to_openai_messages(system: str, messages: list[dict]) -> list[dict]:
    out: list[dict] = []
    if system:
        out.append({"role": "system", "content": system})
    for m in messages:
        role = m["role"]
        if role == "user":
            out.append({"role": "user", "content": m.get("content", "")})
        elif role == "assistant":
            tcs = m.get("tool_calls") or []
            msg: dict = {"role": "assistant", "content": (m.get("content") or None) if tcs else m.get("content", "")}
            if tcs:
                msg["tool_calls"] = [
                    {"id": tc.id, "type": "function", "function": {"name": tc.name, "arguments": json.dumps(tc.input)}}
                    for tc in tcs
                ]
            out.append(msg)
        elif role == "tool":
            out.append({"role": "tool", "tool_call_id": m.get("tool_call_id", ""), "content": m.get("content", "")})
    return out


def _to_openai_tools(tools: list[dict]) -> list[dict]:
    return [
        {
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t.get("description", ""),
                "parameters": t.get("input_schema", {"type": "object", "properties": {}}),
            },
        }
        for t in tools
    ]


class AnthropicBackend:
    """Claude via the official ``anthropic`` SDK. Lazy import; credentials validated on use."""

    def __init__(self, model: str = "claude-opus-4-8", api_key: str | None = None, timeout: float = 120.0):
        self.name = "anthropic"
        self.model_id = model
        self.api_key = api_key
        self._timeout = timeout
        self._client = None

    def _client_or_raise(self):
        if self._client is None:
            try:
                import anthropic
            except Exception as e:  # pragma: no cover - optional dep
                raise RuntimeError("The 'anthropic' package is required. Install jevgym[llm].") from e
            if not self.api_key:
                raise RuntimeError("ANTHROPIC_API_KEY is not set; cannot run the LLM backbone.")
            self._client = anthropic.Anthropic(api_key=self.api_key, timeout=self._timeout)
        return self._client

    def generate(self, *, system, messages, tools=None, max_tokens=1024) -> LLMTurn:
        client = self._client_or_raise()
        kwargs = dict(model=self.model_id, max_tokens=max_tokens, system=system, messages=_to_anthropic_messages(messages))
        if tools:
            kwargs["tools"] = tools
        resp = client.messages.create(**kwargs)
        text = "".join(b.text for b in resp.content if getattr(b, "type", None) == "text")
        tool_calls = [
            LLMToolCall(id=b.id, name=b.name, input=dict(b.input))
            for b in resp.content
            if getattr(b, "type", None) == "tool_use"
        ]
        return LLMTurn(
            text=text,
            tool_calls=tool_calls,
            stop_reason=resp.stop_reason or "end_turn",
            input_tokens=getattr(resp.usage, "input_tokens", None),
        )


class OpenAIBackend:
    """OpenAI-compatible chat backend (``openai`` SDK). Point ``base_url`` at OpenAI, a Qwen
    server (DashScope / vLLM / Ollama), Gemini's compat endpoint, or any other."""

    def __init__(
        self,
        model: str,
        api_key: str | None = None,
        base_url: str | None = None,
        name: str = "openai",
        timeout: float = 120.0,
    ):
        self.name = name
        self.model_id = model
        self.api_key = api_key
        self.base_url = base_url
        self._timeout = timeout
        self._client = None

    def _client_or_raise(self):
        if self._client is None:
            try:
                from openai import OpenAI
            except Exception as e:  # pragma: no cover - optional dep
                raise RuntimeError("The 'openai' package is required. Install jevgym[llm].") from e
            if not self.api_key:
                raise RuntimeError(f"No API key configured for backend '{self.name}' (model {self.model_id}).")
            kwargs = {"api_key": self.api_key, "timeout": self._timeout}
            if self.base_url:
                kwargs["base_url"] = self.base_url
            self._client = OpenAI(**kwargs)
        return self._client

    def generate(self, *, system, messages, tools=None, max_tokens=1024) -> LLMTurn:
        client = self._client_or_raise()
        kwargs = dict(model=self.model_id, messages=_to_openai_messages(system, messages), max_tokens=max_tokens)
        if tools:
            kwargs["tools"] = _to_openai_tools(tools)
            kwargs["tool_choice"] = "auto"
        resp = client.chat.completions.create(**kwargs)
        choice = resp.choices[0]
        msg = choice.message
        tool_calls = []
        for tc in getattr(msg, "tool_calls", None) or []:
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            tool_calls.append(LLMToolCall(id=tc.id, name=tc.function.name, input=args))
        return LLMTurn(
            text=msg.content or "",
            tool_calls=tool_calls,
            stop_reason=choice.finish_reason or "stop",
            input_tokens=getattr(getattr(resp, "usage", None), "prompt_tokens", None),
        )


class MockLLMBackend:
    """Returns scripted turns in order (or from a callable). Ignores prompt content."""

    def __init__(self, turns: list[LLMTurn] | None = None, model_id: str = "mock-llm", fn=None):
        self.name = "mock-llm"
        self.model_id = model_id
        self._turns = list(turns or [])
        self._fn = fn

    def generate(self, *, system, messages, tools=None, max_tokens=1024) -> LLMTurn:
        if self._fn is not None:
            return self._fn(system=system, messages=messages, tools=tools)
        if self._turns:
            return self._turns.pop(0)
        return LLMTurn(text='{"p_yes": 0.5}')


# --- probability parsing ---------------------------------------------------

_P_KEYS = ("p_yes", "probability_yes", "prob_yes", "yes", "p", "probability")


def parse_p_yes(text: str) -> float | None:
    if not text:
        return None
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if m:
        try:
            obj = json.loads(m.group(0))
            for k in _P_KEYS:
                if k in obj and isinstance(obj[k], (int, float)):
                    return _clamp(float(obj[k]))
        except (json.JSONDecodeError, ValueError):
            pass
    m = re.search(r"(?<![\d.])(0?\.\d+|1\.0+|0|1)(?![\d.])", text)
    if m:
        try:
            return _clamp(float(m.group(1)))
        except ValueError:
            return None
    return None


def _clamp(x: float) -> float:
    return min(1.0, max(0.0, x))


def _binary(p_yes: float, candidates: list[str]) -> dict[str, float]:
    if set(candidates) == {"YES", "NO"}:
        return {"YES": p_yes, "NO": 1.0 - p_yes}
    n = len(candidates) or 1
    return {c: (p_yes if c == "YES" else (1.0 - p_yes) / max(1, n - 1)) for c in candidates}


# --- providers -------------------------------------------------------------

_FORECASTER_SYSTEM = (
    "You are a careful, well-calibrated forecaster. Estimate the probability that the "
    "described prediction-market contract ultimately resolves YES, using only the information "
    "provided. Respond with ONLY a JSON object: "
    '{"p_yes": <number between 0 and 1>, "rationale": "<one or two sentences>"}. No other text.'
)


class LLMProvider:
    """Single-pass LLM forecaster."""

    def __init__(self, backend: LLMBackend, name: str = "llm", release_date=None):
        self.backend = backend
        self.name = name
        self.model_id = backend.model_id
        self.release_date = release_date  # events must resolve after release_date + buffer

    def decide(self, state: str, question: str, candidates: list[str]) -> DecisionResult:
        return self.decide_question(
            CanonicalQuestion(state=state, question=question, candidates=candidates)
        )

    def decide_question(self, cq: CanonicalQuestion) -> DecisionResult:
        user = f"{cq.state}\n\nQUESTION\n--------\n{cq.question}\nCandidates: {', '.join(cq.candidates)}"
        t0 = time.perf_counter()
        turn = self.backend.generate(
            system=_FORECASTER_SYSTEM, messages=[{"role": "user", "content": user}], max_tokens=800
        )
        latency = (time.perf_counter() - t0) * 1000.0
        p = parse_p_yes(turn.text)
        p = 0.5 if p is None else p
        return DecisionResult(
            probabilities=_binary(p, cq.candidates),
            selected="YES" if p >= 0.5 else "NO",
            latency_ms=latency,
            raw_response={"text": turn.text, "input_tokens": turn.input_tokens},
            provider=self.name,
            model_id=self.backend.model_id,
        )


SEARCH_TOOL = {
    "name": "search",
    "description": "Search the web for information published on or before the as-of date. Returns titled, dated results.",
    "input_schema": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
}
FETCH_TOOL = {
    "name": "fetch_url",
    "description": "Fetch the text of a web page as it existed on or before the as-of date (Internet Archive snapshot).",
    "input_schema": {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]},
}
SUBMIT_TOOL = {
    "name": "submit_forecast",
    "description": "Submit your final calibrated probability that the contract resolves YES.",
    "input_schema": {
        "type": "object",
        "properties": {"p_yes": {"type": "number"}, "rationale": {"type": "string"}},
        "required": ["p_yes"],
    },
}


class LLMAgentProvider:
    """Agentic LLM forecaster with a time-bounded search/fetch tool.

    All tool use is bounded to ``cq.as_of`` — the historical checkpoint — so the agent gathers
    only evidence public at that time. Without an ``as_of`` it degrades to a single pass (no
    tools), because unbounded search would leak the future.
    """

    def __init__(self, backend: LLMBackend, search, name: str = "llm_agent", max_steps: int = 4, release_date=None):
        self.backend = backend
        self.search = search
        self.name = name
        self.model_id = backend.model_id
        self.max_steps = max_steps
        self.release_date = release_date

    def decide(self, state: str, question: str, candidates: list[str]) -> DecisionResult:
        return self.decide_question(
            CanonicalQuestion(state=state, question=question, candidates=candidates)
        )

    def decide_question(self, cq: CanonicalQuestion) -> DecisionResult:
        if cq.as_of is None:
            return LLMProvider(self.backend, name=self.name).decide_question(cq)

        from ..tools.search import render_results

        as_of = cq.as_of
        system = (
            f"You are a careful, well-calibrated forecaster operating AS OF {iso(as_of)}. "
            "You may call `search` and `fetch_url` to gather evidence — both are strictly limited "
            "to information available on or before that timestamp; you cannot see the future. "
            "Gather what you need, then call `submit_forecast` with the probability the contract "
            "resolves YES."
        )
        user = f"{cq.state}\n\nQUESTION\n--------\n{cq.question}\nCandidates: {', '.join(cq.candidates)}"
        messages: list[dict] = [{"role": "user", "content": user}]
        tools = [SEARCH_TOOL, FETCH_TOOL, SUBMIT_TOOL]

        t0 = time.perf_counter()
        last_text = ""
        total_input_tokens = 0
        for _ in range(self.max_steps):
            turn = self.backend.generate(system=system, messages=messages, tools=tools, max_tokens=2048)
            last_text = turn.text or last_text
            total_input_tokens += turn.input_tokens or 0

            submit = next((tc for tc in turn.tool_calls if tc.name == "submit_forecast"), None)
            if submit is not None:
                p = parse_p_yes(json.dumps(submit.input)) or _clamp(float(submit.input.get("p_yes", 0.5)))
                return self._result(p, cq, t0, total_input_tokens, submit.input.get("rationale"))

            if not turn.tool_calls:
                p = parse_p_yes(turn.text)
                if p is not None:
                    return self._result(p, cq, t0, total_input_tokens, turn.text)
                messages.append({"role": "assistant", "content": turn.text or "(thinking)"})
                messages.append({"role": "user", "content": "Please call submit_forecast now."})
                continue

            # Echo the assistant tool-call turn, then append each tool result.
            messages.append({"role": "assistant", "content": turn.text or "", "tool_calls": turn.tool_calls})
            for tc in turn.tool_calls:
                out = self._run_tool(tc, as_of, render_results)
                messages.append({"role": "tool", "tool_call_id": tc.id, "content": out})

        p = parse_p_yes(last_text)
        return self._result(0.5 if p is None else p, cq, t0, total_input_tokens, last_text)

    def _run_tool(self, tc: LLMToolCall, as_of, render_results) -> str:
        try:
            if tc.name == "search":
                results = self.search.search(tc.input.get("query", ""), as_of, k=5)
                return render_results(results)
            if tc.name == "fetch_url":
                content = self.search.fetch(tc.input.get("url", ""), as_of)
                return content or "(no as-of snapshot available for that URL)"
        except Exception as e:  # keep the loop alive on tool failure
            return f"(tool error: {e})"
        return f"(unknown tool: {tc.name})"

    def _result(self, p_yes: float, cq, t0, input_tokens, rationale) -> DecisionResult:
        p = _clamp(float(p_yes))
        return DecisionResult(
            probabilities=_binary(p, cq.candidates),
            selected="YES" if p >= 0.5 else "NO",
            latency_ms=(time.perf_counter() - t0) * 1000.0,
            raw_response={"rationale": rationale, "input_tokens": input_tokens},
            provider=self.name,
            model_id=self.backend.model_id,
        )
