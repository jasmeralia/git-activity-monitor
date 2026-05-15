# Agent Instructions

## Required Verification for All Code Changes

After any code change, always run:

    make lint-fix && make lint && make test

This runs:
1. `ruff format` + `ruff check --fix` — auto-format and fix lintable issues
2. `ruff check` + `mypy` + `pylint` — full lint pass with no auto-fix
3. `pytest` with coverage — must pass with ≥ 80% coverage

Do not commit or submit changes that fail any of these checks.
