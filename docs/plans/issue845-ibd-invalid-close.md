# Issue #845: finite IBD close prices without compressed sessions

## Selection and scope

Issue #845 is an unclaimed P2 execution/data-integrity bug. At selection, #332 has PR #838, #842 has an active worktree, and PR #839 changes another skill. No open PR, local/remote branch, worktree, or Issue comment claimed #845. Base: `917a9a6fa0784164728021ff93d862fc34367b56`. Work on a new isolated branch/worktree; preserve other checkouts. Limit functional changes to the IBD monitor. Do not modify shared FMP transport, credentials, live accounts, or other agents' changes.

## Intended behavior

- Normalize close prices on copied rows. Accept finite positive JSON numbers and numeric strings; reject booleans, missing/null values, nonnumeric strings, zero/negative, NaN, Infinity, and float conversion overflow. Represent unusable closes as `None` and retain every dated session in its original position; never connect two sessions across a gap. Do not mutate the provider payload.
- Record date-specific missing/invalid close evidence through the quality audit. Make validation safe for the same input forms. Normalize and validate fetch evidence without exposing raw values; effective analysis audit is scoped after `--as-of`. Fetch-wide warnings are not merged into a historical report; empty-fetch flags remain visible. A defect in either index blocks additions. Preserve existing volume behavior; malformed row containers and unrelated OHLC validation are outside this Issue.
- Normalize at the analysis boundary too, so direct `analyze_index` callers receive the same protection as CLI fetches. Apply quality auditing after the as-of slice for analysis, preserving as-of and DD ages.
- Compute EMA only when all rows it consumes have valid closes; compute SMA only when its most recent period is valid. Never remove gaps or warm up from disjoint sessions. Keep the existing EMA algorithm and valid-data results. Missing input or non-finite computed averages produce `None` for the corresponding filter and the combined MA filter, plus an explicit audit flag. A NaN must never become a false comparison and a spurious bearish signal.
- Invalid pairs cannot create DD records or close-based invalidation. Today/previous close summaries preserve the requested dates and use nulls for unavailable prices/changes. Guard finite-derived overflow as well: unavailable/overflowed daily returns and DD invalidation thresholds become null with dated arithmetic audit evidence; an overflowed invalidation threshold cannot trigger removal. Any such effective defect also blocks additions. Test extreme finite positive closes (return division, MA sum and close × 1.05). Preserve healthy DD thresholds, ages, MA settings, risk levels and schemas.
- For an effective history containing invalid closes, retain observed risk/counts as incomplete evidence but prevent a positive portfolio exposure delta: cap the target at current exposure and mark the action `AVOID_NEW_ADDS` only when the existing policy would otherwise add. Preserve policy reductions and stops. Explain the data-quality restriction in the action rationale and audit. Do not invent a new risk level or claim zero counts prove safety.

## Implementation and validation (TDD)

1. Add failing offline regressions for normalization, dated audit, payload immutability, numeric strings and all invalid close variants. Reproduce the actual client/fetch/analysis/CLI path using existing fake sessions; no live API calls.
2. Implement minimal shared close coercion/validity logic and boundary normalization. Add analysis tests for latest/interior/old gaps, as-of slicing, unchanged session ages, no cross-gap DD, valid string equivalence, and independently available SMA when an older gap prevents EMA.
3. Exercise report JSON/Markdown through the real main function: no exceptions or NaN/Infinity close-derived output, unavailable MA stays null, bad dates remain visible, exposure cannot increase, valid numeric inputs retain existing output. Keep unrelated volume/high semantics unchanged.
4. Update the skill and EN/JA documentation with gap handling and audit/action semantics. Refresh the distributable package and any affected verification evidence conservatively (no unsupported axis pass claims).
5. Run the skill suite and relevant metadata/package checks. Request an independent code review against the pinned base, address findings and repeat at most three rounds. Run standard pre-commit and all pre-push test groups, commit and push with hooks enabled, then create a PR linking #845. Report local evidence separately from hosted CI; do not merge.

## Independent review protocol

Plan and code each receive at most three review rounds. A round must identify actionable findings with concrete evidence; address every finding and obtain a clean follow-up before finalizing. If material findings remain after round three, stop short of claiming completion or creating a ready PR and report them. Record outcomes below.

## Review record

- Plan round 1: two findings addressed: isolate historical CLI audit/action from future defects; cover finite-derived arithmetic overflow explicitly.
- Plan round 2: approved; no remaining material findings. Final plan before implementation.
- Code round 1: one P2 finding addressed: preserve invalid versus missing close provenance in final reports without importing future-session evidence. Three new CLI assertions failed before the fix.
- Code round 2: approved; independent reviewer reran all 302 skill tests and diff whitespace checks. No remaining material findings.

## Validation record

- Original skill suite: 221 passed. Initial issue regressions: 73 failed / 1 passed before implementation.
- Updated skill suite: 302 passed (81 added regression cases).
- Production-verification parity: 12 passed; security axis reset to not_verified because the old scan does not assess changed runtime paths.
- No live provider calls or account writes.
