from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import httpx

from git_activity_monitor.config import Settings
from git_activity_monitor.monitors.releases_pinned import run
from git_activity_monitor.state import StateStore


def _settings(tmp_path: Path, owners: list[str] | None = None) -> Settings:
    return Settings(
        github_token="tok",
        discord_webhook_url="https://discord.com/api/webhooks/1/t",
        owners=owners or ["myorg"],
        enabled_events=["releases"],
        state_file_path=tmp_path / "state.json",
        _env_file=None,  # type: ignore[call-arg]
    )


def _meta(full_name: str, private: bool = False, description: str = "") -> dict:  # type: ignore[type-arg]
    return {"full_name": full_name, "private": private, "description": description}


def test_first_run_sends_message(
    tmp_path: Path,
    state_store: StateStore,
    mock_gh: MagicMock,
    mock_discord: MagicMock,
) -> None:
    settings = _settings(tmp_path)
    mock_gh.get_owner_repos_metadata.return_value = [_meta("myorg/repo-a", description="A repo")]
    mock_discord.send_message.return_value = {"id": "111"}

    run(settings, state_store, mock_gh, mock_discord)

    mock_discord.send_message.assert_called_once()
    content = mock_discord.send_message.call_args[0][0]
    assert "myorg/repo-a" in content
    assert "A repo" in content
    assert state_store.releases_pinned_message_id == "111"
    assert state_store.releases_pinned_repos == ["myorg/repo-a"]
    assert state_store.releases_pinned_descriptions == {"myorg/repo-a": "A repo"}


def test_no_change_no_discord(
    tmp_path: Path,
    state_store: StateStore,
    mock_gh: MagicMock,
    mock_discord: MagicMock,
) -> None:
    settings = _settings(tmp_path)
    mock_gh.get_owner_repos_metadata.return_value = [_meta("myorg/repo-a", description="A repo")]
    state_store.releases_pinned_repos = ["myorg/repo-a"]
    state_store.releases_pinned_descriptions = {"myorg/repo-a": "A repo"}

    run(settings, state_store, mock_gh, mock_discord)

    mock_discord.send_message.assert_not_called()
    mock_discord.edit_message.assert_not_called()


def test_repo_list_change_triggers_update(
    tmp_path: Path,
    state_store: StateStore,
    mock_gh: MagicMock,
    mock_discord: MagicMock,
) -> None:
    settings = _settings(tmp_path)
    mock_gh.get_owner_repos_metadata.return_value = [
        _meta("myorg/repo-a"),
        _meta("myorg/repo-b"),
    ]
    state_store.releases_pinned_repos = ["myorg/repo-a"]
    state_store.releases_pinned_descriptions = {"myorg/repo-a": ""}
    state_store.releases_pinned_message_id = "999"
    mock_discord.edit_message.return_value = {"id": "999"}

    run(settings, state_store, mock_gh, mock_discord)

    mock_discord.edit_message.assert_called_once()
    content = mock_discord.edit_message.call_args[0][1]
    assert "myorg/repo-b" in content
    assert state_store.releases_pinned_repos == ["myorg/repo-a", "myorg/repo-b"]


def test_description_change_triggers_update(
    tmp_path: Path,
    state_store: StateStore,
    mock_gh: MagicMock,
    mock_discord: MagicMock,
) -> None:
    settings = _settings(tmp_path)
    mock_gh.get_owner_repos_metadata.return_value = [_meta("myorg/repo-a", description="New desc")]
    state_store.releases_pinned_repos = ["myorg/repo-a"]
    state_store.releases_pinned_descriptions = {"myorg/repo-a": "Old desc"}
    state_store.releases_pinned_message_id = "42"
    mock_discord.edit_message.return_value = {"id": "42"}

    run(settings, state_store, mock_gh, mock_discord)

    mock_discord.edit_message.assert_called_once()
    content = mock_discord.edit_message.call_args[0][1]
    assert "New desc" in content


def test_edit_when_pinned_id_in_settings(
    tmp_path: Path,
    state_store: StateStore,
    mock_gh: MagicMock,
    mock_discord: MagicMock,
) -> None:
    settings = Settings(
        github_token="tok",
        discord_webhook_url="https://discord.com/api/webhooks/1/t",
        owners=["myorg"],
        discord_releases_pinned_message_id="from-env",
        enabled_events=["releases"],
        state_file_path=tmp_path / "state.json",
        _env_file=None,  # type: ignore[call-arg]
    )
    mock_gh.get_owner_repos_metadata.return_value = [_meta("myorg/repo-a")]
    mock_discord.edit_message.return_value = {"id": "from-env"}

    run(settings, state_store, mock_gh, mock_discord)

    mock_discord.edit_message.assert_called_once_with(
        "from-env", mock_discord.edit_message.call_args[0][1]
    )
    mock_discord.send_message.assert_not_called()


def test_edit_404_falls_back_to_send(
    tmp_path: Path,
    state_store: StateStore,
    mock_gh: MagicMock,
    mock_discord: MagicMock,
) -> None:
    settings = _settings(tmp_path)
    mock_gh.get_owner_repos_metadata.return_value = [_meta("myorg/repo-a")]
    state_store.releases_pinned_message_id = "deleted"
    mock_discord.edit_message.side_effect = httpx.HTTPStatusError(
        "not found", request=MagicMock(), response=MagicMock(status_code=404)
    )
    mock_discord.send_message.return_value = {"id": "new-id"}

    run(settings, state_store, mock_gh, mock_discord)

    mock_discord.send_message.assert_called_once()
    assert state_store.releases_pinned_message_id == "new-id"


def test_api_error_returns_without_update(
    tmp_path: Path,
    state_store: StateStore,
    mock_gh: MagicMock,
    mock_discord: MagicMock,
) -> None:
    settings = _settings(tmp_path)
    mock_gh.get_owner_repos_metadata.side_effect = RuntimeError("API down")

    run(settings, state_store, mock_gh, mock_discord)

    mock_discord.send_message.assert_not_called()
    assert state_store.releases_pinned_repos == []


def test_skips_private_repos(
    tmp_path: Path,
    state_store: StateStore,
    mock_gh: MagicMock,
    mock_discord: MagicMock,
) -> None:
    settings = _settings(tmp_path)
    mock_gh.get_owner_repos_metadata.return_value = [
        _meta("myorg/public-repo", private=False, description="Public"),
        _meta("myorg/private-repo", private=True, description="Private"),
    ]
    mock_discord.send_message.return_value = {"id": "1"}

    run(settings, state_store, mock_gh, mock_discord)

    content = mock_discord.send_message.call_args[0][0]
    assert "myorg/public-repo" in content
    assert "myorg/private-repo" not in content
    assert state_store.releases_pinned_repos == ["myorg/public-repo"]


def test_catalog_contains_github_link(
    tmp_path: Path,
    state_store: StateStore,
    mock_gh: MagicMock,
    mock_discord: MagicMock,
) -> None:
    settings = _settings(tmp_path)
    mock_gh.get_owner_repos_metadata.return_value = [_meta("myorg/cool-tool")]
    mock_discord.send_message.return_value = {"id": "1"}

    run(settings, state_store, mock_gh, mock_discord)

    content = mock_discord.send_message.call_args[0][0]
    assert "[myorg/cool-tool](https://github.com/myorg/cool-tool)" in content


def test_repo_with_no_description_omits_dash(
    tmp_path: Path,
    state_store: StateStore,
    mock_gh: MagicMock,
    mock_discord: MagicMock,
) -> None:
    settings = _settings(tmp_path)
    mock_gh.get_owner_repos_metadata.return_value = [_meta("myorg/nodesc", description="")]
    mock_discord.send_message.return_value = {"id": "1"}

    run(settings, state_store, mock_gh, mock_discord)

    content = mock_discord.send_message.call_args[0][0]
    assert " — " not in content.split("\n")[-1]


def test_long_description_truncated() -> None:
    from git_activity_monitor.monitors.releases_pinned import _build_catalog

    repos = ["myorg/repo-a"]
    descriptions = {"myorg/repo-a": "x" * 100}
    content = _build_catalog(repos, descriptions, 0)
    assert "x" * 61 not in content
    assert "…" in content


def test_catalog_truncates_when_too_many_repos() -> None:
    from git_activity_monitor.monitors.releases_pinned import _MAX_LEN, _build_catalog

    repos = [f"myorg/repo-{i:03d}" for i in range(50)]
    descriptions = {r: "A description for this repository." for r in repos}
    content = _build_catalog(repos, descriptions, 0)
    assert len(content) <= _MAX_LEN
    assert "…and" in content
