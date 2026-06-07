#!/usr/bin/env python3
"""Coverage trend across feature commits.

Runs `make coverage` (configurable) at each feature commit and parses total line coverage from the
report whose path/format are declared in the target repo's eval.meta.json (config fallbacks apply).
Declining coverage as the project grows is the testing-decay signal feeding the collapse rule.

This is the slowest script (installs deps / runs the suite per commit). Consider a dependency
cache. If a commit's suite errors, coverage is recorded as null for that point.

Supported report_format: jest-json-summary, coverage-py-json, cobertura-xml, lcov.
Usage: python scripts/coverage_trend.py [config.json]
Restores original HEAD on exit. Writes coverage_trend.json.
"""
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from _common import (load_config, load_meta, feature_commits, checkout, current_ref,
                     restore, print_table)


def parse_coverage(report_path, fmt):
    if not os.path.exists(report_path):
        return None
    try:
        if fmt == "jest-json-summary":
            with open(report_path) as f:
                d = json.load(f)
            return d["total"]["lines"]["pct"]
        if fmt == "coverage-py-json":
            with open(report_path) as f:
                d = json.load(f)
            return d["totals"]["percent_covered"]
        if fmt == "cobertura-xml":
            import xml.etree.ElementTree as ET
            root = ET.parse(report_path).getroot()
            return float(root.attrib["line-rate"]) * 100
        if fmt == "lcov":
            hit = found = 0
            with open(report_path) as f:
                for line in f:
                    if line.startswith("LH:"):
                        hit += int(line[3:])
                    elif line.startswith("LF:"):
                        found += int(line[3:])
            return (hit / found * 100) if found else None
    except (KeyError, ValueError, OSError):
        return None
    return None


def main():
    cfg_path = sys.argv[1] if len(sys.argv) > 1 else "eval.config.json"
    cfg = load_config(cfg_path)
    repo = cfg["repo_path"]
    meta = load_meta(repo, cfg)
    cmd = cfg.get("make", {}).get("coverage", "make coverage")
    report_path = meta["coverage_report"]
    fmt = meta["coverage_format"]
    if not report_path:
        sys.exit("no coverage report path (set in target repo's eval.meta.json or config fallback)")

    commits = feature_commits(repo, cfg)
    origin = current_ref(repo)
    results = []
    try:
        for i, (sha, subj) in enumerate(commits):
            checkout(repo, sha)
            if os.path.exists(report_path):
                os.remove(report_path)
            subprocess.run(cmd, shell=True, cwd=repo, capture_output=True, text=True)
            pct = parse_coverage(report_path, fmt)
            results.append({"idx": i, "sha": sha, "subject": subj, "coverage_pct": pct})
    finally:
        restore(repo, origin)

    pcts = [r["coverage_pct"] for r in results if r["coverage_pct"] is not None]
    cov_max = max(pcts) if pcts else None
    rows = []
    for r in results:
        p = r["coverage_pct"]
        drop = "" if (p is None or cov_max is None) else f"{p - cov_max:+.1f}"
        rows.append([r["idx"], r["sha"][:8],
                     "n/a" if p is None else f"{p:.1f}", drop, r["subject"][:40]])
    print_table(["idx", "sha", "cov%", "vs_max", "subject"], rows)
    print(f"\nproject max coverage: {cov_max}")

    with open("coverage_trend.json", "w") as f:
        json.dump({"max": cov_max, "commits": results}, f, indent=2)
    print("wrote coverage_trend.json")


if __name__ == "__main__":
    main()
