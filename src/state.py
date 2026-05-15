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
    last_pr_number: int = 0
    last_issue_number: int = 0
    last_release_id: int = 0


class StateStore:
    """Loads and saves monitor state as JSON with atomic writes."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._data: dict[str, Any] = {}

    def load(self) -> None:
        if not self._path.exists():
            self._data = {"version": _STATE_VERSION, "repos": {}, "ghcr": {}}
            return
        try:
            with self._path.open() as fh:
                self._data = json.load(fh)
        except json.JSONDecodeError as exc:
            corrupt = self._path.with_suffix(".corrupt")
            self._path.rename(corrupt)
            logger.warning(
                "State file %s is corrupt (%s); starting fresh. Corrupt file saved to %s",
                self._path,
                exc,
                corrupt,
            )
            self._data = {"version": _STATE_VERSION, "repos": {}, "ghcr": {}}

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
            last_pr_number=raw.get("last_pr_number", 0),
            last_issue_number=raw.get("last_issue_number", 0),
            last_release_id=raw.get("last_release_id", 0),
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

    def set_ghcr(self, package: str, versions: list[str]) -> None:
        if "ghcr" not in self._data:
            self._data["ghcr"] = {}
        self._data["ghcr"][package] = {"seen_versions": versions}

    @property
    def pinned_message_id(self) -> str | None:
        val = self._data.get("pinned_message_id")
        return str(val) if val is not None else None

    @pinned_message_id.setter
    def pinned_message_id(self, value: str) -> None:
        self._data["pinned_message_id"] = value
