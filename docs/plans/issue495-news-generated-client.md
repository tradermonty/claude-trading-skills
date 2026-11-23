# Issue #495: news-reaction-failure-analyzer generated FMP migration

## Selection and isolation

Select the unclaimed news-reaction-failure-analyzer remainder of P1 #495 Batch D. Live open Issues/PRs, Issue claims, remote branches and local worktrees show no competing news migration. Other P1s include implemented work pending operational acceptance (#652), existing security worktree (#778), and broader evidence/runner/adoption work. PR #859 owns shared transport repairs and PR #861 owns options migration. Fresh worktree/branch codex/issue495-news-client-20261122 based on main 917a9a6fa0784164728021ff93d862fc34367b56. Preserve other worktrees and all existing generated clients byte-for-byte. Publish Refs #495 without closing the umbrella or merging.

## Implementation contract

1. Register this target (family B, no budget, query authentication, no compatibility shim), add a target-only generated stable light-EOD method with exact symbol/from/to parameters, and replace the analyzer's manual request/backoff with that client. Do not change shared transport templates. Preserve API-key resolution, CLI flags, default 0.25-second pacing and configurable sleep. The generated transport replaces the former five-attempt exponential retry loop: bounded shared 429/JSON retry, one attempt for other HTTP/transport failures. Document this deliberate change.
2. Keep PriceClient.get_eod_rows(symbol, from_date, to_date, as_of=None) -> (rows, error), session injection for callers/tests, and the existing strict light `price` schema. Keep existing price-source/proxy order, future-row cutoff handling, invalid-vs-empty distinctions, static price_attempts status codes, event/detector vintage gates, output schema and reaction math unchanged. Do not add new identity/positive-price policies to a futures/FX analysis migration. In particular, never let generic close normalization shadow validated light price.
3. Preserve response-free diagnostics. Generated core can print redacted transport exceptions even with quiet=True, which would expose non-secret provider details contrary to this analyzer's contract. Add an optional registry redaction-template selector with the existing template as default and a target-only static-detail template. It retains only recognized HTTP codes and invalid-JSON classification; exception/body details are replaced by a fixed marker. Both generated stdout/stderr and report errors must exclude marker secrets (raw/encoded) and arbitrary response markers. Do not redirect process-global stderr or duplicate HTTP/retry logic.
4. Construct the client lazily from the adjacent generated module under a unique module name, independent of another skill's fmp_client import. Preserve missing-requests exit 2 and requirements hint. Give PriceClient an explicit close/context-manager surface; main must close its owned session in finally around price fetching before any later report/early exit. Replacing an injected session closes the previous owned session; close must be idempotent. Keep API-call counters honest to the generated transport (HTTP response attempts, not source probes); document this change without claiming #844's unmerged transport fix.
5. Add the registry target to all generator expected sets, source drift hook, package drift command and source/archive triggers, CI/template command and pinned test constant. Account for scanner expectation changes, if any. Rebuild only this skill's .skill package and update SKILL/EN/JA/source-map/migration notes and changelog. Reset any affected passed verification axes and matching baseline evidence, without promoting certification from local tests.

## TDD and validation

- Run the current news suite as baseline. Write failing regressions first for generated delegation/import/package boundaries and session cleanup; keep existing source-cutoff/reaction/vintage tests, modifying only obsolete transport-specific assertions.
- Fake actual Session.get for stable exact range/query auth/pacing, 402/403/500, empty data, malformed JSON once and exhausted retry, 429/exhaustion and timeout; no live API. Check price-source fallback, status classifications and post-cutoff invariance. Errors must not leak credentials (raw and URL encoded) or response/exception markers in stdout/stderr/JSON/Markdown.
- Verify adjacent import isolation, missing requests/keyless help/input-validation paths, main session closure on success, no-price early exit and exceptions, session replacement/idempotent close, and an extracted standalone archive. Confirm the reaction math file is unchanged.
- Run provider contracts, generator tests/drift, credential scanner/template/example tests, dependency checks, archive parity/smoke, pre-commit all files and the full 75-group normal pre-push matrix. Address failures, never bypass hooks. Existing generated clients must remain unchanged.

## Independent review protocol

Plan and implementation each receive at most three independent review rounds. Fix actionable findings; use clean approval as completion. If material findings remain at the limit, disclose and stop short of a ready PR. Commit/push and create the PR only after findings are resolved. Record local and hosted CI separately.

- Plan round 1: approved; no actionable findings. Explicitly verify exhausted-429 state, invalid-JSON classification and failure-versus-empty distinctions. Final before implementation.
- Code round 1: one P2 finding: shared exhausted-429 state yielded generic error for subsequent proxy attempts. Added failing direct/chain regressions and normalized the exact known stop reason to HTTP 429 in the adapter; no shared-core change.
- Code round 2: approved. Reviewer independently passed all 229 skill tests, verified generator drift for every target and archive/source parity. No actionable findings remain.


## Validation record

- Original skill baseline: 203 passed. Initial new TDD transport tests: 21 failed and 1 passed before implementation. Final skill suite: 229 passed (26 new cases); the round-one 429 regression failed twice before the fix and passes afterward.
- Generator/template/security-scanner/verification-baseline tests passed with the targeted skill suite (298 cases before the final added 429 chain case). Provider/shared-transport and unit-evidence regressions: 988 passed. Fifteen provider contracts validate offline.
- All-files pre-commit passed. Generator drift, generated EN-doc drift, dependency declarations, standalone package imports/compile/parity and marker leakage checks pass. Shared core templates, every pre-existing generated client and reaction_math.py are unchanged.
- Normal commit/push hooks validate the published revision; record the final complete dynamic matrix result and hosted CI independently in the PR. No live API, credentials, brokerage or production state was exercised. Previous unit/security certification is conservatively reset to not_verified.
- PRs #859 and #861 own adjacent transport/options work. Resolve registry/gate/test-constant ordering and regenerate/repackage according to merge order; this branch does not incorporate those changes. Issue #495 remains open for umbrella acceptance.

- Full matrix audit: first push stopped at 74/75 groups; 48 light-provider contract setups still patched the removed analyzer.time and one endpoint assertion referenced the removed local URL constant. Updated these tests to patch shared time.sleep and derive the exact endpoint from the unchanged provider contract. Assertions for schema/cutoff/status/response-free failure behavior are preserved. Code round 3 approved: reviewer independently passed all 96 light-provider contract tests and confirmed assertions are preserved. No production code changes since round 2; no actionable findings remain.
