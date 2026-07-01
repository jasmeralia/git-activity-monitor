from __future__ import annotations

from pathlib import Path

from git_activity_monitor.state import RepoState, StateStore


def test_load_nonexistent_file(tmp_path: Path) -> None:
    store = StateStore(tmp_path / "state.json")
    store.load()  # should not raise
    assert store.get_repo("owner/repo") == RepoState()


def test_round_trip(tmp_path: Path) -> None:
    store = StateStore(tmp_path / "state.json")
    store.load()

    rs = RepoState(stars=10, watches=2, last_pr_number=5, last_issue_number=3, last_release_id=99)
    store.set_repo("owner/repo", rs)
    store.save()

    store2 = StateStore(tmp_path / "state.json")
    store2.load()
    assert store2.get_repo("owner/repo") == rs


def test_unknown_repo_returns_default_state(state_store: StateStore) -> None:
    rs = state_store.get_repo("nonexistent/repo")
    assert rs == RepoState()  # stars/watches=0, cursors=-1 (uninitialized)


def test_atomic_write_no_tmp_left(tmp_path: Path) -> None:
    store = StateStore(tmp_path / "state.json")
    store.load()
    store.save()
    tmp_files = list(tmp_path.glob(".state-*.tmp"))
    assert tmp_files == []


def test_corrupt_json_recovers(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    path.write_text("{not valid json", encoding="utf-8")
    store = StateStore(path)
    store.load()  # should not raise
    assert store.get_repo("owner/repo") == RepoState()
    assert (tmp_path / "state.corrupt").exists()
    assert not path.exists()


def test_invalid_schema_recovers(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    path.write_text("[]", encoding="utf-8")  # valid JSON but wrong type
    store = StateStore(path)
    store.load()  # should not raise
    assert store.get_repo("owner/repo") == RepoState()
    assert (tmp_path / "state.corrupt").exists()


def test_is_ghcr_initialized(tmp_path: Path) -> None:
    store = StateStore(tmp_path / "state.json")
    store.load()
    assert not store.is_ghcr_initialized("owner/pkg")
    store.set_ghcr("owner/pkg", [])  # initialize with empty list
    assert store.is_ghcr_initialized("owner/pkg")


def test_ghcr_round_trip(tmp_path: Path) -> None:
    store = StateStore(tmp_path / "state.json")
    store.load()

    store.set_ghcr("owner/pkg", ["1.0.0", "1.1.0"])
    store.save()

    store2 = StateStore(tmp_path / "state.json")
    store2.load()
    assert store2.get_ghcr("owner/pkg") == ["1.0.0", "1.1.0"]


def test_ghcr_unknown_returns_empty(state_store: StateStore) -> None:
    assert state_store.get_ghcr("no/package") == []


def test_pinned_message_ids(tmp_path: Path) -> None:
    store = StateStore(tmp_path / "state.json")
    store.load()
    assert store.pinned_message_ids == []
    assert store.pinned_message_id is None

    store.pinned_message_ids = ["9876543210", "1111111111"]
    store.save()

    store2 = StateStore(tmp_path / "state.json")
    store2.load()
    assert store2.pinned_message_ids == ["9876543210", "1111111111"]
    assert store2.pinned_message_id == "9876543210"


def test_pinned_message_ids_migrates_old_key(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    import json

    path.write_text(
        json.dumps({"version": 1, "repos": {}, "ghcr": {}, "pinned_message_id": "old-id"})
    )
    store = StateStore(path)
    store.load()
    assert store.pinned_message_ids == ["old-id"]
    assert store.pinned_message_id == "old-id"

    store.pinned_message_ids = ["new-id"]
    store.save()
    data = json.loads(path.read_text())
    assert "pinned_message_ids" in data
    assert "pinned_message_id" not in data


def test_releases_pinned_message_ids(tmp_path: Path) -> None:
    store = StateStore(tmp_path / "state.json")
    store.load()
    assert store.releases_pinned_message_ids == []
    assert store.releases_pinned_message_id is None

    store.releases_pinned_message_ids = ["rel-99", "rel-100"]
    store.save()

    store2 = StateStore(tmp_path / "state.json")
    store2.load()
    assert store2.releases_pinned_message_ids == ["rel-99", "rel-100"]
    assert store2.releases_pinned_message_id == "rel-99"


def test_releases_pinned_message_ids_migrates_old_key(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    import json

    path.write_text(
        json.dumps({"version": 1, "repos": {}, "ghcr": {}, "releases_pinned_message_id": "old"})
    )
    store = StateStore(path)
    store.load()
    assert store.releases_pinned_message_ids == ["old"]

    store.releases_pinned_message_ids = ["new"]
    store.save()
    data = json.loads(path.read_text())
    assert "releases_pinned_message_ids" in data
    assert "releases_pinned_message_id" not in data


def test_releases_pinned_repos(tmp_path: Path) -> None:
    store = StateStore(tmp_path / "state.json")
    store.load()
    assert store.releases_pinned_repos == []

    store.releases_pinned_repos = ["org/foo", "org/bar"]
    store.save()

    store2 = StateStore(tmp_path / "state.json")
    store2.load()
    assert store2.releases_pinned_repos == ["org/foo", "org/bar"]


def test_releases_pinned_descriptions(tmp_path: Path) -> None:
    store = StateStore(tmp_path / "state.json")
    store.load()
    assert store.releases_pinned_descriptions == {}

    store.releases_pinned_descriptions = {"org/foo": "A great tool", "org/bar": ""}
    store.save()

    store2 = StateStore(tmp_path / "state.json")
    store2.load()
    assert store2.releases_pinned_descriptions == {"org/foo": "A great tool", "org/bar": ""}
