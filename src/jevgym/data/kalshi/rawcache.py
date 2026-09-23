"""Local raw-payload cache.

Preserves untouched source payloads on disk. This directory is **never** committed or
published — derived/normalized records (with provenance pointers back here) are what get
released. Storage is plain JSONL/JSON so it is trivially inspectable.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Any

from ...util import iso, utcnow


class RawCache:
    """Generic on-disk raw store rooted at ``base_dir`` (typically ``data/raw``).

    Records are wrapped as ``{"retrieved_at", "endpoint", "obj"}`` so the parser can build
    provenance without guessing when/where a payload came from.
    """

    def __init__(self, base_dir: str | Path):
        self.base = Path(base_dir)

    # --- paths -------------------------------------------------------------
    def path(self, rel: str) -> Path:
        return self.base / rel

    def exists(self, rel: str) -> bool:
        return self.path(rel).exists()

    # --- JSONL (collections of objects) -----------------------------------
    def write_records(
        self, rel: str, objects: Iterable[dict], *, endpoint: str, retrieved_at=None
    ) -> int:
        p = self.path(rel)
        p.parent.mkdir(parents=True, exist_ok=True)
        ts = iso(retrieved_at or utcnow())
        n = 0
        with p.open("w", encoding="utf-8") as f:
            for obj in objects:
                f.write(json.dumps({"retrieved_at": ts, "endpoint": endpoint, "obj": obj}) + "\n")
                n += 1
        return n

    def read_records(self, rel: str) -> Iterator[dict]:
        p = self.path(rel)
        if not p.exists():
            return
        with p.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    yield json.loads(line)

    # --- single JSON blobs (e.g. per-ticker candlesticks) ------------------
    def write_blob(self, rel: str, payload: dict, *, endpoint: str, retrieved_at=None) -> None:
        p = self.path(rel)
        p.parent.mkdir(parents=True, exist_ok=True)
        wrapper = {"retrieved_at": iso(retrieved_at or utcnow()), "endpoint": endpoint, **payload}
        p.write_text(json.dumps(wrapper), encoding="utf-8")

    def read_blob(self, rel: str) -> dict | None:
        p = self.path(rel)
        if not p.exists():
            return None
        return json.loads(p.read_text(encoding="utf-8"))

    def iter_blobs(self, rel_dir: str, suffix: str = ".json") -> Iterator[tuple[str, dict]]:
        d = self.path(rel_dir)
        if not d.exists():
            return
        for p in sorted(d.glob(f"*{suffix}")):
            yield p.stem, json.loads(p.read_text(encoding="utf-8"))


def raw_json_dump(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True)
