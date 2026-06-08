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
    """Return {test_id: state} where state is 'pass' | 'fail' | 'skip'.

    Skips are tracked distinctly: a skipped test is neither a pass nor a fail, and must not
    pollute the pass->fail regression comparison or the removed-test count (tests skip in/out
    across commits depending on env/network, which is not a regression and not a deletion).
    """
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
        children = [child.tag for child in tc]
        status = tc.attrib.get("status", "").lower()
        if "skipped" in children or status in ("skipped", "notrun", "disabled"):
            results[tid] = "skip"
        elif any(t in ("failure", "error") for t in children) or (
                status and status not in ("passed", "run", "")):
            results[tid] = "fail"
        else:
            results[tid] = "pass"
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
    # last_pass[t] = True once we've seen t pass; only flips off when we count a regression for it.
    last_pass = {}
    # ever_seen tracks any test_id we've observed in a non-skip state (to detect genuine drops).
    ever_seen = set()
    prev_exit = None

    try:
        for i, (sha, subj) in enumerate(commits):
            checkout(repo, sha)
            exit_code = run_tests(repo, cmd, junit_path)

            if fmt == "exit-code":
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

            present_nonskip = {t for t, s in cur.items() if s != "skip"}

            # REGRESSION: a test that previously passed is now present AND failing.
            regressions = [t for t, s in cur.items()
                           if s == "fail" and last_pass.get(t)]

            # DROPPED: a test that previously passed is now entirely absent (not skipped, gone).
            # This is the deletion-to-hide-a-failure case the old script missed. Skips don't count.
            dropped = [t for t in last_pass
                       if last_pass[t] and t not in cur]

            new_tests = [t for t in present_nonskip if t not in ever_seen]
            skipped_now = [t for t, s in cur.items() if s == "skip"]

            # advance state
            for t, s in cur.items():
                if s == "pass":
                    last_pass[t] = True
                    ever_seen.add(t)
                elif s == "fail":
                    ever_seen.add(t)
                    if last_pass.get(t):
                        last_pass[t] = False  # counted once; don't double-count while it stays red
                # skip: leave last_pass untouched (don't treat as pass or fail)
            # a dropped test should stop counting after we've flagged it once
            for t in dropped:
                last_pass[t] = False

            results.append({
                "idx": i, "sha": sha, "subject": subj,
                "n_tests_present": len(cur),
                "n_nonskip": len(present_nonskip),
                "n_skipped": len(skipped_now),
                "regressions_introduced": len(regressions),
                "regressed_tests": regressions,
                "dropped_passing_tests": len(dropped),
                "dropped_tests": dropped[:20],  # cap list size
                "new_tests": len(new_tests),
            })
    finally:
        restore(repo, origin)

    rows = []
    total_reg = 0
    total_dropped = 0
    for r in results:
        reg = r.get("regressions_introduced")
        if isinstance(reg, int):
            total_reg += reg
        drp = r.get("dropped_passing_tests", 0)
        if isinstance(drp, int):
            total_dropped += drp
        rows.append([r["idx"], r["sha"][:8],
                     r.get("n_nonskip", r.get("n_tests", "-")),
                     "?" if reg is None else reg,
                     drp if r.get("dropped_passing_tests") is not None else "-",
                     r.get("new_tests", "-"),
                     r["subject"][:34]])
    print_table(["idx", "sha", "#tests", "regr", "drop", "new", "subject"], rows)
    print(f"\ntotal regressions (pass->fail in place): {total_reg}")
    print(f"total dropped passing tests (deleted while green): {total_dropped}")
    if total_dropped:
        print("*** NOTE: dropped passing tests can indicate failures hidden by deletion. "
              "Inspect the 'dropped_tests' lists before trusting a low regression count. ***",
              file=sys.stderr)

    with open("regression_count.json", "w") as f:
        json.dump({"total_regressions": total_reg,
                   "total_dropped_passing": total_dropped,
                   "commits": results}, f, indent=2)
    print("wrote regression_count.json")


if __name__ == "__main__":
    main()