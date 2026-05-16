from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from git_activity_monitor.config import Settings
from git_activity_monitor.discord_client import DiscordClient
from git_activity_monitor.github_client import GitHubClient
from git_activity_monitor.state import StateStore


@pytest.fixture
def sample_settings(tmp_path: Path) -> Settings:
    return Settings(
        github_token="test-token",
        discord_webhook_url="https://discord.com/api/webhooks/123456789/test-webhook-token",
        repositories=["owner/repo"],
        state_file_path=tmp_path / "state.json",
        _env_file=None,  # type: ignore[call-arg]
    )  # owners is empty — explicit repositories list is sufficient


@pytest.fixture
def state_store(tmp_path: Path) -> StateStore:
    store = StateStore(tmp_path / "state.json")
    store.load()
    return store


@pytest.fixture
def mock_gh() -> MagicMock:
    return MagicMock(spec=GitHubClient)


@pytest.fixture
def mock_discord() -> MagicMock:
    return MagicMock(spec=DiscordClient)
