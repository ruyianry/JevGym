from __future__ import annotations

from typer.testing import CliRunner

from jevgym.cli import app

runner = CliRunner()


def test_full_pipeline_offline(tmp_path):
    d = str(tmp_path)

    def run(args):
        result = runner.invoke(app, args + ["--data-dir", d])
        assert result.exit_code == 0, f"{args} failed:\n{result.stdout}\n{result.exception}"
        return result

    run(["ingest", "kalshi", "--from-fixtures"])
    run(["ingest", "polymarket", "--from-fixtures"])  # combined Kalshi + Polymarket
    run(["parse"])
    run(["build-snapshots"])
    run(["validate"])  # exit 0 => no leakage / split violations
    run(["hf-build"])

    res = run(["eval", "--agents", "kalshi_market,mock", "--boot", "200"])
    assert "ARENA" in res.stdout  # reward is the headline metric
    assert "Brier" in res.stdout
    assert "kalshi_market" in res.stdout
