# Value-dividend RSI price-gap safety (#655)

This completes the remaining price-bar zero-default site in
value-dividend-screener. It is a scoped #655 slice; other skills remain under
that Issue. RSI consolidation/period policy (#663) and shared evaluation coverage
(#711) are separate. Existing open PRs and worktrees were checked before claiming
this scope on #655. The original checkout is preserved.

## Final plan

An independent subagent approved the plan in round 1 without findings.

1. Pin the silent-zero defect with pipeline regressions before implementation.
   Rising closes 1..30 give RSI100; replacing the latest missing close with zero
   gives RSI31 and can change candidate selection.
2. Generate the shared price-bar helper and its contract tests for this skill.
   Read each returned raw close through read_price, preserve the complete
   chronology and skip the candidate on any invalid close with a fixed reason.
3. Make direct RSI calculation return None on invalid prices or a non-finite
   result. Preserve Wilder smoothing, rounding, thresholds, ranking, flat-series
   behavior and the existing 20-observation pipeline threshold.
4. Remove only this skill's zero-default allowlist entry; keep the ratchet and
   generated-helper drift gates clean without modifying other consumers.
5. Test the real generated transport with fake HTTP, missing and NaN evidence,
   continued processing of valid candidates and unchanged clean calculations.
   Update SKILL/EN/JA docs, changelog and the standalone package.
6. Independently review the implementation; run focused and repository gates,
   including the normal pre-push full matrix, then commit and create a PR with
   Refs #655. No merge, Issue closure or live provider/brokerage calls.

## Behavior and evidence

The existing generated FMP adapter returns up to 30 recent raw rows. Validation
covers every returned row used for RSI: no history is shortened to hide a gap,
no zero is invented, and adjusted-close fallback is not introduced. Missing,
None, boolean, string, zero, negative or non-finite closes make that candidate
unavailable. The pipeline records a safe stderr reason and proceeds to the next
candidate. A non-finite RSI result is also unavailable.

The initial new regression selection had 40 failures and one clean-history pass
before implementation. Tests cover first/middle/last bad rows, malformed rows,
valid rising/falling/mixed behavior, minimum observations, and raw fake-HTTP
responses through the generated client before screening. No live provider data
was fetched. The existing RSI algorithm and provider price basis are retained.

These checks establish input/result safety, not calibration or investment
performance. The existing empty-result report is not upgraded to a shared
coverage report; stderr distinguishes the skipped candidate until #711 adoption.
