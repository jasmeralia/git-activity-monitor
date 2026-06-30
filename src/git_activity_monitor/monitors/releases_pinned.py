from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

import httpx

if TYPE_CHECKING:
    from git_activity_monitor.config import Settings
    from git_activity_monitor.discord_client import DiscordClient
    from git_activity_monitor.github_client import GitHubClient
    from git_activity_monitor.state import StateStore

logger = logging.getLogger(__name__)

_HEADER = "**Public Repositories**"
_MAX_LEN = 1990
_MAX_DESC = 60


def _repo_line(repo: str, desc: str) -> str:
    if desc and len(desc) > _MAX_DESC:
        desc = desc[:_MAX_DESC] + "…"
    entry = f"**[{repo}](https://github.com/{repo})**"
    if desc:
        entry += f" — {desc}"
    return entry


def _build_catalog(repos: list[str], descriptions: dict[str, str], timestamp: int) -> str:
    header = f"{_HEADER} — last updated <t:{timestamp}:R>"
    lines = [_repo_line(r, descriptions.get(r, "")) for r in repos]

    full = header + "\n\n" + "\n".join(lines)
    if len(full) <= _MAX_LEN:
        return full

    kept: list[str] = []
    for line in lines:
        kept.append(line)
        remaining = len(lines) - len(kept)
        trailer = f"\n…and {remaining} more" if remaining > 0 else ""
        if len(header + "\n\n" + "\n".join(kept) + trailer) > _MAX_LEN:
            kept.pop()
            skipped = len(lines) - len(kept)
            return header + "\n\n" + "\n".join(kept) + f"\n…and {skipped} more"

    return header + "\n\n" + "\n".join(kept)


def _update_pinned(
    discord_client: DiscordClient,
    state_store: StateStore,
    content: str,
    pinned_id: str | None,
) -> None:
    if pinned_id:
        try:
            discord_client.edit_message(pinned_id, content)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code != 404:
                raise
            logger.warning("Releases pinned message %s not found; sending new message", pinned_id)
            msg = discord_client.send_message(content)
            new_id = str(msg["id"])
            state_store.releases_pinned_message_id = new_id
            logger.info(
                "New releases pinned message ID: %s — set DISCORD_RELEASES_PINNED_MESSAGE_ID=%s",
                new_id,
                new_id,
            )
    else:
        msg = discord_client.send_message(content)
        new_id = str(msg["id"])
        state_store.releases_pinned_message_id = new_id
        logger.info(
            "Releases pinned catalog created. Set DISCORD_RELEASES_PINNED_MESSAGE_ID=%s in .env",
            new_id,
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

    pinned_id = (
        settings.discord_releases_pinned_message_id or state_store.releases_pinned_message_id
    )
    content = _build_catalog(repos, descriptions, int(time.time()))
    _update_pinned(discord_client, state_store, content, pinned_id)

    state_store.releases_pinned_repos = repos
    state_store.releases_pinned_descriptions = descriptions
    state_store.save()
    logger.info("Updated releases pinned catalog with %d public repo(s)", len(repos))
