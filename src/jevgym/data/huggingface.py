"""HuggingFace dataset export.

Publishes several *separate* configurations (``markets``, ``price_history``, ``evidence``,
``snapshots``, and a reserved ``weather``) rather than one mega-schema. Rows are transformed
by streaming generators over the normalized JSONL, then built one bounded table at a time.
``hf-build`` writes local Parquet + a dataset card + a hashed manifest; ``hf-push``
publishes (private by default; ``--public`` to opt in). Raw third-party payloads are never
included — only derived, provenance-stamped records.
"""

from __future__ import annotations

import json
import subprocess
from collections.abc import Iterator
from pathlib import Path

from datasets import Dataset, DatasetDict

from ..config import Settings
from ..io import iter_jsonl
from ..models import DatasetManifest, ShardHash
from ..util import sha256_file, utcnow
from ..version import DATASET_VERSION, PARSER_VERSION
from .kalshi import rawpaths  # noqa: F401  (kept for provenance symmetry / future use)

CONFIGS = ["markets", "price_history", "evidence", "snapshots", "weather"]

_NORM = {
    "markets": "markets.jsonl",
    "price_history": "price_history.jsonl",
    "evidence": "evidence.jsonl",
}
_JSON_COLS = {
    "markets": ["custom_strike", "metadata"],
    "price_history": ["ohlc", "metadata"],
    "evidence": ["payload", "metadata"],
}


# --- row transforms --------------------------------------------------------
def _jsonify(row: dict, json_cols: list[str]) -> dict:
    """Stringify nested dict columns so HF/Parquet features stay simple and stable
    (None becomes the JSON literal ``"null"``, avoiding None/struct type conflicts)."""
    out = dict(row)
    for c in json_cols:
        out[c] = json.dumps(out.get(c))
    return out


def _snapshot_row_from_dict(d: dict) -> dict:
    ps, ms, oc = d.get("public_state", {}), d.get("market_state", {}), d.get("outcome", {})
    return {
        "snapshot_id": d["snapshot_id"],
        "market_ticker": d["market_ticker"],
        "event_ticker": d.get("event_ticker"),
        "series_ticker": d.get("series_ticker"),
        "domain": d.get("domain", "other"),
        "timestamp": d["timestamp"],
        "forecast_horizon": d.get("forecast_horizon", ""),
        "horizon_seconds": d.get("horizon_seconds"),
        "lifetime_fraction": d.get("lifetime_fraction"),
        "candidates": d.get("candidates", ["YES", "NO"]),
        "question_kind": d.get("question_kind", "binary"),
        "uncertainty_band": d.get("uncertainty_band", "unknown"),
        "sensitive": bool(d.get("sensitive", False)),
        # convenience flat columns
        "p_market": ms.get("p_market"),
        "y": oc.get("y"),
        "resolved": oc.get("resolved"),
        # full-fidelity blocks (JSON strings)
        "public_state": json.dumps(ps),
        "market_state": json.dumps(ms),
        "outcome": json.dumps(oc),
        "split": d.get("split"),
        "dataset_version": d.get("dataset_version", DATASET_VERSION),
        "parser_version": d.get("parser_version", PARSER_VERSION),
        "source": d.get("source_provider"),  # "kalshi" | "polymarket"
        "source_provider": d.get("source_provider"),
        "source_identifier": d.get("source_identifier"),
        "available_at": d.get("available_at"),
        "retrieved_at": d.get("retrieved_at"),
    }


# --- generators (stream from JSONL) ----------------------------------------
def _keep(is_sensitive: bool, mode: str) -> bool:
    if mode == "all":
        return True
    if mode == "sensitive":
        return is_sensitive
    return not is_sensitive  # "main"


def _simple_gen(
    path: str, json_cols: list[str], *, ticker_field: str = "ticker", sensitive=frozenset(), mode: str = "all"
) -> Iterator[dict]:
    for row in iter_jsonl(path):
        if not _keep(row.get(ticker_field) in sensitive, mode):
            continue
        yield _jsonify(row, json_cols)


def _snapshot_gen(
    path: str, split: str, *, domain: str | None = None, sensitive=frozenset(), mode: str = "all"
) -> Iterator[dict]:
    for d in iter_jsonl(path):
        if d.get("split") != split:
            continue
        if domain is not None and d.get("domain") != domain:
            continue
        is_sens = bool(d.get("sensitive")) or d.get("market_ticker") in sensitive
        if not _keep(is_sens, mode):
            continue
        yield _snapshot_row_from_dict(d)


def _count(path: Path, predicate=None) -> int:
    return sum(1 for d in iter_jsonl(path) if predicate is None or predicate(d))


def sensitive_market_tickers(settings: Settings) -> set[str]:
    """Tickers flagged sensitive (politics / war / elections) — quarantined by default."""
    from ..io import read_model_jsonl
    from ..models import Market
    from ..sensitivity import is_sensitive
    from ..snapshots.builder import domain_of

    out: set[str] = set()
    for m in read_model_jsonl(settings.paths.normalized / _NORM["markets"], Market):
        if is_sensitive(domain_of(m), m.title, m.rules_primary):
            out.add(m.ticker)
    return out


# --- dataset assembly ------------------------------------------------------
def build_datasets(settings: Settings, *, sensitive=frozenset(), mode: str = "main") -> dict[str, DatasetDict]:
    """Build config tables. ``mode``: 'main' (exclude sensitive), 'sensitive' (only those),
    or 'all'. We materialize one bounded table at a time via ``Dataset.from_list``."""
    norm = settings.paths.normalized
    snaps_path = settings.paths.snapshots / "snapshots.jsonl"
    out: dict[str, DatasetDict] = {}

    for cfg in ("markets", "price_history", "evidence"):
        p = norm / _NORM[cfg]
        if _count(p) == 0:
            continue
        tf = "ticker" if cfg == "markets" else "market_ticker"
        rows = list(_simple_gen(str(p), _JSON_COLS[cfg], ticker_field=tf, sensitive=sensitive, mode=mode))
        if rows:
            out[cfg] = DatasetDict({"train": Dataset.from_list(rows)})

    if _count(snaps_path) > 0:
        dd = {}
        for split in ("train", "validation", "test"):
            rows = list(_snapshot_gen(str(snaps_path), split, sensitive=sensitive, mode=mode))
            if rows:
                dd[split] = Dataset.from_list(rows)
        if dd:
            out["snapshots"] = DatasetDict(dd)

        wdd = {}
        for split in ("train", "validation", "test"):
            rows = list(_snapshot_gen(str(snaps_path), split, domain="weather", sensitive=sensitive, mode=mode))
            if rows:
                wdd[split] = Dataset.from_list(rows)
        if wdd:
            out["weather"] = DatasetDict(wdd)

    return out


def write_parquet(datasets: dict[str, DatasetDict], out_dir: Path) -> list[ShardHash]:
    out_dir.mkdir(parents=True, exist_ok=True)
    shards: list[ShardHash] = []
    for cfg, dd in datasets.items():
        cfg_dir = out_dir / cfg
        cfg_dir.mkdir(parents=True, exist_ok=True)
        for split, ds in dd.items():
            path = cfg_dir / f"{split}.parquet"
            ds.to_parquet(str(path))
            digest, size = sha256_file(path)
            shards.append(
                ShardHash(path=str(path.relative_to(out_dir)), sha256=digest, bytes=size, config=cfg, split=split)
            )
    return shards


# --- manifest + card -------------------------------------------------------
def _git_commit() -> str | None:
    try:
        return (
            subprocess.check_output(["git", "rev-parse", "HEAD"], stderr=subprocess.DEVNULL)
            .decode()
            .strip()
        )
    except Exception:
        return None


def build_manifest(settings: Settings, datasets: dict[str, DatasetDict], shards: list[ShardHash]) -> DatasetManifest:
    norm = settings.paths.normalized
    snaps_path = settings.paths.snapshots / "snapshots.jsonl"
    return DatasetManifest(
        dataset_version=DATASET_VERSION,
        parser_version=PARSER_VERSION,
        created_at=utcnow(),
        market_count=_count(norm / "markets.jsonl"),
        event_count=_count(norm / "events.jsonl"),
        price_point_count=_count(norm / "price_history.jsonl"),
        snapshot_count=_count(snaps_path),
        evidence_count=_count(norm / "evidence.jsonl"),
        source_cutoffs={"generated_at": utcnow().isoformat()},
        git_commit=_git_commit(),
        shards=shards,
    )


def generate_dataset_card(settings: Settings, manifest: DatasetManifest, repo_id: str | None) -> str:
    repo = repo_id or "<owner>/JevGym"
    return f"""---
license: other
license_name: mixed-see-card
pretty_name: JevGym
tags:
- prediction-markets
- forecasting
- calibration
- kalshi
- system-one
task_categories:
- tabular-classification
- time-series-forecasting
---

# JevGym

**The JevGym dataset.** A timestamped historical prediction-market dataset for evaluating
probabilistic decision models (Jev-series "System One" models and beyond). Version
`{manifest.dataset_version}`. This release is the **KalshiJev** subset — the Kalshi data — chosen
first because Kalshi quotes a **direct probability** directly comparable to a Jev model's output.
More sources will be added as their own subsets over time.

## What is JevGym?

JevGym replays resolved [Kalshi](https://kalshi.com) markets. At each historical checkpoint
a model sees only information available at that time and forecasts (or trades) the eventual
outcome. Three signals are kept strictly separate: the contemporaneous crowd probability
`p_K(t)` (a **baseline**, `kalshi_market` — *not* an oracle), the historical trajectory, and
the eventual resolution `Y` (the true oracle / label).

## Data sources

- **Kalshi Trade API v2** — market catalog, resolution rules, settlement, candlestick price
  history.
- **Polymarket (Gamma + CLOB)** — resolved binary markets + YES-token price history.
- **FRED (macro evidence)** — unemployment, nonfarm payrolls, CPI (public-domain BLS/BEA/Fed
  series), each stamped with its public release date as `available_at`.

Kalshi and Polymarket are normalized into the **same** schema; every row carries a `source`
field (`kalshi` | `polymarket`). Only derived/normalized records are published here; raw API
payloads are not redistributed.

## Evaluation

The headline metric is **reward (P&L)** in a sequential arena: a model trades on the edge
between its own probability and the market price. Calibration (Brier / log-loss / ECE) is
reported secondarily. For LLM agents, only markets that resolve **after the model's training
cutoff** are scored, so the model cannot have memorized outcomes.

## Configurations

| Config | One row per | Contents |
| --- | --- | --- |
| `markets` | market | metadata, rules, times, category, settlement/result |
| `price_history` | market × timestamp | normalized price observations (probability units) |
| `evidence` | timestamped evidence item | macro figures (release-dated) |
| `snapshots` | benchmark checkpoint | `public_state` / `market_state` / `outcome`, split |
| `weather` | (reserved) | rich weather representation — empty in v0.1 |

## Schema (snapshots)

`snapshot_id, market_ticker, event_ticker, timestamp, forecast_horizon, domain, p_market,
y, resolved, public_state (JSON), market_state (JSON), outcome (JSON), split,
dataset_version`. `public_state.evidence` contains only items with
`available_at <= timestamp`.

## Temporal-leakage policy

For every model-visible evidence item, `available_at <= snapshot.timestamp` is enforced by a
validation pass. Checkpoints never postdate market close.

## Train / dev / test methodology

Chronological, **event-grouped** splits: no event ever spans multiple splits; older events →
`train`, newest → `test`. Labels are present for research use; a hidden-test leaderboard can
be layered on later.

## Known limitations

- Preliminary: currently spans **weather**, **crypto** (daily BTC thresholds), and **the Fed**
  (rate thresholds); more categories are being added.
- Only the economics domain currently has rich external evidence; other domains carry
  Kalshi-native fields only (no fabricated evidence).
- Far-out-of-the-money strikes often never trade, so their price history is sparse.

## Counts

markets={manifest.market_count}, events={manifest.event_count},
price_points={manifest.price_point_count}, snapshots={manifest.snapshot_count},
evidence={manifest.evidence_count}.

## Example usage

```python
from datasets import load_dataset

snapshots = load_dataset("{repo}", "snapshots")
prices = load_dataset("{repo}", "price_history")
```

## Redistribution

Dataset records are derived/normalized (no raw third-party payloads); verify the redistribution
terms for each source before broad public release. See the project repository for terms.

## Collaboration

Active research, expanding fast, and seeking collaborators (research, open-model, and
quantitative/hedge-fund partners). Contact: jevgym@proton.me
"""


# --- orchestration ---------------------------------------------------------
def hf_build(settings: Settings, repo_id: str | None = None, *, include_sensitive: bool = False) -> dict:
    sensitive = sensitive_market_tickers(settings)
    mode = "all" if include_sensitive else "main"

    datasets = build_datasets(settings, sensitive=sensitive, mode=mode)
    out_dir = settings.paths.dataset
    shards = write_parquet(datasets, out_dir)
    manifest = build_manifest(settings, datasets, shards)

    (out_dir / "manifest.json").write_text(
        json.dumps(manifest.model_dump(mode="json"), indent=2), encoding="utf-8"
    )
    (out_dir / "README.md").write_text(
        generate_dataset_card(settings, manifest, repo_id), encoding="utf-8"
    )

    # Quarantine sensitive rows to a separate local dir (never pushed) unless folded in.
    quarantined: dict = {}
    if sensitive and not include_sensitive:
        q = build_datasets(settings, sensitive=sensitive, mode="sensitive")
        write_parquet(q, settings.paths.data_dir / "sensitive")
        quarantined = {cfg: {s: len(ds) for s, ds in dd.items()} for cfg, dd in q.items()}

    return {
        "configs": {cfg: {s: len(ds) for s, ds in dd.items()} for cfg, dd in datasets.items()},
        "shards": len(shards),
        "out_dir": str(out_dir),
        "sensitive_markets": len(sensitive),
        "sensitive_quarantined": quarantined,
        "manifest": manifest.model_dump(mode="json"),
    }


def hf_push(
    settings: Settings,
    repo_id: str,
    *,
    private: bool = True,
    public: bool = False,
    token: str | None = None,
    configs: list[str] | None = None,
    include_sensitive: bool = False,
) -> dict:
    """Publish built configs to the Hub. Private by default; pass ``public=True`` to opt in.
    Sensitive markets (politics/war/elections) are excluded unless ``include_sensitive=True``.
    Requires ``HF_TOKEN`` (or ``token``).
    """
    from huggingface_hub import HfApi

    token = token or settings.hf_token
    if not token:
        raise RuntimeError("HF_TOKEN is not set; cannot push to the Hub.")
    is_private = not public and private

    sensitive = sensitive_market_tickers(settings)
    datasets = build_datasets(settings, sensitive=sensitive, mode="all" if include_sensitive else "main")
    to_push = configs or list(datasets)
    pushed = {}
    for cfg in to_push:
        if cfg not in datasets:
            continue
        datasets[cfg].push_to_hub(repo_id, config_name=cfg, private=is_private, token=token)
        pushed[cfg] = list(datasets[cfg].keys())

    # Ensure a build exists locally, then upload the card.
    card_path = settings.paths.dataset / "README.md"
    if not card_path.exists():
        hf_build(settings, repo_id=repo_id)
    api = HfApi(token=token)
    api.create_repo(repo_id, repo_type="dataset", private=is_private, exist_ok=True)
    api.upload_file(
        path_or_fileobj=str(card_path),
        path_in_repo="README.md",
        repo_id=repo_id,
        repo_type="dataset",
    )
    return {"repo_id": repo_id, "private": is_private, "pushed": pushed}
