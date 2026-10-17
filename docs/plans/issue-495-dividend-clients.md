# Issue #495 Batch B: dividend/value FMP clients

## Selection and isolation

Select P1 #495's complete proposed Batch B: value-dividend-screener,
dividend-growth-pullback-screener and kanchi-dividend-sop. P0 #332 already has
open PR #572; P1 #298 has #571; #496 has a live worktree. #495 Batch A PR #532
is merged (verified on GitHub), and no registered worktree/open PR covers Batch B.
Other batches remain outside this PR. New worktree
`/private/tmp/cts-issue495-dividend-20261017`, branch
`codex/issue495-dividend-clients-20261017`, based on main b29c6df.

## Implementation plan

1. Register all three targets in the existing FMP generator. Use its shared
   header-auth transport, redaction, rate limit, bounded JSON/429 retry and
   API-call accounting. Add a generated dividend extension for stable endpoint
   routing and existing response aliases; do not create local HTTP helpers.
   Preserve byte-identical output for the existing 14 targets (including the
   economic-calendar client used by #572). Scope an optional per-instance
   request-timeout capability to new targets if needed to retain Kanchi's API.
2. Remove hand-written FMP session/network/retry code from the scripts. Keep
   thin subclasses for the existing public FMPClient interfaces and their
   screening/domain calculations. Retain `_get` shape adapters where current
   business methods need them, but implement request routing/normalization in
   the generated extension. Kanchi retains `sleep_seconds`, `timeout`, and
   `api_calls` via shared transport settings/accounting. Keep FINVIZ separate.
3. Route only supported stable endpoints for these targets; remove their dead
   v3 URL fallback. Preserve dividend flat-list -> historical wrapper, ROE and
   dividendsPaid aliases, quote/profile field handling, history list slicing,
   None/[]/{} conventions and CLI key/environment precedence. Public methods,
   filters, financial formulas and successful report formats remain unchanged.
   Failure retry/rate-limit behavior now follows the shared client; document
   this intentional transport change rather than retain divergent old loops.
4. Update tests that explicitly require retired v3 fallback to assert stable
   failure/no v3 requests. Preserve financial/scoring tests unchanged. Add
   fake-transport integration tests for each migrated path: stable params,
   successful return shapes, HTTP/tier/empty/error handling, malformed JSON,
   bounded retries and redaction (including echoed raw/encoded keys). Verify
   Kanchi timeout/sleep/accounting and original single-symbol quote/profile
   calls. Add generator-target tests and an existing-target byte-parity guard.
5. Extend CI/pre-commit FMP package drift target lists for the three skills,
   rebuild their .skill archives, and update affected skill/developer docs with
   the stable-only behavior. No live API calls or secret changes are needed.

## Verification and review

Run each skill suite in isolation (their script/module names overlap), then
FMP generator and provider-contract tests, generator --check, targeted package
--check, dependency declarations, docs/CLI/resource validation and Ruff/codespell.
Honor commit/push hooks; run the long all-skill test hook before opening SSH and
reuse the exact-commit result on push to avoid the known idle-connection timeout.
Review plan and implementation independently, at most three rounds each. Fix all
findings before commit and PR. Keep #495 open for remaining batches.

## Review log

Plan round 1: approved; no required corrections.


## Implementation reviews and validation

Code round 1: approved with no findings. Broad regression discovered stale
CI/pre-commit package-command expectations; updated the exact 17-target test
list and PR template, and added the three clients to existing redaction tests.
Code round 2: approved with no remaining findings; reviewer independently ran
the final template/redaction suite (405 passed).

- Final skill suites: value 147 passed; pullback 150 passed / 2 existing skips;
  Kanchi 95 passed. No new skips were added.
- Generator, provider contracts and new adapter transport cases: 205 passed.
- Final template/redaction cases: 405 passed.
- The first broad scripts run found only the two stale command-list failures;
  the corrected cases pass, and the mandatory full matrix runs before push.
- Seventeen generated clients match their templates; the prior fourteen clients
  are byte-identical to main. All non-FMP top-level class/function ASTs in the
  three main scripts are unchanged, including financial calculations.
- Targeted archive checks, dependency declarations, docs/CLI/resource checks,
  strict metadata/workflows, compatibility, Ruff and codespell passed.
- No live API calls, secret changes, trading actions, releases or merges.


Code round 3: approved with no findings after a coverage correction. The new
shared transport scenarios originally ran only in repository tests; an additional
per-skill check found Kanchi at 63.62%, below the 70% policy floor. Extracted the
same scenarios to a shared test helper and executed them in each skill's own
process/coverage row. Final executable-only local coverage (tests excluded):
value 87.20%, pullback 86.08%, Kanchi 75.36%. The independent reviewer reran the
three repository integration cases and Kanchi's added case successfully. No
production code changed during this correction. The old in-progress all-skill
hook was stopped; required checks rerun on the amended final commit.
