"""Shared Pydantic base + provenance mixin.

Every *record* that can end up in the published dataset carries provenance and version
stamps so it is fully traceable and reproducible (requirement: "add provenance
everywhere"). Provenance fields are flat (not nested) so they become clean, queryable
columns in the exported Parquet/HuggingFace tables.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from ..version import DATASET_VERSION, PARSER_VERSION


class JevBaseModel(BaseModel):
    """Base for all models. Lenient on extra input (Kalshi adds fields over time) and
    permissive on aliases so we can accept upstream field names directly."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)


class ProvenanceMixin(JevBaseModel):
    """Traceability fields attached to every sourced record.

    ``available_at`` is the load-bearing one for temporal-leakage checks: for any evidence
    a model is allowed to see in a snapshot, ``available_at <= snapshot.timestamp`` must
    hold. It is the moment the information became *publicly knowable* (e.g. a macro figure's
    release time), which is distinct from ``retrieved_at`` (when we fetched it).
    """

    source_provider: str  # "kalshi", "fred", ...
    source_endpoint: str  # e.g. "/markets/{ticker}" or "series/UNRATE/observations"
    source_identifier: str  # ticker / series id / etc. (points back to the raw cache)
    retrieved_at: datetime  # when JevGym fetched it
    available_at: datetime  # when the info became public knowledge
    parser_version: str = PARSER_VERSION
    dataset_version: str = DATASET_VERSION

    metadata: dict = Field(default_factory=dict)  # retained documented-but-unmodeled fields
