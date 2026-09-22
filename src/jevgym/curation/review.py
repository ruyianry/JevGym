"""Outcome-blind human review. Packets expose only pre-event contract info, the prior summary,
and quote-quality — never outcomes, final prices, settlement, or model predictions. Only
reviewed records that meet the rubric receive a difficulty label.
"""

from __future__ import annotations

from .schemas import DifficultyAnnotation, FeatureSnapshot, ReviewDecision, ReviewPacket

RUBRIC_QUESTIONS = [
    "Is the contract clear and its window genuinely pre-event?",
    "Is the favored direction explainable mainly by ordinary location/season knowledge?",
    "Does the explanation avoid a current forecast, obscure fact, or specialized multi-step inference?",
    "Is the certainty merely an artifact of many implausible sibling ranges, and is that accounted for?",
]


def _threshold_description(c) -> str:
    if c.threshold_op == "range_in":
        return f"{c.measurement} in [{c.range_low}, {c.range_high}] {c.units}"
    sym = {"gt": ">", "ge": ">=", "lt": "<", "le": "<="}.get(c.threshold_op, c.threshold_op or "?")
    return f"{c.measurement} {sym} {c.threshold_value} {c.units}"


def build_review_packets(
    annotations: list[DifficultyAnnotation], features: list[FeatureSnapshot], *, rubric_version: str, selected_only: bool = True
) -> list[ReviewPacket]:
    feat = {f.snapshot_id: f for f in features}
    packets: list[ReviewPacket] = []
    for ann in annotations:
        if ann.selection_status != "candidate":
            continue
        if selected_only and not ann.selected:
            continue
        f = feat.get(ann.snapshot_id)
        if f is None:
            continue
        c, prior, quote = f.contract, f.prior, f.quote
        packets.append(
            ReviewPacket(
                snapshot_id=ann.snapshot_id,
                event_cluster_id=ann.event_cluster_id,
                as_of=f.as_of,
                horizon_label=f.horizon_label,
                question=c.market_ticker,
                rules=None,  # keep the packet minimal + pre-event; full rules available on request
                station=c.station,
                measurement=c.measurement,
                target_date=c.target_date,
                units=c.units,
                threshold_description=_threshold_description(c),
                permitted_evidence=["contract_question", "rules", "station", "measurement", "target_date", "snapshot_timestamp"],
                prior_summary={
                    "probability_yes": prior.probability_yes,
                    "favored_outcome": prior.favored_outcome,
                    "confidence": prior.confidence,
                    "valid_observations": prior.valid_observation_count,
                    "distinct_years": prior.distinct_year_count,
                    "historical_date_range": prior.historical_date_range,
                    "temporal_status": prior.temporal_status,
                },
                quote_quality={
                    "market_confidence": quote.market_confidence,
                    "spread": quote.spread,
                    "quote_age_seconds": quote.quote_age_seconds,
                    "method": quote.probability_method,
                    "status": quote.status,
                },
                reason_codes=list(ann.reason_codes),
                nomination_reason="odds+prior aligned high-confidence (pending common-sense review)",
                rubric_version=rubric_version,
            )
        )
    return packets


def apply_decisions(annotations: list[DifficultyAnnotation], decisions: list[ReviewDecision]) -> int:
    by_id = {d.snapshot_id: d for d in decisions}
    updated = 0
    for ann in annotations:
        d = by_id.get(ann.snapshot_id)
        if d is None:
            continue
        ann.review_status = d.decision
        ann.reviewer_id = d.reviewer_id
        if d.rubric_version:
            ann.rubric_version = d.rubric_version
        if d.decision == "approved" and d.difficulty in ("easy", "medium", "hard"):
            ann.difficulty = d.difficulty
            ann.selection_status = "approved"
            if d.reasoning_requirement and d.reasoning_requirement != "unknown":
                ann.reasoning_requirement = d.reasoning_requirement
        elif d.decision == "rejected":
            ann.selection_status = "rejected"  # difficulty stays unassigned
        updated += 1
    return updated
