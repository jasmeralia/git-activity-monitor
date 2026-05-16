.DEFAULT_GOAL := help
VENV          := .venv
PIP           := $(VENV)/bin/pip
RUFF          := $(VENV)/bin/ruff
MYPY          := $(VENV)/bin/mypy
PYLINT        := $(VENV)/bin/pylint
PYTEST        := $(VENV)/bin/pytest
SCRIPTS_DIR   := scripts

.PHONY: help setup lint-fix lint test shellcheck hadolint all-checks

help:        ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*##' $(MAKEFILE_LIST) | \
	  awk 'BEGIN {FS = ":.*## "}; {printf "  %-15s %s\n", $$1, $$2}'

setup:       ## Create .venv and install all deps including dev
	python3 -m venv $(VENV)
	$(PIP) install --upgrade pip
	$(PIP) install -e ".[dev]"
	@# Symlink so mypy/pylint can resolve 'git_activity_monitor' to src/
	@test -e git_activity_monitor || ln -s src git_activity_monitor

lint-fix:    ## Auto-fix formatting and import order (ruff format + ruff check --fix)
	$(RUFF) format src/ tests/
	$(RUFF) check --fix src/ tests/

lint:        ## Full lint pass: ruff, mypy, pylint (no auto-fix)
	$(RUFF) check src/ tests/
	$(MYPY) -p git_activity_monitor
	$(PYLINT) git_activity_monitor

test:        ## Run pytest with coverage (minimum 80%)
	$(PYTEST) tests/ \
	  --cov=git_activity_monitor \
	  --cov-report=term-missing \
	  --cov-report=xml:coverage.xml \
	  --cov-fail-under=80 \
	  -v

shellcheck:  ## Lint shell scripts in scripts/
	@if command -v shellcheck >/dev/null 2>&1; then \
	  find $(SCRIPTS_DIR) -name '*.sh' -print0 | xargs -r -0 shellcheck; \
	else \
	  echo "shellcheck not installed; skipping (runs in CI)"; \
	fi

hadolint:    ## Lint Dockerfile
	@if command -v hadolint >/dev/null 2>&1; then \
	  hadolint Dockerfile; \
	else \
	  echo "hadolint not installed; skipping (runs in CI via action)"; \
	fi

all-checks: lint shellcheck hadolint test  ## Run all checks
