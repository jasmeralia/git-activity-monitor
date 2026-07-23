from __future__ import annotations

from unittest.mock import MagicMock

from git_activity_monitor.config import Settings
from git_activity_monitor.discord_client import DiscordClient
from git_activity_monitor.monitors.dependabot_alerts import build_embed, run
from git_activity_monitor.state import StateStore


def _alert(number: int = 7, state: str = "open", **overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "number": number,
        "state": state,
        "html_url": f"https://github.com/owner/repo/security/dependabot/{number}",
        "dependency": {"package": {"name": "aiohttp", "ecosystem": "pip"}},
        "security_advisory": {
            "ghsa_id": "GHSA-4m7w-qmgq-4wj5",
            "cve_id": None,
            "severity": "low",
            "summary": "aiohttp: TLS Server Hostname Override Is Ignored",
        },
    }
    base.update(overrides)
    return base


def test_build_embed_created_uses_severity_color() -> None:
    alert = _alert(security_advisory={**_alert()["security_advisory"], "severity": "critical"})  # type: ignore[dict-item]
    embed = build_embed("created", alert, "owner/repo")
    assert embed["color"] == 0xB30000
    assert embed["title"] == "\U0001f534 New Dependabot Alert"


def test_build_embed_fixed_is_green() -> None:
    embed = build_embed("fixed", _alert(), "owner/repo")
    assert embed["color"] == 0x2ECC71


def test_build_embed_dismissed_includes_reason() -> None:
    embed = build_embed("dismissed", _alert(dismissed_reason="tolerable_risk"), "owner/repo")
    reason = next(f for f in embed["fields"] if f["name"] == "Dismissed reason")
    assert reason["value"] == "tolerable_risk"


def test_first_run_initializes_without_notification(
    sample_settings: Settings,
    state_store: StateStore,
    mock_gh: MagicMock,
    mock_discord: MagicMock,
) -> None:
    sample_settings.enabled_events.append("alerts")
    mock_gh.get_dependabot_alerts.return_value = [_alert()]
    run(sample_settings, state_store, mock_gh, mock_discord)
    mock_discord.send_embed.assert_not_called()
    assert state_store.get_dependabot_alert_states("owner/repo") == {"7": "open"}


def test_new_alert_after_first_run_notifies(
    sample_settings: Settings,
    state_store: StateStore,
    mock_gh: MagicMock,
    mock_discord: MagicMock,
) -> None:
    state_store.set_dependabot_alert_states("owner/repo", {})
    mock_gh.get_dependabot_alerts.return_value = [_alert()]
    run(sample_settings, state_store, mock_gh, mock_discord)
    mock_discord.send_embed.assert_called_once()
    embed = mock_discord.send_embed.call_args[0][0]
    assert embed["title"] == "\U0001f534 New Dependabot Alert"
    assert state_store.get_dependabot_alert_states("owner/repo") == {"7": "open"}


def test_state_transition_to_fixed_notifies(
    sample_settings: Settings,
    state_store: StateStore,
    mock_gh: MagicMock,
    mock_discord: MagicMock,
) -> None:
    state_store.set_dependabot_alert_states("owner/repo", {"7": "open"})
    mock_gh.get_dependabot_alerts.return_value = [_alert(state="fixed")]
    run(sample_settings, state_store, mock_gh, mock_discord)
    mock_discord.send_embed.assert_called_once()
    embed = mock_discord.send_embed.call_args[0][0]
    assert embed["title"] == "✅ Dependabot Alert Resolved"
    assert state_store.get_dependabot_alert_states("owner/repo") == {"7": "fixed"}


def test_reopened_after_fixed_notifies(
    sample_settings: Settings,
    state_store: StateStore,
    mock_gh: MagicMock,
    mock_discord: MagicMock,
) -> None:
    state_store.set_dependabot_alert_states("owner/repo", {"7": "fixed"})
    mock_gh.get_dependabot_alerts.return_value = [_alert(state="open")]
    run(sample_settings, state_store, mock_gh, mock_discord)
    embed = mock_discord.send_embed.call_args[0][0]
    assert embed["title"] == "\U0001f501 Dependabot Alert Reopened"


def test_unchanged_state_no_notification(
    sample_settings: Settings,
    state_store: StateStore,
    mock_gh: MagicMock,
    mock_discord: MagicMock,
) -> None:
    state_store.set_dependabot_alert_states("owner/repo", {"7": "open"})
    mock_gh.get_dependabot_alerts.return_value = [_alert(state="open")]
    run(sample_settings, state_store, mock_gh, mock_discord)
    mock_discord.send_embed.assert_not_called()


def test_routes_to_security_channel(
    sample_settings: Settings,
    state_store: StateStore,
    mock_gh: MagicMock,
    mock_discord: MagicMock,
) -> None:
    state_store.set_dependabot_alert_states("owner/repo", {})
    mock_gh.get_dependabot_alerts.return_value = [_alert()]
    alerts_client = MagicMock(spec=DiscordClient)

    run(sample_settings, state_store, mock_gh, mock_discord, alerts_discord_client=alerts_client)

    alerts_client.send_embed.assert_called_once()
    mock_discord.send_embed.assert_not_called()


def test_alerts_disabled_repo_returns_empty_no_crash(
    sample_settings: Settings,
    state_store: StateStore,
    mock_gh: MagicMock,
    mock_discord: MagicMock,
) -> None:
    mock_gh.get_dependabot_alerts.return_value = []
    run(sample_settings, state_store, mock_gh, mock_discord)
    mock_discord.send_embed.assert_not_called()
