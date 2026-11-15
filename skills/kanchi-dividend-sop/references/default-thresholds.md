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

Without complete, consistent evidence, an observed material USD decrease sets
`dividend_cut_currency_basis_unconfirmed`: Step 1 returns HOLD-REVIEW, the order
blocker is exported, and CLEAN-PASS is unavailable. It does not assert
`cut_flag=True` or hard-fail merely because of that converted-rate decline.
Existing synthetic cut fixtures explicitly include issuer-currency evidence;
their FAIL assertions remain active rather than being weakened.

`dividend_basis.cut_confirmation_required` explicitly marks the review gate.
`dividend_basis.cut_amount_basis` is `original_currency` or `unconfirmed`, and
`original_dividend_currency` records the evidence unit; CSV exposes both fields.
Schema 4 reserves the updated provenance/decision contract while the independent
#769 / PR #775 schema-3 target-basis change is pending. When integrating both,
retain schema 4 and regenerate the shared distributable from combined source.
The standard provider path does not yet acquire these original-currency fields;
it therefore routes ambiguous declines to manual review. This does not fetch or
guess native amounts and does not implement #770's increase/TTM changes.
