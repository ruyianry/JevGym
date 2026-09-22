"""JSONL read/write helpers for Pydantic models and plain dict rows.

Normalized records and snapshots are stored as JSONL (one JSON object per line) so they are
streamable, appendable, and diff-friendly. The HuggingFace export reads these back.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel

M = TypeVar("M", bound=BaseModel)


def write_model_jsonl(path: str | Path, models: Iterable[BaseModel]) -> int:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with p.open("w", encoding="utf-8") as f:
        for m in models:
            f.write(json.dumps(m.model_dump(mode="json")) + "\n")
            n += 1
    return n


def read_model_jsonl(path: str | Path, model_cls: type[M]) -> list[M]:
    p = Path(path)
    if not p.exists():
        return []
    out: list[M] = []
    with p.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(model_cls.model_validate(json.loads(line)))
    return out


def iter_model_jsonl(path: str | Path, model_cls: type[M]) -> Iterator[M]:
    p = Path(path)
    if not p.exists():
        return
    with p.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                yield model_cls.model_validate(json.loads(line))


def write_jsonl(path: str | Path, rows: Iterable[dict]) -> int:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with p.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")
            n += 1
    return n


def iter_jsonl(path: str | Path) -> Iterator[dict]:
    p = Path(path)
    if not p.exists():
        return
    with p.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)
