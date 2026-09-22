"""Typed curation records. Physically separates model input, curation metadata, and labels.

``FeatureSnapshot`` and ``ReviewPacket`` are outcome-free by construction: there is no field
that can carry an eventual outcome, final price, or settlement value. Outcomes join only in
evaluation/audit reporting after selection is frozen.
"""

from __future__ import annotations

from datetime import date, datetime

from pydantic import Field

from ..models.base import JevBaseModel

# --- parsed weather contract ----------------------------------------------


class WeatherContract(JevBaseModel):
    market_ticker: str
    event_cluster_id: str  # station+date+measurement (semantic; not ticker grouping)
    station: str  # human name
    station_id: str | None = None
    measurement: str  # "tmax" | "tmin"
    target_date: date | None = None
    units: str = "F"  # "F" | "C"
    threshold_op: str | None = None  # gt | ge | lt | le | range_in | range_out
    threshold_value: float | None = None
    range_low: float | None = None
    range_high: float | None = None
    obs_window_start_utc: datetime | None = None
    obs_window_end_utc: datetime | None = None
    local_timezone: str | None = None
    local_convention: str | None = None  # e.g. "local_civil_day"; None => ambiguous
    eligible: bool = False
    ineligible_reason: str | None = None


class QuoteQuality(JevBaseModel):
    market_probability: float | None = None
    market_confidence: float | None = None
    yes_bid: float | None = None
    yes_ask: float | None = None
    spread: float | None = None
    quote_timestamp: datetime | None = None
    quote_age_seconds: float | None = None
    probability_method: str | None = None  # "midpoint" | "last_trade" | None
    freshness_verified: bool = False
    status: str = "unknown"  # "ok" | reason code


class WeatherPriorResult(JevBaseModel):
    probability_yes: float | None = None
    favored_outcome: str | None = None  # "YES" | "NO"
    confidence: float | None = None
    method_version: str = "seasonal_reference_v1"
    station: str | None = None
    measurement: str | None = None
    historical_date_range: str | None = None
    valid_observation_count: int = 0
    distinct_year_count: int = 0
    source: str = "unknown"
    vintage: str | None = None
    temporal_status: str = "unknown"  # verified | retrospective_approximation | unknown
    reliability_flags: list[str] = Field(default_factory=list)
    coverage_ok: bool = False
    missing: bool = False
    retrospective_approximation: bool = True


class FeatureSnapshot(JevBaseModel):
    """OUTCOME-FREE mining input. No outcome/settlement/final-price field exists here."""

    snapshot_id: str
    event_cluster_id: str
    domain: str = "weather"
    as_of: datetime
    horizon_label: str  # "primary_24h" | "secondary_6h"

    contract: WeatherContract
    quote: QuoteQuality
    prior: WeatherPriorResult
    favored_outcomes_agree: bool | None = None

    difficulty_config_hash: str
    snapshot_policy_version: str


class DifficultyAnnotation(JevBaseModel):
    snapshot_id: str
    market_ticker: str = ""
    event_cluster_id: str
    domain: str = "weather"

    difficulty: str = "unassigned"  # easy | medium | hard | unassigned
    selection_status: str = "ineligible"  # candidate | approved | rejected | ineligible
    reason_codes: list[str] = Field(default_factory=list)
    reasoning_requirement: str = "unknown"  # background_prior | single_timely_signal | evidence_integration | unknown

    market_probability: float | None = None
    market_confidence: float | None = None
    market_probability_method: str | None = None
    market_quote_timestamp: datetime | None = None
    quote_quality_status: str = "unknown"

    prior_probability: float | None = None
    prior_confidence: float | None = None
    prior_method_version: str | None = None
    prior_temporal_status: str = "unknown"
    prior_coverage_summary: dict = Field(default_factory=dict)

    favored_outcomes_agree: bool | None = None

    horizon_label: str = ""
    as_of: datetime | None = None
    selected: bool = False  # one-per-event deterministic pick

    snapshot_policy_version: str = ""
    difficulty_config_hash: str = ""
    rubric_version: str = ""

    review_status: str = "none"  # none | pending | approved | rejected
    reviewer_id: str | None = None
    annotation_version: int = 1
    split: str | None = None


class ReviewPacket(JevBaseModel):
    """OUTCOME-FREE reviewer material: pre-event contract info + prior summary + quote quality
    + nomination reasons. No outcome, final price, settlement value, post-event text, or model
    prediction."""

    snapshot_id: str
    event_cluster_id: str
    domain: str = "weather"
    as_of: datetime
    horizon_label: str

    question: str
    rules: str | None = None
    station: str | None = None
    measurement: str | None = None
    target_date: date | None = None
    units: str = "F"
    threshold_description: str = ""

    permitted_evidence: list[str] = Field(default_factory=list)
    prior_summary: dict = Field(default_factory=dict)
    quote_quality: dict = Field(default_factory=dict)  # contemporaneous (as-of) quote only
    reason_codes: list[str] = Field(default_factory=list)
    nomination_reason: str = ""
    rubric_version: str = ""


class ReviewDecision(JevBaseModel):
    snapshot_id: str
    decision: str  # approved | rejected
    difficulty: str = "unassigned"  # easy | medium | hard | unassigned
    reasoning_requirement: str = "unknown"
    reviewer_id: str = "unknown"
    rubric_version: str = ""
    decided_at: datetime | None = None
    reason: str = ""
    adjudicated_by: str | None = None
