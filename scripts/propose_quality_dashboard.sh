#!/usr/bin/env bash
# Publish only this run's dashboard update; recover failed publication conservatively.
set -euo pipefail

: "${GH_REPO:?GH_REPO must identify the repository}"
: "${GITHUB_STEP_SUMMARY:?GITHUB_STEP_SUMMARY must be set}"
: "${RUNNER_TEMP:?RUNNER_TEMP must be set}"
if [[ ! "${GITHUB_RUN_ID:-}" =~ ^[0-9]+$ || ! "${GITHUB_RUN_ATTEMPT:-}" =~ ^[0-9]+$ ]]; then
  echo 'Run ID and attempt must be numeric.' >&2
  exit 1
fi
branch="automation/quality-dashboard-${GITHUB_RUN_ID}-${GITHUB_RUN_ATTEMPT}"
ref="refs/heads/$branch"
publishing=0

summary() {
  printf '%s\n' "$1" >> "$GITHUB_STEP_SUMMARY"
}

recover() {
  status=$?
  trap - EXIT INT TERM
  if [ "$publishing" = 0 ]; then exit "$status"; fi
  # Even a failed client response can have created a PR. Include closed PRs.
  if ! prs="$(gh pr list --repo "$GH_REPO" --state all --head "$branch" --limit 1000 --json number --jq 'length')" ||
     [[ ! "$prs" =~ ^[0-9]+$ ]]; then
    summary "Publication failed; preserved $branch because its PR state is unknown. Inspect it manually; evidence remains in the run artifact."
  elif [ "$prs" != 0 ]; then
    summary "Publication failed; preserved $branch because a PR already references it. Inspect that PR; evidence remains in the run artifact."
  elif git push --force-with-lease="$ref:$published_sha" origin ":$ref"; then
    summary "Publication failed; removed this run's branch $branch. Check PR creation permission (Actions settings or an approved GitHub App token) before retrying. Evidence remains in the run artifact."
  else
    summary "Publication failed; preserved $branch (or it is already absent): guarded cleanup failed. Inspect the exact ref manually; never delete an advanced ref. Evidence remains in the run artifact."
  fi
  # Recovery never turns a failed publication into a green scheduled run.
  if [ "$status" = 0 ]; then status=1; fi
  exit "$status"
}
trap recover EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

pending="$(gh pr list --repo "$GH_REPO" --state open --json headRefName --jq '[.[] | select(.headRefName | startswith("automation/quality-dashboard-"))] | length' --limit 1000)"
if [[ ! "$pending" =~ ^[0-9]+$ ]]; then
  summary 'Dashboard PR query returned an invalid count; no branch was published.'
  exit 1
fi
if [ "$pending" != 0 ]; then
  summary 'A dashboard update PR is already open; evidence is available in this run artifact.'
  exit 0
fi
git add docs/assets/quality-dashboard-sources.json docs/en/quality-dashboard.md docs/ja/quality-dashboard.md
if git diff --cached --quiet -- docs/assets/quality-dashboard-sources.json docs/en/quality-dashboard.md docs/ja/quality-dashboard.md; then
  summary 'No dashboard change; no branch was published.'
  exit 0
fi
# No preexisting local or remote run branch may be reused or overwritten.
if git show-ref --verify --quiet "$ref"; then
  summary "Preserved preexisting local branch $branch; no publication attempted."
  exit 1
fi
if git ls-remote --exit-code origin "$ref"; then
  summary "Preserved preexisting remote branch $branch; no publication attempted."
  exit 1
else
  remote_status=$?
  if [ "$remote_status" != 2 ]; then
    summary "Remote state unknown for $branch; no publication attempted."
    exit 1
  fi
fi
git config user.name 'github-actions[bot]'
git config user.email '41898282+github-actions[bot]@users.noreply.github.com'
git switch -c "$branch"
git commit --only -m 'docs: refresh quality dashboard evidence (#298)' -- docs/assets/quality-dashboard-sources.json docs/en/quality-dashboard.md docs/ja/quality-dashboard.md
published_sha="$(git rev-parse HEAD)"
body="$RUNNER_TEMP/dashboard-pr-${GITHUB_RUN_ID}-${GITHUB_RUN_ATTEMPT}.md"
cat > "$body" <<'EOF'
Refresh measured inputs and regenerate both quality dashboards for #298.

Read the input evidence table for each metric's commit and measurement time.
Unknown inputs remain unmeasured. Coverage refers to the selected historical
successful main CI run; collection time does not make that coverage current.

Collector/generator tests, lint, drift and docs source checks ran in the
refresh workflow. PRs opened with GITHUB_TOKEN do not normally trigger
other workflows. Run the remaining required checks before merging.
This PR requires review and merge; it does not deploy or auto-merge.
EOF
# Arm recovery before push: the server can accept a ref despite a client error.
publishing=1
git push --force-with-lease="$ref:" origin "HEAD:$ref"
url="$(gh pr create --repo "$GH_REPO" --base main --head "$branch" --title 'docs: refresh quality dashboard evidence (#298)' --body-file "$body")"
publishing=0
summary "Dashboard update proposed: $url"
