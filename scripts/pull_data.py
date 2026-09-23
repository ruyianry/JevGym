"""Pull your own JevGym data from the public APIs — for your personal, non-commercial use.

This repo ships **code, not data**. This script fetches market data DIRECTLY from each source's
public API into YOUR OWN local copy and builds the leakage-safe snapshots, so you can run the
benchmark and arena on data you obtained yourself.

────────────────────────────────────────────────────────────────────────────────────────────
⚠️  ACKNOWLEDGEMENT — by running this you confirm that:
    • you are accessing the data for YOUR OWN personal, non-commercial purposes; and
    • you will comply with each source's terms of use. In particular, Kalshi's Data Terms of
      Use permit personal, non-commercial access only and, WITHOUT Kalshi's prior written
      consent, PROHIBIT using Kalshi Data to train ML/AI systems or providing archived/cached
      Kalshi datasets to anyone else.
      https://kalshi-public-docs.s3.amazonaws.com/kalshi-data-terms-of-service.pdf
────────────────────────────────────────────────────────────────────────────────────────────

Usage:
    python scripts/pull_data.py                      # interactive — asks you to acknowledge
    python scripts/pull_data.py --i-agree            # non-interactive (you acknowledge the above)
    python scripts/pull_data.py --categories "Economics,Sports" --max-markets 30 --i-agree
    python scripts/pull_data.py --i-agree --data-dir ./data --no-build   # fetch only, skip snapshots
"""

from __future__ import annotations

import argparse
import sys

ACK = """\
This tool fetches data from public market APIs into your OWN local copy, for your OWN
personal, non-commercial use. You are responsible for complying with each source's terms —
notably Kalshi's Data Terms of Use (personal/non-commercial only; no ML/AI training on, or
redistribution of, Kalshi Data without Kalshi's prior written consent).
See https://kalshi-public-docs.s3.amazonaws.com/kalshi-data-terms-of-service.pdf
"""


def _acknowledge(auto: bool) -> bool:
    print(ACK)
    if auto:
        print("Acknowledged via --i-agree (personal, non-commercial use).\n")
        return True
    if not sys.stdin.isatty():
        print("Non-interactive shell: re-run with --i-agree to acknowledge and continue.")
        return False
    try:
        ans = input("Type 'yes' to acknowledge the above and continue: ").strip().lower()
    except EOFError:
        return False
    print()
    return ans in ("y", "yes")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Pull your own JevGym data (personal, non-commercial use).")
    ap.add_argument("--categories", default="", help="Comma-separated categories (default: all non-gated).")
    ap.add_argument("--max-markets", type=int, default=20, help="Max settled markets per series.")
    ap.add_argument("--data-dir", default="data", help="Where to write your local copy (default: ./data).")
    ap.add_argument("--no-build", action="store_true", help="Fetch only; skip parse/snapshots/validate.")
    ap.add_argument("--i-agree", action="store_true", help="Acknowledge personal/non-commercial use (skip the prompt).")
    args = ap.parse_args(argv)

    if not _acknowledge(args.i_agree):
        print("Not acknowledged — nothing fetched.")
        return 1

    from jevgym.config import get_settings
    from jevgym.data.categories import CATEGORY_SERIES
    from jevgym.data.kalshi.ingest import ingest_categories

    settings = get_settings(args.data_dir)
    settings.paths.ensure()
    cats = [c.strip() for c in args.categories.split(",") if c.strip()] or list(CATEGORY_SERIES)

    print(f"Fetching your own copy → {settings.paths.data_dir}  (categories: {', '.join(cats)})")
    out = ingest_categories(settings, cats, max_markets=args.max_markets)
    print(f"  ingested: {out.get('markets', 0)} markets, {out.get('candlestick_sets', 0)} candlestick sets")

    if args.no_build:
        print("\nDone (fetch only). Build snapshots later with: jevgym parse && jevgym build-snapshots")
        return 0

    from jevgym.data.parse import parse_all
    from jevgym.evidence import build_all_evidence
    from jevgym.snapshots.builder import build_snapshots
    from jevgym.validate.leakage import validate_all

    parsed = parse_all(settings)
    build_all_evidence(settings)
    snaps = build_snapshots(settings)
    report = validate_all(settings)
    print(f"  parsed: {parsed.get('markets', 0)} markets, {parsed.get('price_points', 0)} price points")
    print(f"  snapshots: {snaps.get('snapshots', 0)}  (splits: {snaps.get('splits')})")
    print(f"  leakage/split check: {'OK ✓' if report.get('ok') else 'VIOLATIONS — see jevgym validate'}")
    print(
        "\nYour local dataset is ready (personal, non-commercial use). It stays on your machine — "
        "don't redistribute Kalshi Data or train ML/AI on it without Kalshi's written consent.\n"
        "Next:  jevgym eval --agents kalshi_market,jev --track both"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
