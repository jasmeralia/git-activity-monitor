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

_HEADER = "**New Pull Requests**"


def run(
    settings: Settings,
    state_store: StateStore,
    gh_client: GitHubClient,
    discord_client: DiscordClient,
) -> None:
    new_by_repo: dict[str, list[dict[str, Any]]] = {}
    max_by_repo: dict[str, int] = {}

    for repo in settings.repositories:
        owner, name = repo.split("/")
        repo_state = state_store.get_repo(repo)

        # First run (last_pr_number == -1): initialize cursor without notifying.
        # Passing -1 as since_number returns all PRs (numbers are always >= 1).
        if repo_state.last_pr_number < 0:
            pulls = gh_client.get_new_pulls(owner, name, repo_state.last_pr_number)
            repo_state.last_pr_number = max((p["number"] for p in pulls), default=0)
            state_store.set_repo(repo, repo_state)
            logger.info(
                "%s: initialized last_pr_number=%d (no notification)",
                repo,
                repo_state.last_pr_number,
            )
            state_store.save()
            continue

        pulls = gh_client.get_new_pulls(owner, name, repo_state.last_pr_number)
        if pulls:
            new_by_repo[repo] = pulls
            max_by_repo[repo] = max(p["number"] for p in pulls)

    if not new_by_repo:
        return

    sections = []
    for repo, pulls in new_by_repo.items():
        lines = [f"**{repo}**"]
        for pr in pulls:
            # Suppress link previews: several PRs landing at once (e.g. dependabot,
            # or a cross-repo GHA change) would otherwise produce a wall of embeds.
            lines.append(f"• [{_pr_title(pr)}](<{pr['html_url']}>) by `{pr['user']['login']}`")
        sections.append("\n".join(lines))

    for chunk in split_message_chunks(_HEADER, sections):
        discord_client.send_message(chunk)

    for repo, max_num in max_by_repo.items():
        rs = state_store.get_repo(repo)
        rs.last_pr_number = max_num
        state_store.set_repo(repo, rs)

    state_store.save()
    total = sum(len(v) for v in new_by_repo.values())
    logger.info("Notified %d new PR(s) across %d repo(s)", total, len(new_by_repo))


def _pr_title(pr: dict[str, Any]) -> str:
    return f"#{pr['number']} — {pr['title']}"
