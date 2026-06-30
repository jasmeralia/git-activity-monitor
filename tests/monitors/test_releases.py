from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from git_activity_monitor.config import Settings
from git_activity_monitor.discord_client import DiscordClient
from git_activity_monitor.monitors.releases import run
from git_activity_monitor.state import RepoState, StateStore


def _settings_with_public(tmp_path: Path, repos: list[str]) -> Settings:
    return Settings(
        github_token="tok",
        discord_webhook_url="https://discord.com/api/webhooks/1/t",
        repositories=repos,
        public_repositories=repos,
        state_file_path=tmp_path / "state.json",
        _env_file=None,  # type: ignore[call-arg]
    )


def _release(rid: int, tag: str = "v1.0", body: str = "") -> dict:  # type: ignore[type-arg]
    return {
        "id": rid,
        "tag_name": tag,
        "name": tag,
        "html_url": f"https://gh/releases/{tag}",
        "body": body,
        "draft": False,
    }


def test_no_new_releases_no_discord(
    sample_settings: Settings,
    state_store: StateStore,
    mock_gh: MagicMock,
    mock_discord: MagicMock,
) -> None:
    rs = RepoState(last_release_id=100)
    state_store.set_repo("owner/repo", rs)
    mock_gh.get_new_releases.return_value = []
    run(sample_settings, state_store, mock_gh, mock_discord)
    mock_discord.send_message.assert_not_called()


def test_new_release_sends_discord(
    sample_settings: Settings,
    state_store: StateStore,
    mock_gh: MagicMock,
    mock_discord: MagicMock,
) -> None:
    rs = RepoState(last_release_id=100)
    state_store.set_repo("owner/repo", rs)
    mock_gh.get_new_releases.return_value = [_release(101, "v2.0")]
    run(sample_settings, state_store, mock_gh, mock_discord)
    mock_discord.send_message.assert_called_once()
    msg = mock_discord.send_message.call_args[0][0]
    assert "v2.0" in msg
    assert state_store.get_repo("owner/repo").last_release_id == 101


def test_release_body_truncated(
    sample_settings: Settings,
    state_store: StateStore,
    mock_gh: MagicMock,
    mock_discord: MagicMock,
) -> None:
    rs = RepoState(last_release_id=1)
    state_store.set_repo("owner/repo", rs)
    long_body = "x" * 300
    mock_gh.get_new_releases.return_value = [_release(2, body=long_body)]
    run(sample_settings, state_store, mock_gh, mock_discord)
    msg = mock_discord.send_message.call_args[0][0]
    assert "…" in msg
    assert "x" * 201 not in msg


def test_first_run_initializes_without_notification(
    sample_settings: Settings,
    state_store: StateStore,
    mock_gh: MagicMock,
    mock_discord: MagicMock,
) -> None:
    mock_gh.get_new_releases.return_value = [_release(50), _release(49)]
    run(sample_settings, state_store, mock_gh, mock_discord)
    mock_discord.send_message.assert_not_called()
    assert state_store.get_repo("owner/repo").last_release_id == 50


def test_discord_failure_state_not_advanced(
    sample_settings: Settings,
    state_store: StateStore,
    mock_gh: MagicMock,
    mock_discord: MagicMock,
) -> None:
    rs = RepoState(last_release_id=10)
    state_store.set_repo("owner/repo", rs)
    mock_gh.get_new_releases.return_value = [_release(11)]
    mock_discord.send_message.side_effect = RuntimeError("discord down")
    with pytest.raises(RuntimeError):
        run(sample_settings, state_store, mock_gh, mock_discord)
    assert state_store.get_repo("owner/repo").last_release_id == 10


def test_public_repo_routes_to_releases_channel(
    tmp_path: Path,
    state_store: StateStore,
    mock_gh: MagicMock,
    mock_discord: MagicMock,
) -> None:
    settings = _settings_with_public(tmp_path, ["owner/repo"])
    rs = RepoState(last_release_id=100)
    state_store.set_repo("owner/repo", rs)
    mock_gh.get_new_releases.return_value = [_release(101)]
    releases_client = MagicMock(spec=DiscordClient)
    releases_client.send_message.return_value = {"id": "1"}

    run(settings, state_store, mock_gh, mock_discord, releases_discord_client=releases_client)

    releases_client.send_message.assert_called_once()
    mock_discord.send_message.assert_not_called()


def test_private_repo_stays_on_main_channel(
    tmp_path: Path,
    state_store: StateStore,
    mock_gh: MagicMock,
    mock_discord: MagicMock,
) -> None:
    settings = Settings(
        github_token="tok",
        discord_webhook_url="https://discord.com/api/webhooks/1/t",
        repositories=["owner/repo"],
        public_repositories=[],  # repo not in public set → private
        state_file_path=tmp_path / "state.json",
        _env_file=None,  # type: ignore[call-arg]
    )
    rs = RepoState(last_release_id=10)
    state_store.set_repo("owner/repo", rs)
    mock_gh.get_new_releases.return_value = [_release(11)]
    releases_client = MagicMock(spec=DiscordClient)

    run(settings, state_store, mock_gh, mock_discord, releases_discord_client=releases_client)

    mock_discord.send_message.assert_called_once()
    releases_client.send_message.assert_not_called()


def test_fallback_to_main_when_no_releases_client(
    tmp_path: Path,
    state_store: StateStore,
    mock_gh: MagicMock,
    mock_discord: MagicMock,
) -> None:
    settings = _settings_with_public(tmp_path, ["owner/repo"])
    rs = RepoState(last_release_id=100)
    state_store.set_repo("owner/repo", rs)
    mock_gh.get_new_releases.return_value = [_release(101)]

    run(settings, state_store, mock_gh, mock_discord, releases_discord_client=None)

    mock_discord.send_message.assert_called_once()
