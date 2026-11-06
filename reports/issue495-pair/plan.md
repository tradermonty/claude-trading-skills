# Issue 495 pair-trade client migration plan

## Selection

Base: origin/main ff8ca70. Select unclaimed pair-trade-screener from P1 #495's remaining Batch D. P0 #332 currently has PR #640 modifying the shared provider contract layer; this migration avoids those files. PR #635/#636/#639 also have disjoint implementation paths. Existing #495 branches cover calendar/simple GET, dividend and stockbee batches; none claims pair-trade. Original checkout Git state is clean at 6e9a635. Work in a new worktree only. Keep #495 open because the other remaining skills are outside this slice.

## Final intended behavior

Both find_pairs.py and analyze_spread.py delegate all FMP HTTP calls to a generated standalone fmp_client.py. Keep public CLI arguments, API-key precedence, pandas Series shape/name, adjusted-close preference, chronological ordering, lookback row truncation, statistical calculations and output contracts. Remove local endpoint URLs, HTTP loops and module-global breaker dictionaries. The canonical generated historical stable-to-v3 fallback and flat/wrapped response normalizer remain supported inside the generated client. Sector screening becomes stable-only, matching the earlier #495 batches; failure/empty data retains the existing controlled exit. Each adapter call owns a client; no global failed-endpoint state carries across calls.

## Implementation and tests

1. Add failing tests first. Exercise the public adapters with a fake requests.Session boundary through the actual generated client, not a mocked replacement for its methods. Pin key header auth, stable screener params, historical row-based lookback truncation and sparse/delisted histories, chronology, adjusted-close preference, fallback to close, flat stable lists, wrapped histories and ticker alias normalization. Keep valid-data/statistical behavior unchanged.
2. Add a budget-free family-B registry entry for pair-trade-screener (hist_days=730, dict historical return, no v3 compatibility shim). Add a narrowly scoped pair_trade extension for stable screener rows and a public fetch_pair_history method calling the canonical historical transport without a date window, preserving latest-N-row semantics for sparse/delisted symbols. Add a default-false pair_history_validation registry/generator flag and a conditional pre-normalization hook in the core template, emitted only for this new target. Other generated client bytes must remain unchanged; redaction stays untouched. Validate response list/object shape and return failure for malformed provider bodies rather than iterate an error dict.
3. Replace fetch_sector_stocks with the new generated screener method and both fetch_historical_prices adapters with the generated fetch_pair_history method. Preserve the two different public lookback defaults (730 versus 365). Delete private _fetch_raw_historical helpers and old module-global endpoint/breaker state. Keep historical requests unbounded by date, retaining the most-recent N rows locally as before. Target-scoped preflight validation rejects malformed flat/wrapped histories, non-object rows, non-string symbols, invalid dates and unusable selected adjusted/close values with sanitized diagnostics before the common normalizer can raise; failure advances the canonical fallback and eventually returns None. Legacy screener fallback is deliberately retired; historical fallback lives only in generated code.
4. Adapt tests that assert the removed private HTTP implementation to Session fakes and public behavior. Retain meaningful error cases, stable/v3 historical fallback, alias matching, insufficient history and valid pair statistics/CLI tests. Add malformed/empty screener data, HTTP 401/402/403/429/500, invalid JSON, transport errors, per-call recovery after failure, value/query secret redaction and stdout/stderr assertions. Tests must not sleep or access the network. Check oversized/nonnumeric provider bodies where relevant without expanding financial algorithms.
5. Extend registry/generator expectation tests and wire the new target into CI/pre-commit generated-client/package drift lists. Add a fake-transport regression for both adapter modules. Add focused migration documentation without touching provider-contracts.md, and package only pair-trade-screener.skill. Verify existing generated client bytes remain unchanged.
6. Run the pair suite and generator/transport/gate tests first, then the complete canonical matrix, full package parity, metadata/docs/generated drift, lint/format and all-file pre-commit. Refresh Issue/PR/main status before publication. Preserve both original and unrelated worktrees.

## Review and delivery

Objective sub-agent plan review up to three rounds, resolving every actionable finding before implementation. Objective code review up to three rounds, resolving findings and revalidating. Commit only after final review and validation; open an English PR with Refs #495 and no closing reference. Separate local test evidence from hosted CI. No live provider calls, workflow dispatch, repository settings/secret changes, broker operations, merge or Issue closure.

## Plan review log

Round 1: preserve unbounded row-based history semantics for sparse/delisted symbols, and explicitly validate malformed historical shapes before the canonical normalizer. Both incorporated. Round 2: PASS, no outstanding findings. Final plan adopted before runtime implementation.

## Implementation review outcome

Round 1 found a provider-symbol diagnostic that could echo the API key. Target-only static mismatch rejection and bare/query-key regressions fixed it. Round 2: PASS. Final round 3 checked the CI, hook, PR-template and test-constant package target lists: PASS. No unresolved findings. The full-EOD contract now records the new generated owner and its recorded fixture is exercised through both adapters in fresh interpreters.
