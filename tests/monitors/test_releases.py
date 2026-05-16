from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from git_activity_monitor.config import Settings
from git_activity_monitor.monitors.releases import run
from git_activity_monitor.state import RepoState, StateStore


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
