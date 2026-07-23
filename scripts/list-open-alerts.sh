#!/usr/bin/env bash
# List all open Dependabot security alerts across all of an owner's repos, with a direct link.
#
# Usage: scripts/list-open-alerts.sh [owner]
#
# If no owner is given, defaults to the authenticated `gh` user. Only
# non-fork, non-archived repos owned directly by that owner are considered.
# Repos where Dependabot alerts (or dependency graph) aren't enabled are
# reported separately rather than silently showing zero alerts.
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

total_alerts=0
repos_with_alerts=0
disabled_repos=()

while IFS= read -r repo; do
  [[ -z "$repo" ]] && continue

  err_file="$(mktemp)"
  if ! response="$(gh api "repos/$repo/dependabot/alerts?state=open&per_page=100" --paginate 2>"$err_file")"; then
    if grep -qi "disabled" "$err_file"; then
      disabled_repos+=("$repo")
    else
      echo "ERROR checking $repo:" >&2
      cat "$err_file" >&2
    fi
    rm -f "$err_file"
    continue
  fi
  rm -f "$err_file"

  alerts="$(jq -r '.[] | [.number, .security_advisory.severity, .dependency.package.ecosystem,
      .dependency.package.name, (.security_advisory.ghsa_id // ""), (.security_advisory.cve_id // ""),
      .security_advisory.summary, .html_url, (.created_at[:10])] | @tsv' <<<"$response")"

  [[ -z "$alerts" ]] && continue

  repos_with_alerts=$((repos_with_alerts + 1))
  alert_count="$(wc -l <<<"$alerts")"
  total_alerts=$((total_alerts + alert_count))

  echo "$repo ($alert_count open alert$([[ "$alert_count" -eq 1 ]] || echo s))"
  while IFS=$'\t' read -r number severity ecosystem pkg ghsa cve summary url created; do
    id="${ghsa:-$cve}"
    echo "  #$number [$severity] $pkg ($ecosystem) $id, opened $created: $summary"
    echo "    $url"
  done <<<"$alerts"
  echo
done <<<"$repos"

echo "===== Summary ====="
echo "$total_alerts open alert(s) across $repos_with_alerts repo(s) (of $(wc -l <<<"$repos") checked)."
if [[ "${#disabled_repos[@]}" -gt 0 ]]; then
  echo
  echo "Dependabot alerts not enabled (no visibility) on:"
  printf '  - %s\n' "${disabled_repos[@]}"
fi
