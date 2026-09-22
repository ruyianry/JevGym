"""Selection funnel, coverage, and the human-readable difficulty report."""

from __future__ import annotations

from .config import DifficultyConfig
from .schemas import DifficultyAnnotation

FUNNEL_ORDER = [
    "markets_weather",
    "considered",
    "ineligible_contract",
    "market_not_open",
    "timestamp_valid",
    "quote_valid",
    "prior_covered",
    "high_odds",
    "easy_candidate_aligned",
    "easy_candidate_strict",
    "easy_candidate_retrospective_approximation",
    "selected_easy",
]


def selection_funnel(funnel: dict, annotations: list[DifficultyAnnotation]) -> dict:
    def _count(pred) -> int:
        return sum(1 for a in annotations if pred(a))

    exclusions = {
        k: v
        for k, v in funnel.items()
        if k.startswith("quote_") or k in ("ineligible_contract", "market_not_open", "missing_prior", "prior_low_coverage")
    }
    cands = [a for a in annotations if a.selection_status == "candidate"]
    return {
        "stages": {k: funnel.get(k, 0) for k in FUNNEL_ORDER if k in funnel},
        "exclusions": exclusions,
        "candidate_favored_yes": sum(1 for a in cands if a.market_probability is not None and a.market_probability >= 0.5),
        "candidate_favored_no": sum(1 for a in cands if a.market_probability is not None and a.market_probability < 0.5),
        "selected_candidates": _count(lambda a: a.selection_status == "candidate" and a.selected),
        "reviewed_easy": _count(lambda a: a.difficulty == "easy" and a.review_status == "approved"),
        "missing_prior": funnel.get("missing_prior", 0),
        "annotations_total": len(annotations),
    }


def outcome_audit(annotations, features, result_by_ticker: dict, *, selected_only: bool = True) -> dict:
    """POST-SELECTION reporting only. Joins realized outcomes to the curated easy candidates and
    compares the contemporaneous market against the independent prior (as a baseline). Outcomes
    are NOT used to mine or review; this runs after selection is frozen. Upsets are retained.
    """
    feat = {f.snapshot_id: f for f in features}
    rows = []
    for a in annotations:
        if a.selection_status != "candidate":
            continue
        if selected_only and not a.selected:
            continue
        f = feat.get(a.snapshot_id)
        if f is None:
            continue
        y = result_by_ticker.get(f.contract.market_ticker)
        pm, pp = f.quote.market_probability, f.prior.probability_yes
        if y is None or pm is None or pp is None:
            continue
        rows.append(
            {
                "snapshot_id": a.snapshot_id,
                "market_ticker": f.contract.market_ticker,
                "horizon": a.horizon_label,
                "y": y,
                "p_market": pm,
                "p_prior": pp,
                "market_correct": (pm >= 0.5) == (y == 1),
                "prior_correct": (pp >= 0.5) == (y == 1),
                "brier_market": (pm - y) ** 2,
                "brier_prior": (pp - y) ** 2,
            }
        )
    n = len(rows)
    if n == 0:
        return {"n": 0, "note": "no outcome-joined candidates"}
    mkt_brier = sum(r["brier_market"] for r in rows) / n
    pr_brier = sum(r["brier_prior"] for r in rows) / n
    mkt_acc = sum(r["market_correct"] for r in rows) / n
    pr_acc = sum(r["prior_correct"] for r in rows) / n
    return {
        "n": n,
        "market": {"brier": mkt_brier, "accuracy": mkt_acc},
        "independent_prior": {"brier": pr_brier, "accuracy": pr_acc},
        "prior_outpaced_market_brier": pr_brier < mkt_brier,
        "prior_outpaced_market_accuracy": pr_acc > mkt_acc,
        "rows": rows,
    }


def render_report(funnel_obj: dict, annotations: list[DifficultyAnnotation], config: DifficultyConfig) -> str:
    lines = ["# JevGym difficulty report (weather)", ""]
    lines.append(f"config: `{config.version}`  hash: `{config.hash}`  rubric: `{config.rubric_version}`")
    lines.append("")
    lines.append("## Selection funnel")
    lines.append("")
    lines.append("| stage | count |")
    lines.append("|---|---:|")
    for k, v in funnel_obj["stages"].items():
        lines.append(f"| {k} | {v} |")
    lines.append(f"| selected candidates | {funnel_obj['selected_candidates']} |")
    lines.append(f"| reviewed easy | {funnel_obj['reviewed_easy']} |")
    lines.append("")
    lines.append("## Exclusions")
    lines.append("")
    lines.append("| reason | count |")
    lines.append("|---|---:|")
    for k, v in sorted(funnel_obj["exclusions"].items()):
        lines.append(f"| {k} | {v} |")
    lines.append("")
    lines.append("## Balance and provenance")
    lines.append("")
    lines.append(f"- candidate favored YES: {funnel_obj['candidate_favored_yes']}")
    lines.append(f"- candidate favored NO: {funnel_obj['candidate_favored_no']}")
    lines.append(f"- missing prior: {funnel_obj['missing_prior']}")
    lines.append("")
    lines.append("## Limitations")
    lines.append("")
    lines.append(
        "- Offline fixtures cannot verify historical availability, so priors are marked "
        "`retrospective_approximation` and are excluded from the strict temporal subset."
    )
    lines.append("- Odds nominate candidates; difficulty is assigned only by outcome-blind human review.")
    lines.append("- The odds-filtered easy cohort is intentionally selective and is not representative of all markets.")
    lines.append("- Thresholds are initial choices; tune on development data and report sensitivity.")
    return "\n".join(lines)
