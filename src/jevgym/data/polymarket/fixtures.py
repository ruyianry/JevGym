"""Deterministic synthetic Polymarket demo data (2026 events) for offline runs.

Themed on genuinely post-cutoff 2026 events (an Iran nuclear-deal question, a Bitcoin price
question) so the knowledge-cutoff filter has something to keep for small/older models. Not
real Polymarket data. Prices are in probability units [0, 1] (Polymarket convention).
"""

from __future__ import annotations

import json
import math
from datetime import datetime, timedelta, timezone

from ...util import to_unix

_UTC = timezone.utc


def _history(start: datetime, end: datetime, p_start: float, p_end: float) -> list[dict]:
    days = max(1, (end - start).days)
    out = []
    for i in range(days + 1):
        t = start + timedelta(days=i)
        frac = i / days
        p = p_start + (p_end - p_start) * frac + 0.03 * math.sin(i * 0.6)
        out.append({"t": to_unix(t), "p": round(min(0.98, max(0.02, p)), 4)})
    return out


def _market(condition_id, slug, question, description, category, start, end, result, tokens) -> dict:
    yes, no = ("1", "0") if result == "yes" else ("0", "1")
    return {
        "conditionId": condition_id,
        "slug": slug,
        "question": question,
        "description": description,
        "category": category,
        "outcomes": json.dumps(["Yes", "No"]),
        "outcomePrices": json.dumps([yes, no]),
        "clobTokenIds": json.dumps(tokens),
        "closed": True,
        "active": False,
        "umaResolutionStatus": "resolved",
        "createdAt": (start - timedelta(days=1)).isoformat(),
        "startDate": start.isoformat(),
        "endDate": end.isoformat(),
        "volume": 1_250_000,
        "liquidity": 80_000,
    }


_SPECS = [
    dict(
        condition_id="0xiran-nuclear-2026",
        slug="us-iran-nuclear-deal-2026",
        question="Will the US and Iran reach a nuclear deal by June 30, 2026?",
        description="Resolves YES if a formal US-Iran nuclear agreement is announced on or before 2026-06-30.",
        category="Politics",
        start=datetime(2026, 1, 15, tzinfo=_UTC),
        end=datetime(2026, 6, 30, tzinfo=_UTC),
        result="no",
        tokens=["tok-iran-yes", "tok-iran-no"],
        path=(0.35, 0.05),
    ),
    dict(
        condition_id="0xbtc-150k-2026",
        slug="bitcoin-150k-by-july-2026",
        question="Will Bitcoin exceed $150,000 by July 1, 2026?",
        description="Resolves YES if the price of Bitcoin exceeds $150,000 at any point on or before 2026-07-01.",
        category="Crypto",
        start=datetime(2026, 1, 5, tzinfo=_UTC),
        end=datetime(2026, 5, 10, tzinfo=_UTC),
        result="yes",
        tokens=["tok-btc-yes", "tok-btc-no"],
        path=(0.45, 0.90),
    ),
]


def build_polymarket_demo_raw() -> dict:
    markets = []
    prices = {}
    for s in _SPECS:
        markets.append(
            _market(
                s["condition_id"], s["slug"], s["question"], s["description"], s["category"],
                s["start"], s["end"], s["result"], s["tokens"],
            )
        )
        prices[s["condition_id"]] = {
            "condition_id": s["condition_id"],
            "token_id": s["tokens"][0],  # YES token
            "interval_label": "1d",
            "history": _history(s["start"], s["end"], s["path"][0], s["path"][1]),
        }
    return {"markets": markets, "prices": prices}
