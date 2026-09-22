#!/usr/bin/env python3
"""Build and (optionally) push the JevArena HuggingFace dataset.

Thin wrapper over ``jevgym.data.huggingface`` — equivalent to ``jevgym hf-build`` /
``jevgym hf-push``. The repo owner is never hardcoded; pass ``--repo`` or set ``HF_REPO_ID``.
"""

from __future__ import annotations

import argparse
import json
import os


def main() -> None:
    ap = argparse.ArgumentParser(description="Build and optionally push the JevArena dataset.")
    ap.add_argument("--repo", default=os.getenv("HF_REPO_ID"), help="HF dataset repo id.")
    ap.add_argument("--public", action="store_true", help="Publish publicly (default: private).")
    ap.add_argument("--no-push", action="store_true", help="Only build locally, do not push.")
    ap.add_argument("--data-dir", default=None)
    args = ap.parse_args()

    from jevgym.config import get_settings
    from jevgym.data.huggingface import hf_build, hf_push

    settings = get_settings(args.data_dir)
    built = hf_build(settings, repo_id=args.repo)
    print("Built configs:", json.dumps(built["configs"]))
    print("Local dataset:", built["out_dir"])

    if args.no_push:
        return
    if not args.repo:
        raise SystemExit("Set --repo or HF_REPO_ID to push.")
    print("Pushing to", args.repo, "(public)" if args.public else "(private)")
    print(hf_push(settings, args.repo, public=args.public))


if __name__ == "__main__":
    main()
