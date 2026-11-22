# Issue #495 completion plan

## Scope and integration

Finish the original 20-skill migration. A read-only independent acceptance audit found 17 registered targets on main; PR #861 (options, exact head 4a5c016eaa6eaa534c1c1b0b1f338e831d944292) and #862 (news, 1f1d99e39834ee2dcf83ca006c8c8cbfcbebbb0b) implement two more, leaving theme-detector. This fresh worktree starts from #862 and locally merges #861, preserving both commits, extra coverage tests and documentation. Resolve only registry/gate/test-constant/changelog ordering. Never modify the existing PR worktrees or force-push their branches. The final integration PR targets main and includes both existing migrations plus the final theme work; supersession/closure is contingent on final merge approval.

An automatic approval review rejected merging #862 because the current request did not explicitly authorize merging. Do not retry or bypass it. Complete implementation, independent reviews, local/hosted checks and the integration PR first; request approval for the concrete final merge and Issue closure afterward. Do not merge or close #495 during preparation.

## Implementation

1. Add theme-detector as target 20: budget-free family B, query authentication, configurable 15-second timeout and news' target-scoped static diagnostic template. The generated extension owns stable quote, full-EOD and ETF-holdings HTTP, delegating retry/redaction/timeout behavior to existing core. No v3 endpoint fallback and no change to core templates or unrelated generated clients. PR #859's shared-core repair remains separate.
2. Introduce a lazy adjacent-client adapter with unique module identity. Each operation owns and closes a session on success, unavailable evidence and exceptions; missing key never loads the HTTP client. Preserve keyless yfinance/manual behavior and optional dependency guards. Existing app-level pacing remains across operations; shared pacing applies within retries. Use explicit rate/timeout values and fixed diagnostics without response/exception/key details.
3. Replace ETFScanner's handwritten HTTP/endpoint breaker and representative holdings' handwritten HTTP with that adapter. Preserve public interfaces, symbol aliases/cache, one-symbol requests, historical date-range/as-of conversion, response normalization, yfinance fallback, existing selection/ranking/source-state logic. Do not silently disable the endpoint after empty results for different symbols. Define backend fmp_calls/fmp_failures as stable logical operation counts, not raw retry counts. Keep FINVIZ paths untouched.
4. Add an executable acceptance gate with a checked manifest: original 20 skills must be registered and own their generated client; scan tracked runtime Python under skills/scripts/examples (including hidden example snapshots), excluding tests and exact registry-generated outputs, for unreviewed api/v3 references. Exact path/line-pattern exceptions require nonempty reasons and stale exceptions fail. CoinGecko is another provider; historical comments and frozen examples are identified explicitly. Independent diagnostic/weekly utilities outside the original 20 retain narrowly documented compatibility probes, not a blanket exemption for production skill callers. No target skill may be omitted through an exception.
5. Document the full 20-row acceptance matrix with fake-transport evidence pointers, precise legacy allowances and remaining integration conditions. Wire gate into local/CI checks and tests; ensure source/package drift lists cover all targets (the existing all-skills package gate already provides broad coverage). Update SKILL/EN/JA guidance, changelog and theme archive. Reset stale passed verification evidence and matching baseline without asserting renewed certification.

## Validation

- Baseline theme tests; write failing adapter/transport/cleanup regressions before implementation. Preserve existing symbol/cache/as-of/ranking/FINVIZ tests; replace only assertions requiring handwritten HTTP or legacy fallback.
- Actual generated transport with fake Session.get: all three stable endpoints, exact parameters/auth/date cutoff, 15-second timeout, empty and denied payloads, shared JSON/429 retry, stable-only failure to yfinance, multiple empty symbols not disabling later healthy symbols, owned-session closure and raw/encoded key plus body/exception marker non-disclosure.
- Import collision, missing key/requests keyless paths, extracted standalone archive, and deterministic source input non-mutation. No live FMP/yfinance/FINVIZ or brokerage state.
- Gate tests: all 20 targets, unregistered/missing clients, new legacy reference rejection, precise reasoned exceptions, stale/empty/broad exception refusal, hidden snapshots, generated artifact exclusion. Verify every pre-existing generated client remains byte-identical and existing #861/#862 implementation is preserved.
- Run generator/provider contracts, affected skills and root integration/metadata/template/security/baseline tests, dependency and package checks, all-skills package --check, all-files pre-commit and full normal pre-push matrix. Do not bypass failed gates. Reconcile hosted CI and exact final head before requesting merge approval.

## Independent review

Plan and code each receive at most three objective review rounds. Resolve actionable findings and obtain clean approval; otherwise disclose remaining findings at the limit. Record results here. No merge until the final explicit approval required by automatic approval review.

- Acceptance inventory audit: completed read-only; 17 main targets plus two open migrations, theme remaining, existing generic package gate covers all skills.
- Plan round 1: approved. Exact generated-output exclusions must derive from generator targets (including compatibility shims); keep all 20 runtime delegation/test evidence rows explicit. Final before implementation.
- Code round 1: one P2 finding: a generated 429 retry left the caller pacing timestamp at the first attempt, allowing the next operation immediately after the retry. Added failing deterministic-clock regressions for scanner and holdings, then refreshed both caller timestamps in finally after transport completion.
- Code round 2: approved. Reviewer independently passed all 16 theme transport regressions and archive parity; pacing in both callers includes exceptional cleanup. No actionable findings remain.


## Validation record

- Theme baseline: 623 passed, 1 existing optional-dependency skip. Initial transport TDD: 11 failing cases; acceptance-gate TDD: 6 failures before implementation. Final theme suite: 639 passed, 1 optional skip; 16 new transport regressions cover retries, pacing, ownership, import isolation and extracted archive.
- Combined options/news/theme before the final pacing regressions: 976 passed and 1 optional skip. Existing options and news implementation remain byte-identical to their reviewed PR heads; final theme run verifies the added pacing tests.
- Entire root suite: 4,173 passed; one loopback socket bind was denied by the restricted sandbox. That exact case passed under the same permission profile used for normal pre-push. The normal final-head pre-push matrix remains mandatory and is recorded in the PR.
- All 74 distributable skill archives match source; generator drift passes for every target, and only the three newly migrated clients differ from old main. Acceptance gate validates all original 20 targets and precise reasoned exceptions. Fifteen provider contracts, dependency declarations, standalone package smoke and all-files pre-commit pass.
- Main is unchanged. Integration retains existing #861/#862 commits; no original PR branch is rewritten. Merge and Issue closure remain pending the explicit approval required by automatic review. Final hosted CI must be recorded separately from local evidence.
