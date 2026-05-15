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
| `REPOSITORIES` | yes | — | Comma-separated `owner/repo` pairs to monitor |
| `GHCR_PACKAGES` | no | — | Comma-separated `owner/package` pairs for GHCR monitoring |
| `ENABLED_EVENTS` | no | all | Comma-separated subset of: `stars,watches,prs,issues,releases,ghcr` |
| `POLL_INTERVAL_SECONDS` | no | `300` | How often to poll (seconds) |
| `STATE_FILE_PATH` | no | `/data/state.json` | Path to the persistence file |
| `LOG_LEVEL` | no | `INFO` | Log verbosity: `DEBUG`, `INFO`, `WARNING`, `ERROR` |

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
STATE_FILE_PATH=./data/state.json .venv/bin/github-activity-monitor
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

Detects newly opened PRs. All new PRs across all configured repositories are batched into a single Discord message per polling cycle.

```
**New Pull Requests**

**owner/my-app**
• [#74 — Add dark mode](https://github.com/owner/my-app/pull/74) by `alice`
• [#75 — Fix null pointer](https://github.com/owner/my-app/pull/75) by `bob`
```

### Issues

Detects newly created issues (pull requests are excluded).

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

---

## Development

```bash
make setup          # create .venv, install all deps
make lint-fix       # auto-fix formatting (ruff format + ruff check --fix)
make lint           # full lint: ruff + mypy + pylint
make test           # pytest with coverage (minimum 80%)
make all-checks     # lint + shellcheck + hadolint + test
```

All code changes must pass `make lint-fix && make lint && make test` before committing. See [AGENTS.md](AGENTS.md).

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
