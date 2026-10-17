# Issue #298: automatic quality dashboard evidence refresh

## Selection and isolation

Selected P1 #298. At selection (2026-10-17), GitHub had no open PRs; local
worktrees already cover P1 #495 and #496 and P0 #332, but none actively cover #298. The old `codex/issue-298-quality-dashboard`
branch belongs to PR #382, merged 2026-09-13 (live GitHub verification).
Use branch `codex/issue298-dashboard-20261017` in `/private/tmp/cts-issue298-20261017`,
based on `origin/main` b29c6df. Do not edit #496's index/baseline evidence or #495's clients.

## Implementation

1. Add an explicit refresh command, separate from deterministic page generation.
   It queries GitHub with `gh api` (bounded subprocess timeout, pagination), records
   collection time and checked-out commit, and selects the latest successful main
   push run of `ci.yml`. Read its existing coverage report artifact, accepting only
   numeric finite 0..100 percentages (not booleans), unique known skill IDs,
   and schema version 1. Bind the artifact ID to the selected run; read only
   the named JSON member without extracting archive paths. Retain the run's commit, completion time and
   URL separately from collection time. Missing/expired evidence is unknown;
   authentication/API failure fails the refresh before writing anything.
2. Count open P0/P1 issues from the live issue list (exclude PRs; document this
   priority-based proxy rather than imply a per-skill release clearance).
   Summarize the eight production verification declarations directly from the
   index, explicitly as declarations and not fresh independent audits.
3. Keep unknown beta start dates, dual-axis scores, executed smoke counts and
   successful live-data samples explicitly unmeasured. Never infer execution from
   replay inventory or a green report-only canary. Existing coverage/replay
   inventory remains clearly distinguished from measured results.
4. Extend both generated pages with per-metric input provenance (measured commit,
   time, source, or unknown), while preserving offline deterministic `--check`.
   Old snapshots remain supported but lack of provenance is visible. Refresh
   the committed snapshot using actual available GitHub evidence, then regenerate.
5. Add a pinned, locked weekly/manual GitHub workflow. It refreshes snapshot/pages
   and uploads them as a reviewable artifact, then opens a bot PR on a unique
   run branch. Skip if a previous dashboard automation PR remains open. No force
   pushes or automatic merges. Fail explicitly if repository policy disables
   Actions PR creation. Use scoped contents/pull-requests write permissions.
   Run collector/generator tests, Ruff, deterministic drift and docs source
   validation inside the refresh workflow: GITHUB_TOKEN PRs do not normally
   trigger other workflows. Disclose that limitation in its PR body.
   Pages currently uses legacy main:/docs (verified through Pages API); an
   ordinary reviewed merge updates that source. Actual deployment is not tested.

## Validation and completion boundary

Use fake GitHub transport/artifacts for missing/expired evidence, pagination,
failed API, malformed coverage (duplicates/booleans/nonfinite/schema), commit
attribution and repeat generation tests. Verify collection failure leaves all
outputs untouched and expired artifacts clear old measured values.
Run focused collector/generator tests, repo scripts tests if practical, Ruff,
codespell, dashboard drift and docs source validation. Review the complete diff
with a sub-agent, fix findings (at most three rounds), then commit and create PR.

This PR completes automatic collection and attributable dashboard evidence.
Automatic update PRs require a human merge before the public source changes.
No provider secrets or live trading calls are introduced. Unknown measurements
remain explicit; this is not a claim that every verification axis is now audited.

## Review log

Round 1: corrected artifact-only automation to reviewed bot PRs; verified old
PR #382 merged and Pages source; added token-trigger validation limitations,
strict artifact validation and failure atomicity. Round 2: approved by independent sub-agent; no remaining blockers.


## Implementation review log

Round 1: independent review found static metrics could inherit historical catalog
provenance after input edits. Added a fingerprint covering index, policy, replay
inventory and test presence, invalidating only current catalog attribution on
mismatch. Added regression cases for each input; historical declarations retain
their own attribution. Round 2: independent review approved with no remaining findings; 66 focused tests passed.


## Validation results

- Focused collector/generator tests after final fix: 66 passed.
- Full repository scripts regression run: 2,250 passed (20 existing warnings);
  final fingerprint regression tests were added and run separately afterward.
- Ruff check/format, codespell, deterministic dashboard drift, docs source,
  compatibility matrix and strict workflow metadata: passed.
- Actual read-only refresh succeeded against main CI run 38895293520; coverage
  artifact 12043243687 is attributed to b29c6df, independently of collection time.
- Author config and active GitHub account verified as tradermonty.
- Hosted automation and Pages deployment require post-merge verification.
