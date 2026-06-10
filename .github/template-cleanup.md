# Per-deployment notes (delete after reading)

This repo is a GitHub *template*. Each benchmark run = one repo generated from it.

Before/at deploy:
- Generate a new repo from the template (GitHub: "Use this template").
- Optionally rename to encode the model under test, e.g. `matrix-tui-bench-opus-4-8-run1`.
- Provide `.env.local` to the run environment with real matrix.org test credentials (never commit).
- **MANDATORY before the model starts: validate `.env.local` parses and both accounts log in.**
  A malformed `.env.local` silently contaminates the run — the model can't verify its own work, and
  you can't cleanly attribute any resulting failure to the model vs. your credentials file. This has
  already cost one run's clean attribution. Run:
  ```
  python eval/scripts/live_sync_check.py --server-only
  ```
  CHECK 1 must PASS. If it fails, the file shape or credentials are wrong — fix before the model
  starts. Never begin a run on an `.env.local` that has not passed CHECK 1.
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

Run AFTER freezing the repo, against the real homeserver. Credentials are read from `.env.local`
by default (the file the model already used), so no exports are needed:

```
make setup                     # install the model's deps so `make run` works
python eval/scripts/live_sync_check.py --timeout 30 --tui-cmd "make run"
```

To grade with a SEPARATE evaluator pair instead of the model's accounts, override via env vars
(they take precedence over `.env.local`) or point at another dotenv file:

```
MATRIX_USER_A=@evaluator1:matrix.org MATRIX_PASSWORD_A=... \
MATRIX_USER_B=@evaluator2:matrix.org MATRIX_PASSWORD_B=... \
python eval/scripts/live_sync_check.py --tui-cmd "make run"
# or:  python eval/scripts/live_sync_check.py --env-file .env.evaluator --tui-cmd "make run"
```

- CHECK 1 (server truth) failing = your infra/creds problem, not the model's. Fix and rerun.
- CHECK 2 (model TUI receives a live message) failing = functional FAIL for the submission,
  regardless of coverage/regressions/collapse. This is what catches "passes its own mock, not the
  real server."
- Use `--server-only` to validate infra before a run.
- The script feeds the model both accounts via env (MATRIX_USER_A/PASSWORD_A and
  MATRIX_USER_B/PASSWORD_B) under the same names as `.env.local`. If the model reads credentials
  under different names, pass a matching `--tui-cmd` wrapper or adjust `env_for_tui` in the script.
- Also do the manual rendering check: launch the TUI, confirm the input box is visible/focusable
  and messages render. A launching app is not necessarily usable.