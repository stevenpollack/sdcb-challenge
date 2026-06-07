# Makefile contract for the benchmark harness.
#
# The grader calls these targets directly, regardless of your stack. Implement each target's
# body. Replace the `@echo ... && exit 1` lines with real commands. Do NOT rename or remove
# targets, and keep their behavioral contract:
#
#   setup        install all dependencies from a clean checkout
#   run          launch the TUI
#   test         run the full suite; MUST exit non-zero if any test fails
#   coverage     run tests with coverage; write the report to the path you declare in eval.meta.json
#   test-report  run tests emitting JUnit XML to the path you declare in eval.meta.json
#   lint         run your linter/formatter check (may be a no-op, but must exist and exit 0)
#
# After implementing, also set the real report paths in eval.meta.json.

.PHONY: setup run test coverage test-report lint

setup:
	@echo "TODO: implement 'make setup' (install dependencies)" && exit 1

run:
	@echo "TODO: implement 'make run' (launch the TUI)" && exit 1

test:
	@echo "TODO: implement 'make test' (must exit non-zero on failure)" && exit 1

coverage:
	@echo "TODO: implement 'make coverage' (write report path from eval.meta.json)" && exit 1

test-report:
	@echo "TODO: implement 'make test-report' (emit JUnit XML to path in eval.meta.json)" && exit 1

lint:
	@echo "TODO: implement 'make lint' (may be a no-op that exits 0)" && exit 1
