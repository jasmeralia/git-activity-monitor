from __future__ import annotations

import datetime as dt
from unittest.mock import patch

from git_activity_monitor.digest import gh_cli
from git_activity_monitor.digest.collect import collect_digest

NOW = dt.datetime(2026, 7, 28, 15, 0, tzinfo=dt.UTC)


def _open_pr(number: int, assignees: list[str] | None = None) -> dict:  # type: ignore[type-arg]
    return {
        "number": number,
        "title": f"PR {number}",
        "author": {"login": "alice"},
        "assignees": [{"login": a} for a in (assignees or [])],
        "url": f"https://gh/pr/{number}",
        "createdAt": "2026-07-20T10:00:00Z",
    }


def _merged_pr(number: int, merged_at: str) -> dict:  # type: ignore[type-arg]
    return {
        "number": number,
        "title": f"Merged PR {number}",
        "author": {"login": "bob"},
        "url": f"https://gh/pr/{number}",
        "mergedAt": merged_at,
    }


def _alert(number: int, severity: str = "high") -> dict:  # type: ignore[type-arg]
    return {
        "number": number,
        "security_advisory": {
            "severity": severity,
            "ghsa_id": f"GHSA-{number}",
            "cve_id": None,
            "summary": "Something bad",
        },
        "dependency": {"package": {"ecosystem": "npm", "name": "leftpad"}},
        "html_url": f"https://gh/alert/{number}",
        "created_at": "2026-07-21T10:00:00Z",
    }


@patch("git_activity_monitor.digest.collect.gh_cli.list_open_alerts")
@patch("git_activity_monitor.digest.collect.gh_cli.list_merged_prs_since")
@patch("git_activity_monitor.digest.collect.gh_cli.list_open_prs")
@patch("git_activity_monitor.digest.collect.gh_cli.list_repos")
def test_collect_digest_aggregates_across_repos(
    mock_list_repos, mock_open_prs, mock_merged_prs, mock_alerts
) -> None:
    mock_list_repos.return_value = ["jasmeralia/a", "jasmeralia/b"]
    mock_open_prs.side_effect = lambda repo: [_open_pr(1)] if repo == "jasmeralia/a" else []
    mock_merged_prs.side_effect = (
        lambda repo, since: [_merged_pr(2, "2026-07-28T10:00:00Z")]
        if repo == "jasmeralia/b"
        else []
    )
    mock_alerts.side_effect = lambda repo: [_alert(3, "critical")] if repo == "jasmeralia/a" else []

    data = collect_digest("jasmeralia", now=NOW)

    assert data.repos_checked == 2
    assert data.open_pr_count == 1
    assert data.open_prs[0].repo == "jasmeralia/a"
    assert data.open_prs[0].assignees == "unassigned"
    assert data.merged_pr_count == 1
    assert data.merged_prs[0].repo == "jasmeralia/b"
    assert data.alert_count == 1
    assert data.alerts[0].severity == "critical"
    assert data.alerts[0].advisory_id == "GHSA-3"


@patch("git_activity_monitor.digest.collect.gh_cli.list_open_alerts")
@patch("git_activity_monitor.digest.collect.gh_cli.list_merged_prs_since")
@patch("git_activity_monitor.digest.collect.gh_cli.list_open_prs")
@patch("git_activity_monitor.digest.collect.gh_cli.list_repos")
def test_collect_digest_records_assignees(
    mock_list_repos, mock_open_prs, mock_merged_prs, mock_alerts
) -> None:
    mock_list_repos.return_value = ["jasmeralia/a"]
    mock_open_prs.return_value = [_open_pr(1, assignees=["alice", "bob"])]
    mock_merged_prs.return_value = []
    mock_alerts.return_value = []

    data = collect_digest("jasmeralia", now=NOW)

    assert data.open_prs[0].assignees == "alice, bob"


@patch("git_activity_monitor.digest.collect.gh_cli.list_open_alerts")
@patch("git_activity_monitor.digest.collect.gh_cli.list_merged_prs_since")
@patch("git_activity_monitor.digest.collect.gh_cli.list_open_prs")
@patch("git_activity_monitor.digest.collect.gh_cli.list_repos")
def test_collect_digest_tracks_disabled_alert_repos(
    mock_list_repos, mock_open_prs, mock_merged_prs, mock_alerts
) -> None:
    mock_list_repos.return_value = ["jasmeralia/a"]
    mock_open_prs.return_value = []
    mock_merged_prs.return_value = []
    mock_alerts.side_effect = gh_cli.AlertsDisabledError("jasmeralia/a")

    data = collect_digest("jasmeralia", now=NOW)

    assert data.alerts_disabled_repos == ["jasmeralia/a"]
    assert data.alert_count == 0
    assert data.is_empty()


@patch("git_activity_monitor.digest.collect.gh_cli.list_open_alerts")
@patch("git_activity_monitor.digest.collect.gh_cli.list_merged_prs_since")
@patch("git_activity_monitor.digest.collect.gh_cli.list_open_prs")
@patch("git_activity_monitor.digest.collect.gh_cli.list_repos")
def test_collect_digest_one_repo_failure_does_not_abort_others(
    mock_list_repos, mock_open_prs, mock_merged_prs, mock_alerts
) -> None:
    mock_list_repos.return_value = ["jasmeralia/broken", "jasmeralia/ok"]
    mock_open_prs.side_effect = (
        lambda repo: (_ for _ in ()).throw(RuntimeError("boom"))
        if repo == "jasmeralia/broken"
        else [_open_pr(9)]
    )
    mock_merged_prs.return_value = []
    mock_alerts.return_value = []

    data = collect_digest("jasmeralia", now=NOW)

    assert data.open_pr_count == 1
    assert data.open_prs[0].repo == "jasmeralia/ok"
