# Matrix TUI Benchmark — Workspace

This is a benchmark workspace. You (the model under test) build a **terminal UI client for the
Matrix protocol** here, at the repository root. Your performance is evaluated afterward by the
harness in [`eval/`](eval/).

## Read first

- [`eval/PROMPT.md`](eval/PROMPT.md) — your task, constraints, and required artifacts. **Start here.**
- [`eval/EVALUATION.md`](eval/EVALUATION.md) — exactly how you will be scored. You are expected to
  read this; a clear picture of evaluation is fair to have.

## Where to work

- Build your application at the **repository root** (e.g. `src/`, `tests/`, your own layout).
- **Do not modify anything under `eval/`.** Those are the harness and grading scripts.
- Fill in the placeholder files described below.

## Files you must provide or complete

| File | Status in template | What to do |
|---|---|---|
| `Makefile` | stub with required targets | implement each target's body (see stub comments) |
| `eval.meta.json` | example values | set your real report paths/formats |
| `FEATURES.md` | empty ledger | append a row per feature with honest status |
| `README` (yours) | this file | replace with your project's real README (setup must work from a clean checkout) |
| `.env.local` | not present | created for you at run time with test credentials; do not commit it |

## The contract the harness depends on

The grader calls your `Makefile` targets directly and reads `eval.meta.json` for report locations.
If a required target is missing or misbehaves, that capability fails. See `Makefile` and
`eval/PROMPT.md` for the exact list.

## Running the harness (evaluator only, after the run)

From the repository root:

```
python eval/scripts/commit_size.py        eval/eval.config.json
python eval/scripts/duplication_trend.py  eval/eval.config.json
python eval/scripts/complexity_trend.py   eval/eval.config.json
python eval/scripts/coverage_trend.py     eval/eval.config.json
python eval/scripts/regression_count.py   eval/eval.config.json
python eval/scripts/collapse.py
```

(Evaluator: copy `eval/eval.config.example.json` to `eval/eval.config.json` first and adjust
`source_globs` / `complexity.source_dirs` to match the stack the model chose.)
