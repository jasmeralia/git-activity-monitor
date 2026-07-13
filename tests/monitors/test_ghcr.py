from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from git_activity_monitor.config import Settings
from git_activity_monitor.monitors.ghcr import run
from git_activity_monitor.state import StateStore


def _settings_with_ghcr(tmp_path: object) -> Settings:
    from pathlib import Path

    return Settings(
        github_token="tok",
        discord_webhook_url="https://discord.com/api/webhooks/1/t",
        repositories=["owner/repo"],
        ghcr_packages=["owner/my-app"],
        enabled_events=["ghcr"],
        state_file_path=Path(str(tmp_path)) / "state.json",
        _env_file=None,  # type: ignore[call-arg]
    )


def test_no_packages_configured_skips(
    sample_settings: Settings,
    state_store: StateStore,
    mock_gh: MagicMock,
    mock_discord: MagicMock,
) -> None:
    run(sample_settings, state_store, mock_gh, mock_discord)
    mock_gh.get_new_package_versions.assert_not_called()
    mock_discord.send_message.assert_not_called()


def test_new_version_sends_discord(
    tmp_path: object,
    state_store: StateStore,
    mock_gh: MagicMock,
    mock_discord: MagicMock,
) -> None:
    settings = _settings_with_ghcr(tmp_path)
    state_store.set_ghcr("owner/my-app", ["1.0.0"])
    mock_gh.get_new_package_versions.return_value = ["1.1.0"]
    run(settings, state_store, mock_gh, mock_discord)
    mock_discord.send_message.assert_called_once()
    msg = mock_discord.send_message.call_args[0][0]
    assert "1.1.0" in msg


def test_first_run_initializes_without_notification(
    tmp_path: object,
    state_store: StateStore,
    mock_gh: MagicMock,
    mock_discord: MagicMock,
) -> None:
    settings = _settings_with_ghcr(tmp_path)
    # Empty seen list = first run
    mock_gh.get_new_package_versions.return_value = ["1.0.0", "0.9.0"]
    run(settings, state_store, mock_gh, mock_discord)
    mock_discord.send_message.assert_not_called()
    assert "1.0.0" in state_store.get_ghcr("owner/my-app")


def test_no_new_versions_no_discord(
    tmp_path: object,
    state_store: StateStore,
    mock_gh: MagicMock,
    mock_discord: MagicMock,
) -> None:
    settings = _settings_with_ghcr(tmp_path)
    state_store.set_ghcr("owner/my-app", ["1.0.0"])
    mock_gh.get_new_package_versions.return_value = []
    run(settings, state_store, mock_gh, mock_discord)
    mock_discord.send_message.assert_not_called()


def test_discord_failure_state_not_advanced(
    tmp_path: object,
    state_store: StateStore,
    mock_gh: MagicMock,
    mock_discord: MagicMock,
) -> None:
    settings = _settings_with_ghcr(tmp_path)
    state_store.set_ghcr("owner/my-app", ["1.0.0"])
    mock_gh.get_new_package_versions.return_value = ["1.1.0"]
    mock_discord.send_message.side_effect = RuntimeError("discord down")
    with pytest.raises(RuntimeError):
        run(settings, state_store, mock_gh, mock_discord)
    assert state_store.get_ghcr("owner/my-app") == ["1.0.0"]


def test_routes_to_releases_channel(
    tmp_path: object,
    state_store: StateStore,
    mock_gh: MagicMock,
    mock_discord: MagicMock,
) -> None:
    from git_activity_monitor.discord_client import DiscordClient

    settings = _settings_with_ghcr(tmp_path)
    state_store.set_ghcr("owner/my-app", ["1.0.0"])
    mock_gh.get_new_package_versions.return_value = ["1.1.0"]
    releases_client = MagicMock(spec=DiscordClient)
    releases_client.send_message.return_value = {"id": "1"}

    run(settings, state_store, mock_gh, mock_discord, releases_discord_client=releases_client)

    releases_client.send_message.assert_called_once()
    mock_discord.send_message.assert_not_called()


def test_sha_tag_omitted_from_message(
    tmp_path: object,
    state_store: StateStore,
    mock_gh: MagicMock,
    mock_discord: MagicMock,
) -> None:
    settings = _settings_with_ghcr(tmp_path)
    state_store.set_ghcr("owner/my-app", ["1.0.0"])
    mock_gh.get_new_package_versions.return_value = ["sha-13839b3", "1.1.0"]
    run(settings, state_store, mock_gh, mock_discord)
    mock_discord.send_message.assert_called_once()
    msg = mock_discord.send_message.call_args[0][0]
    assert "1.1.0" in msg
    assert "sha-13839b3" not in msg
    # sha tag is still tracked so it isn't reported again later
    assert "sha-13839b3" in state_store.get_ghcr("owner/my-app")


def test_only_sha_tags_updates_state_without_discord(
    tmp_path: object,
    state_store: StateStore,
    mock_gh: MagicMock,
    mock_discord: MagicMock,
) -> None:
    settings = _settings_with_ghcr(tmp_path)
    state_store.set_ghcr("owner/my-app", ["1.0.0"])
    mock_gh.get_new_package_versions.return_value = ["sha-13839b3"]
    run(settings, state_store, mock_gh, mock_discord)
    mock_discord.send_message.assert_not_called()
    assert "sha-13839b3" in state_store.get_ghcr("owner/my-app")


def test_fallback_to_main_when_no_releases_client(
    tmp_path: object,
    state_store: StateStore,
    mock_gh: MagicMock,
    mock_discord: MagicMock,
) -> None:
    settings = _settings_with_ghcr(tmp_path)
    state_store.set_ghcr("owner/my-app", ["1.0.0"])
    mock_gh.get_new_package_versions.return_value = ["1.1.0"]

    run(settings, state_store, mock_gh, mock_discord, releases_discord_client=None)

    mock_discord.send_message.assert_called_once()
