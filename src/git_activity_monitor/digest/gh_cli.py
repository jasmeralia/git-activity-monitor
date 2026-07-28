"""Thin subprocess wrappers around the `gh` CLI.

Uses the `gh` CLI (rather than the httpx-based GitHubClient elsewhere in this
package) deliberately: the host this digest runs on (gelfling) already has
`gh` installed and authenticated with no GITHUB_TOKEN wiring, and the local
MTA needs no SMTP credentials either — see mailer.py. Keeping that zero-secret
deployment story was the whole reason this digest lives on gelfling in the
first place (see rincity-infra's AGENTS.md, "Git Activity Digest" section).
"""

from __future__ import annotations

import datetime as dt
import json
import subprocess  # gh CLI is the trusted, already-authenticated data source here
from typing import Any


class AlertsDisabledError(Exception):
    """Dependabot alerts (or the dependency graph) aren't enabled for a repo."""


def _run_json(args: list[str]) -> Any:
    result = subprocess.run(  # fixed argv, no shell, no user input
        ["gh", *args],
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout) if result.stdout.strip() else []


def get_authenticated_user() -> str:
    result = subprocess.run(
        ["gh", "api", "user", "-q", ".login"],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def list_repos(owner: str) -> list[str]:
    """Non-fork, non-archived repos owned directly by `owner`, sorted by name."""
    items = _run_json(
        [
            "repo",
            "list",
            owner,
            "--source",
            "--no-archived",
            "--limit",
            "1000",
            "--json",
            "nameWithOwner",
        ]
    )
    return sorted(item["nameWithOwner"] for item in items)


def list_open_prs(repo: str) -> list[dict[str, Any]]:
    """Raw open-PR dicts for one repo: number, title, author, assignees, url, createdAt."""
    return list(
        _run_json(
            [
                "pr",
                "list",
                "--repo",
                repo,
                "--state",
                "open",
                "--limit",
                "200",
                "--json",
                "number,title,author,assignees,url,createdAt",
            ]
        )
    )


def list_merged_prs_since(repo: str, since: dt.datetime) -> list[dict[str, Any]]:
    """Raw merged-PR dicts for one repo, merged at or after `since` (UTC)."""
    since_query = since.astimezone(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    return list(
        _run_json(
            [
                "pr",
                "list",
                "--repo",
                repo,
                "--search",
                f"is:merged merged:>={since_query}",
                "--limit",
                "200",
                "--json",
                "number,title,author,url,mergedAt",
            ]
        )
    )


def list_open_alerts(repo: str) -> list[dict[str, Any]]:
    """Raw open Dependabot alert dicts for one repo.

    Raises AlertsDisabledError when the repo has Dependabot alerts (or its
    dependency graph) turned off -- GitHub reports that as a 403, distinct
    from a real fetch failure.
    """
    try:
        result = subprocess.run(
            [
                "gh",
                "api",
                f"repos/{repo}/dependabot/alerts?state=open&per_page=100",
                "--paginate",
            ],
            capture_output=True,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        if "disabled" in (exc.stderr or "").lower():
            raise AlertsDisabledError(repo) from exc
        raise
    stdout = result.stdout.strip()
    if not stdout:
        return []
    # --paginate concatenates one JSON array per page back-to-back, not a
    # single combined array, so decode them one at a time.
    decoder = json.JSONDecoder()
    alerts: list[dict[str, Any]] = []
    idx = 0
    while idx < len(stdout):
        while idx < len(stdout) and stdout[idx].isspace():
            idx += 1
        if idx >= len(stdout):
            break
        page, end = decoder.raw_decode(stdout, idx)
        alerts.extend(page)
        idx = end
    return alerts
