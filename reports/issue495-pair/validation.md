# Issue 495 pair-trade migration validation

## Scope and coordination

Migrate only pair-trade-screener from P1 #495 Batch D; keep #495 OPEN with Refs only. The tracker still includes other unmigrated skills. Current P0 #332 work (#640) modifies the light response contract and shared contract validator; this change uses disjoint files. Other open #635/#636/#639 implementations are also disjoint. Worktree base: ff8ca70.

The two public adapters delegate through their sibling generated client, loaded under a skill-specific module name. Stable company screening retires the local v3 fallback. Historical stable-to-v3 fallback remains canonical generated behavior. Available history is fetched without date bounds and latest-N slicing remains local, preserving sparse/delisted-symbol history, 730/365 defaults, chronological Series, ticker names and adjusted-close preference. Statistics and output contracts are unchanged.

The pair-only pre-normalizer guard rejects malformed row shapes, symbol types/mismatches, dates and selected prices using static diagnostics. Existing generated clients are byte-identical. Source and package drift hooks/CI include the new target; the full-EOD contract lists its new generated owner. Only the pair archive is regenerated.

## Reviews

- Plan round 1 found bounded date-query regression and missing malformed-history guards. Both corrected before implementation. Plan round 2: PASS.
- Code round 1 found an API-key leak through a provider symbol-mismatch diagnostic. Four regressions reproduced it before the static preflight rejection. Code round 2: PASS, no outstanding findings. Reviewer independently verified 84 focused tests plus generator/archive parity, lint and whitespace. Final round 3: PASS after checking CI/pre-commit/PR-template command consistency; seven gate tests independently passed. No unresolved findings.

## Verification

- Session-based migration regressions before implementation: 25 failed.
- Final pair/public adapter/generator/fresh-process suites: 223 passed (two existing constant-series NumPy RuntimeWarnings).
- Shared transport/redaction/truncation/CI tests: 614 passed.
- Generator drift: PASS; all pre-existing generated client files remain unchanged.
- Full archive parity and declared dependency inventory: PASS.
- Full all-file pre-commit final run: PASS. A fake-credential false positive was resolved with an explicit test-only allowlist comment on its exact line; the secret baseline was not changed.
- Initial canonical matrix: 74/75 rows PASS, including all skill suites (8,656 passed; pair skill 200 passed). Two repo-scripts failures exposed a stale hardcoded package-drift command expectation. Updated the regression constant and matching PR-template command; the seven focused gate tests pass. An intermediate retry still observed the pre-fix template. Final retry after the complete fix: 2,987 passed. All 75 canonical rows ultimately PASS; final retained row totals: 11,643 passed. Unchanged skill rows were not repeated after the test/template-only corrections.

## Workspace and operational evidence

Original source checkout remains clean at 6e9a635. During initial setup, uv sync was accidentally run in the original directory and changed four packages; before implementation those changes were restored exactly to the recorded versions: editable project 0.1.0, frozendict 2.4.7, patsy 1.0.2 and tzdata 2026.3. Verification confirmed all four versions. All subsequent implementation and tests use this dedicated worktree's locked environment.

No provider calls, broker/account operations, personal-state access, secrets/settings changes, workflow dispatch, merge or Issue close. Package installation alone used network. Hosted CI remains separate from local evidence. The existing CLI authentication is usable with network-enabled execution for PR publication.
