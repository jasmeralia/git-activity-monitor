# Agent Instructions

## Branching and Pull Requests

Never commit directly to `master`. All changes must go on a feature branch and be merged via a pull request:

1. Create a branch: `git checkout -b feat/short-description`
2. Commit changes on the branch
3. Push the branch: `git push -u origin feat/short-description`
4. Open a PR with `gh pr create`
5. Monitor CI and Release workflows to completion before reporting done

## Required Verification for All Code Changes

After any code change, always run:

    make lintfix && make lint && make test

This runs:
1. `ruff format` + `ruff check --fix` — auto-format and fix lintable issues
2. `ruff check` + `mypy` + `pylint` — full lint pass with no auto-fix
3. `pytest` with coverage — must pass with ≥ 80% coverage

Do not commit or submit changes that fail any of these checks.

## After Merging a Pull Request

After merging any PR, always monitor the resulting GitHub Actions runs to completion:

    gh run watch <run-id>

Check both the CI run (triggered by the merge commit) and the Release run (triggered by CI success). Do not report the merge as complete until all workflows have passed. If a workflow fails, investigate the logs with `gh run view <run-id> --log-failed` and fix the issue.

After all workflows pass, switch the working copy back to master and pull:

    git checkout master && git pull origin master
