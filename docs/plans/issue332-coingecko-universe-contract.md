# Issue #332 — CoinGecko universe response contract

## Scope and non-overlap

P0 #332 explicitly leaves CoinGecko without contracts. Deliver one complete endpoint slice: `/api/v3/coins/markets`, consumed by crypto-regime-analyzer's universe fetch. Open PRs #870/#872/#867/#866/#863/#855 and current worktrees have no CoinGecko consumer or provider-contract changes. Other #332 slices are historical CSV/FMP work. Do not change FMP templates, security evidence, or other crypto endpoints. Keep #332 open for the remaining inventory.

## Implementation plan

1. Record a bounded keyless HTTP response (three public coin rows), retaining consumed id/symbol fields and capture metadata. If capture cannot succeed, do not fabricate recorded evidence; document the limitation and revise scope before claiming completion.
2. Add a versioned `coingecko/coins-markets.v1.json` contract with owner crypto-regime-analyzer, the real request path/query, non-empty rows and required non-null string id/symbol fields with opt-in `non_blank: true`. Add this policy to the generic validator with invalid-policy tests, leaving other contracts unchanged. Extend the existing provider CLI with explicit `coingecko` selection and a bounded keyless JSON fetcher, fixed HTTPS origin, allowlisted path, timeout, disabled redirects, response-size limit, fixed safe error codes and cleanup. Preserve FMP/CSV behavior and offline stdlib importability. CLI `--max-calls` must refuse insufficient budgets before network work.
3. Make the production universe consumer reject unavailable/empty/malformed HTTP-200 payloads with an explicit fixed reason rather than cache an empty universe. Reject nonpositive/non-integer/bool top_n at construction. Validate consumed id/symbol values including blank/whitespace strings; reject path separators, traversal components and control characters in coin IDs before history URLs/cache paths; do not silently drop malformed rows. Preserve exclusion filters, symbol uppercasing, top-N cache scoping and valid inputs; never write a bad result to cache. Reject empty post-exclusion universes before cache writes. Validate cached rows before exclusion checks; malformed cached payloads fail explicitly, while valid newly-excluded coin caches still refresh. Cover cache reads as well as live responses without changing other endpoint semantics.
4. Add a weekly read-only keyless workflow for this one contract, using pinned existing Actions versions, a hard job timeout, one-call budget, machine-readable artifact and summary. Remove stale report before probing; capture probe outcome/exit code, set continue-on-error only on the probe step, and require the existing health gate with --provider coingecko. Infrastructure failures must be visible; provider drift is report-only under #332 policy. Do not trigger the workflow or synthesize notification Issues.
5. Test recorded fixture and renamed/missing/null/retyped/blank/whitespace/empty rows against both contract and actual consumer; prove no false zero output/cache on invalid data. Fake HTTP tests cover transport/status/redirect/oversize/parse errors, cleanup and remaining-provider isolation. Verify existing provider tests, crypto skill tests, docs/package consistency and required pre-push checks.

## Review and delivery

Request independent plan review, at most three rounds; resolve findings before implementation. Request independent code review, at most three rounds; resolve findings before commit and PR. Recheck remote/main and overlapping PRs before publishing. PR uses `Refs #332`, clearly separates offline/live-capture/hosted-CI evidence, and states that other CoinGecko endpoints and providers remain uncovered. No merge or Issue closure.

## Plan review log

Round 1: two P2 findings, both incorporated: explicit nonblank semantics shared by contract and consumer; post-filter/cache/top_n behavior. Also adopted bounded path-safe IDs, explicit provider dispatch (including all), and mandatory operational-health gate. Round 2: APPROVE, no remaining actionable findings. This is the final implementation plan.

## Implementation and review results

- Recorded HTTP-200 public CoinGecko rows and added the versioned contract, opt-in nonblank policy, explicit provider dispatch, keyless bounded fetch, production consumer/cache validation and weekly workflow.
- Code review round 1: one P3 finding (present JSON-null cache indistinguishable from absent file). Fixed with cache-presence evidence and a regression; no P1/P2 findings.
- Code review round 2: APPROVE, no remaining actionable findings; reviewer independently checked 54 endpoint regressions and archive consistency.
- Validation: initial 20 consumer regressions failed before the fix; the final crypto suite contains 111 passing tests. The related provider/summary/health/workflow/docs group has 615 passing tests. Offline contract check validates all 16 contracts; repository dependency check, docs drift, strict index, Ruff and package consistency pass.
- Live evidence: the implemented canary made one keyless GET with `--max-calls 1`, returned HTTP 200 / three rows / no contract anomalies; the operational health gate passed. This is a local endpoint probe, not a scheduled Actions run or full production crypto analysis. Required pre-push suite and hosted CI are recorded separately in the PR.
