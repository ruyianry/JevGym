from __future__ import annotations


def test_difficulty_from_p():
    from jevgym.sensitivity import difficulty_from_p

    assert difficulty_from_p(0.95) == "easy"
    assert difficulty_from_p(0.05) == "easy"
    assert difficulty_from_p(0.50) == "hard"
    assert difficulty_from_p(0.75) == "medium"
    assert difficulty_from_p(None) == "unknown"


def test_is_sensitive():
    from jevgym.sensitivity import is_sensitive

    assert is_sensitive("politics", "x", "y")  # domain
    assert is_sensitive("economics", "Will there be a war?", None)  # keyword
    assert not is_sensitive("crypto", "Will BTC hit 150k?", "price of bitcoin")


def test_snapshots_carry_difficulty_and_sensitive(built):
    from jevgym.snapshots.builder import load_snapshots

    snaps = load_snapshots(built)
    assert all(s.uncertainty_band in {"easy", "medium", "hard", "unknown"} for s in snaps)
    # Kalshi demo is all economics -> none sensitive.
    assert not any(s.sensitive for s in snaps)


def test_politics_is_quarantined_from_main_build(settings):
    from jevgym.data.huggingface import hf_build
    from jevgym.data.kalshi.ingest import seed_from_fixtures as seed_kalshi
    from jevgym.data.parse import parse_all
    from jevgym.data.polymarket.ingest import seed_from_fixtures as seed_poly
    from jevgym.snapshots.builder import build_snapshots, load_snapshots

    seed_kalshi(settings)
    seed_poly(settings)
    parse_all(settings)
    build_snapshots(settings)

    sensitive_markets = {s.market_ticker for s in load_snapshots(settings) if s.sensitive}
    assert "0xiran-nuclear-2026" in sensitive_markets  # politics
    assert "0xbtc-150k-2026" not in sensitive_markets  # crypto

    res = hf_build(settings)  # default: quarantine sensitive
    # main = 56 Kalshi + 14 Bitcoin = 70; the 14 Iran snapshots are quarantined.
    assert sum(res["configs"]["snapshots"].values()) == 70
    assert sum(res["sensitive_quarantined"]["snapshots"].values()) == 14
    assert res["sensitive_markets"] == 1


def test_qualitative_trace_renders(built):
    from jevgym.eval import qualitative_trace

    t = qualitative_trace(built, "mock", market="KXFED-26JAN-CUT")
    assert "state shown to the model" in t
    assert "model  p(YES)" in t
    assert "resolved:" in t
