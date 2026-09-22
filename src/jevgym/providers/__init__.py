"""Provider registry + factory.

``build_provider(name)`` returns a ready provider. The same ``JevWireProvider`` backs the
official reference and the wire-compatible open models; only ``base_url``/``model_id`` differ.
"""

from __future__ import annotations

import os

from ..config import Settings, get_settings
from .base import Baseline, SystemOneProvider, decide_question, is_baseline
from .jev_wire import JevWireProvider
from .kalshi_baseline import KalshiMarketBaseline
from .mock import MockProvider
from .roadmap import ROADMAP_FACTORIES

# Open, Jev-wire-compatible servers (run locally). (env var, default base, default model)
JEV_WIRE_OPEN = {
    "von": ("VON_BASE", "http://127.0.0.1:8000", "von"),
    "decider": ("DECIDER_BASE", "http://127.0.0.1:8001", "decider-2b"),
    "openjev": ("OPENJEV_BASE", "http://127.0.0.1:8002", "openjev-diffusiongemma"),
}

BASELINE_PROVIDERS = ["kalshi_market"]
LLM_PROVIDERS = ["llm", "llm_agent", "gpt", "gpt_agent", "qwen", "qwen_agent", "gemini", "gemini_agent"]
REAL_PROVIDERS = ["mock", "kalshi_market", "jev", "nanojev", "von", "decider", "openjev", *LLM_PROVIDERS]
ROADMAP_PROVIDERS = list(ROADMAP_FACTORIES)
ALL_PROVIDERS = REAL_PROVIDERS + ROADMAP_PROVIDERS

# accepted name (incl. aliases) -> (backend kind, is_agent, canonical provider name)
LLM_AGENT_SPECS = {
    "llm": ("anthropic", False, "llm"),
    "llm_agent": ("anthropic", True, "llm_agent"),
    "gpt": ("openai", False, "gpt"),
    "gpt_agent": ("openai", True, "gpt_agent"),
    "chatgpt": ("openai", False, "gpt"),
    "openai": ("openai", False, "gpt"),
    "qwen": ("qwen", False, "qwen"),
    "qwen_agent": ("qwen", True, "qwen_agent"),
    "gemini": ("gemini", False, "gemini"),
    "gemini_agent": ("gemini", True, "gemini_agent"),
}


def _build_llm_backend(kind: str, settings: Settings, *, model_id=None, api_key=None):
    """Construct an LLM backend. OpenAI/Qwen/Gemini all use the OpenAI-compatible wire."""
    from .llm import AnthropicBackend, OpenAIBackend

    if kind == "anthropic":
        return AnthropicBackend(
            model=model_id or settings.anthropic_model,
            api_key=api_key if api_key is not None else settings.anthropic_api_key,
        )
    if kind == "openai":
        return OpenAIBackend(
            model=model_id or settings.openai_model,
            api_key=api_key if api_key is not None else settings.openai_api_key,
            base_url=settings.openai_base_url,
            name="gpt",
        )
    if kind == "qwen":
        return OpenAIBackend(
            model=model_id or settings.qwen_model,
            api_key=(api_key if api_key is not None else settings.qwen_api_key) or "EMPTY",
            base_url=settings.qwen_base_url,
            name="qwen",
        )
    if kind == "gemini":
        return OpenAIBackend(
            model=model_id or settings.gemini_model,
            api_key=api_key if api_key is not None else settings.gemini_api_key,
            base_url=settings.gemini_base_url,
            name="gemini",
        )
    raise KeyError(kind)


def build_provider(
    name: str,
    settings: Settings | None = None,
    *,
    base_url: str | None = None,
    model_id: str | None = None,
    api_key: str | None = None,
    client=None,
):
    settings = settings or get_settings()
    n = name.strip().lower()

    if n == "mock":
        return MockProvider()
    if n == "kalshi_market":
        return KalshiMarketBaseline()
    if n == "jev":
        return JevWireProvider(
            name="jev",
            model_id=model_id or "jev-latest",
            base_url=base_url or settings.typesafe_api_base,
            api_key=api_key if api_key is not None else settings.typesafe_api_key,
            client=client,
        )
    if n == "nanojev":
        from .nanojev import NanoJevProvider

        return NanoJevProvider(
            model_id=model_id or "nanojev-0.6b",
            base_url=base_url or os.getenv("NANOJEV_BASE") or "http://127.0.0.1:8765",
            client=client,
        )
    if n in JEV_WIRE_OPEN:
        env_key, default_base, default_model = JEV_WIRE_OPEN[n]
        base = base_url or os.getenv(env_key) or default_base
        return JevWireProvider(
            name=n,
            model_id=model_id or default_model,
            base_url=base,
            api_key=api_key,
            client=client,
        )
    if n in LLM_AGENT_SPECS:
        kind, is_agent, canonical = LLM_AGENT_SPECS[n]
        backend = _build_llm_backend(kind, settings, model_id=model_id, api_key=api_key)
        from .cutoffs import release_date_for

        release = release_date_for(backend.model_id)
        if is_agent:
            from ..tools.search import build_search
            from .llm import LLMAgentProvider

            return LLMAgentProvider(
                backend, build_search(settings, client=client), name=canonical, release_date=release
            )
        from .llm import LLMProvider

        return LLMProvider(backend, name=canonical, release_date=release)
    if n in ROADMAP_FACTORIES:
        return ROADMAP_FACTORIES[n]()
    raise KeyError(f"Unknown provider '{name}'. Known: {', '.join(ALL_PROVIDERS)}")


__all__ = [
    "SystemOneProvider",
    "Baseline",
    "JevWireProvider",
    "MockProvider",
    "KalshiMarketBaseline",
    "build_provider",
    "decide_question",
    "is_baseline",
    "ALL_PROVIDERS",
    "REAL_PROVIDERS",
    "ROADMAP_PROVIDERS",
    "BASELINE_PROVIDERS",
    "JEV_WIRE_OPEN",
]
