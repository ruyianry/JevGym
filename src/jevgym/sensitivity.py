"""Sensitive-content classification and difficulty scoring.

Some domains (politics, war/conflict, elections) are sensitive to redistribute or to imply
positions on. By default they are quarantined out of the published dataset and kept in a
separate local location; opt back in explicitly.

Difficulty is a market-implied property of a checkpoint (how much of a toss-up it was),
computed from the crowd probability and independent of any model or the outcome.
"""

from __future__ import annotations

SENSITIVE_DOMAINS = {"politics", "geopolitics", "war", "conflict", "elections"}

# Substrings that flag war/conflict/electoral content regardless of the venue's category.
SENSITIVE_KEYWORDS = (
    "war", "nuclear", "military", "invasion", "invade", "attack", "airstrike", "missile",
    "coup", "assassinat", "ceasefire", "troops", "conflict", "hostage", "genocide",
    "election", "president", "prime minister", "referendum",
)


def is_sensitive(domain: str | None, *texts: str | None) -> bool:
    if domain and domain.strip().lower() in SENSITIVE_DOMAINS:
        return True
    blob = " ".join(t for t in texts if t).lower()
    return any(k in blob for k in SENSITIVE_KEYWORDS)


def difficulty_from_p(p_market: float | None, *, easy_conf: float = 0.35, hard_conf: float = 0.15) -> str:
    """Bucket a checkpoint by market-implied uncertainty.

    conf = |p - 0.5|: a near-0/1 price is an easy call, a near-coin-flip is hard.
    """
    if p_market is None:
        return "unknown"
    conf = abs(float(p_market) - 0.5)
    if conf >= easy_conf:
        return "easy"
    if conf <= hard_conf:
        return "hard"
    return "medium"
