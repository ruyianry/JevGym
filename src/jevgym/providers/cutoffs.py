"""Model release dates — the LLM-validity guard.

An LLM's forecast is only honest if the event resolved *after* the model could have learned
the outcome. The exact training cutoff is usually unknown, but the **public release date** is
citable and is an upper bound on training data, so we use it as the reference and add a
**buffer** (default 90 days) for safety: a model is scored on a market only if

    event_resolution_date > release_date + buffer.

Dates are **approximate** (month granularity, best effort) — override for your exact model,
or pass ``--resolves-after`` to force one global cutoff for a fair head-to-head. Non-LLM
providers (Jev, kalshi_market, Jev-wire servers, mock) have no release date and see everything.
"""

from __future__ import annotations

from datetime import datetime, timezone

DEFAULT_CUTOFF_BUFFER_DAYS = 90  # ~3 months


def _d(year: int, month: int, day: int = 1) -> datetime:
    return datetime(year, month, day, tzinfo=timezone.utc)


# Approximate PUBLIC RELEASE dates (when weights/API went public).
MODEL_RELEASE_DATES: dict[str, datetime] = {
    # Anthropic
    "claude-opus-4-8": _d(2026, 1),
    "claude-opus-4-7": _d(2025, 11),
    "claude-sonnet-4-6": _d(2025, 9),
    "claude-haiku-4-5": _d(2025, 10),
    # OpenAI
    "gpt-4o": _d(2024, 5),
    "gpt-4o-mini": _d(2024, 7),
    "gpt-4.1": _d(2025, 4),
    "gpt-5": _d(2025, 8),
    # Google
    "gemini-1.5": _d(2024, 2),
    "gemini-2.0": _d(2024, 12),
    "gemini-2.5": _d(2025, 3),
    # Qwen (open source)
    "qwen2": _d(2024, 6),
    "qwen2.5": _d(2024, 9),
    "qwen3": _d(2025, 4),
}


def release_date_for(model_id: str | None) -> datetime | None:
    """Best-effort public release date for a model id (exact, else longest substring match)."""
    if not model_id:
        return None
    mid = model_id.lower()
    if mid in MODEL_RELEASE_DATES:
        return MODEL_RELEASE_DATES[mid]
    best: datetime | None = None
    best_len = -1
    for key, dt in MODEL_RELEASE_DATES.items():
        if key in mid and len(key) > best_len:
            best, best_len = dt, len(key)
    return best
