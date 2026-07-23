#!/usr/bin/env bash
# Daily digest of open PRs and open Dependabot alerts across jasmeralia's repos.
# Intended to run from cron on gelfling (which already has an authenticated `gh`
# and a working local MTA). Emails only when there's something to report --
# on an ordinary day with nothing open, this prints and sends nothing.
#
# Usage: scripts/gelfling-daily-digest.sh [owner]
set -euo pipefail

for bin in gh jq; do
  if ! command -v "$bin" >/dev/null 2>&1; then
    echo "Required command not found: $bin" >&2
    exit 1
  fi
done

SENDMAIL="/usr/sbin/sendmail"
if [[ ! -x "$SENDMAIL" ]]; then
  echo "Required command not found: $SENDMAIL" >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RECIPIENT="morgan@windsofstorm.net"

prs_output="$("$SCRIPT_DIR/list-open-prs.sh" "$@")"
alerts_output="$("$SCRIPT_DIR/list-open-alerts.sh" "$@")"

pr_count="$(grep -oE '^[0-9]+ open PR' <<<"$prs_output" | grep -oE '^[0-9]+' || true)"
alert_count="$(grep -oE '^[0-9]+ open alert' <<<"$alerts_output" | grep -oE '^[0-9]+' || true)"
pr_count="${pr_count:-0}"
alert_count="${alert_count:-0}"

sections=()
[[ "$pr_count" -gt 0 ]] && sections+=("$prs_output")
[[ "$alert_count" -gt 0 ]] && sections+=("$alerts_output")

if [[ ${#sections[@]} -eq 0 ]]; then
  echo "No open PRs or alerts, skipping email."
  exit 0
fi

{
  printf 'To: %s\n' "$RECIPIENT"
  printf 'Subject: [jasmeralia] Git Activity Digest - %s\n' "$(date -u +%Y-%m-%d)"
  printf 'Content-Type: text/plain; charset=UTF-8\n\n'
  for section in "${sections[@]}"; do
    printf '%s\n\n' "$section"
  done
} | "$SENDMAIL" -t

echo "Sent digest: ${pr_count} open PR(s), ${alert_count} open alert(s)."
