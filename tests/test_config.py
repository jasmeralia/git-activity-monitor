from __future__ import annotations

import logging
from pathlib import Path

import pytest
from pydantic import ValidationError

from github_activity_monitor.config import Settings


def _make(**kwargs: object) -> Settings:
    base = {
        "github_token": "tok",
        "discord_webhook_url": "https://discord.com/api/webhooks/1/t",
        "repositories": ["owner/repo"],
        "_env_file": None,
    }
    base.update(kwargs)
    return Settings(**base)  # type: ignore[arg-type]


def test_basic_valid() -> None:
    s = _make()
    assert s.github_token == "tok"
    assert s.repositories == ["owner/repo"]
    assert s.poll_interval_seconds == 300


def test_comma_split_repositories() -> None:
    s = _make(repositories="owner/a,owner/b, owner/c")
    assert s.repositories == ["owner/a", "owner/b", "owner/c"]


def test_comma_split_enabled_events() -> None:
    s = _make(enabled_events="stars,prs")
    assert s.enabled_events == ["stars", "prs"]


def test_comma_split_ghcr_packages() -> None:
    s = _make(ghcr_packages="owner/pkg1,owner/pkg2")
    assert s.ghcr_packages == ["owner/pkg1", "owner/pkg2"]


def test_invalid_repo_format_raises() -> None:
    with pytest.raises(ValidationError, match="owner/repo"):
        _make(repositories=["notarepo"])


def test_unknown_event_raises() -> None:
    with pytest.raises(ValidationError, match="Unknown event"):
        _make(enabled_events=["stars", "unknown_event"])


def test_missing_github_token_raises() -> None:
    with pytest.raises(ValidationError):
        Settings(
            discord_webhook_url="https://discord.com/api/webhooks/1/t",
            repositories=["owner/repo"],
            _env_file=None,  # type: ignore[call-arg]
        )


def test_invalid_log_level_raises() -> None:
    with pytest.raises(ValidationError, match="Invalid log level"):
        _make(log_level="VERBOSE")


def test_ghcr_enabled_no_packages_warns(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING):
        _make(enabled_events="stars,ghcr", ghcr_packages=[])
    assert "ghcr" in caplog.text.lower()


def test_state_file_path_default() -> None:
    s = _make()
    assert s.state_file_path == Path("/data/state.json")


def test_pinned_message_id_optional() -> None:
    s = _make(discord_pinned_message_id="12345")
    assert s.discord_pinned_message_id == "12345"

    s2 = _make()
    assert s2.discord_pinned_message_id is None
