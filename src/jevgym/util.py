"""Small, dependency-light utilities shared across the package.

Kept deliberately tiny: time normalization (everything is tz-aware UTC), deterministic
JSON (for hashing and reproducible prompts/ids), and content hashing (for the manifest).
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utcnow() -> datetime:
    """Timezone-aware 'now' in UTC."""
    return datetime.now(timezone.utc)


def ensure_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def from_unix(ts: int | float | None) -> datetime | None:
    if ts is None:
        return None
    return datetime.fromtimestamp(float(ts), tz=timezone.utc)


def to_unix(dt: datetime) -> int:
    return int(ensure_utc(dt).timestamp())  # type: ignore[union-attr]


def parse_dt(value: Any) -> datetime | None:
    """Best-effort parse of Kalshi/FRED timestamps into tz-aware UTC datetimes.

    Accepts ``datetime``, unix seconds (int/float or digit string), or ISO-8601 strings
    (tolerating a trailing ``Z``). Returns ``None`` for empty/unparseable input.
    """
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return ensure_utc(value)
    if isinstance(value, (int, float)):
        return from_unix(value)
    s = str(value).strip()
    if not s:
        return None
    if s.isdigit():
        return from_unix(int(s))
    s = s.replace("Z", "+00:00")
    try:
        return ensure_utc(datetime.fromisoformat(s))
    except ValueError:
        # Date-only fallback (e.g. FRED "2026-08-01").
        try:
            return ensure_utc(datetime.strptime(s[:10], "%Y-%m-%d"))
        except ValueError:
            return None


def iso(dt: datetime | None) -> str | None:
    d = ensure_utc(dt)
    return d.isoformat() if d is not None else None


def stable_json(obj: Any) -> str:
    """Deterministic JSON encoding (sorted keys, compact) for hashing & reproducibility."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str, ensure_ascii=False)


def sha256_str(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def sha256_file(path: str | Path) -> tuple[str, int]:
    """Return (hex_digest, byte_count) for a file, streaming in 1 MiB chunks."""
    h = hashlib.sha256()
    n = 0
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
            n += len(chunk)
    return h.hexdigest(), n


def short_hash(*parts: Any, length: int = 12) -> str:
    """Stable short hash of the given parts, used to mint deterministic ids."""
    return sha256_str("|".join(str(p) for p in parts))[:length]
