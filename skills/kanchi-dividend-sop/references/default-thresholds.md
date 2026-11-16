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
## Issue #768 safety guards

- `BANK_CET1_MIN`: 0.07 (fraction units); below the screening floor is CAUTION, invalid/missing values also block CLEAN-PASS. This is not an issuer-specific regulatory requirement; see sector-step2-modules.md.
- A material decrease of more than `DIVIDEND_CUT_REL_TOL` (0.05 = 5%) below the trailing `DIVIDEND_CUT_LOOKBACK_DAYS` (365) regular-rate peak sets `cut_flag`, even if the year-over-year rate grew. Specials are removed first. For semiannual payers, compare rolling two-payment annual totals to avoid interim/final seasonality. The year-over-year rate comparison uses the same cut tolerance.
- Non-positive supplied EPS/consumer FCF yields HOLD-REVIEW, never a negative payout interpreted as safe. The utility FCF exemption is preserved.

### PR #774 review follow-up: cut persistence and scope

The trailing-year material-cut test stays active through subsequent unchanged
payments until the high reference leaves the window or the rate recovers within
tolerance. A 0.40 -> 0.35 -> 0.35 stream remains a cut. A 0.55 -> 0.53 currency-like
variation does not hard-fail as a cut, and a recurring 0.40/0.60 semiannual pattern
does not compare the lower interim payment directly with the larger final.
The 5% threshold is a configurable screening policy, not proof of an issuer's
board-declared cut or its original-currency cause; a larger FX change can still
require source review. This input has no original-currency declaration evidence.

`DIVIDEND_EQUALITY_EPS` still governs increase/freeze comparisons. Issue #770
separately owns the finer monthly-raise tolerance, TTM evaluation-date window and
price-date provenance; those changes are not folded into #768.

A supplied non-positive GAAP EPS deliberately HOLDs even when adjusted EPS is
positive: this conservative gate runs before one-off/divergence classification.
It can therefore require manual review of an impairment-only loss instead of
using the otherwise-positive adjusted anchor. This differs from the previous
one-off interpretation and is not a claim that adjusted earnings are negative.
CET1 values use fraction units (0.125 = 12.5%); 12.5 itself is invalid/CAUTION,
not silently rescaled. Issue #772's future input path must normalize source units.

## Original-currency evidence gate (schema 4 follow-up)

A material decrease in USD-converted payments is an observation, not proof of a
board-declared cut. Every compared regular record must carry explicit
`original_dividend` (finite positive number), `original_currency` (consistent
three-letter code), and `original_dividend_source` (nonempty issuer/source
reference). Generic quote/profile currency is never substituted for this evidence.
The producer/caller is responsible for verifying that the cited source actually
contains those issuer-currency amounts; the presence of a string is not an
independent source-verification service.

With complete evidence, material-cut and variable-policy calculations use the
original-currency series (including semiannual annual-total comparison), while
USD current yield still uses the original USD cash field and quote. A native
cut hidden by FX remains a cut; an unchanged native rate with falling USD cash
does not become a cut or a variable-payment policy. Other independent yield,
suspension, or policy failures still apply.

Ordinary USD histories without original-currency metadata keep the USD cut
classification (`cut_amount_basis=usd_history`): a material cut sets `cut_flag`
and FAIL. A validated non-USD profile currency, boolean `isAdr=true`, or partial
original-currency metadata requires confirmation when a cut is observed without
complete evidence. Profile currency is only a review hint, never native proof.
The observed `cut_flag=True` is retained for the downstream T6 review monitor.
`cut_confirmation_required=True` yields Step 1 `CURRENCY-REVIEW`, mapped directly
to final HOLD-REVIEW with `t1_blocked=True`, even without CLI-added blockers.
Legacy callers carrying the currency blocker receive the same final cap. This
review is distinct from a freeze's income-cash-cow CONDITIONAL-PASS path.

With complete original evidence, freeze and last-increase date also use the
native series. An FX-only USD decline can clear the cut flag but cannot hide a
native freeze. USD yield/entry valuation remains unchanged.

CSV/JSON expose `cut_confirmation_required`, `cut_amount_basis` and
`original_dividend_currency`. Schema 4 includes the integrated schema-3 entry
basis change. The provider does not acquire original amounts: identified foreign
or ADR declines require manual confirmation. No native values are guessed.
Issue #770's monthly-raise tolerance and TTM changes remain separate.

Withheld entry targets are non-actionable: a Step-1-passing row is capped at
HOLD-REVIEW with the withholding reason, regardless of event-scan result.
Hard FAIL and Step-1 data rechecks keep their stricter dispositions. The
trader-memory-core adapter therefore rejects these rows instead of registering
an entry with a null target. A clean payout-safety freeze reports the missing
entry basis rather than claiming safety was unconfirmed. Provider observations
remain diagnostic and are not reported missing merely because the usable
regular-only average is withheld.
