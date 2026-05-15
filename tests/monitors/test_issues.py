from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from github_activity_monitor.config import Settings
from github_activity_monitor.monitors.issues import run
from github_activity_monitor.state import RepoState, StateStore


def _issue(number: int, labels: list[str] | None = None) -> dict:  # type: ignore[type-arg]
    return {
        "number": number,
        "title": f"Issue {number}",
        "html_url": f"https://gh/issue/{number}",
        "user": {"login": "bob"},
        "labels": [{"name": lbl} for lbl in (labels or [])],
    }


def test_no_new_issues_no_discord(
    sample_settings: Settings,
    state_store: StateStore,
    mock_gh: MagicMock,
    mock_discord: MagicMock,
) -> None:
    rs = RepoState(last_issue_number=5)
    state_store.set_repo("owner/repo", rs)
    mock_gh.get_new_issues.return_value = []
    run(sample_settings, state_store, mock_gh, mock_discord)
    mock_discord.send_message.assert_not_called()


def test_new_issue_sends_discord(
    sample_settings: Settings,
    state_store: StateStore,
    mock_gh: MagicMock,
    mock_discord: MagicMock,
) -> None:
    rs = RepoState(last_issue_number=3)
    state_store.set_repo("owner/repo", rs)
    mock_gh.get_new_issues.return_value = [_issue(4, labels=["bug"])]
    run(sample_settings, state_store, mock_gh, mock_discord)
    mock_discord.send_message.assert_called_once()
    msg = mock_discord.send_message.call_args[0][0]
    assert "#4" in msg
    assert "bug" in msg
    assert state_store.get_repo("owner/repo").last_issue_number == 4


def test_first_run_initializes_without_notification(
    sample_settings: Settings,
    state_store: StateStore,
    mock_gh: MagicMock,
    mock_discord: MagicMock,
) -> None:
    mock_gh.get_new_issues.return_value = [_issue(1), _issue(2)]
    run(sample_settings, state_store, mock_gh, mock_discord)
    mock_discord.send_message.assert_not_called()
    assert state_store.get_repo("owner/repo").last_issue_number == 2


def test_discord_failure_state_not_advanced(
    sample_settings: Settings,
    state_store: StateStore,
    mock_gh: MagicMock,
    mock_discord: MagicMock,
) -> None:
    rs = RepoState(last_issue_number=5)
    state_store.set_repo("owner/repo", rs)
    mock_gh.get_new_issues.return_value = [_issue(6)]
    mock_discord.send_message.side_effect = RuntimeError("discord down")
    with pytest.raises(RuntimeError):
        run(sample_settings, state_store, mock_gh, mock_discord)
    assert state_store.get_repo("owner/repo").last_issue_number == 5
