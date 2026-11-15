# Default Thresholds

Use these defaults when users do not provide custom risk settings.

## Baseline (US Stock-Focused)

| Category | Metric | Default | Interpretation |
|---|---|---:|---|
| Yield | Forward dividend yield | >= 3.5% | Kanchi Step 1 core filter |
| Yield trap | Extreme yield flag | >= 8.0% | Force deep dive before pass |
| Growth | Revenue CAGR (5y) | > 0% | Basic business expansion check |
| Growth | EPS CAGR (5y) | > 0% | Earnings trend health |
| Dividend trend | Dividend growth (5y) | Non-declining | Allow flat only with strong safety |
| Safety | EPS payout ratio | <= 70% | `70-85%` = caution |
| Safety | FCF payout ratio | <= 80% | `>100%` = high risk |
| Balance sheet | Net debt trend | Not persistently rising | Rising 3 periods = warning |
| Balance sheet | Interest coverage | >= 3.0x | `<2.5x` = caution |
| Entry trigger | Yield alpha vs 5y average | +0.5pp | Default Kanchi Step 5 pullback threshold |

## Instrument-Specific Notes

Use these denominator replacements for coverage checks:

| Instrument type | Primary denominator | Notes |
|---|---|---|
| Stock | FCF | Use `CFO - CapEx` |
| REIT | FFO/AFFO | Prefer AFFO if available |
| BDC | NII | Compare NII with distribution |
| ETF | Fund-level distribution coverage unavailable in many cases | Focus on methodology and holdings quality |

## Objective Tuning

Apply profile-specific adjustments:

| Profile | Yield floor | Safety bias | Notes |
|---|---:|---|---|
| Income now | 4.0% | Tight safety checks | Avoid overconcentration in one high-yield sector |
| Balanced | 3.0-3.5% | Medium | Blend current income and dividend growth |
| Growth first | 1.5-2.5% | High quality first | Accept lower initial yield for higher dividend CAGR |

## Step 5 Alpha Tuning

Use this range for yield-trigger alpha:
- Stable mega-cap compounders: `+0.3pp`.
- Default baseline: `+0.5pp`.
- Higher-volatility names: `+0.8pp` to `+1.0pp`.

## Entry Signal Interpretation

When using `build_entry_signals.py`, interpret signals as follows:

| Signal | Meaning | Action |
|---|---|---|
| TRIGGERED | Current price <= buy target price | Ready for first tranche (40%) if thesis intact |
| WAIT | Current price > buy target price | Monitor; set limit order at buy target |
| ASSUMPTION-REQUIRED | Missing data (yield history or dividend) | Manual research needed before entry |

### Drop Needed Percentage

- `0%`: Price already at or below target.
- `1-10%`: Near entry zone; consider scaling in if pullback accelerates.
- `>10%`: Significant gap; wait for pullback or reassess target.

## Portfolio Constraints

Use these as practical defaults:
- Max positions: `15-30`.
- Max single position at cost: `<= 8%`.
- Max sector exposure: `<= 25%`.
- High-yield bucket (REIT/telecom/utilities combined): `<= 35%`.

Override only when user explicitly chooses a different policy.

## Step 5 dividend-basis compatibility (schema version 3, Issue #769)

When declared-dividend history supplies a regular-only current numerator, the
provider's historical ratios are not a verified regular-only five-year average.
The current transport has no matching regular-only annual yield/price history,
so Step 5 withholds its average, target yield, buy price and drop-needed fields:
`signal=ASSUMPTION-REQUIRED`, `target_withheld_reason=regular_only_average_unavailable`,
and T1 orders are blocked. No guessed price or reverse-engineered substitute is
emitted. This applies even when the available history shows no special payment;
that absence does not establish the provider's five-year basis. A nonempty but
unusable history produces `regular_dividend_unavailable` rather than silently
falling back to a profile-based target.

JSON/CSV record `annual_dividend_basis`, `historical_yield_basis`, `yield_basis`
and `target_withheld_reason`. `provider_avg_5y_yield_pct` and
`provider_yield_observation_count` retain raw provider diagnostics; they are not
an actionable regular-only target basis. `yield_observation_count` counts usable
observations (zero for a withheld target). Markdown lists the withholding reason.
The legacy no-history library path retains its provider-total calculation with
both sides explicitly marked `provider_total_unverified`; it does not claim a
regular-only target. Live history-enabled CLI rows use the guarded path.

A future regular-only historical series must use the same special classification
as dividend_basis and demonstrably matching yearly dividend/price periods before
it can enable target calculation. This fix does not add that data acquisition or
assert the evaluator's ORI figures are live market data. Freeze/strong-safety
conditional eligibility alone does not establish an entry level: unresolved
basis evidence keeps such a row HOLD-REVIEW with T1 blocked.
