# Issue #495: options-strategy-advisor generated FMP client slice

## Selection and isolation

Choose the unclaimed options-strategy-advisor remainder of P1 #495 (Batch D). Latest Issues/PRs/comments/local and remote branches/worktrees have no options migration. Several concrete P2 tickets already have PRs; #659/#660/#609 retain operational acceptance rather than missing implementations. Fresh branch/worktree based on `917a9a6fa0784164728021ff93d862fc34367b56`. PR #859 changes shared transport internals; do not incorporate or edit that core. Add a target-specific extension/registry entry and preserve every existing generated client byte-for-byte. Coordinate generated artifacts when merge order is decided. Use Refs #495; the umbrella stays open.

## Intended contract

1. Replace all hand-written FMP requests in black_scholes.py (history, quote, profile) with an adjacent generated FMP client loaded lazily under a unique module name. Register a budget-free family-B, stable-only target with target-specific methods delegating to the existing shared request/retry/timeout/redaction path. Use the established generated-client API-key query authentication. Do not change shared transport behavior or pricing/HV formulas.
2. Preserve get_current_stock_price(symbol, api_key), get_dividend_yield(symbol, api_key), fetch_historical_prices_for_hv(symbol, api_key, days=90). Each call owns/closes its session on every exit. Optional Python-only as_of for history can pin offline temporal tests; default is today's date. Missing key is rejected before network access; no API credential or raw response/exception may appear in adapter diagnostics.
3. Accept stable flat EOD rows and legacy-shaped historical/matching historicalStockList envelopes without calling legacy endpoints. Validate the requested identity (case-insensitive, historical '-' / '.' alias convention), dates, unambiguous envelopes and consumed prices. Exclude future dated history, select the newest requested sessions, reject duplicate consumed dates, and return oldest-first prices for HV. Missing/invalid dates or explicit foreign-symbol rows cannot be silently used. Do not fabricate prices or volatility; unavailable history/quote returns None. `days` must be a positive non-bool integer; malformed evidence fails safely.
4. Prefer adjClose only when consistently available for every selected row; otherwise use provider close only when adjusted evidence is absent for every selected row. Mixed/invalid adjustment evidence is unavailable, not silently mixed. Do not claim raw/provider close is adjusted. Quote/profile values must be finite; prices positive and dividends nonnegative. Keep lastDividend with lastDiv field alias compatibility. No implicit price=1 or malformed-field yield calculation.
5. Retain the existing dividend-yield return compatibility: unavailable evidence returns 0.0, but emits a fixed warning that this is an unverified legacy zero fallback, not confirmation of no dividend. A valid explicit zero dividend is zero without that warning. Keep manual OptionPricer(q=...) and the keyless offline __main__ demonstration usable without loading the HTTP client. Document that callers must supply q explicitly when yield evidence is unavailable. No new broker, live call, model formula, option chain or trading behavior.
6. Extend generator expected-target tests, hooks/CI package drift scope and the PR template's FMP mirror command as applicable. Existing requirements already declare requests/numpy/scipy; validate packaged dependencies and imports. Rebuild only this skill package and update skill/README/EN/JA/migration docs and changelog. Re-establish or conservatively reset affected verification evidence, without certification from green tests alone.

## TDD and acceptance

- Baseline current skill tests; write failing stable-flat history and generated-transport regressions before implementation. Retire tests requiring local hand-written v3 fallback and replace them with the documented stable-only contract.
- Exercise real generated HTTP code through fake Session.get: endpoint/parameters/auth, successful quote/profile/history, 402/403, malformed JSON retry, exhausted 429, timeout, safe diagnostics, owned-session closure and no legacy request. Include raw and URL-encoded marker-key leakage assertions.
- Test list/wrapper/batch identity, chronological ordering/newest selection, invalid/missing/duplicate/future dates, None/bool/string/NaN/Infinity/zero/negative/extreme prices, mixed adjustment basis, explicit dividend zero versus unavailable profile, invalid days, and no input mutation.
- Prove import isolation from another fmp_client module, unchanged pure formulas, keyless demo with HTTP forbidden, and extracted standalone package behavior. All inputs/state are fictional; no live API or account is used.
- Run generator --check and assert all pre-existing targets unchanged, provider contracts, targeted generator/client/skill tests, dependencies/package smoke, full pre-commit and all pre-push groups. Commit/push with hooks after approved code review and create a PR with Refs #495 and closingIssuesReferences empty; do not merge.

## Independent review protocol

Plan and code each receive at most three independent rounds. Address every actionable finding and obtain clean approval; if material findings remain at round three, report them and stop short of claiming completion or publishing a ready PR.

- Plan round 1: approved; no material findings. Implementation must additionally check finite dividend division results and keep provider-close adjustment descriptions accurate. Final before implementation.
- Code round 1: one P2 finding: the new HV example requested 90 prices for 90 returns (91 required). Fixed all three guides to request 91 prices and reject unavailable/short history; added executable synthetic-HTTP regression tests for all three fenced examples and rebuilt the package. No other implementation findings.
- Code round 2: approved. Reviewer independently passed all 65 market-data tests and verified every package entry matches source. No remaining actionable findings.

## Migration notes

The supported options wrapper endpoints are stable-only. The generated base still contains generic methods inherited from the existing transport, but these wrappers never invoke its legacy endpoints. API authentication now follows the generated target's query-key convention; callers must not log request URLs. This slice does not modify shared core templates or other generated clients; PR #859's concurrent transport changes will require ordinary regeneration/package reconciliation according to merge order.

Synthetic tests replace HTTP and never contact FMP. Endpoint entitlement and real provider payloads remain unverified. No production-readiness axis is promoted; the previous security scan is reset because its direct-HTTP premise has changed. The legacy dividend fallback is preserved for compatibility with an explicit warning, not endorsed as a verified model input.

- Final gate audit: extended the local FMP package-mirror hook command and both source/archive trigger patterns to the new target, matching the CI/template scope. Code round 3 approved: reviewer independently verified source/guide/archive trigger matches and all 25 configured package mirrors passed. No actionable findings remain.

## Validation record

- Baseline: 41 passing tests. TDD before implementation: 48 failures and 4 passes for the new transport contract.
- Final skill suite: 101 passed (36 existing pricing/HV tests and 65 market-data regressions). Generator and verification-baseline suites: 31 passed. Provider/shared-client contract suites: 1,021 passed.
- Generator drift check passes for every target; no pre-existing generated client is changed. Dependency declarations, standalone package/import/session checks and package/source parity pass. Pre-commit all-files checks pass; normal commit/push hooks enforce the final checked revision, including the complete dynamic test matrix at push.
- All HTTP is synthetic. Live FMP entitlement/provider behavior, actual trading performance and a renewed security certification are not established. Issue #495 remains open for umbrella acceptance.

- Final automated matrix audit (after the third and final independent code-review round): first push stopped at 74/75 groups. Six repo-script failures exposed stale expected target/credential-scan sets and a documented demo command conflicting with the existing library-only example rule. Updated only these expected sets and the demo prose, rebuilt the archive, and retained the existing library-example assertions. No pricing/transport code changed. Re-run the normal hooks without bypassing the failed gate.
