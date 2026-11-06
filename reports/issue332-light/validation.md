# Issue 332 light-endpoint validation

## Scope and evidence

This is a bounded contribution to P0 #332, not completion of the provider-contract tracker. Add the uncovered historical-price-eod/light contract and harden its news-reaction-failure-analyzer boundary. The existing weekly FMP canary discovers it without a workflow change. Other endpoints/providers and broader consumer/operational acceptance remain outstanding; keep #332 open with no closing reference.

One authenticated read-only GET returned HTTP 200 with five public SPY price rows for 2026-10-26 through 2026-10-30, captured at 2026-11-06T11:25:26.755774+00:00. Only symbol/date/price/volume were retained. No credentials or request URLs are committed; subscription tier and futures/free-tier coverage are unverified. All denied/malformed response tests are synthetic. No further live calls or workflow dispatches were made.

## Reviews

- Plan round 1 requested finite-number contract enforcement and correction of the mocked HTTP close shape. Both incorporated. Plan round 2: PASS; final plan adopted before runtime changes.
- Code round 1 reproduced two P2 findings: extra close could shadow validated price; malformed finite type declarations could crash populated-row validation. Eight regression cases failed before correction. The boundary now strips close, and invalid finite policy returns a fatal result before body validation. Offline contract-checker and canary regressions included.
- Code round 2: PASS; no outstanding findings. Reviewer independently ran 222 targeted tests and verified all 14 contracts, Ruff, package parity and whitespace.

## Verification

- Initial focused regression run: 24 failed, 2 passed, 22 errors because the new contract did not yet exist.
- Related provider/consumer/summary/canary-health/workflow suites after review fixes: 674 passed.
- Final focused light suite: 62 passed.
- All 14 provider contracts validate offline; complete archive parity passes. Only news-reaction-failure-analyzer.skill regenerated.
- Full all-file pre-commit after review corrections: PASS, including docs/metadata/generated checks and source/package parity.
- Complete canonical matrix: 75/75 rows PASS; 11,646 passed and one existing skip. The repo-scripts row passed 3,051 tests; existing UTC deprecation warnings remain on main and are handled by separate PR #639. No failed rows or retries.

## Behavior and boundaries

The contract requires non-null date and finite numeric price. The additive finite rule is opt-in and does not change existing contracts. Consumer checks canonical dates and rejects malformed rows with static schema_drift reason codes. Generic reaction_math close support remains unchanged. Empty provider lists, all-future rows, schema drift and HTTP failures stay distinct in attempts; a successful fallback retains proxy/source metadata. Exhausting the source chain retains no_price_source and the existing insufficient-evidence verdict.

Work was performed in a new worktree from ff8ca70. Original checkout and other agent worktrees are untouched. Publication preflight confirmed current main remains ff8ca70, #332 is OPEN, and current #635/#636/#639 implementation paths are disjoint. A scan of every local and remote Git ref found no pre-existing committed historical-price-eod-light.v1.json contract. No broker operations, personal-state reads, repository settings/secrets changes, merge or Issue close.
