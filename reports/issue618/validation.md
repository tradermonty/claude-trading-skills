# Issue 618 validation and reviews

## Behavior

Replace ten deprecated production UTC calls while preserving existing UTC date, timestamp precision and Z/offset formats. Narrow the three silent data-path catches, retain expected fallback behavior, emit sanitized stderr diagnostics, and expose missing freshness metadata in the returned warning. Unexpected programming errors propagate. Support requests, curl_cffi, yfinance and JSON parsing exceptions at the relevant boundaries.

Enable B904/B007/B017 and C901 with a fixed 128 ceiling. Resolve 22 skill/script and six bundled-example violations. Add a filename-based pytest deprecation audit supporting flat imports, collection and initial-conftest warnings, while preserving dependency warnings and explicit expected-warning assertions. No test inventory or root conftest changes.

## Reviews

- Plan round 1: three findings (warning attribution, actual exception families, precise complexity budget). All addressed. Round 2: PASS.
- Code round 1: two reproducible findings (early warning crash, uncaught yfinance JSON decode). Both addressed with regressions. Round 2: PASS. Round 3 reviewed the dependency declaration correction and latest-main integration: PASS, no outstanding findings; 96 independent tests passed. Reviewers also ran 87 targeted tests in round 2; all 15 archive member diffs are scoped.

## Tests and gates

- Before implementation: targeted regression run 15 failed / 71 passed. New plugin subprocess tests also failed before the plugin existed.
- Early-warning bug reproduction: 2 failed / 4 passed; fixed with queued warning classification.
- Final related suites: 744 passed (theme, breadth, postmortem, plugin and policy tests).
- New warning/policy regressions: 8 passed; dependency/generator/theme-scanner review checks: 96 passed.
- Both `python -m pytest` and console `pytest` startup verified.
- Canonical matrix initial run: 74/75 rows passed (8,611 skill tests); repo-scripts found two undeclared curl_cffi dependency failures. Added the optional dependency to its generator source, the import/distribution map and an actual absence regression. Retry: 2,969 repo-scripts tests passed. Final latest-main repo-scripts rerun: 2,984 passed. Final theme suite: 510 passed (three more than the initial matrix row). All 75 canonical rows ultimately pass; aggregate retained final row results total 11,598 passed. Unchanged skill rows were retained from the full run rather than repeated after the independent dashboard/licence merges.
- Full all-file pre-commit after latest-main integration: PASS. Initial lint findings corrected; secret baseline auto-refresh changes only the existing fake-credential line number and generation timestamp.
- Full 74-skill archive parity: PASS; 15 changed archives regenerated. No SKILL.md behavior/documentation changes in this PR. Main advanced to 5e2ad2e while tests ran; rebase retained merged #637 licence text and #638 dashboard changes. The only conflict was the manifold archive, regenerated from the combined source; reviewer verified its sole PR-relative member change is run_backtest.py.
- Ruff lint/format, strict metadata/workflow validation, docs source validation and whitespace: PASS. Pre-commit also checked generated docs/catalogs/workflows/skillsets/navigator and shared client/calendar parity.

## Operational boundaries

No provider requests, broker actions, personal-state access, repository settings changes, workflow dispatch or merge. Test dependency installation alone used network access. Original checkout remains unchanged. Sandboxed GitHub CLI authentication checks failed because network access was restricted; network-enabled authentication verification passed with the existing account. The connected GitHub integration rejected PR creation with 403 and browser control was unavailable, so publication uses the authenticated CLI. Branch push uses the existing SSH origin.

All Issue acceptance criteria are implemented. The PR may carry Closes #618 after final gates pass; no Issue is closed directly. Original worktree remains on its original branch/head. Independent active PR #635 retains its separate pytest inventory scope; this PR leaves testpaths and root conftest untouched.
