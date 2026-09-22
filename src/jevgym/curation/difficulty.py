"""Backward difficulty mining.

Historical odds NOMINATE candidates; difficulty is assigned only by review. For every
considered (market, horizon) we emit an annotation, including failures and missing-data cases,
so a rejected easy candidate never silently becomes hard. The mining input is outcome-free:
we read the contract, the contemporaneous quote at a pre-chosen timestamp, and an independent
prior. We never read the market result.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timedelta

from ..config import Settings
from ..util import sha256_str
from .config import DifficultyConfig
from .schemas import DifficultyAnnotation, FeatureSnapshot, QuoteQuality, WeatherContract
from .weather_contract import parse_weather_contract
from .weather_prior import SeasonalReferencePrior


def seeded_hash(seed: str, key: str) -> str:
    return sha256_str(f"{seed}|{key}")


def market_quote_at(points, as_of: datetime, config: DifficultyConfig) -> QuoteQuality:
    """Latest quality-controlled quote at or before ``as_of``. A candle whose interval ends
    after ``as_of`` (spans or postdates it) is not usable. Zero and one are valid, not null."""
    usable = [p for p in points if p.timestamp is not None and p.timestamp <= as_of]
    if not usable:
        return QuoteQuality(status="no_quote_before_snapshot")
    q = max(usable, key=lambda p: p.timestamp)
    age = (as_of - q.timestamp).total_seconds()
    bid, ask = q.yes_bid, q.yes_ask
    base = QuoteQuality(yes_bid=bid, yes_ask=ask, quote_timestamp=q.timestamp, quote_age_seconds=age)
    if bid is None or ask is None:  # explicit None check; 0/1 are valid values
        base.status = "missing_bid_or_ask"
        return base
    if not (0.0 <= bid <= 1.0 and 0.0 <= ask <= 1.0):
        base.status = "quote_out_of_range"
        return base
    if ask < bid:
        base.status = "crossed_quote"
        return base
    spread = ask - bid
    p = (bid + ask) / 2.0
    base.spread = spread
    base.market_probability = p
    base.market_confidence = max(p, 1.0 - p)
    base.probability_method = "midpoint"
    fresh = age <= float(config.mq("max_quote_age_seconds"))
    base.freshness_verified = fresh
    if spread > float(config.mq("max_yes_spread")):
        base.status = "wide_spread"
    elif age > float(config.mq("max_quote_age_seconds")):
        base.status = "stale_quote"
    elif config.mq("require_verified_quote_freshness") and not fresh:
        base.status = "unverified_freshness"
    else:
        base.status = "ok"
    return base


def _blank_annotation(m_ticker: str, contract: WeatherContract, config: DifficultyConfig, horizon_label: str) -> DifficultyAnnotation:
    return DifficultyAnnotation(
        snapshot_id="",
        market_ticker=m_ticker,
        event_cluster_id=contract.event_cluster_id,
        domain="weather",
        horizon_label=horizon_label,
        difficulty_config_hash=config.hash,
        snapshot_policy_version=config.snapshot_policy_version,
        rubric_version=config.rubric_version,
        annotation_version=config.annotation_version,
        reason_codes=[],
    )


def mine(settings: Settings, config: DifficultyConfig, obs_source) -> tuple[list[DifficultyAnnotation], list[FeatureSnapshot], dict]:
    from ..data.parse import load_markets, load_prices
    from ..snapshots.builder import domain_of

    markets = [m for m in load_markets(settings) if domain_of(m) == "weather"]
    prices: dict[str, list] = defaultdict(list)
    for p in load_prices(settings):
        prices[p.market_ticker].append(p)

    prior_engine = SeasonalReferencePrior(obs_source, config)
    annotations: list[DifficultyAnnotation] = []
    features: list[FeatureSnapshot] = []
    funnel: Counter = Counter()
    funnel["markets_weather"] = len(markets)
    nominated: dict[tuple, list] = defaultdict(list)  # (event, horizon) -> [(hashkey, idx)]

    for m in markets:
        contract = parse_weather_contract(m)
        for horizon_label, offset in config.horizons():
            funnel["considered"] += 1
            ann = _blank_annotation(m.ticker, contract, config, horizon_label)

            if not contract.eligible:
                ann.snapshot_id = seeded_hash("sid", f"{m.ticker}|{horizon_label}")[:12]
                ann.selection_status = "ineligible"
                ann.reason_codes = (contract.ineligible_reason or "ineligible").split(",")
                annotations.append(ann)
                funnel["ineligible_contract"] += 1
                continue

            as_of = contract.obs_window_start_utc - timedelta(hours=offset)
            ann.as_of = as_of
            ann.snapshot_id = seeded_hash("sid", f"{m.ticker}|{horizon_label}|{as_of.isoformat()}")[:12]

            if m.open_time is None or m.open_time > as_of:
                ann.selection_status = "ineligible"
                ann.reason_codes = ["market_not_open"]
                annotations.append(ann)
                funnel["market_not_open"] += 1
                continue
            funnel["timestamp_valid"] += 1

            quote = market_quote_at(prices.get(m.ticker, []), as_of, config)
            ann.market_probability = quote.market_probability
            ann.market_confidence = quote.market_confidence
            ann.market_probability_method = quote.probability_method
            ann.market_quote_timestamp = quote.quote_timestamp
            ann.quote_quality_status = quote.status
            if quote.status != "ok":
                ann.selection_status = "ineligible"
                ann.reason_codes = [quote.status]
                annotations.append(ann)
                funnel[f"quote_{quote.status}"] += 1
                continue
            funnel["quote_valid"] += 1

            prior = prior_engine.compute(contract)
            ann.prior_probability = prior.probability_yes
            ann.prior_confidence = prior.confidence
            ann.prior_method_version = prior.method_version
            ann.prior_temporal_status = prior.temporal_status
            ann.prior_coverage_summary = prior_engine.coverage_summary(prior)

            m_fav = "YES" if quote.market_probability >= 0.5 else "NO"
            agree = None if prior.favored_outcome is None else (m_fav == prior.favored_outcome)
            ann.favored_outcomes_agree = agree

            features.append(
                FeatureSnapshot(
                    snapshot_id=ann.snapshot_id,
                    event_cluster_id=contract.event_cluster_id,
                    as_of=as_of,
                    horizon_label=horizon_label,
                    contract=contract,
                    quote=quote,
                    prior=prior,
                    favored_outcomes_agree=agree,
                    difficulty_config_hash=config.hash,
                    snapshot_policy_version=config.snapshot_policy_version,
                )
            )

            if prior.missing:
                ann.selection_status = "ineligible"
                ann.reason_codes.append("missing_prior")
                annotations.append(ann)
                funnel["missing_prior"] += 1
                continue
            if not prior.coverage_ok:
                ann.selection_status = "ineligible"
                ann.reason_codes.append("prior_low_coverage")
                annotations.append(ann)
                funnel["prior_low_coverage"] += 1
                continue
            funnel["prior_covered"] += 1

            mc_ok = quote.market_confidence >= float(config.cand("min_market_confidence"))
            pc_ok = prior.confidence >= float(config.cand("min_prior_confidence"))
            if mc_ok:
                funnel["high_odds"] += 1

            idx = len(annotations)
            if mc_ok and pc_ok and agree:
                cohort = "strict" if (prior.temporal_status == "verified" and quote.freshness_verified) else "retrospective_approximation"
                ann.selection_status = "candidate"
                ann.reasoning_requirement = "background_prior"
                ann.reason_codes += ["easy_prior_candidate", f"cohort:{cohort}"]
                funnel["easy_candidate_aligned"] += 1
                funnel[f"easy_candidate_{cohort}"] += 1
                nominated[(contract.event_cluster_id, horizon_label)].append((seeded_hash(config.seed(), ann.snapshot_id), idx))
            else:
                ann.selection_status = "ineligible"
                if not mc_ok:
                    ann.reason_codes.append("market_conf_below_threshold")
                if not pc_ok:
                    ann.reason_codes.append("prior_conf_below_threshold")
                if mc_ok and pc_ok and agree is False:
                    ann.reason_codes.append("market_prior_disagree")
            annotations.append(ann)

    # Deterministic one-per-event selection (outcome-independent seeded hash). Keep all siblings.
    for (_event, _hz), lst in nominated.items():
        lst.sort(key=lambda x: x[0])
        for rank, (_hk, idx) in enumerate(lst):
            if config.one_per_event():
                annotations[idx].selected = rank == 0
                if rank > 0:
                    annotations[idx].reason_codes.append("sibling_not_selected")
            else:
                annotations[idx].selected = True
        if config.one_per_event() and lst:
            funnel["selected_easy"] += 1
        else:
            funnel["selected_easy"] += len(lst)

    return annotations, features, dict(funnel)
