#!/usr/bin/env bash
# List all open PRs across all of an owner's repos, with author and a direct link.
#
# Usage: scripts/list-open-prs.sh [owner]
#
# If no owner is given, defaults to the authenticated `gh` user. Only
# non-fork, non-archived repos owned directly by that owner are considered.
set -euo pipefail

for bin in gh jq; do
  if ! command -v "$bin" >/dev/null 2>&1; then
    echo "Required command not found: $bin" >&2
    exit 1
  fi
done

OWNER="${1:-}"
if [[ -z "$OWNER" ]]; then
  OWNER="$(gh api user -q .login)"
fi

echo "Owner: $OWNER"
echo

repos="$(gh repo list "$OWNER" --source --no-archived --limit 1000 --json nameWithOwner -q '.[].nameWithOwner' | sort)"

if [[ -z "$repos" ]]; then
  echo "No repos found for $OWNER."
  exit 0
fi

total_prs=0
repos_with_prs=0

while IFS= read -r repo; do
  [[ -z "$repo" ]] && continue

  prs="$(gh pr list --repo "$repo" --state open --json number,title,author,url \
    -q '.[] | "\(.number)\t\(.author.login)\t\(.title)\t\(.url)"')"

  [[ -z "$prs" ]] && continue

  repos_with_prs=$((repos_with_prs + 1))
  pr_count="$(wc -l <<<"$prs")"
  total_prs=$((total_prs + pr_count))

  echo "$repo ($pr_count open PR$([[ "$pr_count" -eq 1 ]] || echo s))"
  while IFS=$'\t' read -r number author title url; do
    echo "  #$number by $author: $title"
    echo "    $url"
  done <<<"$prs"
  echo
done <<<"$repos"

echo "===== Summary ====="
echo "$total_prs open PR(s) across $repos_with_prs repo(s) (of $(wc -l <<<"$repos") checked)."
