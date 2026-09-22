<div align="center">

# 🏟️ JevGym

**Measuring the Jev-series models' capacity — a timestamped benchmark + trading arena for real-world probabilistic forecasting.**

[![status](https://img.shields.io/badge/status-expanding-success.svg)](#-components--pick-one-to-dive-in)
[![kalshi](https://img.shields.io/badge/component-Kalshi_live-success.svg)](KALSHIJEV.md)
[![demo](https://img.shields.io/badge/demo-can_you_beat_Jev%3F-6d67ff.svg)](beat-jev.html)

*Can the Jev-series decision models forecast — and profitably trade — real-world events? Reward is the headline metric 🤑.*

</div>

> **Why prediction markets?** They quote a **direct probability** for every event — continuously
> updated and **directly comparable to a Jev model's** output (probability in, probability out).

JevGym is built from many data sources, each its own **subset** with its own leaderboard.
We're **expanding the dataset fast** — new sources and categories land continuously.

## 🧩 Components — pick one to dive in

| Component | Status | Explore |
| --- | --- | --- |
| **Kalshi** — the `KalshiJev` subset | ✅ **live** | **[→ Kalshi report](KALSHIJEV.md)** · [site](kalshi.html) |
| Polymarket | 🔜 soon | normalizes into the same schema — slots straight in |
| More sources | 🔜 expanding | added continuously |

**Kalshi is live now** — Jev outperforms the market on the clearer markets and **trades them at
a profit (+11.8% average return per contract)**, across **three categories** (weather · crypto ·
the Fed) with more on the way. Dive in → **[KALSHIJEV.md](KALSHIJEV.md)**.

🎮 **[Can you beat Jev?](beat-jev.html)** — a slider game on six resolved questions, one per category.

## 🌐 The site

Deployable, self-contained pages (GitHub Pages, no build step):
[`index.html`](index.html) (this overview) → [`kalshi.html`](kalshi.html) (the Kalshi report) →
[`beat-jev.html`](beat-jev.html) (the game).

## ⚡ Run it (offline)

The CLI is **`jevgym`** — the engine that runs it all (benchmark, arena, and dataset build).

```bash
pip install -e ".[dev,hf]"
jevgym ingest kalshi --from-fixtures
jevgym parse && jevgym build-snapshots && jevgym validate
jevgym eval --agents kalshi_market,mock --track both
```

Set a key in `.env` to benchmark Jev live: `jevgym eval --agents kalshi_market,jev --track both`.

## 🤝 Seeking collaborators

Active research, growing fast. We'd love to work with research groups (calibration, agentic
forecasting), teams who want a System-One model benchmarked, and quantitative / hedge-fund
partners interested in working together.

Reach out: **jevarena@proton.me**
