from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from .dependabot_alerts import run as run_dependabot_alerts
from .ghcr import run as run_ghcr
from .issues import run as run_issues
from .pulls import run as run_pulls
from .releases import run as run_releases
from .releases_pinned import run as run_releases_pinned
from .stars import run as run_stars
from .utils import split_message_chunks

if TYPE_CHECKING:
    from git_activity_monitor.config import Settings
    from git_activity_monitor.discord_client import DiscordClient
    from git_activity_monitor.github_client import GitHubClient
    from git_activity_monitor.state import StateStore

MonitorFn = Callable[["Settings", "StateStore", "GitHubClient", "DiscordClient"], None]

# Standard monitors dispatched uniformly by _run_cycle.
# "releases", "ghcr", and "alerts" are called explicitly with extra args and are omitted here.
STANDARD_MONITORS: dict[str, MonitorFn] = {
    "stars": run_stars,
    "watches": run_stars,
    "prs": run_pulls,
    "issues": run_issues,
}

# Backwards-compat alias used by existing tests.
ALL_MONITORS = STANDARD_MONITORS

__all__ = [
    "ALL_MONITORS",
    "STANDARD_MONITORS",
    "MonitorFn",
    "run_dependabot_alerts",
    "run_ghcr",
    "run_releases",
    "run_releases_pinned",
    "split_message_chunks",
]
