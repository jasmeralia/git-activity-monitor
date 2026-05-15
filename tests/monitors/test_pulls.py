from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from github_activity_monitor.config import Settings
from github_activity_monitor.monitors.pulls import run
from github_activity_monitor.state import RepoState, StateStore


def _pr(number: int) -> dict:  # type: ignore[type-arg]
    return {
        "number": number,
        "title": f"PR {number}",
        "html_url": f"https://gh/pr/{number}",
        "user": {"login": "alice"},
    }


def test_no_new_pulls_no_discord(
    sample_settings: Settings,
    state_store: StateStore,
    mock_gh: MagicMock,
    mock_discord: MagicMock,
) -> None:
    rs = RepoState(last_pr_number=10)
    state_store.set_repo("owner/repo", rs)
    mock_gh.get_new_pulls.return_value = []
    run(sample_settings, state_store, mock_gh, mock_discord)
    mock_discord.send_message.assert_not_called()


def test_new_pull_sends_discord(
    sample_settings: Settings,
    state_store: StateStore,
    mock_gh: MagicMock,
    mock_discord: MagicMock,
) -> None:
    rs = RepoState(last_pr_number=5)
    state_store.set_repo("owner/repo", rs)
    mock_gh.get_new_pulls.return_value = [_pr(6)]
    run(sample_settings, state_store, mock_gh, mock_discord)
    mock_discord.send_message.assert_called_once()
    assert state_store.get_repo("owner/repo").last_pr_number == 6


def test_first_run_initializes_without_notification(
    sample_settings: Settings,
    state_store: StateStore,
    mock_gh: MagicMock,
    mock_discord: MagicMock,
) -> None:
    # last_pr_number=-1 (default) means first run
    mock_gh.get_new_pulls.return_value = [_pr(1), _pr(2), _pr(3)]
    run(sample_settings, state_store, mock_gh, mock_discord)
    mock_discord.send_message.assert_not_called()
    assert state_store.get_repo("owner/repo").last_pr_number == 3


def test_discord_failure_state_not_advanced(
    sample_settings: Settings,
    state_store: StateStore,
    mock_gh: MagicMock,
    mock_discord: MagicMock,
) -> None:
    rs = RepoState(last_pr_number=5)
    state_store.set_repo("owner/repo", rs)
    mock_gh.get_new_pulls.return_value = [_pr(6)]
    mock_discord.send_message.side_effect = RuntimeError("discord down")
    with pytest.raises(RuntimeError):
        run(sample_settings, state_store, mock_gh, mock_discord)
    assert state_store.get_repo("owner/repo").last_pr_number == 5


def test_multiple_prs_one_message(
    sample_settings: Settings,
    state_store: StateStore,
    mock_gh: MagicMock,
    mock_discord: MagicMock,
) -> None:
    rs = RepoState(last_pr_number=10)
    state_store.set_repo("owner/repo", rs)
    mock_gh.get_new_pulls.return_value = [_pr(11), _pr(12), _pr(13)]
    run(sample_settings, state_store, mock_gh, mock_discord)
    assert mock_discord.send_message.call_count == 1
    assert state_store.get_repo("owner/repo").last_pr_number == 13
