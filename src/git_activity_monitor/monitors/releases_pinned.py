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
    from git_activity_monitor.state import StateStore

logger = logging.getLogger(__name__)

_HEADER = "**Public Repositories**"
_HEADER_CONT = "**Public Repositories** (cont.)"
_MAX_LEN = 1990
_MAX_DESC = 60


def _repo_line(repo: str, desc: str) -> str:
    if desc and len(desc) > _MAX_DESC:
        desc = desc[:_MAX_DESC] + "…"
    entry = f"**[{repo}](https://github.com/{repo})**"
    if desc:
        entry += f" — {desc}"
    return entry


def _build_catalog(repos: list[str], descriptions: dict[str, str], timestamp: int) -> list[str]:
    header = f"{_HEADER} — last updated <t:{timestamp}:R>"
    cont_header = f"{_HEADER_CONT} — last updated <t:{timestamp}:R>"
    sections = [_repo_line(r, descriptions.get(r, "")) for r in repos]
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
                logger.warning("Releases pinned message %s not found; sending new message", msg_id)
                msg = discord_client.send_message(chunk)
                new_ids.append(str(msg["id"]))
        else:
            msg = discord_client.send_message(chunk)
            new_ids.append(str(msg["id"]))

    state_store.releases_pinned_message_ids = new_ids

    if is_first_run:
        logger.info(
            "Releases pinned catalog created. Set DISCORD_RELEASES_PINNED_MESSAGE_ID=%s in .env",
            new_ids[0],
        )


def run(
    settings: Settings,
    state_store: StateStore,
    gh_client: GitHubClient,
    discord_client: DiscordClient,
) -> None:
    """Maintain a pinned catalog of public repos on the releases Discord channel."""
    repos: list[str] = []
    descriptions: dict[str, str] = {}

    for owner in settings.owners:
        try:
            metadata = gh_client.get_owner_repos_metadata(owner)
        except Exception:  # pylint: disable=broad-exception-caught
            logger.exception(
                "Failed to fetch repo metadata for owner %s; skipping pinned update", owner
            )
            return
        for item in metadata:
            if not item["private"]:
                repos.append(item["full_name"])
                descriptions[item["full_name"]] = item["description"]

    if (
        repos == state_store.releases_pinned_repos
        and descriptions == state_store.releases_pinned_descriptions
    ):
        return

    config_id = settings.discord_releases_pinned_message_id
    stored_ids = state_store.releases_pinned_message_ids
    pinned_ids = [config_id, *stored_ids[1:]] if config_id else stored_ids

    chunks = _build_catalog(repos, descriptions, int(time.time()))
    _update_pinned(discord_client, state_store, chunks, pinned_ids)

    state_store.releases_pinned_repos = repos
    state_store.releases_pinned_descriptions = descriptions
    state_store.save()
    logger.info("Updated releases pinned catalog with %d public repo(s)", len(repos))
