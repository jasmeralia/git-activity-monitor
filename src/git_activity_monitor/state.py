from __future__ import annotations

import contextlib
import json
import logging
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_STATE_VERSION = 1


@dataclass
class RepoState:
    stars: int = 0
    watches: int = 0
    last_pr_number: int = -1  # -1 = uninitialized; 0 = initialized, no PRs yet
    last_issue_number: int = -1  # -1 = uninitialized; 0 = initialized, no issues yet
    last_release_id: int = -1  # -1 = uninitialized; 0 = initialized, no releases yet


class StateStore:
    """Loads and saves monitor state as JSON with atomic writes."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._data: dict[str, Any] = {}

    def _reset(self) -> None:
        self._data = {"version": _STATE_VERSION, "repos": {}, "ghcr": {}}

    def load(self) -> None:
        if not self._path.exists():
            self._reset()
            return
        try:
            with self._path.open() as fh:
                data = json.load(fh)
        except json.JSONDecodeError as exc:
            corrupt = self._path.with_suffix(".corrupt")
            self._path.rename(corrupt)
            logger.warning(
                "State file %s is corrupt (%s); starting fresh. Corrupt file saved to %s",
                self._path,
                exc,
                corrupt,
            )
            self._reset()
            return

        if (
            not isinstance(data, dict)
            or not isinstance(data.get("repos", {}), dict)
            or not isinstance(data.get("ghcr", {}), dict)
        ):
            corrupt = self._path.with_suffix(".corrupt")
            self._path.rename(corrupt)
            logger.warning(
                "State file %s has invalid schema; starting fresh. Saved to %s",
                self._path,
                corrupt,
            )
            self._reset()
            return

        self._data = data

    def save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp_fd, tmp_path = tempfile.mkstemp(dir=self._path.parent, prefix=".state-", suffix=".tmp")
        try:
            with os.fdopen(tmp_fd, "w") as fh:
                json.dump(self._data, fh, indent=2)
            os.replace(tmp_path, self._path)
        except Exception:
            with contextlib.suppress(OSError):
                os.unlink(tmp_path)
            raise

    def get_repo(self, repo: str) -> RepoState:
        raw = self._data.get("repos", {}).get(repo, {})
        return RepoState(
            stars=raw.get("stars", 0),
            watches=raw.get("watches", 0),
            last_pr_number=raw.get("last_pr_number", -1),
            last_issue_number=raw.get("last_issue_number", -1),
            last_release_id=raw.get("last_release_id", -1),
        )

    def set_repo(self, repo: str, state: RepoState) -> None:
        if "repos" not in self._data:
            self._data["repos"] = {}
        self._data["repos"][repo] = {
            "stars": state.stars,
            "watches": state.watches,
            "last_pr_number": state.last_pr_number,
            "last_issue_number": state.last_issue_number,
            "last_release_id": state.last_release_id,
        }

    def get_ghcr(self, package: str) -> list[str]:
        return list(self._data.get("ghcr", {}).get(package, {}).get("seen_versions", []))

    def is_ghcr_initialized(self, package: str) -> bool:
        return package in self._data.get("ghcr", {})

    def set_ghcr(self, package: str, versions: list[str]) -> None:
        if "ghcr" not in self._data:
            self._data["ghcr"] = {}
        self._data["ghcr"][package] = {"seen_versions": versions}

    @property
    def pinned_message_ids(self) -> list[str]:
        ids = self._data.get("pinned_message_ids")
        if ids is not None:
            return [str(i) for i in ids]
        old = self._data.get("pinned_message_id")
        return [str(old)] if old is not None else []

    @pinned_message_ids.setter
    def pinned_message_ids(self, value: list[str]) -> None:
        self._data["pinned_message_ids"] = list(value)
        self._data.pop("pinned_message_id", None)

    @property
    def pinned_message_id(self) -> str | None:
        ids = self.pinned_message_ids
        return ids[0] if ids else None

    @property
    def pinned_repos(self) -> list[str]:
        val = self._data.get("pinned_repos", [])
        return [str(r) for r in val] if isinstance(val, list) else []

    @pinned_repos.setter
    def pinned_repos(self, value: list[str]) -> None:
        self._data["pinned_repos"] = list(value)

    @property
    def releases_pinned_message_ids(self) -> list[str]:
        ids = self._data.get("releases_pinned_message_ids")
        if ids is not None:
            return [str(i) for i in ids]
        old = self._data.get("releases_pinned_message_id")
        return [str(old)] if old is not None else []

    @releases_pinned_message_ids.setter
    def releases_pinned_message_ids(self, value: list[str]) -> None:
        self._data["releases_pinned_message_ids"] = list(value)
        self._data.pop("releases_pinned_message_id", None)

    @property
    def releases_pinned_message_id(self) -> str | None:
        ids = self.releases_pinned_message_ids
        return ids[0] if ids else None

    @property
    def releases_pinned_repos(self) -> list[str]:
        val = self._data.get("releases_pinned_repos", [])
        return [str(r) for r in val] if isinstance(val, list) else []

    @releases_pinned_repos.setter
    def releases_pinned_repos(self, value: list[str]) -> None:
        self._data["releases_pinned_repos"] = list(value)

    @property
    def releases_pinned_descriptions(self) -> dict[str, str]:
        val = self._data.get("releases_pinned_descriptions", {})
        return {str(k): str(v) for k, v in val.items()} if isinstance(val, dict) else {}

    @releases_pinned_descriptions.setter
    def releases_pinned_descriptions(self, value: dict[str, str]) -> None:
        self._data["releases_pinned_descriptions"] = dict(value)
