"""The frozen renderer: turns a snapshot into the semantically-identical question every
model receives. The renderer alone controls what is revealed, so a single stored snapshot
serves both the blind and market-aware tracks (no dataset duplication).

Do NOT tune this per-model in the primary benchmark — semantic identity across models is the
whole point.
"""

from __future__ import annotations

from ..models import ACTION_CANDIDATES, ActionType, CanonicalQuestion, Snapshot

FORECAST_QUESTION = "Which outcome will this contract ultimately resolve to?"
YES_DESC = "The contract ultimately resolves YES."
NO_DESC = "The contract ultimately resolves NO."

ACTION_QUESTION = (
    "You may buy one YES or one NO contract now at the listed prices, or wait. You can still "
    "act at a later timestep any time before the market resolves. Which action is best right now?"
)


def _fmt_evidence(snapshot: Snapshot) -> str:
    items = snapshot.public_state.evidence
    if not items:
        return "(no external evidence available at this timestamp)"
    lines = []
    for e in items:
        when = e.available_at.strftime("%Y-%m-%d")
        p = e.payload if isinstance(e.payload, dict) else {}
        if e.evidence_type == "macro_indicator":
            lines.append(
                f"- [{when}] {p.get('series_id')} {p.get('title', '')} — "
                f"{p.get('period')}: {p.get('value')} {p.get('units', '')}".rstrip()
            )
        elif e.evidence_type == "prior_decisions":
            recent = p.get("recent", [])
            hist = "; ".join(
                f"{d.get('title')} → {str(d.get('result') or '').upper()} ({d.get('settled')})"
                for d in recent
            )
            lines.append(
                f"- [{when}] Prior decisions in {p.get('series')} "
                f"({p.get('n_prior')} settled, YES rate {p.get('yes_rate')}): {hist}"
            )
        else:
            lines.append(f"- [{when}] {e.evidence_type}: {p}")
    return "\n".join(lines)


def _render_state(snapshot: Snapshot, reveal_market: bool) -> str:
    ps = snapshot.public_state
    rules = ps.rules_primary or "(no resolution criteria provided)"
    if ps.rules_secondary:
        rules = f"{rules}\n{ps.rules_secondary}"

    blocks = [
        "STATE",
        "-----",
        f"Historical timestamp: {snapshot.timestamp.isoformat()}",
        "",
        "Market:",
        ps.market_title,
        "",
        "Resolution criteria:",
        rules,
        "",
        "Information available at this timestamp:",
        _fmt_evidence(snapshot),
    ]

    if reveal_market and snapshot.market_state.p_market is not None:
        p = snapshot.market_state.p_market
        blocks += [
            "",
            "Contemporaneous Kalshi market probability:",
            f"YES: {p:.3f}",
            f"NO: {1.0 - p:.3f}",
        ]
    return "\n".join(blocks)


def render(snapshot: Snapshot, reveal_market: bool = False) -> CanonicalQuestion:
    """Frozen forecasting question. ``reveal_market`` toggles blind vs. market-aware."""
    return CanonicalQuestion(
        state=_render_state(snapshot, reveal_market),
        question=FORECAST_QUESTION,
        candidates=list(snapshot.candidates),
        candidate_descriptions={"YES": YES_DESC, "NO": NO_DESC},
        kind="choice",
        as_of=snapshot.timestamp,
    )


def render_action(snapshot: Snapshot) -> CanonicalQuestion:
    """Frozen arena action question (always market-aware — you need prices to trade)."""
    ms = snapshot.market_state
    yes_ask = ms.yes_ask if ms.yes_ask is not None else ms.p_market
    no_ask = (1.0 - ms.yes_bid) if ms.yes_bid is not None else (
        1.0 - ms.p_market if ms.p_market is not None else None
    )
    state = _render_state(snapshot, reveal_market=True)
    price_lines = ["", "Current tradable prices (cost to buy one contract, $):"]
    price_lines.append(f"YES ask: {yes_ask:.3f}" if yes_ask is not None else "YES ask: n/a")
    price_lines.append(f"NO ask: {no_ask:.3f}" if no_ask is not None else "NO ask: n/a")
    state = state + "\n" + "\n".join(price_lines)

    return CanonicalQuestion(
        state=state,
        question=ACTION_QUESTION,
        candidates=list(ACTION_CANDIDATES),
        candidate_descriptions={
            ActionType.BET_YES.value: "Buy one YES contract now at the current YES ask.",
            ActionType.BET_NO.value: "Buy one NO contract now at the current NO ask.",
            ActionType.WAIT.value: "Do not trade now; wait for a later timestep.",
        },
        kind="choice",
        as_of=snapshot.timestamp,
    )
