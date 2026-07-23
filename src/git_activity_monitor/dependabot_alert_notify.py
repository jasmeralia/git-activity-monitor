from __future__ import annotations

import json
import logging
import os
import sys
from typing import Any

from git_activity_monitor.discord_client import DiscordClient

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
    "auto_reopened": "\U0001f501 Dependabot Alert Reopened",
    "reintroduced": "\U0001f501 Dependabot Alert Reintroduced",
    "fixed": "✅ Dependabot Alert Resolved",
    "dismissed": "⚪ Dependabot Alert Dismissed",
    "auto_dismissed": "⚪ Dependabot Alert Dismissed",
}

# Actions that don't warrant a Discord notification.
_SKIP_ACTIONS = frozenset({"assignees_changed"})


def build_embed(action: str, alert: dict[str, Any], repo_full_name: str) -> dict[str, Any] | None:
    """Build a Discord embed for a dependabot_alert webhook event, or None to skip it."""
    if action in _SKIP_ACTIONS:
        return None

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


def main() -> int:
    logging.basicConfig(level=logging.INFO)

    webhook_url = os.environ["DISCORD_WEBHOOK_URL"]
    event_path = os.environ["GITHUB_EVENT_PATH"]

    with open(event_path, encoding="utf-8") as f:
        event = json.load(f)

    action = event["action"]
    alert = event["alert"]
    repo_full_name = event["repository"]["full_name"]

    embed = build_embed(action, alert, repo_full_name)
    if embed is None:
        logger.info("Skipping notification for action=%s", action)
        return 0

    with DiscordClient(webhook_url) as client:
        client.send_embed(embed)
    logger.info("Posted alert #%s (%s) to Discord", alert.get("number"), action)
    return 0


if __name__ == "__main__":
    sys.exit(main())
