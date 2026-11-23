# Issue #849: regular-payment growth and historical eligibility

## Selection and isolation

58 open Issues; P0 #332 and several concrete P2 bugs have open PRs. Choose unclaimed P2 #849: special payouts and date-window artifacts alter financial eligibility. No claim/PR/local or remote branch/worktree matched #849. New isolated branch/worktree based on `917a9a6fa0784164728021ff93d862fc34367b56`. PR #851 changes financial-health functions, #854 changes output paths; neither changes dividend aggregation. Preserve those functions and record shared package/changelog merge coordination. No live API, account or real state access.

## Final behavior to prove

- Exclude explicitly special/supplemental/one-time/extra payments (case-insensitive frequency/label evidence, following the existing Kanchi convention). Do not classify ordinary raises as specials by amount. Filter future ex-dates before amount/cadence processing. Use finite positive regular amounts; unusable eligible regular evidence must return unavailable rather than become zero or silently manufacture growth. Keep tuple shapes and ordinary CAGR/5% consistency thresholds.
- Preserve value-dividend-screener's current regular-payment information rather than returning partial current calendar totals or delaying an ordinary raise until year-end. Replace fixed 365-day windows with equally sized payment-count annual buckets at a validated cadence (monthly=12, quarterly=4, semiannual=2, annual=1). Infer cadence only when the recent median gap falls within +/-20% of exactly one supported nominal interval (365.25 / payments_per_year days); these distinct bands reject twice-monthly and other unsupported schedules. Cross-check explicit frequency metadata: monthly/quarterly/semiannual/annual (or their numeric payments/year equivalents) must agree, while Irregular/unsupported or mixed frequency values require unavailable rather than being dropped; ambiguous/mixed cadence, duplicate regular dates, missing-payment gaps or insufficient complete buckets are unavailable. Require `payments_per_year * (years_back + 1)` eligible payments. Validate selected gaps against 0.5..1.5 of the nominal cadence interval, and require each pair N payments apart to be 365.25 +/-31 days apart (rejecting persistent 25-day/36-day schedules that fit a broad median band but are not monthly annual cadence) and require the latest payment to be no older than one nominal interval plus min(31 days, half an interval) at as_of; these are explicit supported-cadence bounds, not proof of provider completeness. Keep annual issuers supported and `years_back` positive integer. The latest annual numerator is the latest N regular payments, not a forward dividend or literal fixed-day TTM.
- Value screener's separate stability/scoring analysis must use the same special/future/amount eligibility policy; keep its existing completed-calendar-year convention. Do not leave special payouts in downstream stability gates after excluding them from CAGR/yield.
- Dividend-growth-pullback-screener keeps its completed-calendar-year convention: exclude all years >= as_of.year, not just the current year. Add optional Python `as_of` for deterministic tests; default remains today's date. Require four consecutive available completed years for 3-year CAGR, and break growth streaks across missing years. Keep the latest available completed year as the annual payout basis; do not claim this proves freshness or full provider history.
- Document the two existing annual-basis conventions accurately in instructions/reports: latest regular payment-year for value; latest completed calendar year for growth. Include additive basis metadata in JSON and a visible report explanation. Do not introduce new CLI options, shared transport changes, split/FX reconstruction or corporate-action inference. Raw provider dividend adjustment and unlabelled special-payment detection remain outside this Issue.

## TDD and validation

1. Baseline both suites separately (they have isolated imports). Add failing fixed-as_of regressions for all three Issue reproductions before implementation.
2. Test explicit special labels/frequencies, ordinary raises, a real cut, leap-year/day-drift boundaries, monthly/quarterly/semiannual/annual cadence, twice-monthly/unsupported cadence and inference-band boundaries with/without explicit metadata, future regular/special rows, malformed/non-finite values, insufficient buckets, missing years/payments, unchanged input payloads and valid current-year payments in value.
3. Exercise real screening functions with fake provider histories, including a flat payer plus a large special that must not pass growth/yield, a current regular grower, and a December report with a next-year declaration. Verify selected metrics and gating, not only helpers. Check JSON/Markdown basis metadata and package/source consistency offline.
4. Update skill and EN/JA docs, changelog and both packages. Keep applicable verification evidence honest: rerun recorded evidence or reset stale axes; no pass upgrade from aggregate green checks.
5. Independent code review and corrections (max three rounds). Run standard lint/format/spelling, metadata/docs/package checks, pre-commit and all pre-push groups with hooks. Commit/push and create a PR linked to #849 after clean review; distinguish hosted CI from local tests and do not merge.

## Independent review protocol

Plan and code each receive at most three independent rounds. Resolve actionable findings and obtain clean approval; if material findings remain after round three, report them without claiming completion or creating a ready PR.

- Plan round 1: cadence ambiguity addressed: distinct +/-20% median inference bands precede broader gap validation; unsupported/Irregular metadata is non-actionable. Twice-monthly and boundary regressions added to the plan.
- Plan round 2: approved; no remaining actionable findings. Final before implementation.
- Plan round 3: approved narrow strengthening: annual matched-payment spacing must agree with the inferred cadence; broad median inference alone must not annualize a persistent 25/36-day schedule.
- Code round 1: approved; no actionable material findings. Independent reviewer reran 41 value + 19 growth regressions and verified both ZIPs against packaged sources.

## Validation record

- Baselines: value 234 passed; growth 210 passed.
- Before implementation: value Issue tests 28 failed / 6 passed; growth Issue tests 17 failed. Annual-spacing strengthening: 4 failed before the guard.
- Current suites: value 275 passed; growth 229 passed (60 added regression cases combined). Real screening and JSON/Markdown basis cases included.
- Both skills already declare every applicable verification axis not_verified; no axis upgrades or unsupported certifications are introduced.
