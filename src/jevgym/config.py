"""Runtime configuration: filesystem paths + environment-driven endpoints/credentials.

Design notes
------------
* Everything is env-driven so the *same* code runs offline (fixtures) or live.
* Importing this module never requires credentials; clients/providers validate their
  own credentials lazily, only when a live call is actually made.
* Paths are derived from a single ``data_dir`` so tests can point at a tmp directory.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

try:  # dotenv is a declared dependency, but keep import defensive for minimal installs.
    from dotenv import load_dotenv
except Exception:  # pragma: no cover
    load_dotenv = None  # type: ignore[assignment]

DEFAULT_KALSHI_API_BASE = "https://external-api.kalshi.com/trade-api/v2"
DEFAULT_FRED_API_BASE = "https://api.stlouisfed.org/fred"
DEFAULT_TYPESAFE_API_BASE = "https://api.typesafe.ai"
DEFAULT_ANTHROPIC_MODEL = "claude-opus-4-8"
DEFAULT_SEARCH_PROVIDER = "wayback"  # "wayback" (fetch-only, free) | "serp" (dated search) | "mock"

# LLM backbones reachable through the OpenAI-compatible wire (openai SDK + base_url).
DEFAULT_OPENAI_MODEL = "gpt-4o"  # override via OPENAI_MODEL
DEFAULT_QWEN_MODEL = "qwen2.5-72b-instruct"  # override via QWEN_MODEL (local/served Qwen)
DEFAULT_QWEN_BASE_URL = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"  # or local vLLM/Ollama /v1
DEFAULT_GEMINI_MODEL = "gemini-2.0-flash"  # override via GEMINI_MODEL
DEFAULT_GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"


@dataclass(frozen=True)
class Paths:
    """Canonical on-disk layout, all under a single ``data_dir``.

    ``raw`` holds untouched third-party payloads and is *never* published.
    ``normalized`` / ``snapshots`` / ``dataset`` hold derived, publishable artifacts.
    """

    data_dir: Path

    @property
    def raw(self) -> Path:
        return self.data_dir / "raw"

    @property
    def normalized(self) -> Path:
        return self.data_dir / "normalized"

    @property
    def snapshots(self) -> Path:
        return self.data_dir / "snapshots"

    @property
    def dataset(self) -> Path:
        return self.data_dir / "dataset"

    @property
    def manifest(self) -> Path:
        return self.data_dir / "manifest.json"

    def ensure(self) -> Paths:
        for p in (self.raw, self.normalized, self.snapshots, self.dataset):
            p.mkdir(parents=True, exist_ok=True)
        return self


@dataclass(frozen=True)
class Settings:
    paths: Paths

    kalshi_api_base: str
    kalshi_api_key_id: str | None
    kalshi_private_key_path: str | None

    fred_api_base: str
    fred_api_key: str | None

    typesafe_api_base: str
    typesafe_api_key: str | None

    # LLM backbones (generic-LLM provider / agentic forecaster).
    anthropic_api_key: str | None
    anthropic_model: str

    openai_api_key: str | None  # ChatGPT (also any OpenAI-compatible server)
    openai_model: str
    openai_base_url: str | None  # None => api.openai.com/v1

    qwen_api_key: str | None  # DashScope key, or "EMPTY" for local vLLM/Ollama
    qwen_model: str
    qwen_base_url: str

    gemini_api_key: str | None
    gemini_model: str
    gemini_base_url: str

    # Time-bounded search (agentic evidence gathering)
    search_provider: str
    search_api_key: str | None  # SerpAPI/Google-CSE key for dated search (Wayback needs none)

    hf_repo_id: str | None
    hf_token: str | None


def _env(name: str, default: str | None = None) -> str | None:
    val = os.getenv(name)
    if val is None or val == "":
        return default
    return val


def get_settings(data_dir: str | os.PathLike[str] | None = None) -> Settings:
    """Load settings from environment (and a local ``.env`` if present).

    Not cached: cheap to build, and tests frequently vary ``JEVARENA_DATA_DIR``.
    Pass ``data_dir`` to override the location explicitly (used by the CLI/tests).
    """

    if load_dotenv is not None:
        load_dotenv()

    resolved = Path(data_dir or _env("JEVARENA_DATA_DIR", "data") or "data").resolve()
    return Settings(
        paths=Paths(data_dir=resolved),
        kalshi_api_base=_env("KALSHI_API_BASE", DEFAULT_KALSHI_API_BASE) or DEFAULT_KALSHI_API_BASE,
        kalshi_api_key_id=_env("KALSHI_API_KEY_ID"),
        kalshi_private_key_path=_env("KALSHI_PRIVATE_KEY_PATH"),
        fred_api_base=_env("FRED_API_BASE", DEFAULT_FRED_API_BASE) or DEFAULT_FRED_API_BASE,
        fred_api_key=_env("FRED_API_KEY"),
        typesafe_api_base=_env("TYPESAFE_API_BASE", DEFAULT_TYPESAFE_API_BASE)
        or DEFAULT_TYPESAFE_API_BASE,
        typesafe_api_key=_env("TYPESAFE_API_KEY") or _env("TS_TOKEN"),
        anthropic_api_key=_env("ANTHROPIC_API_KEY"),
        anthropic_model=_env("ANTHROPIC_MODEL", DEFAULT_ANTHROPIC_MODEL) or DEFAULT_ANTHROPIC_MODEL,
        openai_api_key=_env("OPENAI_API_KEY"),
        openai_model=_env("OPENAI_MODEL", DEFAULT_OPENAI_MODEL) or DEFAULT_OPENAI_MODEL,
        openai_base_url=_env("OPENAI_BASE_URL"),
        qwen_api_key=_env("QWEN_API_KEY") or _env("DASHSCOPE_API_KEY"),
        qwen_model=_env("QWEN_MODEL", DEFAULT_QWEN_MODEL) or DEFAULT_QWEN_MODEL,
        qwen_base_url=_env("QWEN_BASE_URL", DEFAULT_QWEN_BASE_URL) or DEFAULT_QWEN_BASE_URL,
        gemini_api_key=_env("GEMINI_API_KEY") or _env("GOOGLE_API_KEY"),
        gemini_model=_env("GEMINI_MODEL", DEFAULT_GEMINI_MODEL) or DEFAULT_GEMINI_MODEL,
        gemini_base_url=_env("GEMINI_BASE_URL", DEFAULT_GEMINI_BASE_URL) or DEFAULT_GEMINI_BASE_URL,
        search_provider=_env("SEARCH_PROVIDER", DEFAULT_SEARCH_PROVIDER) or DEFAULT_SEARCH_PROVIDER,
        search_api_key=_env("SEARCH_API_KEY"),
        hf_repo_id=_env("HF_REPO_ID"),
        hf_token=_env("HF_TOKEN"),
    )
