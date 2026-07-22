#!/usr/bin/env bash
# Merge (or auto-merge) open Dependabot PRs on a given GitHub repo.
#
# - Private repos: squash-merges PRs whose checks pass. If a PR needs a
#   rebase against its base branch (which can happen mid-run, once an
#   earlier PR in the same run has just been merged), it is left alone
#   and commented on with "@dependabot rebase" instead of being merged.
# - Public repos: enables auto-merge (squash) on PRs whose checks pass.
#   Dependabot rebases those PRs itself if a later merge makes it necessary.
# - PRs with failing checks are never touched; they are surfaced in the
#   final report as needing manual review.
#
# Each PR's check status and merge state are re-fetched immediately before
# acting on that PR (not from a batch fetched up front), because merging
# one PR can change the check/rebase status of the next one.
#
# Usage: scripts/dependabot-merge.sh <owner/repo>
set -euo pipefail

REPO="${1:-}"
if [[ -z "$REPO" ]]; then
  echo "Usage: $0 <owner/repo>" >&2
  exit 1
fi

for bin in gh jq; do
  if ! command -v "$bin" >/dev/null 2>&1; then
    echo "Required command not found: $bin" >&2
    exit 1
  fi
done

REBASE_COMMENT_BODY='@dependabot rebase'

merged=()
automerge_enabled=()
already_automerge=()
rebase_requested=()
needs_review=()
blocked=()
pending=()
drafts=()

is_private="$(gh repo view "$REPO" --json isPrivate -q '.isPrivate')"
echo "Repo: $REPO (private=$is_private)"

pr_numbers="$(gh pr list --repo "$REPO" --author "app/dependabot" --state open --json number -q '.[].number' | sort -n)"

if [[ -z "$pr_numbers" ]]; then
  echo "No open Dependabot PRs found."
  exit 0
fi

check_state() {
  jq -r '
    (.statusCheckRollup // []) as $rollup
    | if ($rollup | length) == 0 then "none"
      else
        ($rollup | map(.conclusion // .state // "PENDING")) as $vals
        | if ($vals | any(. == "FAILURE" or . == "ERROR" or . == "CANCELLED"
              or . == "TIMED_OUT" or . == "ACTION_REQUIRED"
              or . == "STARTUP_FAILURE" or . == "STALE")) then "failing"
          elif ($vals | any(. == "PENDING")) then "pending"
          else "passing"
          end
      end
  '
}

while IFS= read -r pr; do
  [[ -z "$pr" ]] && continue

  view="$(gh pr view "$pr" --repo "$REPO" \
    --json number,title,isDraft,mergeStateStatus,autoMergeRequest,statusCheckRollup)"
  title="$(jq -r '.title' <<<"$view")"
  label="#$pr ($title)"

  if [[ "$(jq -r '.isDraft' <<<"$view")" == "true" ]]; then
    echo "SKIP  $label: draft PR"
    drafts+=("$label")
    continue
  fi

  checks="$(check_state <<<"$view")"

  if [[ "$checks" == "failing" ]]; then
    echo "FAIL  $label: checks failing, needs manual review"
    needs_review+=("$label")
    continue
  fi

  if [[ "$checks" == "pending" ]]; then
    echo "WAIT  $label: checks still running, skipping this run"
    pending+=("$label")
    continue
  fi

  merge_state="$(jq -r '.mergeStateStatus' <<<"$view")"

  if [[ "$is_private" == "true" ]]; then
    case "$merge_state" in
      BEHIND | DIRTY)
        echo "REBASE $label: needs rebase (mergeStateStatus=$merge_state), requesting via comment"
        gh pr comment "$pr" --repo "$REPO" --body "$REBASE_COMMENT_BODY" >/dev/null
        rebase_requested+=("$label (follow-up needed once Dependabot rebases)")
        ;;
      BLOCKED)
        echo "BLOCK $label: blocked (e.g. missing required review), needs manual review"
        blocked+=("$label")
        ;;
      UNKNOWN)
        echo "WAIT  $label: mergeability still being computed, skipping this run"
        pending+=("$label")
        ;;
      CLEAN | UNSTABLE | HAS_HOOKS)
        echo "MERGE $label: checks passed, squash-merging"
        gh pr merge "$pr" --repo "$REPO" --squash >/dev/null
        merged+=("$label")
        ;;
      *)
        echo "WAIT  $label: unrecognized mergeStateStatus=$merge_state, skipping this run"
        pending+=("$label")
        ;;
    esac
  else
    if [[ "$(jq -r '.autoMergeRequest' <<<"$view")" != "null" ]]; then
      echo "SKIP  $label: auto-merge already enabled"
      already_automerge+=("$label")
      continue
    fi
    echo "AUTO  $label: checks passed, enabling auto-merge (squash)"
    gh pr merge "$pr" --repo "$REPO" --squash --auto >/dev/null
    automerge_enabled+=("$label")
  fi
done <<<"$pr_numbers"

print_section() {
  local header="$1"
  shift
  if [[ "$#" -gt 0 ]]; then
    echo
    echo "$header"
    printf '  - %s\n' "$@"
  fi
}

echo
echo "===== Summary ====="
print_section "Squash-merged:" "${merged[@]}"
print_section "Auto-merge enabled:" "${automerge_enabled[@]}"
print_section "Auto-merge already enabled (untouched):" "${already_automerge[@]}"
print_section "Rebase requested (needs follow-up run after Dependabot rebases):" "${rebase_requested[@]}"
print_section "NEEDS MANUAL REVIEW (failing checks):" "${needs_review[@]}"
print_section "NEEDS MANUAL REVIEW (blocked, e.g. missing required review):" "${blocked[@]}"
print_section "Still pending (checks or mergeability not settled, re-run later):" "${pending[@]}"
print_section "Skipped (draft):" "${drafts[@]}"

if [[ "${#needs_review[@]}" -gt 0 || "${#blocked[@]}" -gt 0 ]]; then
  exit 2
fi
