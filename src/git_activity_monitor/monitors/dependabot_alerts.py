from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from git_activity_monitor.config import Settings
    from git_activity_monitor.discord_client import DiscordClient
    from git_activity_monitor.github_client import GitHubClient
    from git_activity_monitor.state import StateStore

logger = logging.getLogger(__name__)

_SEVERITY_COLORS: dict[str, int] = {
    "critical": 0xB30000,
    "high": 0xE74C3C,
    "medium": 0xE67E22,
    "low": 0xF1C40F,
}
_COLOR_FIXED = 0x2ECC71
_COLOR_DISMISSED = 0x95A5A6
_COLOR_DEFAULT = 0x7289DA

_TITLES: dict[str, str] = {
    "created": "\U0001f534 New Dependabot Alert",
    "reopened": "\U0001f501 Dependabot Alert Reopened",
    "fixed": "✅ Dependabot Alert Resolved",
    "dismissed": "⚪ Dependabot Alert Dismissed",
    "auto_dismissed": "⚪ Dependabot Alert Dismissed",
}


def build_embed(action: str, alert: dict[str, Any], repo_full_name: str) -> dict[str, Any]:
    """Build a Discord embed describing a Dependabot alert's current state."""
    advisory = alert.get("security_advisory", {})
    dependency = alert.get("dependency", {})
    package = dependency.get("package", {})
    severity = advisory.get("severity", "unknown")

    if action in ("dismissed", "auto_dismissed"):
        color = _COLOR_DISMISSED
    elif action == "fixed":
        color = _COLOR_FIXED
    else:
        color = _SEVERITY_COLORS.get(severity, _COLOR_DEFAULT)

    advisory_id = advisory.get("ghsa_id") or advisory.get("cve_id") or "unknown"

    fields = [
        {"name": "Repository", "value": repo_full_name, "inline": True},
        {
            "name": "Package",
            "value": f"{package.get('name', 'unknown')} ({package.get('ecosystem', 'unknown')})",
            "inline": True,
        },
        {"name": "Severity", "value": severity, "inline": True},
        {"name": "Advisory", "value": advisory_id, "inline": True},
    ]

    if action in ("dismissed", "auto_dismissed") and alert.get("dismissed_reason"):
        fields.append(
            {"name": "Dismissed reason", "value": str(alert["dismissed_reason"]), "inline": True}
        )

    return {
        "title": _TITLES.get(action, f"Dependabot Alert: {action}"),
        "description": advisory.get("summary", ""),
        "url": alert.get("html_url"),
        "color": color,
        "fields": fields,
    }


def _action_for_transition(state: str, prev_state: str | None) -> str:
    if prev_state is None:
        return "created"
    if state == "open":
        return "reopened"
    return state


def run(
    settings: Settings,
    state_store: StateStore,
    gh_client: GitHubClient,
    discord_client: DiscordClient,
    alerts_discord_client: DiscordClient | None = None,
) -> None:
    target = alerts_discord_client or discord_client
    notified = 0

    for repo in settings.repositories:
        owner, name = repo.split("/")
        alerts = gh_client.get_dependabot_alerts(owner, name)

        first_run = not state_store.is_dependabot_alerts_initialized(repo)
        previous = state_store.get_dependabot_alert_states(repo)
        current: dict[str, str] = {}

        for alert in alerts:
            number = str(alert["number"])
            state = alert["state"]
            current[number] = state

            if first_run:
                continue

            prev_state = previous.get(number)
            if prev_state == state:
                continue

            action = _action_for_transition(state, prev_state)
            target.send_embed(build_embed(action, alert, repo))
            notified += 1

        if first_run:
            logger.info(
                "%s: initialized dependabot alert state with %d alert(s) (no notification)",
                repo,
                len(current),
            )

        state_store.set_dependabot_alert_states(repo, current)

    state_store.save()
    if notified:
        logger.info("Notified %d dependabot alert change(s)", notified)
