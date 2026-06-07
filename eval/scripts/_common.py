"""Shared helpers for the eval scripts. Stdlib only."""
import json
import os
import subprocess
import sys
from fnmatch import fnmatch
import re

def load_config(path="eval.config.json"):
    if not os.path.exists(path):
        sys.exit(f"config not found: {path} (copy eval.config.example.json and fill it in)")
    with open(path) as f:
        return json.load(f)


def git(repo, *args):
    """Run a git command in repo, return stdout (stripped)."""
    out = subprocess.run(
        ["git", "-C", repo, *args],
        capture_output=True, text=True,
    )
    if out.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {out.stderr.strip()}")
    return out.stdout


def all_commits_chrono(repo):
    """List of (sha, subject) oldest-first."""
    raw = git(repo, "log", "--reverse", "--pretty=format:%H%x00%s")
    rows = []
    for line in raw.splitlines():
        if "\x00" in line:
            sha, subject = line.split("\x00", 1)
            rows.append((sha, subject))
    return rows


def feature_commits(repo, cfg):
    """Subset of commits that count as 'features', per config. Oldest-first."""
    commits = all_commits_chrono(repo)
    fc = cfg.get("feature_commits", {"mode": "all"})
    if fc.get("mode") == "all":
        return commits
    if fc.get("mode") == "exclude":
        rx = re.compile(fc["exclude_regex"])
        return [(s, subj) for (s, subj) in commits if not rx.search(subj)]
    rx = re.compile(fc["subject_regex"])
    return [(s, subj) for (s, subj) in commits if rx.search(subj)]


def matches_any(path, globs):
    return any(fnmatch(path, g) for g in globs)


def is_source(path, cfg):
    inc = cfg.get("source_globs", ["**"])
    exc = cfg.get("exclude_globs", [])
    if matches_any(path, exc):
        return False
    return matches_any(path, inc)


def checkout(repo, sha):
    git(repo, "checkout", "--quiet", sha)


def current_ref(repo):
    """Remember where HEAD is so we can restore it."""
    try:
        return git(repo, "symbolic-ref", "--quiet", "--short", "HEAD").strip()
    except RuntimeError:
        return git(repo, "rev-parse", "HEAD").strip()


def restore(repo, ref):
    git(repo, "checkout", "--quiet", ref)


def have(cmd):
    """Is an executable on PATH?"""
    from shutil import which
    return which(cmd) is not None


def load_meta(repo, cfg):
    """Read the target repo's eval.meta.json (written by the model), with config fallbacks.

    Returns dict with coverage_report, coverage_format, junit_report (absolute paths for the
    *_report fields).
    """
    meta = {}
    meta_path = os.path.join(repo, cfg.get("meta_file", "eval.meta.json"))
    if os.path.exists(meta_path):
        with open(meta_path) as f:
            meta = json.load(f)
    cov_report = meta.get("coverage_report", cfg.get("fallback_coverage_report"))
    cov_format = meta.get("coverage_format", cfg.get("fallback_coverage_format"))
    junit = meta.get("junit_report", cfg.get("fallback_junit_report"))
    return {
        "coverage_report": os.path.join(repo, cov_report) if cov_report else None,
        "coverage_format": cov_format,
        "junit_report": os.path.join(repo, junit) if junit else None,
    }


def print_table(headers, rows):
    widths = [len(h) for h in headers]
    for r in rows:
        for i, c in enumerate(r):
            widths[i] = max(widths[i], len(str(c)))
    fmt = "  ".join("{:<" + str(w) + "}" for w in widths)
    print(fmt.format(*headers))
    print(fmt.format(*["-" * w for w in widths]))
    for r in rows:
        print(fmt.format(*[str(c) for c in r]))