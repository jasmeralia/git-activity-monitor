from __future__ import annotations

from pathlib import Path

from github_activity_monitor.state import RepoState, StateStore


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


def test_unknown_repo_returns_zero_state(state_store: StateStore) -> None:
    rs = state_store.get_repo("nonexistent/repo")
    assert rs == RepoState()


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


def test_pinned_message_id(tmp_path: Path) -> None:
    store = StateStore(tmp_path / "state.json")
    store.load()
    assert store.pinned_message_id is None

    store.pinned_message_id = "9876543210"
    store.save()

    store2 = StateStore(tmp_path / "state.json")
    store2.load()
    assert store2.pinned_message_id == "9876543210"
