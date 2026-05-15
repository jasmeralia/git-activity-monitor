from __future__ import annotations

import logging
from pathlib import Path

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_VALID_EVENTS: frozenset[str] = frozenset({"stars", "watches", "prs", "issues", "releases", "ghcr"})


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
    )

    github_token: str
    discord_webhook_url: str
    discord_pinned_message_id: str | None = None

    poll_interval_seconds: int = 300
    owners: list[str] = []
    repositories: list[str] = []
    ghcr_packages: list[str] = []
    enabled_events: list[str] = list(_VALID_EVENTS)

    state_file_path: Path = Path("/data/state.json")
    log_level: str = "INFO"

    @field_validator("owners", "repositories", "ghcr_packages", "enabled_events", mode="before")
    @classmethod
    def _split_comma(cls, v: object) -> object:
        if isinstance(v, str):
            return [item.strip() for item in v.split(",") if item.strip()]
        return v

    @field_validator("poll_interval_seconds", mode="after")
    @classmethod
    def _validate_poll_interval(cls, v: int) -> int:
        if v < 30:
            raise ValueError(f"POLL_INTERVAL_SECONDS must be at least 30, got {v}")
        return v

    @field_validator("repositories", mode="after")
    @classmethod
    def _validate_repo_format(cls, v: list[str]) -> list[str]:
        for repo in v:
            if repo.count("/") != 1:
                raise ValueError(f"Repository must be 'owner/repo', got: {repo!r}")
        return v

    @field_validator("ghcr_packages", mode="after")
    @classmethod
    def _validate_ghcr_package_format(cls, v: list[str]) -> list[str]:
        for pkg in v:
            if pkg.count("/") != 1:
                raise ValueError(f"GHCR package must be 'owner/package', got: {pkg!r}")
        return v

    @field_validator("enabled_events", mode="after")
    @classmethod
    def _validate_event_names(cls, v: list[str]) -> list[str]:
        unknown = set(v) - _VALID_EVENTS
        if unknown:
            raise ValueError(f"Unknown event types: {unknown!r}")
        return v

    @field_validator("log_level", mode="after")
    @classmethod
    def _validate_log_level(cls, v: str) -> str:
        v = v.upper()
        if not hasattr(logging, v):
            raise ValueError(f"Invalid log level: {v!r}")
        return v

    @model_validator(mode="after")
    def _require_owners_or_repositories(self) -> Settings:
        if not self.owners and not self.repositories:
            raise ValueError("At least one of OWNERS or REPOSITORIES must be set.")
        return self

    @model_validator(mode="after")
    def _warn_ghcr_no_packages(self) -> Settings:
        if "ghcr" in self.enabled_events and not self.ghcr_packages:
            logging.getLogger(__name__).warning(
                "'ghcr' is in ENABLED_EVENTS but GHCR_PACKAGES is empty; "
                "ghcr monitor will be a no-op."
            )
        return self
