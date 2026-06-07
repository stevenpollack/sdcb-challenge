#!/usr/bin/env python3
"""Regression count across feature commits.

WHAT 'REGRESSION' MEANS HERE
----------------------------
A regression is a test that PASSED at an earlier commit and FAILS at a later one. This is the only
definition that survives an evolving suite: you cannot compare a commit's failures to a fixed
baseline, because tests are added and removed as the project grows. So we track each test by a
stable id and watch for pass -> fail transitions.

The hard part abstractly is getting a per-test pass/fail map out of an arbitrary test runner. We
solve it by requiring a machine-readable test report (JUnit XML — emitted by virtually every
runner: pytest --junitxml, jest-junit, go test via gotestsum, cargo nextest, vitest, mocha, etc).
The config's test_command must produce one. We parse <testcase> nodes; a testcase with a <failure>
or <error> child, or status!=passed, is a fail.

Per feature commit we compute:
  - regressions_introduced: tests that passed at the previous evaluated commit and fail now
  - newly_passing / new_tests / removed_tests (context, not penalized)
A test only counts as a regression once (at the commit where it broke), not repeatedly while it
stays broken — we advance the 'last known good' map forward.

The test command is `make test-report` (the model is required to provide this target; it must emit
JUnit XML). The JUnit path is read from the target repo's eval.meta.json ("junit_report"). If a
runner genuinely cannot emit JUnit, set test_report.format to "exit-code" in eval.config.json: we
fall back to suite exit code (0 = all pass), a coarse 0/1 'suite broke' signal per commit. Prefer
JUnit.

Relevant config (eval.config.json):
  "make": { "test_report": "make test-report" },
  "test_report": { "format": "junit" }        // or "exit-code"
and in the TARGET repo's eval.meta.json:
  { "junit_report": "junit.xml" }

Usage: python scripts/regression_count.py [config.json]
Restores original HEAD on exit. Writes regression_count.json.
"""
import json
import os
import subprocess
import sys
import xml.etree.ElementTree as ET

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from _common import (load_config, load_meta, feature_commits, checkout, current_ref,
                     restore, print_table)


def parse_junit(path):
    """Return {test_id: passed_bool}. test_id = classname::name for stability."""
    if not os.path.exists(path):
        return None
    results = {}
    try:
        tree = ET.parse(path)
    except ET.ParseError:
        return None
    for tc in tree.iter("testcase"):
        cls = tc.attrib.get("classname", "")
        name = tc.attrib.get("name", "")
        tid = f"{cls}::{name}"
        failed = any(child.tag in ("failure", "error") for child in tc)
        status = tc.attrib.get("status", "")
        if status and status.lower() not in ("passed", "run", ""):
            failed = True
        results[tid] = not failed
    return results


def run_tests(repo, cmd, junit_path):
    if junit_path and os.path.exists(junit_path):
        os.remove(junit_path)
    proc = subprocess.run(cmd, shell=True, cwd=repo, capture_output=True, text=True)
    return proc.returncode


def main():
    cfg_path = sys.argv[1] if len(sys.argv) > 1 else "eval.config.json"
    cfg = load_config(cfg_path)
    repo = cfg["repo_path"]
    meta = load_meta(repo, cfg)
    fmt = cfg.get("test_report", {}).get("format", "junit")
    cmd = cfg.get("make", {}).get("test_report", "make test-report")
    junit_path = meta["junit_report"]
    if fmt == "junit" and not junit_path:
        sys.exit("no junit report path (set junit_report in target repo's eval.meta.json)")

    commits = feature_commits(repo, cfg)
    origin = current_ref(repo)
    results = []
    last_good = {}   # test_id -> True, the most recent passing state we've seen
    prev_exit = None

    try:
        for i, (sha, subj) in enumerate(commits):
            checkout(repo, sha)
            exit_code = run_tests(repo, cmd, junit_path)

            if fmt == "exit-code":
                # coarse: regression = was-green, now-red
                regressed = 1 if (prev_exit == 0 and exit_code != 0) else 0
                prev_exit = exit_code
                results.append({"idx": i, "sha": sha, "subject": subj,
                                "suite_passed": exit_code == 0,
                                "regressions_introduced": regressed})
                continue

            cur = parse_junit(junit_path)
            if cur is None:
                results.append({"idx": i, "sha": sha, "subject": subj,
                                "error": "no junit report parsed",
                                "regressions_introduced": None})
                continue

            regressions = [t for t, passed_now in cur.items()
                           if not passed_now and last_good.get(t) is True]
            new_tests = [t for t in cur if t not in last_good]
            newly_passing = [t for t, p in cur.items()
                             if p and last_good.get(t) is False]
            removed = [t for t in last_good if t not in cur]

            # advance last_good: record current passing tests as the new known-good baseline
            for t, p in cur.items():
                if p:
                    last_good[t] = True
                else:
                    # keep its prior known-good status so it still counts as regressed until fixed-once
                    last_good.setdefault(t, False)
                    if last_good[t] is True:
                        last_good[t] = False  # mark broken so we don't double-count next commit

            results.append({
                "idx": i, "sha": sha, "subject": subj,
                "n_tests": len(cur),
                "regressions_introduced": len(regressions),
                "regressed_tests": regressions,
                "new_tests": len(new_tests),
                "newly_passing": len(newly_passing),
                "removed_tests": len(removed),
            })
    finally:
        restore(repo, origin)

    rows = []
    total_reg = 0
    for r in results:
        reg = r.get("regressions_introduced")
        if isinstance(reg, int):
            total_reg += reg
        rows.append([r["idx"], r["sha"][:8],
                     r.get("n_tests", "-"),
                     "?" if reg is None else reg,
                     r.get("new_tests", "-"),
                     r["subject"][:38]])
    print_table(["idx", "sha", "#tests", "regr", "new", "subject"], rows)
    print(f"\ntotal regressions introduced across history: {total_reg}")

    with open("regression_count.json", "w") as f:
        json.dump({"total_regressions": total_reg, "commits": results}, f, indent=2)
    print("wrote regression_count.json")


if __name__ == "__main__":
    main()
