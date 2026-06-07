#!/usr/bin/env python3
"""Commit size distribution over time.

For each commit (oldest-first), counts source lines added+deleted (excluding lockfiles/generated
per config). Reports per-commit sizes, the median of the first third of the project, and flags
commits exceeding 2x that median (the 'discipline collapse' signal used by the collapse rule).

Usage: python scripts/commit_size.py [config.json]
Writes commit_size.json and prints a table.
"""
import json
import sys
from statistics import median

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from _common import load_config, git, all_commits_chrono, is_source, print_table


def commit_churn(repo, sha, cfg):
    # --numstat gives "added<TAB>deleted<TAB>path" per file; binary files show "-".
    raw = git(repo, "show", "--numstat", "--format=", sha)
    total = 0
    for line in raw.splitlines():
        parts = line.split("\t")
        if len(parts) != 3:
            continue
        added, deleted, path = parts
        if added == "-" or deleted == "-":
            continue
        if not is_source(path, cfg):
            continue
        total += int(added) + int(deleted)
    return total


def main():
    cfg_path = sys.argv[1] if len(sys.argv) > 1 else "eval.config.json"
    cfg = load_config(cfg_path)
    repo = cfg["repo_path"]

    commits = all_commits_chrono(repo)
    sizes = [(sha, subj, commit_churn(repo, sha, cfg)) for sha, subj in commits]

    n = len(sizes)
    first_third = [s for _, _, s in sizes[: max(1, n // 3)]]
    base_median = median(first_third) if first_third else 0
    threshold = 2 * base_median

    rows = []
    for i, (sha, subj, size) in enumerate(sizes):
        flag = "OVERSIZE" if base_median and size > threshold else ""
        rows.append([i, sha[:8], size, flag, subj[:48]])

    print_table(["idx", "sha", "churn", "flag", "subject"], rows)
    print(f"\nfirst-third median churn: {base_median}  | oversize threshold (2x): {threshold}")

    out = {
        "base_median_first_third": base_median,
        "oversize_threshold": threshold,
        "commits": [
            {"idx": i, "sha": sha, "subject": subj, "churn": size,
             "oversize": bool(base_median and size > threshold)}
            for i, (sha, subj, size) in enumerate(sizes)
        ],
    }
    with open("commit_size.json", "w") as f:
        json.dump(out, f, indent=2)
    print("\nwrote commit_size.json")


if __name__ == "__main__":
    main()
