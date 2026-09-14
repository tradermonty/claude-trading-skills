# Issue #293: FTD detector coverage batch

This batch exercises the FTD detector's real state-machine, health-assessment,
serialization, and report-writing handoffs with fictional OHLCV data. It adds
29 behavioral cases to the existing 56 tests. Provider I/O is replaced at the
client boundary and unexpected HTTP requests fail the new CLI tests.

## Selection and final plan

At selection, no non-Dependabot pull requests were open. Issue #293 is P0;
`ftd-detector` still had a 65% effective floor against a 70% target and was
scheduled for the week ending 2026-09-13 in the coverage burn-down policy.
Work starts from `f8114b1f090352bc19a3d9468da8ef93daaf5b69`.

1. Measure executable-only coverage using the existing CI matrix runner.
2. Test actual JSON/Markdown artifacts for dual/single FTD confirmation,
   unconfirmed and invalidated signals, quote fallback, absent optional QQQ
   history, missing credentials, and fatal missing S&P 500 history.
3. Test score boundaries 59/60 and 79/80, defensive guidance, missing volume
   evidence, risk/watch-level details, serialization, and report write errors.
4. Run skill, package, formatting, metadata, generated-document, and hook checks.
5. Obtain an independent implementation review before the first commit and
   draft PR. Use `Refs #293`; the broader issue remains open.
6. Remove only this skill's waiver after its exact-head Ubuntu/Python 3.9 CI
   artifact proves at least 70% coverage. Review that policy/evidence delta,
   push it to the same draft PR, and verify final-head CI. Retain the waiver if
   the required evidence is unavailable.

No production code, coverage exclusions, denominator-reduction changes,
provider calls, trading activity, or lifecycle-status changes are needed.
The distribution package excludes tests and remains unchanged.

## Local evidence

The existing matrix runner and `coverage json --omit='*/tests/*'` produce:

| Measurement | Tests | Covered / executable statements | Coverage |
|---|---:|---:|---:|
| Before this batch, Python 3.9 | 56 passed | 689 / 1,043 | 66.0594% |
| After this batch, locked Python 3.9 environment | 85 passed | 947 / 1,043 | 90.7958% |

The production statement count remains 1,043. The orchestrator reaches 100%
and the report generator 99.59%; these measure execution, not proof of trading
correctness or live-provider compatibility. Existing pytest temporary-directory
cleanup warnings appeared after successful tests; unrelated temporary data was
not changed. The new assertions verify artifact contents and failure outcomes,
including quote/history separation and absence of internal rally-day arrays.

Reproduce with the lockfile environment:

```bash
uv sync --locked --no-install-project --extra dev --extra ci --python python3.9
.venv/bin/python scripts/ci_test_matrix.py run ftd-detector --coverage-dir coverage-data
COVERAGE_FILE=coverage-data/coverage.ftd-detector .venv/bin/python -m coverage json \
  --omit='*/tests/*' -o ftd-coverage.json
```

The initial dependency download encountered sandbox DNS failure. Retrying the
same locked sync with network permission succeeded, using a task-specific cache.
The standard full-suite runner also needed that permission to fetch its build
dependency. `bash scripts/run_all_tests.sh` finished with 74/75 rows passing;
the sole unsuccessful row was `futures-position-sizer`, interrupted by an
agent-generated signal (`KeyboardInterrupt`), with no assertion failure.
An isolated rerun of that exact matrix row with a task-specific temporary
directory passed all 212 tests. All 75 discovered rows therefore have successful
test evidence, including 1,163 passed / 1 skipped in `repo-scripts`; the original
runner's exit status was 1 and is not represented as a clean full-run exit.
The completed row evidence is reused rather than running the pre-push pytest
hook again. All other applicable push hooks run normally.

## Review and CI record

- Plan review round 1: no actionable findings. The suggested 59/60 and 79/80
  boundary cases were included. A later implementation-review round is reserved
  for the conditional waiver change.
- Implementation review round 1: no actionable findings; the reviewer also ran
  all 85 skill tests independently. A secret-scanner false positive on a literal
  test credential was annotated on that assertion only.
- Local validation: skill tests, Ruff 0.16.6 check/format, package parity,
  catalog/skill/workflow/skillset documentation checks, strict metadata/workflow
  validation, skillsets, navigator snapshot, quality dashboard, and
  `pre-commit run --all-files` passed.
- Ubuntu/Python 3.9 evidence: [CI run 34859569722](https://github.com/tradermonty/claude-trading-skills/actions/runs/34859569722)
  for `73a5f33cba4d7e3f070b18cbe8fba3b1904438a0`, artifact
  `executable-code-coverage-report` (ID `10354777482`), reports
  `ftd-detector.actual = 90.79578139980825`, `status = target_met`, and no
  coverage violations. Its raw report confirms 947 / 1,043 statements.
  This meets the 70% target and permits removing only the FTD waiver;
  future CI enforces the default 70% floor.
- Implementation review round 2: no actionable findings. The reviewer
  independently verified the live CI run/head/artifact and loaded the changed
  policy to confirm `floor=70`, `target=70`, and `waiver=None`.
  Policy/dashboard tests: 54 passed. Dashboard regeneration made no changes;
  its drift check and the final `pre-commit run --all-files` passed.
  Final-head CI is checked on [draft PR #403](https://github.com/tradermonty/claude-trading-skills/pull/403)
  after the policy commit; merge remains outside this job's scope.

Issue #293 remains open because other per-skill waivers still require their own
evidence and remediation. The same CI report measures repository aggregate
coverage at 76.7152%, above the 75% target; its existing waiver is deliberately
outside this single-skill batch and remains for a separate removal review.
This batch does not satisfy the whole issue's closure criteria.
