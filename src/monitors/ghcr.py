from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from github_activity_monitor.monitors.utils import split_message_chunks

if TYPE_CHECKING:
    from github_activity_monitor.config import Settings
    from github_activity_monitor.discord_client import DiscordClient
    from github_activity_monitor.github_client import GitHubClient
    from github_activity_monitor.state import StateStore

logger = logging.getLogger(__name__)

_HEADER = "**New Container Image Versions**"


def run(
    settings: Settings,
    state_store: StateStore,
    gh_client: GitHubClient,
    discord_client: DiscordClient,
) -> None:
    if not settings.ghcr_packages:
        return

    new_by_package: dict[str, list[str]] = {}
    all_versions_by_package: dict[str, list[str]] = {}

    for package in settings.ghcr_packages:
        owner, pkg_name = package.split("/")

        # First run: set seen versions without notifying, even if the package has none yet.
        if not state_store.is_ghcr_initialized(package):
            all_current = gh_client.get_new_package_versions(owner, pkg_name, [])
            state_store.set_ghcr(package, all_current)
            logger.info(
                "%s: initialized with %d version(s) (no notification)",
                package,
                len(all_current),
            )
            state_store.save()
            continue

        seen = state_store.get_ghcr(package)
        new_versions = gh_client.get_new_package_versions(owner, pkg_name, seen)
        if new_versions:
            new_by_package[package] = new_versions
            all_versions_by_package[package] = seen + new_versions

    if not new_by_package:
        return

    sections = []
    for package, versions in new_by_package.items():
        version_list = ", ".join(f"`{v}`" for v in versions)
        sections.append(f"**{package}**: {version_list}")

    for chunk in split_message_chunks(_HEADER, sections):
        discord_client.send_message(chunk)

    for package, all_versions in all_versions_by_package.items():
        state_store.set_ghcr(package, all_versions)

    state_store.save()
    total = sum(len(v) for v in new_by_package.values())
    logger.info("Notified %d new GHCR version(s) across %d package(s)", total, len(new_by_package))
