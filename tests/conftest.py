"""Shared pytest fixtures. Everything runs offline against the deterministic demo data."""

from __future__ import annotations

import pytest

from jevgym.config import Settings, get_settings


@pytest.fixture
def settings(tmp_path) -> Settings:
    return get_settings(str(tmp_path))


@pytest.fixture
def seeded(settings) -> Settings:
    """Raw cache seeded with the offline demo payloads."""
    from jevgym.data.kalshi.ingest import seed_from_fixtures

    seed_from_fixtures(settings)
    return settings


@pytest.fixture
def parsed(seeded) -> Settings:
    from jevgym.data.parse import parse_all
    from jevgym.evidence import build_all_evidence

    parse_all(seeded)
    build_all_evidence(seeded)
    return seeded


@pytest.fixture
def built(parsed) -> Settings:
    """Full pipeline through snapshots."""
    from jevgym.snapshots.builder import build_snapshots

    build_snapshots(parsed)
    return parsed
