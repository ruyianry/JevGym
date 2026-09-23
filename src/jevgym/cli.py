"""JevGym command-line interface.

    jevgym ingest kalshi --all-resolved     # discover + download (--from-fixtures offline)
    jevgym parse                            # raw -> normalized records (+ evidence)
    jevgym build-snapshots                  # construct benchmark checkpoints
    jevgym validate                         # leakage + split-integrity checks
    jevgym hf-build                         # local Parquet + card + manifest
    jevgym hf-push --repo "$HF_REPO_ID"     # publish (private by default; --public to opt in)
    jevgym eval --agents kalshi_market,jev,nanojev,openjev,decider

Heavy imports (datasets, eval) are deferred into the commands that need them so
``jevgym --help`` stays fast.
"""

from __future__ import annotations

import json

import typer

from .config import Settings, get_settings

app = typer.Typer(
    no_args_is_help=True,
    add_completion=False,
    help="JevGym: a timestamped Kalshi benchmark + arena for Jev-style decision models.",
)
ingest_app = typer.Typer(no_args_is_help=True, help="Ingest source data into the raw cache.")
app.add_typer(ingest_app, name="ingest")

DataDir = typer.Option(None, "--data-dir", help="Data directory (default: ./data or $JEVARENA_DATA_DIR).")


def _settings(data_dir: str | None) -> Settings:
    return get_settings(data_dir)


def _echo(obj) -> None:
    typer.echo(json.dumps(obj, indent=2, default=str))


@ingest_app.command("kalshi")
def ingest_kalshi(
    all_resolved: bool = typer.Option(False, "--all-resolved", help="Crawl all settled markets."),
    series: str = typer.Option("", "--series", help="Comma-separated series tickers to target."),
    categories: str = typer.Option("Economics", "--categories", help="Comma-separated categories."),
    max_markets: int = typer.Option(500, "--max-markets"),
    from_fixtures: bool = typer.Option(False, "--from-fixtures", help="Seed the offline demo (no network)."),
    data_dir: str = DataDir,
):
    """Discover and download Kalshi series/markets/candlesticks into the raw cache."""
    settings = _settings(data_dir)
    settings.paths.ensure()
    if from_fixtures:
        from .data.kalshi.ingest import seed_from_fixtures

        _echo(seed_from_fixtures(settings))
        return
    from .data.kalshi.ingest import IngestConfig
    from .data.kalshi.ingest import ingest_kalshi as _ingest

    config = IngestConfig(
        all_resolved=all_resolved,
        series_tickers=[s for s in series.split(",") if s],
        categories=[c for c in categories.split(",") if c],
        max_markets=max_markets,
    )
    _echo(_ingest(settings, config))


@ingest_app.command("categories")
def ingest_categories_cmd(
    categories: str = typer.Option("", "--categories", help="Comma-separated categories (default: all registered)."),
    max_markets: int = typer.Option(200, "--max-markets", help="Max markets per series."),
    data_dir: str = DataDir,
):
    """Expand the dataset: ingest every registered series in the given categories (economics
    indicators, crypto, storms), stamping the category so evidence attaches to the right domain."""
    settings = _settings(data_dir)
    settings.paths.ensure()
    from .data.categories import CATEGORY_SERIES
    from .data.kalshi.ingest import ingest_categories as _ic

    cats = [c.strip() for c in categories.split(",") if c.strip()] or list(CATEGORY_SERIES)
    _echo(_ic(settings, cats, max_markets=max_markets))


@ingest_app.command("scaled")
def ingest_scaled_cmd(
    categories: str = typer.Option("", "--categories", help="Comma-separated categories (default: all non-gated)."),
    target_events: int = typer.Option(100, "--target-events", help="Distinct settlement events to aim for per category."),
    per_event: int = typer.Option(2, "--per-event", help="Max markets (strikes) kept per event."),
    pool: int = typer.Option(600, "--pool", help="Settled markets to pool per series before selecting."),
    data_dir: str = DataDir,
):
    """Scale each bench: pool many settled markets and keep the *significant* ones — real price
    trajectory, near-the-money (drops 1c tails) — spread across ~target-events distinct events."""
    settings = _settings(data_dir)
    settings.paths.ensure()
    from .data.categories import CATEGORY_SERIES
    from .data.kalshi.ingest import ingest_scaled as _is

    cats = [c.strip() for c in categories.split(",") if c.strip()] or list(CATEGORY_SERIES)
    _echo(_is(settings, cats, target_events=target_events, per_event_cap=per_event, pool_per_series=pool))


@ingest_app.command("fred")
def ingest_fred_cmd(
    series: str = typer.Option("", "--series", help="Comma-separated FRED series ids (default: the macro set)."),
    data_dir: str = DataDir,
):
    """Fetch FRED macro observations (trend evidence for economics markets). Needs FRED_API_KEY."""
    settings = _settings(data_dir)
    settings.paths.ensure()
    from .evidence.macro import fetch_fred

    ids = [s.strip() for s in series.split(",") if s.strip()] or None
    _echo(fetch_fred(settings, ids))


@ingest_app.command("polymarket")
def ingest_polymarket(
    max_markets: int = typer.Option(500, "--max-markets"),
    from_fixtures: bool = typer.Option(False, "--from-fixtures", help="Seed the offline demo (no network)."),
    data_dir: str = DataDir,
):
    """Discover and download resolved binary Polymarket markets + price history."""
    settings = _settings(data_dir)
    settings.paths.ensure()
    if from_fixtures:
        from .data.polymarket.ingest import seed_from_fixtures

        _echo(seed_from_fixtures(settings))
        return
    from .data.polymarket.ingest import PolymarketIngestConfig
    from .data.polymarket.ingest import ingest_polymarket as _ingest_poly

    _echo(_ingest_poly(settings, PolymarketIngestConfig(max_markets=max_markets)))


@ingest_app.command("weather")
def ingest_weather(
    from_fixtures: bool = typer.Option(False, "--from-fixtures", help="Seed offline weather markets + observations."),
    series: str = typer.Option("", "--series", help="Comma-separated Kalshi weather series (default: all listed cities)."),
    status: str = typer.Option("settled", "--status", help="Market status filter (settled|open|unopened)."),
    max_markets: int = typer.Option(60, "--max-markets", help="Max markets per series."),
    data_dir: str = DataDir,
):
    """Ingest real Kalshi daily-temperature markets (available options only) + candlesticks.

    Live by default; ``--from-fixtures`` seeds the deterministic offline demo instead.
    """
    settings = _settings(data_dir)
    settings.paths.ensure()
    if from_fixtures:
        from .curation.fixtures import seed_weather_fixtures

        _echo(seed_weather_fixtures(settings))
        return
    from .data.kalshi.ingest import ingest_weather as _ingest_weather

    tickers = [s.strip().upper() for s in series.split(",") if s.strip()] or None
    _echo(_ingest_weather(settings, tickers, status=status, max_markets=max_markets))


@app.command()
def parse(
    with_evidence: bool = typer.Option(True, "--with-evidence/--no-evidence", help="Also build evidence."),
    data_dir: str = DataDir,
):
    """Normalize raw payloads into typed records (and build evidence)."""
    settings = _settings(data_dir)
    from .data.parse import parse_all

    out = parse_all(settings)
    if with_evidence:
        from .evidence import build_all_evidence

        out["evidence"] = len(build_all_evidence(settings))
    _echo(out)


@app.command("build-snapshots")
def build_snapshots_cmd(data_dir: str = DataDir):
    """Construct canonical benchmark snapshots from normalized records."""
    settings = _settings(data_dir)
    from .snapshots.builder import build_snapshots

    _echo(build_snapshots(settings))


@app.command()
def validate(data_dir: str = DataDir):
    """Check temporal leakage and split integrity. Exits non-zero on any violation."""
    settings = _settings(data_dir)
    from .validate.leakage import validate_all

    report = validate_all(settings)
    _echo(report)
    if not report["ok"]:
        raise typer.Exit(code=1)


@app.command("hf-build")
def hf_build_cmd(
    repo: str = typer.Option(None, "--repo", help="Repo id to embed in the dataset card."),
    include_sensitive: bool = typer.Option(
        False, "--include-sensitive", help="Fold politics/war/elections into the published set (default: quarantine)."
    ),
    data_dir: str = DataDir,
):
    """Build local Parquet configs + dataset card + hashed manifest (no upload)."""
    settings = _settings(data_dir)
    from .data.huggingface import hf_build

    res = hf_build(settings, repo_id=repo or settings.hf_repo_id, include_sensitive=include_sensitive)
    _echo(
        {
            "configs": res["configs"],
            "shards": res["shards"],
            "out_dir": res["out_dir"],
            "sensitive_markets": res["sensitive_markets"],
            "sensitive_quarantined": res["sensitive_quarantined"],
        }
    )


@app.command("hf-push")
def hf_push_cmd(
    repo: str = typer.Option(None, "--repo", help="HF dataset repo id (or set HF_REPO_ID)."),
    public: bool = typer.Option(False, "--public", help="Publish publicly (default: private)."),
    config: str = typer.Option("", "--config", help="Comma-separated configs (default: all)."),
    include_sensitive: bool = typer.Option(
        False, "--include-sensitive", help="Include politics/war/elections (default: excluded)."
    ),
    data_dir: str = DataDir,
):
    """Publish the dataset to the Hub. Private by default; pass --public to opt in.
    Sensitive categories are excluded unless --include-sensitive."""
    settings = _settings(data_dir)
    repo_id = repo or settings.hf_repo_id
    if not repo_id:
        raise typer.BadParameter("Provide --repo or set HF_REPO_ID.")
    from .data.huggingface import hf_push

    configs = [c for c in config.split(",") if c] or None
    _echo(hf_push(settings, repo_id, public=public, configs=configs, include_sensitive=include_sensitive))


@app.command()
def eval(
    agents: str = typer.Option("kalshi_market,mock", "--agents", help="Comma-separated agent names."),
    track: str = typer.Option("both", "--track", help="blind | market-aware | both."),
    split: str = typer.Option("", "--split", help="Restrict to a split (train/validation/test)."),
    arena: bool = typer.Option(True, "--arena/--no-arena", help="Run the sequential arena (reward)."),
    arena_mode: str = typer.Option(
        "one_shot", "--arena-mode", help="one_shot (edge) | action | repeated (multi-day, ~1 week)."
    ),
    edge_threshold: float = typer.Option(0.0, "--edge-threshold", help="Min model-vs-ask edge to trade."),
    max_days: int = typer.Option(7, "--max-days", help="repeated mode: trading window before resolution (days)."),
    max_contracts: int = typer.Option(0, "--max-contracts", help="repeated mode: cap total contracts/market (0 = uncapped)."),
    respect_cutoffs: bool = typer.Option(
        True, "--respect-cutoffs/--no-respect-cutoffs", help="Only score LLMs on events after release_date + buffer."
    ),
    cutoff_buffer_days: int = typer.Option(90, "--cutoff-buffer-days", help="Safety buffer after a model's release date."),
    resolves_after: str = typer.Option("", "--resolves-after", help="Global floor: only events resolving after this date."),
    boot: int = typer.Option(2000, "--boot", help="Bootstrap resamples for CIs."),
    data_dir: str = DataDir,
):
    """Run the benchmark and print the leaderboard (reward is the headline metric)."""
    settings = _settings(data_dir)
    from .eval import TRACK_BLIND, TRACK_MARKET_AWARE
    from .eval.runner import evaluate
    from .util import parse_dt

    track_map = {
        "blind": [TRACK_BLIND],
        "market-aware": [TRACK_MARKET_AWARE],
        "market_aware": [TRACK_MARKET_AWARE],
        "both": [TRACK_BLIND, TRACK_MARKET_AWARE],
    }
    tracks = track_map.get(track)
    if tracks is None:
        raise typer.BadParameter("track must be one of: blind, market-aware, both")

    out = evaluate(
        settings,
        agents=[a.strip() for a in agents.split(",") if a.strip()],
        tracks=tracks,
        split=split or None,
        arena=arena,
        arena_mode=arena_mode,
        edge_threshold=edge_threshold,
        max_days=max_days,
        max_contracts=max_contracts or None,
        respect_cutoffs=respect_cutoffs,
        resolves_after=parse_dt(resolves_after) if resolves_after else None,
        n_boot=boot,
    )
    typer.echo(out["text"])
    typer.echo(f"\n(results written to {settings.paths.data_dir / 'eval'})")


@app.command()
def example(
    agent: str = typer.Option("mock", "--agent", help="Agent to trace (mock, jev, qwen, ...)."),
    market: str = typer.Option("", "--market", help="Market ticker to trace."),
    horizon: str = typer.Option("", "--horizon", help="Checkpoint horizon (e.g. 7d, q50)."),
    uncertainty: str = typer.Option("", "--uncertainty", help="Market-uncertainty band: easy | medium | hard."),
    blind: bool = typer.Option(False, "--blind", help="Hide the market price from the model."),
    data_dir: str = DataDir,
):
    """Print one qualitative trace: state shown, model probability, arena trade, outcome."""
    settings = _settings(data_dir)
    from .eval.qualitative import qualitative_trace

    typer.echo(
        qualitative_trace(
            settings,
            agent,
            market=market or None,
            horizon=horizon or None,
            uncertainty=uncertainty or None,
            reveal_market=not blind,
        )
    )


difficulty_app = typer.Typer(no_args_is_help=True, help="Auditable difficulty curation (weather first).")
app.add_typer(difficulty_app, name="difficulty")

_CONFIG = typer.Option("configs/difficulty_weather_v1.yaml", "--config", help="Frozen difficulty config.")


@difficulty_app.command("mine")
def difficulty_mine(
    config: str = _CONFIG,
    prior: str = typer.Option("auto", "--prior", help="Prior obs source: auto|fixture|open-meteo."),
    data_dir: str = DataDir,
):
    """Nominate easy candidates from odds+prior; annotate every considered snapshot; print funnel."""
    settings = _settings(data_dir)
    from .curation.run import run_mine

    _echo(run_mine(settings, config, prior=prior))


@difficulty_app.command("export-review")
def difficulty_export_review(
    output: str = typer.Option("", "--output", help="Where to write review packets."), config: str = _CONFIG, data_dir: str = DataDir
):
    """Export outcome-blind review packets for nominated candidates."""
    settings = _settings(data_dir)
    from .curation.run import run_export_review

    _echo(run_export_review(settings, output or None, config))


@difficulty_app.command("apply-review")
def difficulty_apply_review(
    input: str = typer.Option("", "--input", help="Reviewer decisions JSONL."), config: str = _CONFIG, data_dir: str = DataDir
):
    """Apply reviewer decisions; only approved records receive a difficulty label."""
    settings = _settings(data_dir)
    from .curation.run import run_apply_review

    _echo(run_apply_review(settings, input or None, config))


@difficulty_app.command("validate")
def difficulty_validate(data_dir: str = DataDir):
    """Check outcome-free + annotation invariants. Exits non-zero on any violation."""
    settings = _settings(data_dir)
    from .curation.run import run_validate

    report = run_validate(settings)
    _echo(report)
    if not report["ok"]:
        raise typer.Exit(code=1)


@difficulty_app.command("report")
def difficulty_report_cmd(config: str = _CONFIG, data_dir: str = DataDir):
    """Regenerate the selection funnel + difficulty_report.md."""
    settings = _settings(data_dir)
    from .curation.run import run_report

    _echo(run_report(settings, config))


@difficulty_app.command("audit")
def difficulty_audit(
    all_candidates: bool = typer.Option(False, "--all-candidates", help="Audit all candidates, not just selected."),
    data_dir: str = DataDir,
):
    """POST-SELECTION only: join outcomes to curated candidates; market vs independent-prior accuracy."""
    settings = _settings(data_dir)
    from .curation.run import run_audit

    _echo(run_audit(settings, selected_only=not all_candidates))


def main() -> None:
    app()


if __name__ == "__main__":
    main()
