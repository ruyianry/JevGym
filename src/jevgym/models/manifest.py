"""Deterministic dataset manifest + per-shard content hashes (versioning requirement)."""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from .base import JevBaseModel


class ShardHash(JevBaseModel):
    path: str  # relative to the dataset root
    sha256: str
    bytes: int
    config: str | None = None
    split: str | None = None


class DatasetManifest(JevBaseModel):
    dataset_version: str
    parser_version: str
    created_at: datetime

    market_count: int = 0
    event_count: int = 0
    price_point_count: int = 0
    snapshot_count: int = 0
    evidence_count: int = 0

    source_cutoffs: dict[str, str] = Field(default_factory=dict)
    git_commit: str | None = None
    shards: list[ShardHash] = Field(default_factory=list)
