from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from git_activity_monitor.monitors.utils import split_message_chunks

if TYPE_CHECKING:
    from git_activity_monitor.config import Settings
    from git_activity_monitor.discord_client import DiscordClient
    from git_activity_monitor.github_client import GitHubClient
    from git_activity_monitor.state import StateStore

logger = logging.getLogger(__name__)

_HEADER = "**New Releases**"
_BODY_MAX = 200


def _build_sections(new_by_repo: dict[str, list[dict[str, Any]]]) -> list[str]:
    sections = []
    for repo, releases in new_by_repo.items():
        lines = [f"**{repo}**"]
        for release in releases:
            body = (release.get("body") or "").strip()
            if len(body) > _BODY_MAX:
                body = body[:_BODY_MAX] + "…"
            tag = release["tag_name"]
            url = release["html_url"]
            title = release.get("name") or tag
            line = f"**{title}** ({tag}) — [Release notes]({url})"
            if body:
                line += f"\n> {body}"
            lines.append(line)
        sections.append("\n".join(lines))
    return sections


def run(
    settings: Settings,
    state_store: StateStore,
    gh_client: GitHubClient,
    discord_client: DiscordClient,
    releases_discord_client: DiscordClient | None = None,
) -> None:
    new_by_repo: dict[str, list[dict[str, Any]]] = {}
    max_id_by_repo: dict[str, int] = {}
    public_repos = set(settings.public_repositories)

    for repo in settings.repositories:
        owner, name = repo.split("/")
        repo_state = state_store.get_repo(repo)

        releases = gh_client.get_new_releases(owner, name, repo_state.last_release_id)

        # First run (last_release_id == -1): initialize cursor without notifying.
        # get_new_releases(-1) returns all releases since any real ID > -1.
        if repo_state.last_release_id < 0:
            repo_state.last_release_id = max((r["id"] for r in releases), default=0)
            state_store.set_repo(repo, repo_state)
            logger.info(
                "%s: initialized last_release_id=%d (no notification)",
                repo,
                repo_state.last_release_id,
            )
            state_store.save()
            continue

        if releases:
            new_by_repo[repo] = releases
            max_id_by_repo[repo] = max(r["id"] for r in releases)

    if not new_by_repo:
        return

    # Route public repos to the releases channel; private repos stay on main channel.
    target = releases_discord_client or discord_client
    public_new = {r: v for r, v in new_by_repo.items() if r in public_repos}
    private_new = {r: v for r, v in new_by_repo.items() if r not in public_repos}

    if public_new:
        for chunk in split_message_chunks(_HEADER, _build_sections(public_new)):
            target.send_message(chunk)

    if private_new:
        for chunk in split_message_chunks(_HEADER, _build_sections(private_new)):
            discord_client.send_message(chunk)

    for repo, max_id in max_id_by_repo.items():
        rs = state_store.get_repo(repo)
        rs.last_release_id = max_id
        state_store.set_repo(repo, rs)

    state_store.save()
    total = sum(len(v) for v in new_by_repo.values())
    logger.info("Notified %d new release(s) across %d repo(s)", total, len(new_by_repo))
