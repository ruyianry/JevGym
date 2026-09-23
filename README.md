<div align="center">

# 🏟️ JevGym

**A timestamped benchmark and trading arena for real-world probabilistic forecasting.**

[![status](https://img.shields.io/badge/status-expanding-success.svg)](#-whats-inside)
[![kalshi](https://img.shields.io/badge/component-Kalshi_live-success.svg)](KALSHIJEV.md)
[![site](https://img.shields.io/badge/site-ruyianry.github.io%2FJevGym-4f46e5.svg)](https://ruyianry.github.io/JevGym/)
[![demo](https://img.shields.io/badge/demo-can_you_beat_Jev%3F-6d67ff.svg)](https://ruyianry.github.io/JevGym/beat-jev.html)

*Can a decision model forecast — and profitably trade — real-world events it has never seen?*

</div>

JevGym replays **real, already-resolved prediction markets** as a decision task: a model sees only
the information available at a past moment, commits to a probability, and is then scored against
what actually happened. Because a prediction market quotes a **direct probability** for every
event, the crowd becomes a strong, continuously-updated baseline — directly comparable to a
model's output (probability in, probability out). **Realized P&L in the trading arena is the
headline metric**; calibration (Brier, log-loss, ECE) is the check.

It measures the **Jev-series** ("System One") decision models, but the arena is open to any
model — official Jev, open Jev-wire servers, a fine-tuned Qwen, or a plain LLM — over the same
markets, the same frozen prompt, and the same scoring.

## ✨ Why it's different

- **No leakage, by construction.** Every piece of evidence carries a public-availability
  timestamp and `available_at ≤ snapshot.timestamp` is enforced; agents that search the web are
  bounded to the same moment via the Internet Archive. Models forecast the past *as if it were
  the present*.
- **Reward, not just accuracy.** A sequential arena turns each forecast into a trade against the
  contemporaneous market price and scores realized P&L — the thing that actually matters.
- **The crowd is a baseline, never the oracle.** The oracle is the resolved outcome. The market
  price is just a strong reference to beat.
- **One dataset, many uses.** The same leakage-safe snapshots power the benchmark, the arena,
  and an interactive site.

## 📊 What the numbers say (Kalshi, live)

On real resolved Kalshi markets, official **Jev is profitable in the arena — +11.8% average
return per contract** on the clearer markets, across **weather · crypto · the Fed**, and it
carries real signal *before a contract is even priced*. Near resolution the crowd is hard to
out-calibrate — which is exactly where the headroom is. Full method,
per-difficulty tables, and honest caveats: **[KALSHIJEV.md](KALSHIJEV.md)**.

🎮 **[Can you beat Jev?](https://ruyianry.github.io/JevGym/beat-jev.html)** — a slider game on
resolved questions, one per category. 🧪 **[Evaluate Jev yourself](https://ruyianry.github.io/JevGym/evaluate.html)**
— bring your own key, ask any question, grade the answer.

## 🧩 What's inside

| Component | Status | Explore |
| --- | --- | --- |
| **Kalshi** — the `KalshiJev` subset | ✅ **live** | **[→ Kalshi report](KALSHIJEV.md)** |
| Polymarket | 🔜 soon | normalizes into the same schema |
| More sources & categories | 🔜 expanding | added continuously |

Coverage spans weather, crypto, and economics/the Fed today, with more categories flowing in.
Harder markets are **enriched with extra context** a model can leverage — macro-economic trends
and the series' own prior decisions — all timestamped and leakage-safe.

## ⚡ Quickstart (runs offline, no keys)

The CLI is **`jevgym`** — benchmark, arena, and dataset build in one tool.

```bash
pip install -e ".[dev,hf]"
jevgym ingest kalshi --from-fixtures        # or a live pull (public reads need no auth)
jevgym parse && jevgym build-snapshots && jevgym validate
jevgym eval --agents kalshi_market,mock --track both
```

**Bring your own data.** The repo ships code, not data. Pull a live copy from the public APIs for
your personal, non-commercial use — the script acknowledges each source's terms, then fetches and
builds the snapshots:

```bash
python scripts/pull_data.py --i-agree     # your own copy → ./data → snapshots (personal, non-commercial)
```

Benchmark a real model by pointing the arena at it (key in `.env`):

```bash
jevgym eval --agents kalshi_market,jev --track both      # official Jev
```

## 🏋️ A fine-tuned Jev outperforms the market

A fine-tuned open Jev, run blind, **out-forecasts the crowd on weather** (83% vs 59% accuracy)
and trades it at **+14.8% per contract**. See the
[Kalshi report](https://ruyianry.github.io/JevGym/kalshi.html).

## ⚖️ Data, licensing & disclaimer

JevGym is independent research, **not affiliated** with Kalshi, Polymarket, or TypeSafe. **The
project ships code only — it does not include or redistribute any market operator's data.** You
fetch data yourself, for your own personal, non-commercial use, and are responsible for complying
with each source's terms — in particular **Kalshi's Data Terms of Use** (personal, non-commercial
access; no ML/AI training on, or redistribution of, Kalshi Data without Kalshi's prior written
consent). This is **not financial advice**. See [DISCLAIMER.md](DISCLAIMER.md); the code is
source-available under a research / non-commercial [LICENSE](LICENSE).

## 🤝 Collaborate

We're keen to work with research groups (calibration, agentic forecasting), teams who want a
System-One model benchmarked, and quantitative partners. Reach out: **jevarena@proton.me**
