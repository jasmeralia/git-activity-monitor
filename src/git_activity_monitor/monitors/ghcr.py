from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

from git_activity_monitor.monitors.utils import split_message_chunks

if TYPE_CHECKING:
    from git_activity_monitor.config import Settings
    from git_activity_monitor.discord_client import DiscordClient
    from git_activity_monitor.github_client import GitHubClient
    from git_activity_monitor.state import StateStore

logger = logging.getLogger(__name__)

_HEADER = "**New Container Image Versions**"

# Digest-derived tags like "sha-13839b3" aren't meaningful release identifiers
# and clutter the report; omit them while still tracking them as seen.
_SHA_TAG_PATTERN = re.compile(r"^sha-[0-9a-f]+$", re.IGNORECASE)


def _is_reportable(version: str) -> bool:
    return not _SHA_TAG_PATTERN.match(version)


def run(
    settings: Settings,
    state_store: StateStore,
    gh_client: GitHubClient,
    discord_client: DiscordClient,
    releases_discord_client: DiscordClient | None = None,
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
        # The GitHub API returns versions newest-first; the report reads oldest-first.
        reportable = [v for v in reversed(versions) if _is_reportable(v)]
        if reportable:
            version_list = ", ".join(f"`{v}`" for v in reportable)
            sections.append(f"**{package}**: {version_list}")

    if sections:
        target = releases_discord_client or discord_client
        for chunk in split_message_chunks(_HEADER, sections):
            target.send_message(chunk)

    for package, all_versions in all_versions_by_package.items():
        state_store.set_ghcr(package, all_versions)

    state_store.save()
    total = sum(len(v) for v in new_by_package.values())
    logger.info("Notified %d new GHCR version(s) across %d package(s)", total, len(new_by_package))
