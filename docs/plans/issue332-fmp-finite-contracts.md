# Issue #332: finite required numeric fields in FMP contracts

Status: FINAL — independent plan review approved in round 2.

## Selection and isolation

Selected the P0 provider-contract issue after refreshing all 50 open Issues, open
PRs (none), local/remote branches and worktrees. Existing #332 work is the merged
CSV parser/numeric-limit slice; this change is limited to FMP JSON contract data
and offline validation tests. #831 has active exposure-coach edits and is excluded.
P1 security/client worktrees and unrelated files remain untouched. Work begins on
a new `codex/issue332-fmp-finite-20261121` worktree at main `465e6649`.

## Confirmed defect and acceptance

On the exact base, copying recorded fixtures and setting quote.price to Infinity,
full-EOD.close to NaN, or ratios.priceToEarningsRatio to 10**400 still makes
validate_rows().ok true. The finite validator already exists, but only light-EOD
price and quote volume opt in. There are 39 numeric-only required fields across
10 FMP contracts; 37 fields across nine contracts lack the policy.

Deliver this independent slice, retaining `Refs #332`: every numeric-only required
FMP field must reject NaN/Infinity/integers outside finite float range through
fixture checking, HTTP-200 canary validation and CLI report/exit behavior. Existing
valid recorded fixtures, allowed nulls, zero, negative finite financial values,
type checks and all-null rules must preserve their existing semantics. This does
not complete the umbrella's remaining provider inventory or live acceptance.

## Implementation

1. Add failing field-by-field regression tests using recorded fixtures. Cover
   float-accepting fields with NaN and both infinities; all integer-accepting
   fields with an out-of-float-range integer. Assert fixed fatal anomaly codes
   and canary ok=false. Retain type failures for bool/string values and test
   malformed observations beyond the first row.
2. Enable existing `finite: true` on the 37 missing numeric-only required fields.
   Do not add positivity, range, date or string coercion rules. Tightened contract
   policy is versioned: rename the nine affected .v1 files to .v2 and increment
   contract_version to 2; retain schema_version 1, endpoint keys, owner lists,
   queries, fixture values/capture dates, optional fields and aliases. Keep only
   one active file per endpoint, with prior versions retained in Git history.
   Audit repository-wide direct filename consumers before renaming: migrate
   test_pair_fmp_migration.py to endpoint-keyed load_contracts() access and update
   current pair-trade migration guide references; preserve historical plan context.
   The already-finite light EOD contract and nonnumeric SP500 contract stay v1.
3. Keep the generic validator opt-in. Update the old test that assumes the real
   quote.price is unchecked: explicitly remove the policy from a copied custom
   contract to test the unchanged default behavior.
4. Add CLI integration with the actual canary command and a fake FMP transport:
   HTTP 200 quote JSON containing the valid JSON overflow token `1e400`, decoded
   by the real requests.Response.json() and existing fetcher with only requests.get
   mocked, plus a healthy later contract must produce
   a complete finite JSON report, fatal field reason and exit 1, without leaking
   a marker credential or raw response. Verify healthy fixtures return exit 0,
   budget guards remain intact and nullable/all-null policies are unchanged.
5. Update the provider-contract guide's current file/version references and
   finite-policy scope; record the user-visible change in CHANGELOG. No skill
   runtime, generated FMP client, package, workflow, notifier or verification
   metadata is changed. No new live response is claimed or captured.

## Verification

- Capture fail-before/pass-after results for the new semantic regressions.
- Run provider contract/light/summary/numeric-limit, canary health/workflow and
  notifier suites, all four pair-FMP-migration cases and the offline `check` over
  all 15 contracts. Search all operational source/doc references for renamed files.
- Check fixture data/recorded_on/owner/query equivalence to base separately from
  the intentional policy/version changes; no fixture rewriting to hide drift.
- Run relevant Ruff/format, all-file pre-commit and the ordinary required full
  pre-push matrix. No real key, provider call, notification, dispatch or live
  setting is needed. Optional test skips remain distinct from exercised cases.
- Ask an independent sub-agent to review the implementation, at most three
  rounds, addressing all actionable findings and revalidating each correction.
- Recheck current Issue comments, open PRs and scope overlap before commit/push;
  preserve concurrent main changes using normal integration if necessary.
- Commit and create one PR with `Refs #332`, actual validation and remaining
  umbrella/live gates. Do not merge or close #332 as part of this request.

## Review log

Plan round 1: CHANGES REQUESTED. Reviewer independently verified the inventory.
Required P2: a pair-trade test directly opens a v1 filename; endpoint-keyed loading,
repository-wide filename audit, guide update and four-case validation were added.
Clarification: CLI integration now explicitly decodes valid JSON `1e400` through
the real fetcher with only HTTP GET mocked, covering standards-valid overflow
rather than depending on nonstandard NaN/Infinity decoding.

Plan round 2: APPROVE. Reviewer confirmed both corrections and found no remaining
actionable plan findings. Implementation verification: new regressions failed on the baseline (180 failed,
260 passed); the first combined run exposed an unchanged 30-second cold-import
pair subprocess timeout (rerun: all four passed) and a strict economic-calendar
policy-dictionary assertion, updated to require the added finite attribute.
Implementation round 1: APPROVE, no required changes. Independent reviewer ran
1,083 passing targeted tests and the 15-contract offline check; independently
confirmed fixture/version/field-policy equivalence and operational references.
One informational comment: the illustrative profile v2 JSON omitted finite on
marketCap; corrected to match the active contract. Round 2 documentation-only
confirmation: APPROVE, no remaining actionable findings; unchanged suites were
not repeated.
