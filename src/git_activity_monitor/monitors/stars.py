from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

import httpx

if TYPE_CHECKING:
    from git_activity_monitor.config import Settings
    from git_activity_monitor.discord_client import DiscordClient
    from git_activity_monitor.github_client import GitHubClient
    from git_activity_monitor.state import RepoState, StateStore

logger = logging.getLogger(__name__)


def _build_summary(repos: list[str], staged: dict[str, RepoState]) -> str:
    now_ts = int(time.time())
    lines = [f"**GitHub Repository Stats** — last updated <t:{now_ts}:R>", ""]
    for repo in repos:
        rs = staged[repo]
        lines.append(
            f"**[{repo}](https://github.com/{repo})**  Stars: {rs.stars}  Watchers: {rs.watches}"
        )
    return "\n".join(lines)


def _update_pinned(
    discord_client: DiscordClient,
    state_store: StateStore,
    summary: str,
    pinned_id: str | None,
) -> None:
    if pinned_id:
        try:
            discord_client.edit_message(pinned_id, summary)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code != 404:
                raise
            logger.warning("Pinned message %s not found; sending new message", pinned_id)
            msg = discord_client.send_message(summary)
            new_id = str(msg["id"])
            state_store.pinned_message_id = new_id
            logger.info(
                "New pinned message ID: %s — set DISCORD_PINNED_MESSAGE_ID=%s", new_id, new_id
            )
    else:
        msg = discord_client.send_message(summary)
        new_id = str(msg["id"])
        state_store.pinned_message_id = new_id
        logger.info(
            "Pinned summary message created. Set DISCORD_PINNED_MESSAGE_ID=%s in .env", new_id
        )


def run(
    settings: Settings,
    state_store: StateStore,
    gh_client: GitHubClient,
    discord_client: DiscordClient,
) -> None:
    """Check star/watch counts and update the pinned Discord summary if any changed."""
    changed = False
    staged: dict[str, RepoState] = {}
    active_repos: list[str] = []
    for repo in settings.repositories:
        owner, name = repo.split("/")
        stats = gh_client.get_repo_stats(owner, name)
        if stats.get("archived"):
            logger.debug("Skipping archived repo %s", repo)
            continue
        repo_state = state_store.get_repo(repo)
        new_stars = stats["stars"]
        new_watches = stats["watches"]

        if new_stars != repo_state.stars or new_watches != repo_state.watches:
            changed = True
            if new_stars != repo_state.stars:
                delta = new_stars - repo_state.stars
                logger.info("%s: stars %d → %d (%+d)", repo, repo_state.stars, new_stars, delta)
            if new_watches != repo_state.watches:
                delta = new_watches - repo_state.watches
                logger.info(
                    "%s: watchers %d → %d (%+d)", repo, repo_state.watches, new_watches, delta
                )

        repo_state.stars = new_stars
        repo_state.watches = new_watches
        staged[repo] = repo_state
        active_repos.append(repo)

    # Force a refresh when the set of repos in the summary changes (e.g. a repo
    # was archived or a new one was discovered) so the pinned message stays in sync.
    if active_repos != state_store.pinned_repos:
        changed = True

    if not changed:
        return

    summary = _build_summary(active_repos, staged)
    pinned_id = settings.discord_pinned_message_id or state_store.pinned_message_id
    _update_pinned(discord_client, state_store, summary, pinned_id)

    for repo, repo_state in staged.items():
        state_store.set_repo(repo, repo_state)
    state_store.pinned_repos = active_repos
    state_store.save()
