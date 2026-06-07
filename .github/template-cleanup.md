# Per-deployment notes (delete after reading)

This repo is a GitHub *template*. Each benchmark run = one repo generated from it.

Before/at deploy:
- Generate a new repo from the template (GitHub: "Use this template").
- Optionally rename to encode the model under test, e.g. `matrix-tui-bench-opus-4-8-run1`.
- Provide `.env.local` to the run environment with real matrix.org test credentials (never commit).
- EXTENSION_TASKS.md is intentionally NOT in this template. Keep it in a separate private repo and
  use it only during the post-run extensibility test.

After the run (evaluator):
- `cp eval/eval.config.example.json eval/eval.config.json`, adjust `source_globs` and
  `complexity.source_dirs` to the stack the model used.
- Run the harness scripts from the repo root (see root README).
- Recalibrate collapse thresholds against the git history before trusting the collapse index.
