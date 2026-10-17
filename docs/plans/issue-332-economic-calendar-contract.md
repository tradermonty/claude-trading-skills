# Issue #332: economic-calendar contract and fail-closed consumer

## Selection and isolation

P0 #332 is the highest-priority open implementation issue. Select its remaining
FMP `/stable/economic-calendar` endpoint slice. Open PR #571 is #298 and touches
the dashboard only. #332's earlier canary/contract PRs (#519, #481, #459, #353)
and #495 Batch A (#532) are merged; no active registered worktree covers this
endpoint contract. Residual #332 temp directories do not have live checkouts.
No other agent's index, verification baseline or generated client migration is
modified. Worktree `/private/tmp/cts-issue332-economic-20261017`, branch
`codex/issue332-economic-contract-20261017`, based on main b29c6df.

## Goal and implementation

1. Add versioned `config/provider-contracts/fmp/economic-calendar.v1.json` using
   a minimal subset of the actual 2026-10-17 read-only HTTP 200 recording for
   2026-10-01 through 2026-10-07 (568 public macro-event rows, no credentials).
   Owner: economic-calendar-fetcher. Required consumer fields: date, country,
   event, currency, impact (strings); previous, estimate, actual, change,
   changePercentage (number or null). Unit is optional. The canary uses this
   known populated historical window and min_rows 1; future real-world ranges
   are not assumed to contain events. Report tier entitlement honestly: 402
   remains a failure, not zero events. The existing loader automatically adds
   one budgeted canary call; do not change canary promotion/report-only policy.
2. Add a standalone validator in the owning skill, called by its real fetch
   path after the existing generated FMP client. Reject malformed objects,
   renamed/missing required keys, wrong types, booleans/nonfinite numeric
   values, empty required strings and unparsable event timestamps. Permit
   null readings (including all-null actual/estimate); preserve unknown extra
   fields and successful JSON/text formats. Do not import repository-only code
   from the packaged skill or modify the generated HTTP client/template.
3. Add machine-readable CLI stderr reasons. Malformed event arrays and the
   generated client's explicit `Unexpected API response format:` ValueError
   (HTTP-200 object/string/scalar) become a dedicated standalone schema exception:
   `economic_calendar_schema_drift`, exit 1. Preserve the original generated
   client. HTTP-200 null and exhausted malformed-JSON retries cannot be reliably
   identified from its generic failure API; document them as acquisition failures
   together with transport/HTTP/tier failures, never as a successful empty result:
   `calendar_fetch_failed`, exit 1. Clean empty array:
   `empty_calendar_unverified`, exit 1, no successful output write. Since a
   global economic calendar has no trusted holiday/completeness classifier,
   do not assert an empty provider response proves no scheduled events. The
   low-level fetch API may return [] so callers can apply their own policy.
   Test actual `requests.Session.get` transport stubs for HTTP-200 object,
   string, null and invalid JSON, plus 402/503/connection failure; assert the
   supported classification above (invalid JSON retains its existing bounded
   retry). Validate error text does not expose body/key.
   Validation happens before any output file opens; existing output survives
   drift/empty/fetch failure. Never echo malformed provider payloads or API keys.
4. Bind repository contract tests to the actual owning consumer via injected
   transport, using the recorded fixture and mutations; verify contract and
   standalone validation agree on required names/types/nullability. Update
   explicit contract inventories and fake canary routing, preserving dynamic
   max-call accounting. Add per-skill tests for types, date validity, null
   handling, empty CLI behavior and existing-output preservation.
5. Document the new contract and exit behavior in provider docs and the skill,
   regenerate its .skill package and only generator-owned docs if needed.
   Keep #332 open for other endpoints/non-FMP providers and canary promotion.

## Validation and review

Run owning-skill tests and repository provider-contract/canary tests, provider
`check`, FMP generator drift, package --check, affected docs checks, Ruff and
codespell. Mandatory commit/push hooks also apply. Review plan and implementation
independently with sub-agents (at most 3 rounds each); fix all findings before
commit/PR. No release, secret configuration, canary dispatch or trading actions.

## Review log

Plan round 1: clarified pre-validator generated-client failure classification;
object/string/scalar map by explicit shape error, while null/malformed JSON stay
acquisition failures. Added real-transport HTTP/body/error matrix. Round 2: approved; no remaining required corrections.


## Implementation review and evidence

Code review round 1: no findings. The independent reviewer ran 333 owning-skill
and provider-contract tests and validated all 568 recorded live rows.

Author validation: full repository scripts suite 2,251 passed (20 existing
warnings); 388 focused owning/provider/canary tests passed; all nine
provider contracts validate offline. FMP generator drift and owning .skill
package consistency passed. Ruff check/format, codespell, documentation CLI
examples, strict workflow/metadata checks, bundled resource references and docs
source checks passed. All 568 recorded rows passed the standalone validator.

The generated client and canary promotion policy are unchanged. No scheduled
live canary was dispatched, secrets were not changed, and no trading action or
release was performed. #332 remains open for its broader remaining scope.
