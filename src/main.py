from __future__ import annotations

import logging
import signal
import time
import types
from collections.abc import Callable

import httpx

from github_activity_monitor.config import Settings
from github_activity_monitor.discord_client import DiscordClient
from github_activity_monitor.github_client import GitHubClient
from github_activity_monitor.monitors import ALL_MONITORS, MonitorFn
from github_activity_monitor.state import StateStore

logger = logging.getLogger(__name__)


def _resolve_monitors(enabled_events: list[str]) -> list[MonitorFn]:
    """Return deduplicated monitor functions in the order they first appear."""
    seen: set[Callable[..., None]] = set()
    result: list[MonitorFn] = []
    for event in enabled_events:
        fn = ALL_MONITORS[event]
        if fn not in seen:
            seen.add(fn)
            result.append(fn)
    return result


def _effective_repositories(settings: Settings, gh_client: GitHubClient) -> list[str]:
    """Merge owner-discovered repos with explicitly listed repos, preserving order."""
    seen: set[str] = set()
    repos: list[str] = []
    for owner in settings.owners:
        try:
            discovered = gh_client.get_owner_repos(owner)
        except Exception:  # pylint: disable=broad-exception-caught
            logger.exception("Failed to list repos for owner %s; skipping", owner)
            discovered = []
        for repo in discovered:
            if repo not in seen:
                seen.add(repo)
                repos.append(repo)
        logger.debug("Owner %s: discovered %d repo(s)", owner, len(discovered))
    for repo in settings.repositories:
        if repo not in seen:
            seen.add(repo)
            repos.append(repo)
    return repos


def _run_cycle(
    settings: Settings,
    state_store: StateStore,
    gh_client: GitHubClient,
    discord_client: DiscordClient,
    monitor_fns: list[MonitorFn],
) -> None:
    effective = _effective_repositories(settings, gh_client)
    if not effective:
        logger.warning("No repositories to monitor this cycle.")
        return
    effective_settings = settings.model_copy(update={"repositories": effective})
    for fn in monitor_fns:
        try:
            fn(effective_settings, state_store, gh_client, discord_client)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code in {401, 403, 404}:
                logger.critical(
                    "Monitor %s: permanent webhook/API failure (HTTP %d) — "
                    "verify DISCORD_WEBHOOK_URL and GITHUB_TOKEN are correct",
                    fn.__name__,
                    exc.response.status_code,
                )
            else:
                logger.exception("Monitor %s failed; continuing with next monitor", fn.__name__)
        except Exception:  # pylint: disable=broad-exception-caught
            logger.exception("Monitor %s failed; continuing with next monitor", fn.__name__)


def main() -> None:
    settings = Settings()
    logging.basicConfig(
        level=settings.log_level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )
    logger.info("Starting GitHub activity monitor")

    state_store = StateStore(settings.state_file_path)
    state_store.load()

    monitor_fns = _resolve_monitors(settings.enabled_events)
    logger.info(
        "Enabled monitors: %s",
        ", ".join(fn.__module__.split(".")[-1] for fn in monitor_fns),
    )

    shutdown = False

    def _handle_signal(sig: int, _frame: types.FrameType | None) -> None:
        nonlocal shutdown
        logger.info("Received signal %d; shutting down after current cycle", sig)
        shutdown = True

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    with (
        GitHubClient(settings.github_token) as gh_client,
        DiscordClient(settings.discord_webhook_url) as discord_client,
    ):
        while not shutdown:
            cycle_start = time.monotonic()
            _run_cycle(settings, state_store, gh_client, discord_client, monitor_fns)
            elapsed = time.monotonic() - cycle_start
            sleep_for = int(max(0.0, settings.poll_interval_seconds - elapsed))
            logger.debug("Cycle complete in %.1fs; sleeping %ds", elapsed, sleep_for)
            for _ in range(sleep_for):
                if shutdown:
                    break
                time.sleep(1)

    logger.info("Shutdown complete")


if __name__ == "__main__":
    main()
