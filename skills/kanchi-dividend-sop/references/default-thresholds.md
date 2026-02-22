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

## Portfolio Constraints

Use these as practical defaults:
- Max positions: `15-30`.
- Max single position at cost: `<= 8%`.
- Max sector exposure: `<= 25%`.
- High-yield bucket (REIT/telecom/utilities combined): `<= 35%`.

Override only when user explicitly chooses a different policy.
