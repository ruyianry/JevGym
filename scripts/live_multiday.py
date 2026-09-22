"""One-off: a small REAL multi-day arena run on settled Kalshi markets with live Jev.

Builds genuine Snapshot objects (resolution criteria in the state, so Jev gets the
threshold+date — no ad-hoc rendering) at each daily checkpoint over the final week, then
runs the real RepeatedBetMode. Budget-capped. Prints numbers only; fabricates nothing.
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
        if isinstance(v, (int, float)):  # cents form
            v = v / 100.0
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def build_snaps(series, ticker, mkt, days=7, max_ckpts=5):
    from jevgym.models import MarketState, Outcome, PublicState, Snapshot
    from jevgym.util import utcnow

    res = (mkt.get("result") or "").lower()
    if res not in ("yes", "no"):
        return []
    y = 1 if res == "yes" else 0
    c = dt.datetime.fromisoformat(mkt["close_time"].replace("Z", "+00:00"))
    start = int((c - dt.timedelta(days=days)).timestamp())
    end = int(c.timestamp())
    url = f"{BASE}/series/{series}/markets/{ticker}/candlesticks?start_ts={start}&end_ts={end}&period_interval=1440"
    cs = get(url).get("candlesticks", [])
    title = mkt.get("title") or ticker
    rules = mkt.get("rules_primary") or mkt.get("subtitle") or ""
    snaps = []
    for cd in cs:
        ya = _dollars(cd.get("yes_ask"))
        yb = _dollars(cd.get("yes_bid"))
        pr = _dollars(cd.get("price"))
        if ya is None and pr is not None:
            ya = pr
        if yb is None and pr is not None:
            yb = pr
        if ya is None or yb is None:
            continue
        ts = dt.datetime.fromtimestamp(cd["end_period_ts"], tz=dt.timezone.utc)
        pm = max(0.0, min(1.0, (ya + yb) / 2))
        snaps.append(
            Snapshot(
                snapshot_id=f"{ticker}-{ts.date()}",
                market_ticker=ticker,
                event_ticker=mkt.get("event_ticker", ticker),
                domain="weather",
                timestamp=ts,
                forecast_horizon=f"{(c - ts).days}d",
                public_state=PublicState(market_title=title, rules_primary=rules),
                market_state=MarketState(p_market=pm, yes_bid=yb, yes_ask=ya),
                outcome=Outcome(resolved=True, y=y),
                source_provider="kalshi",
                source_endpoint="candlesticks",
                source_identifier=ticker,
                retrieved_at=utcnow(),
                available_at=ts,
            )
        )
    return snaps[-max_ckpts:]


class CachedJev:
    """Wraps forecasts already fetched from live Jev, keyed by snapshot_id, so the arena can
    be re-run across edge thresholds / modes without spending any extra API calls."""

    name = "jev"
    model_id = "jev"

    def __init__(self, probs):
        self._p = probs

    def predict(self, snapshot):
        from jevgym.models import DecisionResult

        p = self._p[snapshot.snapshot_id]
        return DecisionResult(probabilities={"YES": p, "NO": 1 - p}, provider="jev", model_id="jev")


def _pick_meaningful(series, settled, n_events):
    """One bracket per distinct event (month), preferring a genuinely-uncertain strike
    (entry mid-price nearest 0.5) so we test forecasting, not decided penny tails."""
    by_event = {}
    for m in settled:
        by_event.setdefault(m.get("event_ticker", m["ticker"]), []).append(m)
    chosen = []
    for _ev, ms in by_event.items():
        best, best_snaps, best_dist = None, None, 9.9
        for m in ms:
            s = build_snaps(series, m["ticker"], m)
            if len(s) < 3:
                continue
            entry = s[0].market_state.p_market
            dist = abs(entry - 0.5)
            if dist < best_dist:
                best, best_snaps, best_dist = m, s, dist
        if best is not None:
            chosen.append((best, best_snaps))
        if len(chosen) >= n_events:
            break
    return chosen


def main():
    _load_env()
    from jevgym.config import get_settings
    from jevgym.eval.arena import forecast_p_yes, run_arena
    from jevgym.providers import build_provider

    settings = get_settings()
    try:
        jev = build_provider("jev", settings)
    except Exception as e:  # noqa: BLE001
        print("Jev provider unavailable:", e)
        sys.exit(2)

    series = sys.argv[1] if len(sys.argv) > 1 else "KXTORNADO"
    n_events = int(sys.argv[2]) if len(sys.argv) > 2 else 6
    mk = get(f"{BASE}/markets?series_ticker={series}&status=settled&limit=60")["markets"]
    settled = [m for m in mk if (m.get("result") or "").lower() in ("yes", "no")]
    chosen = _pick_meaningful(series, settled, n_events)
    if not chosen:
        print(f"No {series} markets with >=3 daily checkpoints.")
        sys.exit(3)

    all_snaps = [s for _m, snaps in chosen for s in snaps]
    print(f"== {series}: {len(chosen)} independent events, {len(all_snaps)} checkpoints (live Jev calls) ==")
    probs = {}
    for m, snaps in chosen:
        entry = snaps[0].market_state.p_market
        for s in snaps:
            probs[s.snapshot_id] = forecast_p_yes(jev, s)  # the only live calls
        pj = probs[snaps[0].snapshot_id]
        print(f"   {m['ticker']:24s} result={m['result']:>3} ckpts={len(snaps)} entry_mkt={entry:.2f} jev@entry={pj:.2f}")

    cached = CachedJev(probs)
    print("\nMode        edge≥   markets  contracts   total$    ret/contract")
    for mode in ("one_shot", "repeated"):
        for thr in (0.0, 0.03, 0.05, 0.10):
            rs = run_arena(cached, all_snaps, mode=mode, edge_threshold=thr, max_days=7)
            tc = sum(r.contracts for r in rs)
            tr = sum(r.reward for r in rs)
            ent = sum(1 for r in rs if r.entered)
            rpc = (tr / tc * 100) if tc else 0.0
            label = "multi-day" if mode == "repeated" else "one-shot "
            print(f"{label}  {thr:5.2f}   {ent:5d}    {tc:7.0f}   {tr:+7.3f}    {rpc:+6.1f}%")


if __name__ == "__main__":
    main()
