# Issue #507 validation record

Date: 2026-11-03
Outcome: local validation PASS; no live smoke run or promotion claimed.

## Change

The packaged dependency runner distinguishes pass/fail/incomplete, emits
warnings for incomplete coverage, and returns 0/1/2 respectively. A table or
malformed-manifest failure is recorded before any child command starts.
Pending, skip-only, mixed-skip, empty contracts, and empty inventory cannot
produce success. Execution failure overrides incomplete coverage.

This is a partial implementation of #507. The nightly remains report-only
under #349; GitHub green alone is not proof of complete smoke coverage.
No workflow dispatch, external API writes, account state access, merge,
release, or Issue closure is performed.

## Reviews

- Plan: 2 rounds, final PASS. Round 1 requested malformed-manifest handling
  and explicit empty-contract regression coverage; both addressed.
- Implementation: 1 round, PASS, no unresolved findings. Independent reviewer
  ran the targeted 19 tests successfully.

## Checks

- Baseline smoke runner/table tests: 14 passed.
- Regression reproduction before implementation: 7 failed, 5 passed.
- Python 3.9 smoke runner/table tests after implementation: 19 passed.
- Ruff check and format check on changed Python files: PASS.
- Catalog, skill docs, strict metadata/workflow, skillsets, workflow docs,
  skillset docs, navigator snapshot, and git diff whitespace checks: PASS.
- No skill source changed, so no archive regeneration is required.
- Full canonical matrix: 75/75 rows passed, 11,507 passed, 3 skipped.
- pre-commit all files: PASS, including the added execution records.

The initial full-matrix attempt stopped before tests because the sandbox
could not open the existing ~/.cache/uv cache. Re-running with reviewed
permission to use that cache; no cache deletion or environment workaround.

## Delivery

Draft PR will use Refs #507; closingIssuesReferences must be empty and the
Issue must remain OPEN. Hosted CI is separate from local validation.
