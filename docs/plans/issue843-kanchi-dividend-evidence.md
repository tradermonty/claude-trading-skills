# Issue #843: distinguish unknown dividends and use a consistent split basis

## Selection

Open queue: 58 Issues; PRs #838, #839, #851 and #852 are active. P0 #332 has #838; P1 #778 has an existing worktree; #652 retains native notification acceptance; #513/#514 already have substantial implementations; #495/#496/#297/#298 require broader migrations/evidence and shared paths. Choose the concrete unclaimed P2 #843: incorrect no-dividend and split-induced cut outcomes affect financial eligibility. No matching Issue comments, PR, local/remote branch or worktree existed. Work in a fresh isolated branch based on `917a9a6fa0784164728021ff93d862fc34367b56`. Preserve the original checkout and other agents' work.

## Contract and boundaries

1. `get_stock_dividend` returns `None` for transport/access/response-shape failures, `[]` only for a successful empty list. A nonempty list containing malformed rows must not silently become confirmed absence. Fixed safe reasons never expose provider content or credentials.
2. An unknown dividend history creates an `ASSUMPTION-REQUIRED` basis and `STEP1-RECHECK`, never `NO-DIVIDEND` or an actionable pass based on profile lastDiv. A nonempty history yielding no eligible/usable rows (future declarations/ex-dates only or unusable dates/amounts) also requires recheck; it never establishes absence. Add real CLI regressions for these versus true empty success. Successful empty history remains confirmed `NO-DIVIDEND` / `FAIL no_dividend`. Surface availability in JSON/CSV/Markdown and block order readiness. Preserve unrelated safety/event failures and their priority.
3. Use finite positive `adjDividend` when supplied for every eligible history row; raw-only histories retain compatibility with an explicit raw/unverified adjustment basis. Do not mix raw and adjusted monetary bases. Missing, malformed, non-finite, zero or negative adjusted values in an otherwise adjusted series require recheck rather than raw fallback. Apply declaration/as-of eligibility before choosing a basis, so future-only defects do not poison historical analysis.
4. In the CLI, require split evidence and provide split history to Step 1: raw-only dividends plus unknown splits (`None`) require recheck, distinct from confirmed `splits=[]`. Preserve legacy direct-library callers using an explicit `require_split_evidence=False` default, and mark raw amounts unverified; main always enables the requirement. If a relevant split exists and adjusted amounts are unavailable, require review rather than infer a cut. Never infer corporate-action ratios from dividend changes. When sourced original-currency policy amounts cannot be established on the same split basis, require review instead of manufacturing an original-currency cut. Preserve the existing original-currency versus FX safeguards on ordinary unsplit histories.
5. Add an explicit dividend amount-basis field/reasons to the report. Keep yield reconstruction and current numerator consistent, special-payment handling and declaration dates intact. Do not claim live FMP semantics, point-in-time adjustment availability or successful production validation: this is an offline correction using the repo's existing adjDividend convention. No shared FMP transport changes, live API/account writes, corporate-action backfill, or other Issue fixes.

## TDD and implementation

- First reproduce both Issue cases and add failing regressions. Fake the real generated-client HTTP boundary for failure versus successful empty; test build_entry_row and real main/report outputs. No real API calls.
- Test 429/timeout/access error/wrong shape, malformed nonempty lists, empty success, regular data and specials; verify unknown does not produce no_dividend or permit an order.
- Test a raw 0.50 -> 0.25 split with adjDividend 0.25 throughout, a genuine adjusted cut, numeric strings, missing/invalid adjusted values, mixed bases, known split without adjusted history, reverse splits, future-only defective rows, original-currency evidence, no input mutation, and consistency with reconstructed yield.
- Implement the smallest boundary/basis changes, retaining normal raw-only callers and unrelated safety logic. Run the entire skill suite, relevant workflow/schema/verification checks, and package consistency.
- Update instructions, EN/JA docs, changelog and distributable package. Reset affected stale verification evidence to not_verified unless fully re-established; do not upgrade axes from aggregate green checks.
- Independently review code and fix findings (max three rounds). Run normal pre-commit and all pre-push groups, commit/push with hooks, create PR linked to #843, verify exact head and initial CI state. Do not merge.

## Review protocol

Plan and code each have at most three independent review rounds. Resolve every actionable finding and obtain clean follow-up approval. If material findings remain after round three, report them and do not claim completion or publish a ready PR.

- Plan round 1: two findings addressed: distinguish unknown versus confirmed-empty split evidence in CLI (explicit library compatibility); treat nonempty eligibility-filtered/unusable histories as unknown rather than no-dividend.
- Plan round 2: approved. No remaining actionable findings; final before implementation.
- Code round 1: one P2 finding addressed: malformed split responses/evidence cannot establish no splits or bypass the unknown-split gate; adapter, basis and CLI regressions added.
- Code round 2: approved. Independent reviewer ran all 53 Issue regressions; no remaining actionable findings.

## Validation record

- Original skill suite: 340 passed. Initial Issue regressions: 36 failed / 4 passed before implementation.
- Pre-review implementation: 383 passed (43 new cases); review regression: 7 failed / 44 passed before the malformed-split fix.
- Final skill suite: 393 passed (340 existing + 53 new regression cases).
- Verification-baseline parity: 12 passed. Security axis reset to not_verified; no unsupported axis upgrades.
- No live provider/account writes or production acceptance claimed.


## PR #853 review follow-up: blank declaration dates

- A whitespace-only declarationDate was mistakenly truthy after the two-pass eligible-history refactor. Normalize the declarationDate on the current eligible row before recording confirmation; do not reuse the first loop's last decl value.
- Added 12 regressions for empty/space/tab/newline/full-width/nonbreaking-space values, chronological/reversed provider order, and a valid padded latest declaration alongside an older blank row. Before the fix: 8 failed, 4 passed; blank dates could incorrectly turn a near-floor RECHECK into PASS.
- Preserve the near-floor gate: a blank latest declaration remains unconfirmed and STEP1-RECHECK; a real latest declaration remains confirmed and STEP1-PASS regardless of input order. Merge current main without discarding either changelog entry, rebuild the archive and run normal hooks.

- Follow-up validation: all 405 Kanchi tests pass, including the 12 new declaration/order regressions; verification-baseline parity 12 passed; archive rebuilt and matches source. Pricing/basis logic is otherwise unchanged.
