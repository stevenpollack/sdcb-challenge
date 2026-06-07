#!/usr/bin/env python3
"""Code duplication trend across feature commits.

Checks out each feature commit, runs jscpd (polyglot copy-paste detector) over the configured
source dirs, and records duplicated-lines percentage. Rising duplication as the project grows is
the copy-paste-rot signal.

Requires jscpd on PATH:  npm i -g jscpd
Usage: python scripts/duplication_trend.py [config.json]
Restores the original branch/HEAD on exit. Writes duplication_trend.json.
"""
import json
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from _common import (load_config, feature_commits, checkout, current_ref,
                     restore, have, print_table)


def run_jscpd(repo, source_dirs):
    with tempfile.TemporaryDirectory() as td:
        paths = [os.path.join(repo, d) for d in source_dirs]
        paths = [p for p in paths if os.path.exists(p)]
        if not paths:
            return None
        cmd = ["jscpd", "--silent", "--reporters", "json", "--output", td, *paths]
        r = subprocess.run(cmd, capture_output=True, text=True)
        report = os.path.join(td, "jscpd-report.json")
        if not os.path.exists(report):
            return None
        with open(report) as f:
            data = json.load(f)
        # jscpd stats.total.percentage = % duplicated lines
        return data.get("statistics", {}).get("total", {}).get("percentage")


def main():
    cfg_path = sys.argv[1] if len(sys.argv) > 1 else "eval.config.json"
    cfg = load_config(cfg_path)
    repo = cfg["repo_path"]
    source_dirs = cfg.get("duplication", {}).get("source_dirs", ["src"])

    if not have("jscpd"):
        sys.exit("jscpd not found on PATH. Install with: npm i -g jscpd")

    commits = feature_commits(repo, cfg)
    origin = current_ref(repo)
    results = []
    try:
        for i, (sha, subj) in enumerate(commits):
            checkout(repo, sha)
            pct = run_jscpd(repo, source_dirs)
            results.append({"idx": i, "sha": sha, "subject": subj, "dup_pct": pct})
    finally:
        restore(repo, origin)

    rows = []
    prev = None
    for r in results:
        pct = r["dup_pct"]
        delta = "" if (pct is None or prev is None) else f"{pct - prev:+.1f}"
        rows.append([r["idx"], r["sha"][:8],
                     "n/a" if pct is None else f"{pct:.1f}", delta, r["subject"][:40]])
        if pct is not None:
            prev = pct
    print_table(["idx", "sha", "dup%", "delta", "subject"], rows)

    with open("duplication_trend.json", "w") as f:
        json.dump(results, f, indent=2)
    print("\nwrote duplication_trend.json")


if __name__ == "__main__":
    main()
