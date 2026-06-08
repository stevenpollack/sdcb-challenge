# Per-deployment notes (delete after reading)

This repo is a GitHub *template*. Each benchmark run = one repo generated from it.

Before/at deploy:
- Generate a new repo from the template (GitHub: "Use this template").
- Optionally rename to encode the model under test, e.g. `matrix-tui-bench-opus-4-8-run1`.
- Provide `.env.local` to the run environment with real matrix.org test credentials (never commit).
- EXTENSION_TASKS.md is intentionally NOT in this template. Keep it in a separate private repo and
  use it only during the post-run extensibility test.

After the run (evaluator):
- The model should have tagged `run-complete`. If it didn't (it may have degraded near the time
  limit), tag the final commit yourself: `git tag run-complete <sha> && git push origin run-complete`.
- Trigger the analysis: Actions tab → `post-run-analysis` → Run workflow (defaults to the
  `run-complete` tag; override `ref` if needed). Or run the scripts locally per the root README.
- Before trusting trends: `cp eval/eval.config.example.json eval/eval.config.json` and adjust
  `source_globs` / `complexity.source_dirs` to the stack the model used, if it isn't `src/`.
- Recalibrate collapse thresholds against the git history before trusting the collapse index.

## Live functional check (the actual pass/fail)

Run AFTER freezing the repo, against the real homeserver, with your TWO test accounts:

```
export MATRIX_HOMESERVER=https://matrix.org
export MATRIX_USER_A=@testuser1:matrix.org  MATRIX_PASS_A=...
export MATRIX_USER_B=@testuser2:matrix.org  MATRIX_PASS_B=...
make setup                     # install the model's deps so `make run` works
python eval/scripts/live_sync_check.py --timeout 30 --tui-cmd "make run"
```

- CHECK 1 (server truth) failing = your infra/creds problem, not the model's. Fix and rerun.
- CHECK 2 (model TUI receives a live message) failing = functional FAIL for the submission,
  regardless of coverage/regressions/collapse. This is what catches "passes its own mock, not the
  real server."
- Use `--server-only` to validate infra before a run.
- The script feeds the model A's credentials via env (MATRIX_USER/PASSWORD) exactly as `.env.local`
  did during the run. If the model reads credentials under different names, pass a matching
  `--tui-cmd` wrapper or adjust the env in the script's `env_for_tui`.
- Also do the manual rendering check: launch the TUI, confirm the input box is visible/focusable
  and messages render. A launching app is not necessarily usable.