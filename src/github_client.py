from __future__ import annotations

import logging
from collections.abc import Iterator
from typing import Any

import httpx
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

logger = logging.getLogger(__name__)

_RATE_LIMIT_WARN_THRESHOLD = 50


def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in {429, 500, 502, 503, 504}
    return isinstance(exc, (httpx.TimeoutException, httpx.NetworkError))


class GitHubClient:
    _BASE = "https://api.github.com"

    def __init__(self, token: str, timeout: float = 30.0) -> None:
        self._client = httpx.Client(
            base_url=self._BASE,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            timeout=timeout,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> GitHubClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    @retry(
        retry=retry_if_exception(_is_retryable),
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=2, max=60),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )
    def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        resp = self._client.get(path, params=params)
        remaining = resp.headers.get("X-RateLimit-Remaining")
        if remaining is not None and int(remaining) < _RATE_LIMIT_WARN_THRESHOLD:
            logger.warning("GitHub rate limit low: %s remaining", remaining)
        resp.raise_for_status()
        return resp.json()

    def _paginate(
        self, path: str, params: dict[str, Any] | None = None
    ) -> Iterator[dict[str, Any]]:
        page = 1
        while True:
            p: dict[str, Any] = {**(params or {}), "per_page": 100, "page": page}
            items: list[dict[str, Any]] = self._get(path, params=p)
            if not items:
                break
            yield from items
            page += 1

    def get_repo_stats(self, owner: str, repo: str) -> dict[str, int]:
        data = self._get(f"/repos/{owner}/{repo}")
        return {
            "stars": data["stargazers_count"],
            "watches": data["subscribers_count"],
        }

    def get_new_pulls(self, owner: str, repo: str, since_number: int) -> list[dict[str, Any]]:
        results = []
        for pr in self._paginate(
            f"/repos/{owner}/{repo}/pulls",
            params={"state": "open", "sort": "created", "direction": "asc"},
        ):
            if pr["number"] > since_number:
                results.append(pr)
        return results

    def get_new_issues(self, owner: str, repo: str, since_number: int) -> list[dict[str, Any]]:
        results = []
        for item in self._paginate(
            f"/repos/{owner}/{repo}/issues",
            params={"state": "open", "sort": "created", "direction": "asc"},
        ):
            if "pull_request" in item:
                continue
            if item["number"] > since_number:
                results.append(item)
        return results

    def get_new_releases(self, owner: str, repo: str, since_id: int) -> list[dict[str, Any]]:
        results = []
        for release in self._paginate(f"/repos/{owner}/{repo}/releases"):
            if release["id"] <= since_id:
                break
            if not release.get("draft", False):
                results.append(release)
        return results

    def get_new_package_versions(
        self, owner: str, package_name: str, seen_versions: list[str]
    ) -> list[str]:
        versions = self._fetch_package_versions(owner, package_name)
        seen = set(seen_versions)
        return [v for v in versions if v not in seen]

    def get_owner_repos(self, owner: str) -> list[str]:
        """Return 'owner/repo' strings for all non-fork, non-archived repos under owner."""
        try:
            items = list(self._paginate(f"/users/{owner}/repos", params={"type": "owner"}))
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code != 404:
                raise
            items = list(self._paginate(f"/orgs/{owner}/repos", params={"type": "public"}))
        return [
            item["full_name"]
            for item in items
            if not item.get("fork", False) and not item.get("archived", False)
        ]

    def _fetch_package_versions(self, owner: str, package_name: str) -> list[str]:
        try:
            data = self._get(f"/users/{owner}/packages/container/{package_name}/versions")
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code != 404:
                raise
            data = self._get(f"/orgs/{owner}/packages/container/{package_name}/versions")
        tags: list[str] = []
        for version in data:
            tags.extend(version.get("metadata", {}).get("container", {}).get("tags", []))
        return tags
