# Qualified Dividend Checklist (US)

Use this checklist for planning assumptions.

## Classification Pass

For each holding, verify:
1. Distribution is potentially eligible for qualified treatment by instrument/type.
2. Shares meet required holding-period test around the ex-dividend date window.
3. No known disqualifying condition in the current fact pattern.

If any item is uncertain, mark as `ASSUMPTION-REQUIRED`.

## Holding-Period Rules (US Federal, Common Planning Baseline)

- Common stock baseline: hold shares for **more than 60 days** during the **121-day period** that starts **60 days before** the ex-dividend date.
- Preferred stock (certain long-period dividends): often uses **more than 90 days** during a **181-day period** starting **90 days before** ex-dividend date.

Use current IRS guidance as source of truth:
- [IRS Publication 550, Qualified Dividends](https://www.irs.gov/publications/p550).
- IRS Form 1099-DIV instructions.

## Script Planning Limitations

`build_tax_planning_sheet.py` compares an operator-supplied day count against
61 days for common stock or 91 days for `security_type: preferred`. It does
not derive the applicable window from acquisition, disposal, or ex-dividend
dates, and it does not subtract days when the risk of loss was reduced.
Prepare the qualifying day count before supplying it to the script.

Publication 550 limits the preferred-stock 91-day test to dividends covering
periods longer than 366 days; shorter-period preferred dividends follow the
common-stock test. The script has no dividend-period field and applies the
91-day preferred threshold as a planning shortcut. Its result can therefore
be more restrictive for shorter-period preferred dividends. Verify those
cases manually against the applicable IRS window rather than treating the
script label as a final tax determination. The same manual review applies
to issuer eligibility and other conditions beyond the supplied day count.

REIT and BDC rows retain an `ordinary_likely` planning label regardless of
the day count. Actual distributions may contain multiple tax components;
use broker/issuer breakdowns to determine the final treatment.

## Practical Data Fields

Track these fields for each position:
- Ticker
- Account type
- Ex-dividend date
- Purchase date(s)
- Disposal date(s), if any
- Days held in required window
- Preliminary classification (`qualified-likely`, `ordinary-likely`, `unknown`)

## Common Pitfalls

- Assuming all common-stock dividends will be qualified without holding-period verification.
- Ignoring short holding periods caused by frequent tactical trading.
- Treating REIT/BDC distributions as identical to standard qualified-dividend flows.
- **Modeling special / variable dividends as steady qualified income**
  (WS-8 hand-off from `kanchi-dividend-sop`). When the upstream
  `dividend_basis` carries `special_dividend_flag` or
  `variable_policy_flag` (e.g. ORI annual specials, CALM variable policy),
  treat that cash as **lumpy and non-recurring** for account-location and
  cash-flow planning: budget the *regular* run-rate as base income and the
  special/variable component separately (timing unpredictable; may still
  be qualified but must not be annualized as if recurring).

## Recommended Source Hierarchy

1. Broker tax documents and distribution breakdowns.
2. Official IRS publications/instructions for current-year rules (Publication 550, 1099-DIV instructions).
3. Issuer or fund notices when classification is revised.
