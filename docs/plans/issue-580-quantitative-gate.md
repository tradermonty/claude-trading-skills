# Issue #580: require quantitative evaluation before bubble verdicts

## Selection and scope

Live queue: PR #581 is draft, CLEAN, checks pass, no reviews or requested changes.
Its futures-position-sizer files do not overlap this change. Dependabot #577/#578
are excluded. Root checkout is on another branch and remains untouched; work
starts from origin/main cb0f3aa in a separate worktree.

Candidates evaluated in priority order (6 total):

| Issue | Decision |
| --- | --- |
| #332 (P0) | Skip: existing local/remote issue332-economic-contract-20261017 branch and worktree. |
| #496 (P1) | Skip: existing local/remote issue496-unit-evidence-20261014 branch; worktree registration is prunable. |
| #495 (P1) | Skip: existing local/remote issue495-dividend-clients-20261017 branch and worktree. |
| #298 (P1) | Skip: existing local/remote issue298-dashboard-20261017 branch and worktree. |
| #297 (P1) | Skip: existing local/remote issue297-regime-provenance-20261017 branch and worktree. |
| #580 | Select: direct decision-gate defect; no pre-existing matching branch/worktree; offline fix. |

No pre-existing work location is reused, changed, or deleted.

## Plan

1. Audit both quick references and other skill text for qualitative-question
   shortcuts to a phase or action, including the taxi-driver exit slogan.
2. Change both emergency-question sections to warning/assessment triggers only.
   Explain that YES/NO answers alone establish neither a phase nor an action;
   require Phase 1 data and Phase 2 quantitative scoring before Phase 3 evidence
   adjustments and the final score. Critical remains 13–15 on the final score.
   If data are missing, leave the assessment incomplete. Align both reference
   files (both currently contain English text despite the unsuffixed filename).
3. Remove phase verdicts from individual YES/NO interpretations and replace the
   taxi-driver exit slogans in both quick references and bubble_framework.md
   with a quantitative-assessment trigger. Preserve
   existing price/ATR stop rules and scoring formulas.
   Align the JA guide emergency example and taxi-driver explanation with this
   warning-only contract. Audit theoretical wording for the same shortcut.
4. Add targeted prompt-contract regressions for both quick references, the
   framework taxi-driver rule, and the JA emergency example, using the
   existing test suite, and first verify the new checks fail before the edits.
5. Regenerate only the affected skill package. Run skill pytest, ruff lint/format,
   package check, all catalog/docs/index/workflow/skillset/snapshot drift gates,
   pre-commit all-files, and diff check. Broaden tests if changes justify it.
6. Obtain independent plan review before implementation (max 3 rounds) and
   independent implementation review after validation (max 3 rounds). Resolve
   every finding before committing and creating one draft PR. Record results.

## Completion criteria

Both quick references require the full evaluation before any question-derived
verdict/action, including their slogans. Scoring, risk bands, and independent
price/ATR rules remain intact. Package matches source and checks pass.
Use `Closes #580` because this addresses the complete documentation defect;
verify the PR's closing references and draft state. Never merge.

## Review and validation record

Plan review round 1: requested explicit JA emergency-example alignment and
regressions for the framework slogan. Both are now included. Round 2: approved with no remaining findings.

TDD baseline: 17 passed; new regression checks: 4 failed, 17 passed before fixes.


Implementation review round 1: approved, no actionable findings. Reviewer
independently confirmed 21 tests, package parity, and diff check.

Validation so far:
- Python 3.9 skill suite: 21 passed (baseline 17 passed; four new checks failed
  before the documentation fix).
- Ruff check and format check: passed.
- Package check, catalog, skill docs, strict index/workflows, skillsets,
  workflow docs, skillset docs, and navigator snapshot: passed.
- pre-commit all-files: passed.
- Full suite initially blocked by sandbox access to the default uv cache;
  temporary-cache retry reached a DNS failure downloading dependencies.
  Outside-sandbox retry with a dedicated temporary uv cache passed:
  **75/75 test rows**; repo-scripts: 2,400 passed, 1 skipped.
  Only documentation/plan recording changed afterward; the completed pre-push
  full-suite check is not repeated during push.
- Root checkout and existing worktrees left untouched.
