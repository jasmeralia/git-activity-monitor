from __future__ import annotations

from unittest.mock import MagicMock

import httpx
import pytest

from git_activity_monitor.config import Settings
from git_activity_monitor.monitors.stars import run
from git_activity_monitor.state import StateStore


def test_no_change_no_discord_call(
    sample_settings: Settings,
    state_store: StateStore,
    mock_gh: MagicMock,
    mock_discord: MagicMock,
) -> None:
    state_store.set_repo("owner/repo", state_store.get_repo("owner/repo"))
    state_store.pinned_repos = ["owner/repo"]
    mock_gh.get_repo_stats.return_value = {"stars": 0, "watches": 0, "archived": False}
    run(sample_settings, state_store, mock_gh, mock_discord)
    mock_discord.send_message.assert_not_called()
    mock_discord.edit_message.assert_not_called()


def test_archived_repo_excluded_from_summary(
    sample_settings: Settings,
    state_store: StateStore,
    mock_gh: MagicMock,
    mock_discord: MagicMock,
) -> None:
    state_store.pinned_repos = ["owner/repo"]
    mock_gh.get_repo_stats.return_value = {"stars": 99, "watches": 9, "archived": True}
    mock_discord.send_message.return_value = {"id": "1"}
    run(sample_settings, state_store, mock_gh, mock_discord)
    # Repo dropped out of pinned_repos → refresh fires with an empty list
    mock_discord.send_message.assert_called_once()
    sent = mock_discord.send_message.call_args[0][0]
    assert "owner/repo" not in sent
    assert state_store.pinned_repos == []


def test_summary_contains_repo_link(
    sample_settings: Settings,
    state_store: StateStore,
    mock_gh: MagicMock,
    mock_discord: MagicMock,
) -> None:
    mock_gh.get_repo_stats.return_value = {"stars": 5, "watches": 1, "archived": False}
    mock_discord.send_message.return_value = {"id": "1"}
    run(sample_settings, state_store, mock_gh, mock_discord)
    sent = mock_discord.send_message.call_args[0][0]
    assert "[owner/repo](https://github.com/owner/repo)" in sent
    assert state_store.pinned_repos == ["owner/repo"]


def test_star_change_calls_send_when_no_pinned_id(
    sample_settings: Settings,
    state_store: StateStore,
    mock_gh: MagicMock,
    mock_discord: MagicMock,
) -> None:
    mock_gh.get_repo_stats.return_value = {"stars": 10, "watches": 1}
    mock_discord.send_message.return_value = {"id": "12345"}
    run(sample_settings, state_store, mock_gh, mock_discord)
    mock_discord.send_message.assert_called_once()
    assert state_store.pinned_message_id == "12345"
    # New counts must be persisted so the next cycle doesn't re-trigger
    rs = state_store.get_repo("owner/repo")
    assert rs.stars == 10
    assert rs.watches == 1


def test_summary_contains_new_counts(
    sample_settings: Settings,
    state_store: StateStore,
    mock_gh: MagicMock,
    mock_discord: MagicMock,
) -> None:
    mock_gh.get_repo_stats.return_value = {"stars": 42, "watches": 7}
    mock_discord.send_message.return_value = {"id": "1"}
    run(sample_settings, state_store, mock_gh, mock_discord)
    sent = mock_discord.send_message.call_args[0][0]
    assert "42" in sent
    assert "7" in sent


def test_star_change_calls_edit_with_pinned_id(
    sample_settings: Settings,
    state_store: StateStore,
    mock_gh: MagicMock,
    mock_discord: MagicMock,
) -> None:
    state_store.pinned_message_id = "99999"
    mock_gh.get_repo_stats.return_value = {"stars": 5, "watches": 2}
    mock_discord.edit_message.return_value = {"id": "99999"}
    run(sample_settings, state_store, mock_gh, mock_discord)
    mock_discord.edit_message.assert_called_once_with(
        "99999", mock_discord.edit_message.call_args[0][1]
    )
    mock_discord.send_message.assert_not_called()


def test_edit_404_falls_back_to_send(
    sample_settings: Settings,
    state_store: StateStore,
    mock_gh: MagicMock,
    mock_discord: MagicMock,
) -> None:
    state_store.pinned_message_id = "deleted-id"
    mock_gh.get_repo_stats.return_value = {"stars": 3, "watches": 1}
    mock_discord.edit_message.side_effect = httpx.HTTPStatusError(
        "not found", request=MagicMock(), response=MagicMock(status_code=404)
    )
    mock_discord.send_message.return_value = {"id": "new-id"}
    run(sample_settings, state_store, mock_gh, mock_discord)
    mock_discord.send_message.assert_called_once()
    assert state_store.pinned_message_id == "new-id"


def test_discord_failure_state_not_advanced(
    sample_settings: Settings,
    state_store: StateStore,
    mock_gh: MagicMock,
    mock_discord: MagicMock,
) -> None:
    mock_gh.get_repo_stats.return_value = {"stars": 50, "watches": 5}
    mock_discord.send_message.side_effect = RuntimeError("Discord down")
    with pytest.raises(RuntimeError):
        run(sample_settings, state_store, mock_gh, mock_discord)
    # State should not have been saved
    rs = state_store.get_repo("owner/repo")
    assert rs.stars == 0
