# Roadmap

## Planned

### Gitea support

Extend the service to monitor Gitea instances in addition to GitHub. Gitea exposes a REST API that is broadly compatible with GitHub's (stars, issues, pull requests, releases), but has no equivalent to GHCR or GitHub Packages.

Scope:
- Add a `GITEA_URL` and `GITEA_TOKEN` config option (Gitea base URL + personal access token)
- Add `GITEA_OWNERS` / `GITEA_REPOSITORIES` analogous to the GitHub equivalents
- Implement a `GiteaClient` mirroring the interface of `GitHubClient` (same `get_repo_stats`, `get_new_pulls`, `get_new_issues`, `get_new_releases`; no package version method)
- Run GitHub and Gitea monitors in the same polling loop, posting to the same Discord channel
- Rate-limit and retry behaviour consistent with the GitHub client

Key differences to account for:
- Gitea repo endpoint returns `stars_count` and `watchers_count` (not `stargazers_count` / `subscribers_count`)
- Gitea paginates with `limit` + `page` query params (same as GitHub's `per_page` + `page`)
- Gitea issues API returns PRs inline (same `pull_request` key pattern as GitHub — existing filter logic applies)
- No fine-grained PAT scopes; a standard Gitea token with read access is sufficient
