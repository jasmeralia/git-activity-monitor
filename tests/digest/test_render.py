from __future__ import annotations

import datetime as dt

from git_activity_monitor.digest.models import Alert, DigestData, MergedPR, OpenPR
from git_activity_monitor.digest.render import build_html, build_text

NOW = dt.datetime(2026, 7, 28, 15, 0, tzinfo=dt.UTC)


def _empty_data() -> DigestData:
    return DigestData(owner="jasmeralia", generated_at=NOW, repos_checked=5)


def test_build_html_empty_digest_has_zero_stats_and_no_sections() -> None:
    html = build_html(_empty_data())
    assert "Git Activity Digest: jasmeralia" in html
    assert ">0<" in html  # all three stat counts are zero
    assert "Merged in the last" not in html
    assert "Open Pull Requests" not in html
    assert "Open Security Alerts" not in html


def test_build_html_includes_merged_section() -> None:
    data = _empty_data()
    data.merged_prs = [
        MergedPR(
            repo="jasmeralia/foo",
            number=5,
            title="Fix thing",
            author="alice",
            url="https://gh/pr/5",
            merged_at=NOW - dt.timedelta(hours=1),
        )
    ]
    html = build_html(data)
    assert "Merged in the last 24h (1)" in html
    assert "jasmeralia/foo" in html
    assert "Fix thing" in html
    assert "https://gh/pr/5" in html


def test_build_html_groups_open_prs_by_repo() -> None:
    data = _empty_data()
    data.open_prs = [
        OpenPR(
            repo="jasmeralia/foo",
            number=1,
            title="A",
            author="alice",
            assignees="unassigned",
            url="https://gh/pr/1",
            created_at="2026-07-20",
        ),
        OpenPR(
            repo="jasmeralia/foo",
            number=2,
            title="B",
            author="bob",
            assignees="alice",
            url="https://gh/pr/2",
            created_at="2026-07-21",
        ),
    ]
    html = build_html(data)
    assert "jasmeralia/foo (2)" in html
    assert "#1 A" in html
    assert "#2 B" in html


def test_build_html_sorts_alerts_by_severity_and_shows_disabled_note() -> None:
    data = _empty_data()
    data.alerts = [
        Alert(
            repo="jasmeralia/foo",
            number=1,
            severity="moderate",
            ecosystem="npm",
            package="pkg-a",
            advisory_id="GHSA-1",
            summary="moderate issue",
            url="https://gh/alert/1",
            created_at="2026-07-20",
        ),
        Alert(
            repo="jasmeralia/foo",
            number=2,
            severity="critical",
            ecosystem="npm",
            package="pkg-b",
            advisory_id="GHSA-2",
            summary="critical issue",
            url="https://gh/alert/2",
            created_at="2026-07-21",
        ),
    ]
    data.alerts_disabled_repos = ["jasmeralia/no-graph"]
    html = build_html(data)
    assert html.index("pkg-b") < html.index("pkg-a")  # critical sorts before moderate
    assert "Dependabot alerts not enabled" in html
    assert "jasmeralia/no-graph" in html


def test_build_text_includes_all_sections() -> None:
    data = _empty_data()
    data.merged_prs = [
        MergedPR(
            repo="jasmeralia/foo",
            number=5,
            title="Fix thing",
            author="alice",
            url="https://gh/pr/5",
            merged_at=NOW - dt.timedelta(hours=1),
        )
    ]
    data.open_prs = [
        OpenPR(
            repo="jasmeralia/foo",
            number=1,
            title="A",
            author="alice",
            assignees="unassigned",
            url="https://gh/pr/1",
            created_at="2026-07-20",
        )
    ]
    data.alerts_disabled_repos = ["jasmeralia/no-graph"]

    text = build_text(data)
    assert "=== Merged in the last 24h ===" in text
    assert "=== Open Pull Requests ===" in text
    assert "Dependabot alerts not enabled" in text
    assert "jasmeralia/no-graph" in text
