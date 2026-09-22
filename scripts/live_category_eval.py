"""One-off: honest per-category Jev eval on settled Kalshi markets, through the PROPER
snapshot renderer (threshold + date + rules in the state — no ad-hoc prompt).

For each series it takes independent settled events, builds a snapshot ~N days before
close, asks Jev BLIND (it does not see the price), and scores Brier + accuracy against the
revealed outcome — alongside the crowd's Brier at the same checkpoint. One Jev call/market.
Prints numbers only; fabricates nothing.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys
import urllib.request

BASE = "https://api.elections.kalshi.com/trade-api/v2"


def _load_env():
    p = os.path.join(os.path.dirname(__file__), "..", ".env")
    if os.path.exists(p):
        for line in open(p):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def get(url):
    with urllib.request.urlopen(url, timeout=20) as r:
        return json.load(r)


def _dollars(node):
    if not isinstance(node, dict):
        return None
    v = node.get("close_dollars")
    if v is None:
        v = node.get("close")
        if isinstance(v, (int, float)):
            v = v / 100.0
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def build_checkpoint(series, ticker, mkt, days_before=3):
    """One Snapshot ~days_before days before close, with a real market price."""
    from jevgym.models import MarketState, Outcome, PublicState, Snapshot
    from jevgym.util import utcnow

    res = (mkt.get("result") or "").lower()
    if res not in ("yes", "no"):
        return None
    y = 1 if res == "yes" else 0
    c = dt.datetime.fromisoformat(mkt["close_time"].replace("Z", "+00:00"))
    start = int((c - dt.timedelta(days=10)).timestamp())
    end = int(c.timestamp())
    url = f"{BASE}/series/{series}/markets/{ticker}/candlesticks?start_ts={start}&end_ts={end}&period_interval=1440"
    cs = get(url).get("candlesticks", [])
    priced = []
    for cd in cs:
        ya, yb, pr = _dollars(cd.get("yes_ask")), _dollars(cd.get("yes_bid")), _dollars(cd.get("price"))
        p = pr if pr is not None else (ya if ya is not None else yb)
        if p is None:
            continue
        ts = dt.datetime.fromtimestamp(cd["end_period_ts"], tz=dt.timezone.utc)
        priced.append((ts, max(0.0, min(1.0, p))))
    if not priced:
        return None
    target = c - dt.timedelta(days=days_before)
    ts, pm = min(priced, key=lambda x: abs((x[0] - target).total_seconds()))
    snap = Snapshot(
        snapshot_id=f"{ticker}-{ts.date()}",
        market_ticker=ticker,
        event_ticker=mkt.get("event_ticker", ticker),
        domain="markets",
        timestamp=ts,
        forecast_horizon=f"{days_before}d",
        public_state=PublicState(
            market_title=mkt.get("title") or ticker,
            rules_primary=mkt.get("rules_primary") or mkt.get("subtitle") or "",
        ),
        market_state=MarketState(p_market=pm, yes_bid=pm, yes_ask=pm),
        outcome=Outcome(resolved=True, y=y),
        source_provider="kalshi",
        source_endpoint="candlesticks",
        source_identifier=ticker,
        retrieved_at=utcnow(),
        available_at=ts,
    )
    return snap, pm, y


def _pick(series, settled, n, per_event=3):
    """Up to ``n`` settled markets, capping brackets-per-event so one month can't dominate
    the Brier (calibration tolerates correlated brackets; the arena P&L did not)."""
    counts, out, events = {}, [], set()
    for m in settled:
        ev = m.get("event_ticker", m["ticker"])
        if counts.get(ev, 0) >= per_event:
            continue
        counts[ev] = counts.get(ev, 0) + 1
        events.add(ev)
        out.append(m)
        if len(out) >= n:
            break
    return out, len(events)


def main():
    _load_env()
    from jevgym.config import get_settings
    from jevgym.providers import build_provider
    from jevgym.providers.base import decide_question
    from jevgym.snapshots.render import render

    settings = get_settings()
    jev = build_provider("jev", settings)

    series = sys.argv[1] if len(sys.argv) > 1 else "KXTORNADO"
    label = sys.argv[2] if len(sys.argv) > 2 else series
    n = int(sys.argv[3]) if len(sys.argv) > 3 else 10
    mk = get(f"{BASE}/markets?series_ticker={series}&status=settled&limit=80")["markets"]
    settled = [m for m in mk if (m.get("result") or "").lower() in ("yes", "no")]
    chosen, n_events = _pick(series, settled, n)

    rows = []
    for m in chosen:
        built = build_checkpoint(series, m["ticker"], m)
        if built is None:
            continue
        snap, pm, y = built
        cq = render(snap, reveal_market=False)  # BLIND — Jev never sees the price
        dr = decide_question(jev, cq).normalized()
        pj = float(dr.probabilities.get("YES", 0.5))
        rows.append((m["ticker"], y, pj, pm))

    if not rows:
        print(f"{label}: no scorable markets.")
        return
    jb = sum((pj - y) ** 2 for _t, y, pj, _pm in rows) / len(rows)
    cb = sum((pm - y) ** 2 for _t, y, _pj, pm in rows) / len(rows)
    ja = sum(1 for _t, y, pj, _pm in rows if (pj >= 0.5) == (y == 1)) / len(rows)
    ca = sum(1 for _t, y, _pj, pm in rows if (pm >= 0.5) == (y == 1)) / len(rows)
    print(f"== {label} ({series}) — BLIND Jev vs crowd, n={len(rows)} markets / {n_events} events ==")
    for t, y, pj, pm in rows:
        print(f"   {t:26s} y={y} jev={pj:.2f} mkt={pm:.2f}")
    print(f"\n   Jev   Brier={jb:.3f}  acc={ja*100:.0f}%")
    print(f"   Crowd Brier={cb:.3f}  acc={ca*100:.0f}%")
    print(f"   -> Jev {'beats' if jb < cb else 'trails'} crowd on Brier by {abs(jb-cb):.3f}")


if __name__ == "__main__":
    main()
