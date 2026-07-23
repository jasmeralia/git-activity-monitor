# GitHub Activity Monitor

A Dockerized polling service that watches GitHub repositories and posts activity updates to Discord.

```
GitHub API ──► polling loop ──► Discord webhook
                    │
                    └──► state.json (persisted across restarts)
```

## What It Monitors

| Event | Discord behavior |
|---|---|
| Stars / Watchers | Edits a pinned summary message; one notification per cycle |
| New Pull Requests | One batched message per cycle listing all new PRs |
| New Issues | One batched message per cycle listing all new issues |
| New Releases | One batched message per cycle listing all new releases |
| New GHCR versions | One batched message per cycle listing all new container image versions |

## Prerequisites

- A GitHub personal access token (PAT)
- A Discord channel webhook URL
- Docker + Docker Compose (for deployment) or Python 3.12+ (for local dev)

---

## Getting a GitHub Token

1. Go to **GitHub → Settings → Developer settings → Personal access tokens → Fine-grained tokens**
2. Click **Generate new token**
3. Set a descriptive name and expiration
4. Under **Repository access**, select the repositories you want to monitor
5. Under **Permissions**, grant:
   - **Contents** → Read-only (for releases)
   - **Issues** → Read-only
   - **Pull requests** → Read-only
   - **Metadata** → Read-only (required, auto-selected)
6. Under **Account permissions**, grant:
   - **Packages** → Read-only (for GHCR monitoring)
7. Click **Generate token** and copy the value immediately

> **Note:** Classic tokens also work. Required scopes: `repo` (read) and `read:packages`.

---

## Getting a Discord Webhook URL

1. Open your Discord server and navigate to the channel where you want notifications
2. Click the gear icon (⚙) → **Integrations** → **Webhooks**
3. Click **New Webhook**, give it a name and optionally an avatar
4. Click **Copy Webhook URL**

---

## Configuration

Copy `.env.example` to `.env` and fill in your values:

```bash
cp .env.example .env
```

| Variable | Required | Default | Description |
|---|---|---|---|
| `GITHUB_TOKEN` | yes | — | GitHub PAT with repo read + read:packages |
| `DISCORD_WEBHOOK_URL` | yes | — | Discord webhook URL |
| `DISCORD_PINNED_MESSAGE_ID` | no | — | ID of the pinned star/watch summary message (see below) |
| `OWNERS` | one of | — | Comma-separated GitHub users/orgs; monitors all their non-fork, non-archived repos |
| `REPOSITORIES` | one of | — | Comma-separated `owner/repo` pairs to monitor explicitly |
| `GHCR_PACKAGES` | no | — | Comma-separated `owner/package` pairs for GHCR monitoring |
| `ENABLED_EVENTS` | no | all | Comma-separated subset of: `stars,watches,prs,issues,releases,ghcr` |
| `POLL_INTERVAL_SECONDS` | no | `300` | How often to poll (seconds; minimum 30) |
| `STATE_FILE_PATH` | no | `/data/state.json` | Path to the persistence file |
| `LOG_LEVEL` | no | `INFO` | Log verbosity: `DEBUG`, `INFO`, `WARNING`, `ERROR` |

At least one of `OWNERS` or `REPOSITORIES` must be set. Both can be used together — repos are deduplicated.

---

## Owner-Based Monitoring

Set `OWNERS` to a comma-separated list of GitHub usernames or organization names. Each polling cycle the service calls the GitHub API to discover all non-fork, non-archived repositories under each owner and monitors them automatically. No manual `REPOSITORIES` list is needed.

```ini
# Monitor everything under a user or org
OWNERS=jasmeralia

# Mix owners and explicit repos (duplicates are ignored)
OWNERS=jasmeralia
REPOSITORIES=some-org/a-specific-repo
```

If a new repository is created under a monitored owner, it is picked up on the next polling cycle without a restart.

---

## Quick Start — Docker Compose

```bash
# 1. Copy and fill in your .env file
cp .env.example .env
$EDITOR .env

# 2. Create the data directory
mkdir -p data

# 3. Start
docker compose up -d

# 4. Tail logs
docker compose logs -f
```

---

## Quick Start — Local Development

```bash
make setup          # create .venv and install deps
make test           # run tests

# Run locally (reads .env from current directory)
STATE_FILE_PATH=./data/state.json .venv/bin/git-activity-monitor
```

---

## Pinned Star/Watch Summary Message

On the first run with `stars` or `watches` monitoring enabled, the service sends a new Discord message containing the current star/watch counts for all configured repositories. The message ID is printed prominently in the logs:

```
INFO: Pinned summary message created. Set DISCORD_PINNED_MESSAGE_ID=1234567890123456789 in .env
```

Set `DISCORD_PINNED_MESSAGE_ID=<that id>` in your `.env` file and restart. On subsequent runs the service will **edit** that message in place rather than posting a new one each cycle.

If the pinned message is deleted, the service will automatically create a new one and log the new ID.

---

## Event Types

### Stars / Watches

Monitors repository star and watcher counts. When counts change, the pinned summary message is updated. Stars and watches are always handled together in one API call regardless of whether you enable one or both.

Example pinned message:
```
**GitHub Repository Stats** — last updated 5 minutes ago

**owner/my-app**  Stars: 142 (+3)  Watchers: 8
**owner/other**   Stars: 3  Watchers: 1
```

### Pull Requests

Detects PRs created since the last poll (open or closed/merged — anything opened in the interval is reported). All new PRs across all configured repositories are batched into a single Discord message per polling cycle.

```
**New Pull Requests**

**owner/my-app**
• [#74 — Add dark mode](https://github.com/owner/my-app/pull/74) by `alice`
• [#75 — Fix null pointer](https://github.com/owner/my-app/pull/75) by `bob`
```

### Issues

Detects issues created since the last poll (open or closed — anything created in the interval is reported). Pull requests are excluded.

### Releases

Detects new GitHub releases. Draft releases are ignored. Release body text is included (truncated to 200 characters).

### GHCR Package Versions

Detects new container image versions in the GitHub Container Registry. Requires `GHCR_PACKAGES` to be configured.

---

## State File

The state file (default `/data/state.json`) persists:
- Current star and watcher counts per repository
- Highest seen PR number per repository
- Highest seen issue number per repository
- Highest seen release ID per repository
- Set of seen GHCR version tags per package
- Pinned Discord message ID

**To reset all state:** delete the file and restart. The service will re-initialize from current GitHub state without sending notifications for existing activity.

**To reset one repository:** edit the JSON file and remove or zero out that repository's entry.

If the state file is corrupt or has an invalid schema on startup, it is renamed to `state.json.corrupt` and the service starts fresh (no notifications for existing activity).

---

## Maintenance Scripts

### `scripts/dependabot-merge.sh`

Merges (or auto-merges) open Dependabot PRs on a given repo:

```bash
scripts/dependabot-merge.sh <owner/repo>
```

Requires the [`gh` CLI](https://cli.github.com/) (authenticated) and `jq`. Each open Dependabot PR is checked and acted on individually — status is re-fetched immediately before acting on each PR, since merging one PR can change the check/rebase status of the next.

- **Private repos**: PRs with passing checks are squash-merged directly. If a PR needs rebasing against its base branch (e.g. because an earlier PR in the same run was just merged), it's left alone — a `@dependabot rebase` comment is posted instead, and it's reported as needing a follow-up run once Dependabot finishes rebasing.
- **Public repos**: PRs with passing checks have auto-merge (squash) enabled. Dependabot rebases those PRs itself if a later merge makes it necessary, so no manual rebase step is needed.
- **PRs with failing checks are never touched** — they're surfaced in the final summary as needing manual review, along with any PRs blocked by branch protection (e.g. missing required review) or still pending (checks running, mergeability not yet computed).

The script exits non-zero if any PR needs manual review, so it's safe to use in a monitoring/cron context.

### `scripts/list-open-prs.sh`

Lists every open PR across all of an owner's repos, with the author and a direct link:

```bash
scripts/list-open-prs.sh [owner]
```

Requires the [`gh` CLI](https://cli.github.com/) (authenticated) and `jq`. If `owner` is omitted, defaults to the authenticated `gh` user. Only non-fork, non-archived repos owned directly by that owner are considered. Output is grouped by repo, one line per PR (`#number by author, assigned: ..., opened YYYY-MM-DD: title`, or `assigned: unassigned` when nobody is assigned) followed by its URL, with a summary count at the end.

### `scripts/list-open-alerts.sh`

Lists every open Dependabot security alert across all of an owner's repos, with severity, package, advisory ID, and a direct link:

```bash
scripts/list-open-alerts.sh [owner]
```

Requires the [`gh` CLI](https://cli.github.com/) (authenticated) and `jq`. Same repo scope as `list-open-prs.sh`. Repos where Dependabot alerts aren't enabled (dependency graph off, or alerts specifically disabled) are reported separately at the end rather than silently showing zero alerts, since that distinction matters — no alerts and no visibility look identical otherwise.

---

## Dependabot Alert Notifications (Reusable Workflow)

`dependabot_alert` webhook events (created/dismissed/fixed/reopened) don't show up as PRs, so they're invisible to the event types above — they only fire for public repos (or private repos with GitHub Advanced Security). This repo hosts a [reusable workflow](https://docs.github.com/en/actions/using-workflows/reusing-workflows), `.github/workflows/dependabot-alert-discord.yml`, that other repos call to post a Discord embed whenever one of these fires.

Each subscribing repo needs:

1. A small trigger workflow (`dependabot_alert` is repo-scoped, so this can't be centralized further):

   ```yaml
   name: Dependabot Alert Notify
   on:
     dependabot_alert:
       types: [created, dismissed, fixed, reopened, auto_dismissed, auto_reopened, reintroduced]
   jobs:
     notify:
       uses: jasmeralia/git-activity-monitor/.github/workflows/dependabot-alert-discord.yml@master
       secrets:
         discord_webhook_url: ${{ secrets.DISCORD_SECURITY_WEBHOOK_URL }}
   ```

2. A `DISCORD_SECURITY_WEBHOOK_URL` repo secret (personal accounts have no org-level secrets to inherit from, so this has to be set per repo: `gh secret set DISCORD_SECURITY_WEBHOOK_URL --repo <owner>/<repo>`).

The embed is built by `dependabot-alert-notify` (`src/git_activity_monitor/dependabot_alert_notify.py`, installed as a console script) — color-coded by severity for new/reopened alerts, green for fixed, gray for dismissed, skipped entirely for `assignees_changed`. It reads the triggering event straight from `$GITHUB_EVENT_PATH` (reusable workflows inherit the caller's original event payload) rather than needing alert data passed in as inputs.

---

## Development

```bash
make setup          # create .venv, install all deps
make lintfix       # auto-fix formatting (ruff format + ruff check --fix)
make lint           # full lint: ruff + mypy + pylint
make test           # pytest with coverage (minimum 80%)
make all-checks     # lint + shellcheck + hadolint + test
```

All code changes must pass `make lintfix && make lint && make test` before committing. See [AGENTS.md](AGENTS.md).

---

## Contributing

This project uses [Conventional Commits](https://www.conventionalcommits.org/). Merge tags are auto-created from commit messages on push to `master`:

- `feat: ...` → minor version bump
- `fix: ...`, `chore: ...`, `docs: ...`, etc. → patch bump
- `BREAKING CHANGE:` in footer → major bump

All pull requests must be squash-merged.

---

## License

MIT
