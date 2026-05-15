from __future__ import annotations

import httpx
import pytest
import respx

from github_activity_monitor.github_client import GitHubClient

_API = "https://api.github.com"


@pytest.fixture
def gh() -> GitHubClient:
    return GitHubClient(token="test-token")


def _paginated(items: list[object]) -> list[httpx.Response]:
    """Return items on first page, empty list on second (stops pagination)."""
    return [
        httpx.Response(200, json=items),
        httpx.Response(200, json=[]),
    ]


@respx.mock
def test_get_repo_stats(gh: GitHubClient) -> None:
    respx.get(f"{_API}/repos/owner/repo").mock(
        return_value=httpx.Response(200, json={"stargazers_count": 42, "subscribers_count": 7})
    )
    stats = gh.get_repo_stats("owner", "repo")
    assert stats == {"stars": 42, "watches": 7}


@respx.mock
def test_get_new_pulls_filters_by_number(gh: GitHubClient) -> None:
    respx.get(f"{_API}/repos/owner/repo/pulls").mock(
        side_effect=_paginated(
            [
                {"number": 10, "title": "Old", "html_url": "...", "user": {"login": "a"}},
                {"number": 11, "title": "New", "html_url": "...", "user": {"login": "b"}},
                {"number": 12, "title": "Newer", "html_url": "...", "user": {"login": "c"}},
            ]
        )
    )
    pulls = gh.get_new_pulls("owner", "repo", since_number=10)
    assert [p["number"] for p in pulls] == [11, 12]


@respx.mock
def test_get_new_issues_excludes_pull_requests(gh: GitHubClient) -> None:
    respx.get(f"{_API}/repos/owner/repo/issues").mock(
        side_effect=_paginated(
            [
                {
                    "number": 5,
                    "title": "Real issue",
                    "html_url": "...",
                    "user": {"login": "a"},
                    "labels": [],
                },
                {
                    "number": 6,
                    "title": "A PR",
                    "html_url": "...",
                    "user": {"login": "b"},
                    "labels": [],
                    "pull_request": {},
                },
            ]
        )
    )
    issues = gh.get_new_issues("owner", "repo", since_number=4)
    assert len(issues) == 1
    assert issues[0]["number"] == 5


@respx.mock
def test_get_new_releases_stops_at_known_id(gh: GitHubClient) -> None:
    # Releases don't use _paginate's empty-page stop; they stop at since_id
    respx.get(f"{_API}/repos/owner/repo/releases").mock(
        side_effect=_paginated(
            [
                {
                    "id": 300,
                    "tag_name": "v3.0",
                    "name": "v3.0",
                    "html_url": "...",
                    "body": "",
                    "draft": False,
                },
                {
                    "id": 200,
                    "tag_name": "v2.0",
                    "name": "v2.0",
                    "html_url": "...",
                    "body": "",
                    "draft": False,
                },
                {
                    "id": 100,
                    "tag_name": "v1.0",
                    "name": "v1.0",
                    "html_url": "...",
                    "body": "",
                    "draft": False,
                },
            ]
        )
    )
    releases = gh.get_new_releases("owner", "repo", since_id=200)
    assert len(releases) == 1
    assert releases[0]["id"] == 300


@respx.mock
def test_get_new_releases_skips_drafts(gh: GitHubClient) -> None:
    respx.get(f"{_API}/repos/owner/repo/releases").mock(
        side_effect=_paginated(
            [
                {
                    "id": 300,
                    "tag_name": "v3.0",
                    "name": "v3.0",
                    "html_url": "...",
                    "body": "",
                    "draft": True,
                },
                {
                    "id": 200,
                    "tag_name": "v2.0",
                    "name": "v2.0",
                    "html_url": "...",
                    "body": "",
                    "draft": False,
                },
            ]
        )
    )
    releases = gh.get_new_releases("owner", "repo", since_id=100)
    assert len(releases) == 1
    assert releases[0]["id"] == 200


@respx.mock
def test_get_new_package_versions_user_endpoint(gh: GitHubClient) -> None:
    respx.get(f"{_API}/users/owner/packages/container/pkg/versions").mock(
        return_value=httpx.Response(
            200,
            json=[
                {"metadata": {"container": {"tags": ["1.0.0", "latest"]}}},
                {"metadata": {"container": {"tags": ["0.9.0"]}}},
            ],
        )
    )
    new = gh.get_new_package_versions("owner", "pkg", seen_versions=["0.9.0"])
    assert set(new) == {"1.0.0", "latest"}


@respx.mock
def test_get_new_package_versions_org_fallback(gh: GitHubClient) -> None:
    respx.get(f"{_API}/users/org/packages/container/pkg/versions").mock(
        return_value=httpx.Response(404, json={"message": "Not Found"})
    )
    respx.get(f"{_API}/orgs/org/packages/container/pkg/versions").mock(
        return_value=httpx.Response(
            200,
            json=[{"metadata": {"container": {"tags": ["2.0.0"]}}}],
        )
    )
    new = gh.get_new_package_versions("org", "pkg", seen_versions=[])
    assert new == ["2.0.0"]


@respx.mock
def test_get_owner_repos_filters_forks_and_archived(gh: GitHubClient) -> None:
    respx.get(f"{_API}/users/alice/repos").mock(
        side_effect=_paginated(
            [
                {"full_name": "alice/good", "fork": False, "archived": False},
                {"full_name": "alice/forked", "fork": True, "archived": False},
                {"full_name": "alice/old", "fork": False, "archived": True},
            ]
        )
    )
    repos = gh.get_owner_repos("alice")
    assert repos == ["alice/good"]


@respx.mock
def test_get_owner_repos_org_fallback(gh: GitHubClient) -> None:
    respx.get(f"{_API}/users/myorg/repos").mock(return_value=httpx.Response(404))
    respx.get(f"{_API}/orgs/myorg/repos").mock(
        side_effect=_paginated(
            [
                {"full_name": "myorg/repo-a", "fork": False, "archived": False},
            ]
        )
    )
    repos = gh.get_owner_repos("myorg")
    assert repos == ["myorg/repo-a"]


@respx.mock
def test_get_repo_stats_retries_on_500(gh: GitHubClient, monkeypatch: pytest.MonkeyPatch) -> None:
    # Patch tenacity sleep so this test doesn't wait 2 seconds for the retry backoff
    monkeypatch.setattr("tenacity.nap.time.sleep", lambda _: None)
    respx.get(f"{_API}/repos/owner/repo").mock(
        side_effect=[
            httpx.Response(500),
            httpx.Response(200, json={"stargazers_count": 1, "subscribers_count": 1}),
        ]
    )
    stats = gh.get_repo_stats("owner", "repo")
    assert stats["stars"] == 1
