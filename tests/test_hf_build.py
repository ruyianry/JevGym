from __future__ import annotations

import pathlib


def test_hf_build_counts_and_artifacts(built):
    from jevgym.data.huggingface import hf_build

    res = hf_build(built, repo_id="Owner/JevArena-Kalshi")
    cfg = res["configs"]
    m = res["manifest"]

    assert cfg["markets"]["train"] == m["market_count"] == 4
    assert cfg["price_history"]["train"] == m["price_point_count"]
    assert cfg["evidence"]["train"] == m["evidence_count"] == 9
    assert sum(cfg["snapshots"].values()) == m["snapshot_count"] == 56

    out = pathlib.Path(res["out_dir"])
    for rel in ("snapshots/train.parquet", "snapshots/test.parquet", "markets/train.parquet", "manifest.json", "README.md"):
        assert (out / rel).exists(), rel

    card = (out / "README.md").read_text()
    for section in ("JevArena-Kalshi", "Temporal-leakage policy", "Configurations", "load_dataset"):
        assert section in card

    assert m["shards"] and all(s["sha256"] and s["bytes"] > 0 for s in m["shards"])


def test_snapshots_parquet_roundtrip(built):
    from datasets import Dataset

    from jevgym.data.huggingface import hf_build

    res = hf_build(built)
    ds = Dataset.from_parquet(str(pathlib.Path(res["out_dir"]) / "snapshots" / "train.parquet"))
    assert "p_market" in ds.column_names and "y" in ds.column_names
    assert set(ds["y"]) <= {0, 1}
