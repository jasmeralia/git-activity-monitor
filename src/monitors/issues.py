from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from github_activity_monitor.monitors.utils import split_message_chunks

if TYPE_CHECKING:
    from github_activity_monitor.config import Settings
    from github_activity_monitor.discord_client import DiscordClient
    from github_activity_monitor.github_client import GitHubClient
    from github_activity_monitor.state import StateStore

logger = logging.getLogger(__name__)

_HEADER = "**New Issues**"


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

        # First run: initialize to current max without notifying
        if repo_state.last_issue_number == 0:
            issues = gh_client.get_new_issues(owner, name, 0)
            if issues:
                max_num = max(i["number"] for i in issues)
                repo_state.last_issue_number = max_num
                state_store.set_repo(repo, repo_state)
                logger.info("%s: initialized last_issue_number=%d (no notification)", repo, max_num)
            state_store.save()
            continue

        issues = gh_client.get_new_issues(owner, name, repo_state.last_issue_number)
        if issues:
            new_by_repo[repo] = issues
            max_by_repo[repo] = max(i["number"] for i in issues)

    if not new_by_repo:
        return

    sections = []
    for repo, issues in new_by_repo.items():
        lines = [f"**{repo}**"]
        for issue in issues:
            labels = _format_labels(issue)
            suffix = f" {labels}" if labels else ""
            lines.append(
                f"• [#{issue['number']} — {issue['title']}]({issue['html_url']})"
                f" by `{issue['user']['login']}`{suffix}"
            )
        sections.append("\n".join(lines))

    for chunk in split_message_chunks(_HEADER, sections):
        discord_client.send_message(chunk)

    for repo, max_num in max_by_repo.items():
        rs = state_store.get_repo(repo)
        rs.last_issue_number = max_num
        state_store.set_repo(repo, rs)

    state_store.save()
    total = sum(len(v) for v in new_by_repo.values())
    logger.info("Notified %d new issue(s) across %d repo(s)", total, len(new_by_repo))


def _format_labels(issue: dict[str, Any]) -> str:
    labels = [lbl["name"] for lbl in issue.get("labels", [])]
    if not labels:
        return ""
    return "[" + ", ".join(f"`{lbl}`" for lbl in labels[:3]) + "]"
