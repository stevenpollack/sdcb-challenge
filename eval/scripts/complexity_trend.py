#!/usr/bin/env python3
"""Cyclomatic complexity trend across feature commits.

Checks out each feature commit and runs lizard (language-agnostic: C/C++/Java/JS/TS/Python/Go/
Rust/etc) over the configured source dirs, recording mean and max function complexity. Climbing
complexity marks where structure breaks down.

Requires lizard:  pip install lizard
Usage: python scripts/complexity_trend.py [config.json]
Restores original HEAD on exit. Writes complexity_trend.json.
"""
import json
import os
import sys

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from _common import (load_config, feature_commits, checkout, current_ref,
                     restore, print_table)

try:
    import lizard
except ImportError:
    sys.exit("lizard not found. Install with: pip install lizard")


def analyze(repo, source_dirs):
    ccns = []
    for d in source_dirs:
        full = os.path.join(repo, d)
        if not os.path.exists(full):
            continue
        for res in lizard.analyze([full]):
            for fn in res.function_list:
                ccns.append(fn.cyclomatic_complexity)
    if not ccns:
        return None, None, 0
    return sum(ccns) / len(ccns), max(ccns), len(ccns)


def main():
    cfg_path = sys.argv[1] if len(sys.argv) > 1 else "eval.config.json"
    cfg = load_config(cfg_path)
    repo = cfg["repo_path"]
    source_dirs = cfg.get("complexity", {}).get("source_dirs", ["src"])

    commits = feature_commits(repo, cfg)
    origin = current_ref(repo)
    results = []
    try:
        for i, (sha, subj) in enumerate(commits):
            checkout(repo, sha)
            mean_cc, max_cc, nfun = analyze(repo, source_dirs)
            results.append({"idx": i, "sha": sha, "subject": subj,
                            "mean_cc": mean_cc, "max_cc": max_cc, "n_functions": nfun})
    finally:
        restore(repo, origin)

    rows = []
    for r in results:
        rows.append([r["idx"], r["sha"][:8],
                     "n/a" if r["mean_cc"] is None else f"{r['mean_cc']:.2f}",
                     "n/a" if r["max_cc"] is None else r["max_cc"],
                     r["n_functions"], r["subject"][:38]])
    print_table(["idx", "sha", "mean_cc", "max_cc", "#fn", "subject"], rows)

    with open("complexity_trend.json", "w") as f:
        json.dump(results, f, indent=2)
    print("\nwrote complexity_trend.json")


if __name__ == "__main__":
    main()
