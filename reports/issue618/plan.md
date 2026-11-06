# Issue 618 implementation plan

Base: origin/main d8e71ce2f0b069eb5b6fca352857c168c35e6c46.

## Selection and coordination

Live open issues, five open PRs (#634–#638), all remote branches (160), local branches and worktrees were inspected. P0 #332 and P1 #297/#298/#495/#496 already have work branches. Most P2 code tickets also have branches; #610/#524 require maintainer settings and #506 requires a separate private runner and unresolved provider decisions. #198 has a local agent branch. Choose unclaimed P3 #618 to remove existing data-path and warning debt without duplicating an active ticket. No comments or branch mention work on #618. PR #635 touches pytest testpaths in pyproject.toml; this change touches independent lint/warning sections only, preserving main's test inventory and conftest. Changed-file inspection confirms PR #637 also regenerates manifoldbt-backtester.skill for a SKILL.md-only licence change. This change edits only run_backtest.py in that archive; regenerate from the eventual merged source if merge order changes. PR #636 touches maintenance-runbook.md, so use a separate docs/dev/code-hygiene.md. These are independent changes, not duplicate Issue work.

## Scope and implementation

1. Add failing regression tests before changing behavior. Cover timestamp compatibility (UTC, existing naive-Z or explicit offset formats), degraded provider failures on stderr without secret/URL/raw-exception leaks, fallback retention, and propagation of unexpected programming errors. Test offline with fake transports.
2. Replace all ten production datetime.utcnow calls with datetime.now(timezone.utc). For legacy ISO strings ending in Z, strip tzinfo before isoformat and retain Z, preserving existing precision. Preserve strftime outputs.
3. Narrow FMP failures using stable requests.RequestException plus JSON ValueError imports; support yfinance YFException and curl_cffi RequestException with optional imports. Catch numeric P/E TypeError/ValueError only around conversion. Breadth HEAD catches requests failures and header ValueError/TypeError/OverflowError. Emit a concise static stderr warning identifying the degraded operation, never raw exception text. Preserve fallback behavior and make degraded freshness explicit in its returned warning; do not change public output schemas unnecessarily.
4. Fix all current B904/B007/B017 violations (exception chaining, unused loop names, precise expected exceptions); remove the global ignores. Enable C901 at the measured current maximum across production Python (expected 128), with a tested fixed ceiling <=128 and C901 enabled: lower explicitly over time; no automatic decrease is claimed. Regression checks reject rule suppressions. Avoid unrelated refactors. Add an automated policy regression to prevent increasing the budget and reintroducing ignores.
5. Load a standalone pytest plugin through addopts (-p scripts.pytest_firstparty_warnings), with pythonpath=["."] supporting both pytest and python -m pytest, leaving conftest.py untouched. Classify recorded unexpected DeprecationWarnings by resolved source filename beneath production skills/ and scripts/ (exclude tests). Accumulate findings in pytest_warning_recorded and fail the session in pytest_sessionfinish; never raise inside the recording hook. Report an explicit summary. Subprocess regressions cover flat imports, arbitrary messages, collection-time warnings, dependency warnings, and invocation with the canonical matrix's pytest options. Explicit pytest.warns expectations remain valid.
6. Regenerate only affected skill archives, validate source/package parity, lint/format, metadata/docs drift and all-file pre-commit. Run affected skill tests first, then full canonical 75-row matrix using the locked environment. Record results honestly in reports/issue618/validation.md.

## Review and delivery

Independent sub-agent plan review up to three rounds; revise all actionable findings before finalizing. Implement in this new worktree only. Independent code review up to three rounds; resolve all actionable findings and revalidate. Refresh GitHub issue/PR/main state before publication, commit and create an English PR. Use Closes #618 only if all acceptance criteria are met, otherwise keep it open with explicit remaining scope. No merge, live provider requests, repository setting changes or messages to third parties.

## Plan review log

Round 1: three findings addressed: filename-based pytest warning audit, actual optional yfinance/curl exception families with narrow numeric conversion, and explicit <=128 fixed complexity ceiling. Round 2: PASS; all findings resolved. Final plan adopted before implementation.

## Integration and final review

Main advanced to 5e2ad2e through #637 and #638 before publication. Rebased in the isolated worktree; regenerated the single conflicting manifold archive with main's licence and this PR's code changes. The final code review round 3 approved this integration and the explicit optional curl-cffi dependency manifest/mapping/absence test required by the full suite. No outstanding review findings.
