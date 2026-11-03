# Issue #507: explicit incomplete smoke outcomes

Date: 2026-11-03
Base: origin/main d8e71ce

## Selection

Live PRs #634 and #635 are CLEAN, each with 90 successful checks and one
scheduled-only skip. No requested changes or unresolved threads remain;
#634's IV documentation comment is addressed by its current head.

Evaluated candidates, in priority order (10 total):
- #332 (P0): skip; existing local/remote issue332 branches.
- #495 (P1): skip; existing local/remote issue495 branches.
- #496 (P1): skip; existing issue496 branches and active worktree.
- #298 (P1): skip; existing local/remote issue298 branches.
- #297 (P1): skip; existing local/remote issue297 branches.
- #616 (P2): skip; active worktree and open PR #635.
- #610 (P2): skip; repository ruleset changes need maintainer approval.
- #609 (P2): skip; Actions permission change and remote branch deletion.
- #524 (P2): skip; tag ruleset and live release acceptance need maintainer action.
- #507 (P2): select; no existing matching branch/worktree at selection.

Existing PR files do not overlap the intended paths below. The original
checkout is on another branch and is left untouched. Work uses a new isolated
worktree created from origin/main. Existing work locations are not reused.

## Deliverable

Bounded implementation of the cross-cutting skip-is-not-pass rule in the
packaged dependency smoke runner. This is a partial contribution, not closure
of #507 or promotion of #349's report-only nightly.

1. Add regression tests for pending-only, skipped-only, mixed executed/skipped,
   empty inventory, empty contract lists, malformed requirements mixed with a
   passing skill, and failure combined with incomplete coverage.
2. Add explicit per-skill outcome and aggregate outcome/counts to JSON.
   Only fully executed successful contracts may report ok=true. Incomplete
   coverage reports ok=null and a visible GitHub warning. Existing execution
   errors remain failures and dominate incomplete status.
   Validate every requirements manifest before execution; malformed manifests
   are table failures (including alongside passing skills). Table errors also
   emit aggregate outcome=fail with the same summary schema.
3. Return 0 only for complete passing execution, 1 for failures, and 2 for
   incomplete coverage (including zero eligible skills). Keep the nightly's
   report-only workflow setting and its promotion prerequisites unchanged.
4. Document the evidence schema, exit codes, report-only limitation, and the
   remaining #507 layers in the maintenance runbook and smoke documentation.

Intended files: scripts/smoke_contracts_runner.py,
scripts/tests/test_smoke_contracts_runner.py, docs/dev/packaged-deps-smoke.md,
docs/dev/maintenance-runbook.md, reports/issue507/{plan,validation}.md.
No skill/package/generated metadata changes are expected.

## Validation and review

Run Python 3.9 targeted smoke runner/table tests, Ruff and format checks,
all standard generated/metadata/workflow/snapshot checks, full canonical test
matrix as appropriate for the runner change, pre-commit all files, and diff
whitespace checks. Tests mock venvs and child commands; no live services,
workflow dispatch, installation, or personal state is required.

Obtain independent plan and implementation reviews, each up to three rounds;
resolve all findings before commit. Create at most one draft English PR with
Refs #507. Verify closingIssuesReferences=[], Issue OPEN, exact head/draft state,
and live CI. Do not merge.

## Plan review log

Round 1: reviewer required malformed-manifest failure handling and explicit
empty-contract coverage. Both are included above; table failures also use the
aggregate outcome schema. Round 2: PASS, no unresolved findings.
