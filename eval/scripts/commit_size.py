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
    # Oversize should mean "unusually large FOR THIS PROJECT", not "larger than the empty scaffold".
    # Basing the threshold on the first third compares real feature commits against initial/scaffold
    # commits (near-zero churn), so everything trips. Use the median of substantive (nonzero-churn)
    # commits instead.
    nonzero = [s for _, _, s in sizes if s > 0]
    base_median = median(nonzero) if nonzero else 0
    threshold = 3 * base_median  # 3x the typical substantive commit

    rows = []
    for i, (sha, subj, size) in enumerate(sizes):
        flag = "OVERSIZE" if base_median and size > threshold else ""
        rows.append([i, sha[:8], size, flag, subj[:48]])

    print_table(["idx", "sha", "churn", "flag", "subject"], rows)
    print(f"\nnonzero median churn: {base_median}  | oversize threshold (3x): {threshold}")

    total_churn = sum(s for _, _, s in sizes)
    if total_churn == 0 and len(sizes) > 1:
        print("\n*** WARNING: total source churn across ALL commits is 0. This almost certainly\n"
              "    means source_globs does not match where the code lives. Check eval.config.json\n"
              "    'source_globs' against the model's actual layout — the commit-size signal is\n"
              "    meaningless until this is fixed. ***", file=sys.stderr)

    out = {
        "base_median_nonzero": base_median,
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