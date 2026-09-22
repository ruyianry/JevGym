<div align="center">

# 📊 KalshiJev — the Kalshi report

**The Kalshi component of [JevGym](README.md) — Jev vs. the market on real resolved markets.**

[![status](https://img.shields.io/badge/status-preliminary-orange.svg)](#status)
[![categories](https://img.shields.io/badge/categories-3_live_·_more_soon-success.svg)](#categories)
[![demo](https://img.shields.io/badge/demo-can_you_beat_Jev%3F-6d67ff.svg)](beat-jev.html)

*Reward is the headline metric 🤑 — closer-to-truth-than-the-market means real profit. We do not assume Jev wins.*

</div>

> Central question: **How well can the Jev-series "System One" decision models forecast — and
> profitably trade — real-world events?** The arena also supports other System-One models;
> results coming soon.

> **Why Kalshi first?** Its markets quote a **direct probability** for every event — continuously
> updated and **directly comparable to Jev's** probabilistic output (probability in, probability
> out). JevGym isn't limited to Kalshi; the benchmark will be **populated from many sources**.
> Kalshi is simply the cleanest first case study.

JevGym replays historical prediction markets from **[Kalshi](https://kalshi.com) and
[Polymarket](https://polymarket.com)** (normalized into one schema). At each historical
checkpoint a decision model sees only the information available *at that time* and must
forecast (and, in the arena, *trade*) the eventual outcome. Kalshi supplies three
distinct signals that we keep strictly separate:

| Signal | Symbol | Role |
| --- | --- | --- |
| Contemporaneous crowd probability | `p_K(t)` | **baseline** (`kalshi_market`) — *not* an oracle |
| Historical market trajectory | candlesticks | replay state + tradable prices |
| Eventual resolved outcome | `Y` | the **true oracle** (label) |

Official **Jev** (TypeSafe AI's System One model) is the focus. The arena is open to other
System-One models — measured on the same markets, with **results coming soon**. **We do not
assume Jev wins the market, either.**

> ⚠️ This is **preliminary work** — a foundation designed to grow. Interfaces favor
> extension (new models, domains, arena modes, evidence sources = one small adapter each).

---

## Why bother — readjusting the market

A prediction-market price is just the crowd's probability that something happens. Sometimes the
crowd is off. If your model can put a number **closer to the truth than the price**, it can help
**readjust the market** toward reality — that's the point (not extracting arbitrage, but
correcting the price).

So JevGym's headline metric isn't accuracy — it's **reward**: how much a model would move the
price toward the truth (its edge vs the crowd, held to resolution). A model that's merely accurate
is nice; a model that's accurate **where the crowd is wrong** is the one that moves prices.

> Built to be forked. In the spirit of **nanoGPT** and **llama.cpp**: small, readable, runs
> offline on your laptop, and adding a new model is one small adapter — no framework to learn.

## Why this exists

Kalshi's post-cutoff, verifiably-resolved markets make an excellent testbed for probabilistic
forecasting: each market prices an event day by day and then settles to a verified yes/no.
JevGym turns that into (a) a **maintained, versioned dataset** — where **KalshiJev** is the
Kalshi **subset** of the JevGym dataset — and (b) an **arena** in which any
System-One-compatible model can participate and be judged on both calibration *and* final reward (P&L).

## The unifying abstraction

Every supported model — official Jev and every open reproduction — implements one contract:

```python
class SystemOneProvider(Protocol):
    name: str
    model_id: str
    def decide(self, state: str, question: str, candidates: list[str]) -> DecisionResult: ...
```

Any model that speaks the `POST {base}/v1/systemone` wire format is served by a single
`JevWireProvider` (the official reference and any wire-compatible server alike); anything else is
one small adapter. **The evaluator never knows which model produced a probability**, so new
models drop in without touching the benchmark. Results for additional models: **coming soon.**

### Generic LLM & agentic forecasting

A general LLM can serve as the decision backbone too (à la
[JevHarness](https://github.com/TianyuCodings/JevHarness)):

* **`llm`** — single-pass LLM forecaster returning a calibrated P(YES).
* **`llm_agent`** — an agent that may **search and fetch evidence, but only as-of the
  snapshot timestamp**. Search/fetch are bounded to `available_at ≤ as_of` via the Internet
  Archive (leakage-safe, no key) or dated web search (with a key), so the model can gather
  real evidence without ever seeing the future. This is what keeps "real-time predicted
  probability vs. the eventual event" an honest comparison.

The backbone is swappable behind one `LLMBackend` seam. Ship-ready backbones (each with an
`_agent` variant, e.g. `gpt_agent`):

| Agent | Backbone | Reached via |
| --- | --- | --- |
| `llm` | Claude (Anthropic) | `anthropic` SDK |
| `gpt` | ChatGPT (OpenAI) | `openai` SDK |
| `qwen` | Qwen (open source) | OpenAI-compatible server — DashScope, local vLLM, or Ollama |
| `gemini` | Gemini (Google) | Gemini's OpenAI-compatibility endpoint |

OpenAI, Qwen and Gemini share a single OpenAI-compatible code path — they differ only by
`base_url` + `model` + key.

## First vertical: macro → the Fed

v0.1 focuses on a few questions rather than a broad crawl: **Kalshi FOMC / Fed-funds
rate-decision markets** as prediction targets, with **timestamped macro indicators**
(unemployment, nonfarm payrolls, CPI — via FRED, stamped with real release dates) as
leakage-safe evidence. Other Kalshi categories are ingested with their native structured
fields but **no fabricated external evidence**. Weather and other rich-evidence domains come
later.

## Two evaluation tracks

* **Arena (the headline)** — the model steps through the trajectory and **trades on its own
  probability's edge vs. the market** (`edge = p_model − ask`): it enters the side with
  positive expected value at the first such checkpoint, one contract, held to resolution.
  Judged on **final reward (P&L)**. v0 is one-shot timing; repeated-bet / full-trading modes
  are behind the same interface.
* **Forecast** (blind & market-aware) — a single probability per checkpoint → Brier, log
  loss, ECE, Δ vs Jev / Δ vs Kalshi with **paired bootstrap CIs clustered by event** (kept as
  secondary calibration metrics).

**LLM validity.** An LLM only forecasts events that resolve *after* its training cutoff, so it
can't have memorized the outcome (a per-model filter, plus a global `--resolves-after`).
Example: **Qwen-0.6B on 2026 tasks** — an ongoing Iran crisis or the next Fed decision are
genuine unknowns for it, so those markets count; a market it could have trained on is dropped.

---

## Jev outperforms the market on Kalshi

> **Case study: weather** (Kalshi daily-temperature markets). This is one category — **more to
> come** (see [Categories](#categories--weather-today-more-coming) below).

*…on the clearer markets — where it matches the crowd and **trades them at a profit 🤑** — with
real room to grow on the genuinely hard ones.*

First live run: **official Jev (`jev-1.13.0`)** on **72 real, already-resolved Kalshi
daily-temperature markets** (720 held-out checkpoints). Each bet is placed with only
pre-resolution state; then the outcome is revealed and scored. Reward (arena P&L, real **$$**)
is the headline metric; Brier is the calibration check.

### By difficulty — easy to hard

"Difficulty" is how uncertain the *market itself* is: a near-0/near-1 price is easy, a coin-flip
price is hard. Brier is per-checkpoint (lower is better); arena reward is realized P&L per market.

| Difficulty | Jev Brier ↓ | Market Brier ↓ | Jev return / contract |
| --- | --- | --- | --- |
| **Easy** (market ~certain) | 0.007 | 0.003 | +2.4% |
| **Medium** | 0.159 | 0.145 | +0.4% |
| **Hard** (market ~coin-flip) | 0.305 | 0.249 | +7.4% |
| *Before the market has a price* | 0.197 | 0.250 | +26.9% |

Read it straight:

- **Easy / clear markets** — Jev is essentially perfect and **level with the crowd**, and trades
  them at a profit. This is where Jev's edge is real today.
- **Hard markets** — the crowd is still **better calibrated**; Jev is *overconfident* here
  (0.305 vs 0.249). It nets small P&L, but the headroom is obvious.
- **Before a contract is priced**, Jev already has signal (0.197 vs a clueless ~0.50).
- **Arena overall:** **+11.8%** average return per contract (49 wins / 20 losses). *(Return =
  P&L as a % of the $1 contract.)*

Honest shape of the win: **Jev outperforms on the easier, clearer markets and profits trading
the crowd — with clear potential to do better on the hard ones.** Small sample, weather-only,
CIs not yet tight.

#### The same, split by contract category (calibration Brier)

| Difficulty | Category | N | Jev Brier ↓ | Market Brier ↓ | Better |
| --- | --- | --- | --- | --- | --- |
| Easy | threshold (`≥`/`≤`) | 142 | 0.003 | 0.001 | market |
| Easy | range/bucket | 224 | 0.009 | 0.005 | market |
| Medium | threshold (`≥`/`≤`) | 12\* | 0.086 | 0.103 | **Jev** |
| Medium | range/bucket | 32 | 0.186 | 0.161 | market |
| Hard | threshold (`≥`/`≤`) | 6\* | 0.338 | 0.239 | market |
| Hard | range/bucket | 44 | 0.300 | 0.250 | market |
| No price yet | threshold (`≥`/`≤`) | 80 | 0.124 | 0.250 | **Jev** |
| No price yet | range/bucket | 180 | 0.230 | 0.250 | **Jev** |

\*small N — read with care. The only *priced* cell Jev wins is medium-threshold; wherever the
market has a real price and enough samples, the crowd leads. Jev's clear wins are the easy end
and the pre-price gap. (New verticals will add their own categories here — see the roadmap.)

### What actually happens — one bet, revealed

JevGym is a backtest loop: **state → bet → reveal**. Two real trades from this run make it
concrete (both are narrow one-degree "bucket" contracts):

- ✅ **Correct, profitable.** `KXHIGHLAX-26SEP20-B82.5` — *"LA high 82–83°F"*. Jev forecast
  **P(YES) = 0.11** (confident NO). Settled **NO**. Return **+50%**.
- ❌ **Confident, wrong.** `KXHIGHMIA-26SEP19-B90.5` — *"Miami high 90–91°F"*. Jev forecast
  **P(YES) = 0.03** (very confident NO). Settled **YES** — the high landed right in the bucket.
  Return **−82%**.

That contrast is exactly why the headline metric is **reward, not accuracy**: Jev is right on
most of these narrow buckets and banks small wins, but one confident miss on the bucket that
*does* hit costs more than several wins. Blind Jev made the wrong directional call on **14 of
72** markets — almost all of them narrow buckets it under-weighted.

### Other models — measured, not quoted

The arena is open to any System-One model: it runs on the **same markets**, through the same
renderer, scored on the same outcomes — no numbers copied from anyone's README. Plug one in as a
provider and it lands in the tables above, right next to Jev. Those results are **coming soon**.

<a id="categories"></a>

## 🗂️ Categories — three live, more coming

The deep-dive case study above is **weather**; **crypto** and **the Fed** are now live too. The
same pipeline extends to every Kalshi category, each becoming its own leaderboard with its own
reward 🤑. Politics and elections stay behind an opt-in gate and are excluded from the default set.

| Category | Status | What's in it |
| --- | --- | --- |
| **Weather** — daily temperature | ✅ live | case study above — Jev **+11.8% avg return** across 72 markets |
| **Crypto** — daily BTC thresholds | ✅ live | Jev near-perfect (Brier 0.02); mostly easy, market prices still sparse *(preliminary)* |
| **Economics & the Fed** — rate thresholds | ✅ live | Jev real signal (Brier 0.21, 64% acc; +9% on 22 arena trades) *(preliminary)* |
| Financials & companies | 🔜 soon | earnings beats, guidance, price ranges, IPOs |
| Sports | 🔜 soon | games, matches, tournaments |
| Science & technology | 🔜 soon | launches, releases, records |
| World & climate | 🔜 soon | global events, climate metrics |
| Entertainment | 🔜 soon | awards, box office, culture |

---

## Install

```bash
pip install -e ".[dev,hf]"   # core + test tooling + HuggingFace export
```

## Command workflow

```bash
jevgym ingest kalshi --all-resolved      # discover + download broadly (--from-fixtures offline)
jevgym ingest polymarket                 # Polymarket (Gamma + CLOB); combined into one dataset
jevgym parse                             # raw payloads -> normalized records (both sources)
jevgym build-snapshots                   # construct benchmark checkpoints
jevgym validate                          # leakage + split-integrity checks
jevgym hf-build                          # build Parquet configs + dataset card + manifest (local)
jevgym hf-push --repo "$HF_REPO_ID"      # publish KalshiJev (private by default; --public to opt in)
jevgym eval --agents kalshi_market,jev            # benchmark Jev (reward is the headline)
```

Kalshi and Polymarket normalize into the **same** schema (each row tagged `source`), so the
published dataset spans both and a model can be scored across either. Each snapshot is a
(state → verified outcome) example, so every forecast is graded against what actually happened.

Everything runs **offline on fixtures** with no credentials, network, or GPU:

```bash
jevgym ingest kalshi --from-fixtures && jevgym parse && jevgym build-snapshots \
  && jevgym validate && jevgym hf-build \
  && jevgym eval --agents kalshi_market,mock --track both
```

## Tokens for live runs

Everything above is optional for the offline demo. Set these to go live; each is read from the
environment (or `.env`):

| Token / var | Enables | Needed for |
| --- | --- | --- |
| `HF_TOKEN` + `HF_REPO_ID` | Publish the dataset | `jevgym hf-push` |
| `TYPESAFE_API_KEY` | Official **Jev** reference | `--agents jev` |
| `ANTHROPIC_API_KEY` | Claude backbone | `--agents llm,llm_agent` |
| `OPENAI_API_KEY` | ChatGPT backbone | `--agents gpt,gpt_agent` |
| `QWEN_API_KEY` (+ `QWEN_BASE_URL`) | Qwen (DashScope or local vLLM/Ollama) | `--agents qwen,qwen_agent` |
| `GEMINI_API_KEY` | Gemini backbone | `--agents gemini,gemini_agent` |
| `SEARCH_API_KEY` | Dated web *search* (Wayback *fetch* needs none) | `*_agent` with `SEARCH_PROVIDER=serp` |
| `KALSHI_API_KEY_ID` + `KALSHI_PRIVATE_KEY_PATH` | Higher-rate ingest (public reads work without) | large `jevgym ingest` |
| `FRED_API_KEY` | Live macro evidence | live evidence refresh |

```bash
pip install -e ".[dev,hf,llm]"          # adds the LLM backbones (anthropic + openai SDKs)
# once keys are set — compare Jev against several LLM backbones:
jevgym eval --agents kalshi_market,jev,llm,gpt,qwen,gemini --track both
```

## Data & redistribution policy

Raw third-party payloads live only in `data/raw/` and are **never** committed or published.
Published records are **derived/normalized** and carry full provenance
(`source_provider`, `source_endpoint`, `source_identifier`, `retrieved_at`, `available_at`,
`parser_version`). `hf-push` creates a **private** repo unless `--public` is passed. Macro
evidence via FRED originates from public-domain BLS/BEA/Fed series.

## Layout

```
src/jevgym/
  models/      Pydantic schemas (provenance + versioning on every record)
  data/        Kalshi client/ingest/parse + HuggingFace export
  evidence/    EvidenceSource protocol + macro (FRED) source
  snapshots/   horizons, snapshot builder, frozen-prompt renderer
  validate/    leakage + split-integrity checks
  providers/   SystemOneProvider + JevWireProvider + kalshi_market + mock (+ roadmap stubs)
  eval/        metrics, clustered-bootstrap comparison, arena env, runner, leaderboard
```

<a id="status"></a>

## 🩺 Status

v0.1 — offline-runnable scaffold across the whole pipeline, now with **live results**: official
Jev (`jev-1.13.0`) and the Kalshi crowd benchmarked on real resolved markets (see the results
section above), plus real Kalshi weather ingest. Real ingest, live model servers, and HF
publishing activate via env vars. The arena is open to other System-One models (one small
adapter each) — **results coming soon**. **Preliminary — more to go.**

## 🤝 Seeking collaborators

JevGym is active research and we are looking for collaborators. We would especially like to
work with:

- research groups on difficulty curation, calibration, and agentic forecasting;
- open-model teams who want their System-One model benchmarked;
- quantitative and hedge-fund partners interested in working together.

Reach out at **jevarena@proton.me**.
