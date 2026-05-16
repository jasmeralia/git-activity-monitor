# Design: GitHub Activity Monitor

## Overview

A Dockerized Python polling service that watches GitHub repositories and posts activity updates to Discord. It polls on a schedule and sends notifications for stars/watches, pull requests, issues, releases, and GHCR package versions.

## Architecture

```
main.py (polling loop)
  ├── config.py        — pydantic-settings: reads .env, validates all settings
  ├── state.py         — atomic JSON persistence: tracks last-seen values per repo
  ├── github_client.py — httpx + tenacity: GitHub REST API calls with retry
  ├── discord_client.py— httpx + tenacity: Discord webhook send + edit
  └── monitors/
      ├── stars.py     — star/watch counts → edits pinned summary message
      ├── pulls.py     — new PRs → batched Discord message
      ├── issues.py    — new issues → batched Discord message
      ├── releases.py  — new releases → batched Discord message
      └── ghcr.py      — new container versions → batched Discord message
```

## Source Layout

Source files live directly in `src/` (not `src/git_activity_monitor/`). The `package-dir` mapping in `pyproject.toml` maps the `git_activity_monitor` package name to `src/`, so imports work as `from git_activity_monitor.config import Settings` while files are at `src/config.py`.

## State Schema

```json
{
  "version": 1,
  "pinned_message_id": "1234567890123456789",
  "repos": {
    "owner/repo": {
      "stars": 142,
      "watches": 8,
      "last_pr_number": 73,
      "last_issue_number": 51,
      "last_release_id": 189023456
    }
  },
  "ghcr": {
    "owner/package": {
      "seen_versions": ["1.0.0", "1.1.0", "latest"]
    }
  }
}
```

State is written atomically (write to `.tmp` sibling, then `os.replace()`). On load, if the file contains invalid JSON or an unexpected schema (non-dict top level, wrong key types), it is renamed to `state.json.corrupt` and the service starts fresh.

## Owner-Based Repository Discovery

`Settings` accepts an `OWNERS` list (comma-separated GitHub usernames or org names) in addition to the explicit `REPOSITORIES` list. At least one must be set.

At the start of every polling cycle, `_effective_repositories()` in `main.py`:

1. For each owner, calls `GitHubClient.get_owner_repos(owner)`, which uses a three-tier strategy:
   - Tries `/user/repos?affiliation=owner` (authenticated; returns private repos), filtered to rows where `owner.login` matches the requested owner.
   - Falls back to `/orgs/{owner}/repos?type=all` on 404 (org accounts sometimes 404 on the `/user/` endpoint).
   - Falls back to `/users/{owner}/repos?type=owner` as a last resort (public only).
2. Filters out any repo where `fork=True` or `archived=True`.
3. Deduplicates using insertion-order-preserving logic (owner repos first, then explicit repos).
4. Passes the resolved list to monitors via `settings.model_copy(update={"repositories": effective})` so the rest of the codebase needs no changes.

If a repo discovery call fails, that owner is skipped with an exception log and the cycle continues with whatever repos are available. New repositories under a monitored owner are picked up on the next cycle without a restart.

## Key Design Decisions

### State advanced only after Discord success

If Discord is down, changes accumulate and are batched on recovery. Missed notifications are worse than delayed batches. Duplicate notifications (state saved but Discord silently dropped the message) are an accepted edge case.

### First-run initialization

Numeric cursors (`last_pr_number`, `last_issue_number`, `last_release_id`) default to `-1` in a freshly created `RepoState`. Any value `< 0` triggers the initialization branch: the monitor fetches current items, sets the cursor to the current maximum (or `0` if there are none), saves state, and returns without notifying Discord. This prevents a notification flood on first deploy. Operators who want historical notifications should manually reset the state file.

### GHCR versions as a set

GHCR version tags are stored as a complete seen-set rather than a high-water mark because semver creation order is not monotonic (backport releases get older version numbers) and version tags can be re-pushed. The seen-set grows over time but is bounded by the actual number of package versions.

### Sync HTTP (no async)

`httpx.Client` (sync) is used throughout. A polling daemon that sleeps between cycles has no benefit from async I/O. Sync code is simpler to test and reason about.

### Batching

All batching monitors (pulls, issues, releases, ghcr) collect events across all configured repositories in one pass, then send a single Discord message (or multiple if the message would exceed Discord's 2000-character limit). Splitting happens at repository group boundaries.

### Stars and watches

"Stars" and "watches" both map to the same monitor function (`run_stars`) which makes one API call per repository. The main loop deduplicates by function identity so the monitor runs once even if both events are enabled.

### Discord message format

Plain text with Discord markdown (no embeds — embeds require a bot token, not a webhook). Timestamps use Discord's `<t:UNIX:R>` relative format.

## Retry Strategy

`GitHubClient` uses `tenacity` with exponential backoff (2s → 60s max, 5 attempts) for 429, 5xx, and network errors. GitHub secondary rate limits (403 with `Retry-After`) are also retried.

`DiscordClient` does not use `tenacity`. Discord 429 responses include a `X-RateLimit-Reset-After` header with a variable delay, so 429s are handled with an inline sleep-and-retry loop (up to 3 retries). After 3 retries the exception is raised. All other errors propagate immediately.

## Polling Loop

The sleep between cycles is interruptible (1-second increments checking a `shutdown` flag). SIGTERM and SIGINT set the flag; the loop exits cleanly after the current cycle completes.

Each monitor runs inside a try/except. Permanent failures (HTTP 401/403/404 from the GitHub or Discord API) are logged at `CRITICAL` level with a message identifying the misconfiguration. All other exceptions are logged at `ERROR` and the loop continues with the next monitor. The container does not stop on any monitor failure.

## Docker

Multi-stage build: `builder` installs dependencies with `--prefix=/install`, `final` copies only the installed files and the source. Runs as non-root user `monitor` (uid 1001). State volume at `/data`.

## Versioning

Git tags follow semver (`v1.2.3`). Docker image tags strip the `v` prefix (`1.2.3` and `latest`). Tags are auto-created on push to `master` by `mathieudutour/github-tag-action` using conventional commit prefixes.
