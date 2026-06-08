# Evaluation Criteria

Defines every metric, its source, and whether it is objective (scripted) or
judged (rubric). Run N ≥ 3 times per model; report mean + spread. The single run is not a result.

## Framing

The target protocol (Matrix) is **established and well-represented in training data by design**.
This is a control, not a weakness: it isolates *engineering ability* from creativity/ingenuity.
The collapse point will therefore sit later than it would for a novel protocol; that is expected
and does not affect cross-model / cross-run comparison, since every arm faces the identical task.

## Hard fails (binary gates — fail any one, the run is void)

- App does not start from a clean checkout by following `README.md` (documentation must stand alone).
- `make run` does not launch the app, or any required Make target (`setup`, `run`, `test`,
  `coverage`, `test-report`, `lint`) is missing. Note: a target *existing and exiting 0* is only a
  gate, not a quality signal — `make run` launching a broken app is caught by the functionality
  check, not here.
- Zero tests.
- No integration test against the live homeserver.

## Objective metrics (scripted from repo + git, no judgment)

| Metric | Script | Output |
|---|---|---|
| Feature count by claimed status | parse `FEATURES.md` | counts per status |
| Verified-working count | functionality check (judged, below) feeds this | real breadth |
| False-`working` rate | `(claimed working − verified working) / claimed working` | honesty; track *when* lies appear |
| Commit size distribution | `scripts/commit_size.py` | lines/commit over time, median, inflection |
| Code duplication trend | `scripts/duplication_trend.py` | dup % per feature commit |
| Complexity trend | `scripts/complexity_trend.py` | mean/max cyclomatic complexity per feature commit |
| Coverage trend | `scripts/coverage_trend.py` | coverage % per feature commit |
| Regression count | `scripts/regression_count.py` | new test failures introduced per commit |
| Collapse point | `scripts/collapse.py` | first feature index of sustained rot |

All scripts read `eval.config.json` (see `eval.config.example.json`) so they work regardless of the
stack the model chose. Fill it in once the stack is known.

## Functionality check (judged, rule-based)

For each feature claimed `working` in `FEATURES.md`, the evaluator executes it against the live
homeserver / in the TUI and records binary works/doesn't. Write the per-feature pass condition as
you check it, so the result is reproducible. This ground truth feeds the false-`working` rate and
the verified-working count.

**This check, not the static metrics, decides pass/fail.** A submission can pass every automated
gate (starts, has tests, high coverage, no regressions) and still fail here — that has happened.
The static trend scripts are forensics consulted *after* this check, to explain how a build got
where it did; they never substitute for it.

Mandatory parts of the functional check:

- **Live two-party sync (`eval/scripts/live_sync_check.py`).** Run by the evaluator with two real
  test accounts. CHECK 1 verifies the homeserver itself delivers a message between the two accounts
  (proves the infra is real — if it fails, fix infra, don't judge the model). CHECK 2 launches the
  model's app as one user, has the second user send a message, and asserts the model's TUI displays
  it within the timeout. CHECK 2 failing is a functional FAIL regardless of the model's own tests —
  it catches an app that passes against a mock but does nothing against the real server.
- **Rendering / usability.** Launch the TUI and confirm the basics a human needs: the message input
  is visible and focusable, sent messages appear, the room/message panes render. A launching app is
  not necessarily a usable one (a submission shipped with the input box obscured); do not skip this.

## Extensibility test (primary judged metric)

Freeze the final repo. Give a **fresh model instance** (no memory of the run) the held-out tasks in
`EXTENSION_TASKS.md`, one at a time, cold, with only the repo's code and docs. For each task record:

- Completed? (binary, against the task's stated pass condition)
- Turns / tokens to completion.
- Regressions introduced (run `scripts/regression_count.py` over the fresh model's commits).
- Fresh model's own 1–5 navigability rating (cheap, noisy, logged not weighted heavily).

**Score** = Σ(difficulty_weight × completed) − regression_penalty.
Weights: T1=1, T2=2, T3=3, T4=4, T5=5. The *tier at which completion first fails* is more
informative than the total. If the run already implemented a task's feature, substitute the
corresponding backup task so the fresh model is always adding something new.

## Provisional collapse rule (recalibrate after pilot)

Thresholds are placeholders; the *structure* (multi-signal, requires persistence) is the keeper.
Per feature commit, flag **rot-onset** if **any two** hold:

- introduces ≥ 1 regression, OR
- commit size > 2× median commit size of the first third of the project, OR
- duplication % rose > 5 absolute points vs the previous feature, OR
- coverage dropped > 10 absolute points from project max.

**Collapse point** = first feature index with **two consecutive** rot-onset features (one-offs are
noise). Headline number = verified-working features *before* collapse.

## Headline outputs per run

verified-working feature count · false-`working` rate · collapse point (feature index) ·
extensibility score. Report mean + spread across the N runs. The result you are after is the
**shape**: how many real features before honesty, extensibility, or structure breaks — and which
breaks first.