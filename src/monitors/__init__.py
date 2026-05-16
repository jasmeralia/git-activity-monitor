from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from .ghcr import run as run_ghcr
from .issues import run as run_issues
from .pulls import run as run_pulls
from .releases import run as run_releases
from .stars import run as run_stars
from .utils import split_message_chunks

if TYPE_CHECKING:
    from git_activity_monitor.config import Settings
    from git_activity_monitor.discord_client import DiscordClient
    from git_activity_monitor.github_client import GitHubClient
    from git_activity_monitor.state import StateStore

MonitorFn = Callable[["Settings", "StateStore", "GitHubClient", "DiscordClient"], None]

# "stars" and "watches" are handled by the same monitor function
ALL_MONITORS: dict[str, MonitorFn] = {
    "stars": run_stars,
    "watches": run_stars,
    "prs": run_pulls,
    "issues": run_issues,
    "releases": run_releases,
    "ghcr": run_ghcr,
}

__all__ = ["ALL_MONITORS", "MonitorFn", "split_message_chunks"]
