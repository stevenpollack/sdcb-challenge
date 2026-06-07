#!/usr/bin/env python3
"""Collapse point — combines the four trend outputs into the headline number.

Reads commit_size.json, duplication_trend.json, complexity_trend.json, coverage_trend.json,
regression_count.json (run those first). Applies the provisional rule from EVALUATION.md:

  A feature commit is 'rot-onset' if >=2 of:
    - introduced >=1 regression
    - oversize commit (churn > 2x first-third median)
    - duplication rose >5 absolute points vs previous feature
    - coverage dropped >10 absolute points from project max

  Collapse point = first feature index with TWO CONSECUTIVE rot-onset commits.

Thresholds are PLACEHOLDERS — recalibrate after a pilot run. Override via flags.
Usage: python scripts/collapse.py [--dup-jump 5] [--cov-drop 10] [--oversize-mult 2]
"""
import argparse
import json
import os
import sys

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from _common import print_table


def load(path):
    if not os.path.exists(path):
        sys.exit(f"missing {path} — run the trend scripts first")
    with open(path) as f:
        return json.load(f)


def index_by_sha(commits, key):
    return {c["sha"]: c.get(key) for c in commits}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dup-jump", type=float, default=5.0)
    ap.add_argument("--cov-drop", type=float, default=10.0)
    args = ap.parse_args()

    size = load("commit_size.json")
    dup = load("duplication_trend.json")
    comp = load("complexity_trend.json")          # reported, not in rule by default
    cov = load("coverage_trend.json")
    reg = load("regression_count.json")

    oversize = {c["sha"]: c["oversize"] for c in size["commits"]}
    reg_by = index_by_sha(reg["commits"], "regressions_introduced")
    cov_max = cov.get("max")
    cov_by = index_by_sha(cov["commits"], "coverage_pct")
    comp_by = index_by_sha(comp if isinstance(comp, list) else comp.get("commits", []), "mean_cc")

    # duplication is ordered; compute deltas vs previous feature
    dup_list = dup if isinstance(dup, list) else dup.get("commits", [])
    dup_flag = {}
    prev = None
    for c in dup_list:
        p = c.get("dup_pct")
        dup_flag[c["sha"]] = (prev is not None and p is not None and (p - prev) > args.dup_jump)
        if p is not None:
            prev = p

    # iterate in feature order using duplication list as the canonical ordering
    rows = []
    rot_flags = []
    for i, c in enumerate(dup_list):
        sha = c["sha"]
        signals = []
        r = reg_by.get(sha)
        if isinstance(r, int) and r >= 1:
            signals.append("regr")
        if oversize.get(sha):
            signals.append("oversize")
        if dup_flag.get(sha):
            signals.append("dup_jump")
        cv = cov_by.get(sha)
        if cv is not None and cov_max is not None and (cov_max - cv) > args.cov_drop:
            signals.append("cov_drop")
        rot = len(signals) >= 2
        rot_flags.append(rot)
        rows.append([i, sha[:8], r if r is not None else "?",
                     "Y" if oversize.get(sha) else "",
                     "Y" if dup_flag.get(sha) else "",
                     "" if cv is None else f"{cv:.0f}",
                     "ROT" if rot else "", ",".join(signals)])

    print_table(["idx", "sha", "regr", "oversz", "dupjmp", "cov", "flag", "signals"], rows)

    collapse_idx = None
    for i in range(len(rot_flags) - 1):
        if rot_flags[i] and rot_flags[i + 1]:
            collapse_idx = i
            break

    if collapse_idx is None:
        print("\nNo sustained collapse detected (no two consecutive rot-onset commits).")
    else:
        print(f"\nCOLLAPSE POINT: feature index {collapse_idx} "
              f"(sha {dup_list[collapse_idx]['sha'][:8]})")
        print(f"Verified-working features before collapse are counted up to idx {collapse_idx}.")

    with open("collapse.json", "w") as f:
        json.dump({"collapse_index": collapse_idx,
                   "rot_flags": rot_flags,
                   "params": vars(args)}, f, indent=2)
    print("wrote collapse.json")


if __name__ == "__main__":
    main()
