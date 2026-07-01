from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

import httpx

from git_activity_monitor.monitors.utils import split_message_chunks

if TYPE_CHECKING:
    from git_activity_monitor.config import Settings
    from git_activity_monitor.discord_client import DiscordClient
    from git_activity_monitor.github_client import GitHubClient
    from git_activity_monitor.state import RepoState, StateStore

logger = logging.getLogger(__name__)

_MAX_LEN = 1990
_HEADER = "**GitHub Repository Stats**"


def _build_summary(repos: list[str], staged: dict[str, RepoState]) -> list[str]:
    now_ts = int(time.time())
    header = f"{_HEADER} — last updated <t:{now_ts}:R>"
    cont_header = f"{_HEADER} (cont.) — last updated <t:{now_ts}:R>"
    sections = [
        f"**[{r}](https://github.com/{r})**"
        f"  Stars: {staged[r].stars}  Watchers: {staged[r].watches}"
        for r in repos
    ]
    return split_message_chunks(header, sections, max_len=_MAX_LEN, cont_header=cont_header)


def _update_pinned(
    discord_client: DiscordClient,
    state_store: StateStore,
    chunks: list[str],
    pinned_ids: list[str],
) -> None:
    is_first_run = not pinned_ids
    new_ids: list[str] = []

    for i, chunk in enumerate(chunks):
        if i < len(pinned_ids):
            msg_id = pinned_ids[i]
            try:
                discord_client.edit_message(msg_id, chunk)
                new_ids.append(msg_id)
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code != 404:
                    raise
                logger.warning("Pinned message %s not found; sending new message", msg_id)
                msg = discord_client.send_message(chunk)
                new_ids.append(str(msg["id"]))
        else:
            msg = discord_client.send_message(chunk)
            new_ids.append(str(msg["id"]))

    state_store.pinned_message_ids = new_ids

    if is_first_run:
        logger.info("Pinned summary created. Set DISCORD_PINNED_MESSAGE_ID=%s in .env", new_ids[0])


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

    chunks = _build_summary(active_repos, staged)
    config_id = settings.discord_pinned_message_id
    stored_ids = state_store.pinned_message_ids
    pinned_ids = [config_id, *stored_ids[1:]] if config_id else stored_ids
    _update_pinned(discord_client, state_store, chunks, pinned_ids)

    for repo, repo_state in staged.items():
        state_store.set_repo(repo, repo_state)
    state_store.pinned_repos = active_repos
    state_store.save()
